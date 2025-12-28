"""
ReAct Act Node
行动节点：执行 LLM 决定的工具调用
"""
from typing import Dict, Any, Optional
from loguru import logger
from ..state import GraphState
import json
import re


# 全局 ToolGateway 实例
_tool_gateway = None


async def get_tool_gateway():
    """获取或创建 ToolGateway 实例"""
    global _tool_gateway
    if _tool_gateway is None:
        from tool_gateway import ToolGateway
        _tool_gateway = ToolGateway()
        logger.info("ToolGateway 初始化完成（ReAct Act）")
    return _tool_gateway


def _extract_json_object(text: str) -> Optional[str]:
    """
    从文本中提取完整的 JSON 对象（支持嵌套大括号）
    
    Args:
        text: 以 { 开头的文本
        
    Returns:
        完整的 JSON 字符串，如果无法提取则返回 None
    """
    text = text.strip()
    if not text.startswith('{'):
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    
    for i, char in enumerate(text):
        if escape_next:
            escape_next = False
            continue
            
        if char == '\\' and in_string:
            escape_next = True
            continue
            
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
            
        if in_string:
            continue
            
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[:i+1]
    
    return None


def _repair_diagram_params(tool_name: str, params: Dict[str, Any], state: GraphState) -> Dict[str, Any]:
    """
    修复 diagram 工具的参数
    
    当 params 中缺少 nodes 或 edges 字段时，尝试从 LLM 原始输出中重新提取
    
    Args:
        tool_name: 工具名称
        params: 当前解析的参数
        state: 当前状态（包含 next_action.thought 等原始信息）
        
    Returns:
        修复后的参数
    """
    # 只处理 diagram 工具
    if not tool_name.startswith("diagram."):
        return params
    
    # 检查是否缺少必要字段
    if isinstance(params, dict) and "nodes" in params and "edges" in params:
        return params  # 参数完整，无需修复
    
    logger.warning(f"diagram 工具参数不完整，尝试修复: {list(params.keys()) if isinstance(params, dict) else type(params)}")
    
    # 尝试从 state 中获取原始 LLM 输出
    # 可能的来源：next_action.thought, metadata.raw_llm_output 等
    raw_sources = []
    
    next_action = state.get("next_action", {})
    if next_action.get("thought"):
        raw_sources.append(next_action["thought"])
    
    # 从 execution_history 中获取最近的 LLM 输出
    execution_history = state.get("execution_history", [])
    if execution_history:
        last_record = execution_history[-1] if execution_history else {}
        if last_record.get("thought"):
            raw_sources.append(last_record["thought"])
    
    # 尝试从各个来源中提取完整的 JSON 参数
    for source in raw_sources:
        if not source:
            continue
            
        # 尝试多种模式提取 JSON
        patterns = [
            # 模式 1: PARAMS: {...}
            r'PARAMS:\s*(\{)',
            # 模式 2: ```json {...} ```
            r'```json\s*(\{)',
            # 模式 3: ``` {...} ```
            r'```\s*(\{)',
            # 模式 4: "nodes": [...] 开头的 JSON
            r'(\{"(?:nodes|containers|edges)")',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE | re.DOTALL)
            if match:
                # 找到起始位置
                start_pos = match.start(1)
                json_text = _extract_json_object(source[start_pos:])
                
                if json_text:
                    try:
                        extracted_params = json.loads(json_text)
                        # 验证提取的参数是否包含必要字段
                        if isinstance(extracted_params, dict) and "nodes" in extracted_params:
                            logger.info(f"成功从原始输出中修复 diagram 参数，包含字段: {list(extracted_params.keys())}")
                            return extracted_params
                    except json.JSONDecodeError as e:
                        logger.debug(f"JSON 解析失败: {e}")
                        continue
    
    # 如果仍然无法修复，尝试构建最小有效参数
    if not isinstance(params, dict):
        params = {}
    
    if "nodes" not in params:
        params["nodes"] = []
        logger.warning("无法修复 nodes 字段，使用空列表")
    
    if "edges" not in params:
        params["edges"] = []
        logger.warning("无法修复 edges 字段，使用空列表")
    
    return params


async def react_act_node(state: GraphState) -> GraphState:
    """ReAct 行动节点

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    state["current_node"] = "react_act"

    try:
        # 获取下一步行动
        next_action = state.get("next_action")
        if not next_action:
            error_msg = "没有找到 next_action"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["last_observation"] = f"错误: {error_msg}"
            return state

        action_type = next_action.get("action_type")

        # 如果是 FINISH，不执行任何操作
        if action_type == "FINISH":
            logger.info("行动类型是 FINISH，跳过执行")
            state["last_observation"] = "任务已完成"
            return state

        # 如果是 TOOL，执行工具调用
        if action_type == "TOOL":
            tool_name = next_action.get("tool_name")
            params = next_action.get("params", {})

            if not tool_name:
                error_msg = "工具名称为空"
                logger.error(error_msg)
                state["errors"].append(error_msg)
                state["last_observation"] = f"错误: {error_msg}"
                return state

            # 对 mysql 工具自动补全 database 参数（仅在显式缺失且用户问题中有明确库名时）
            if tool_name.startswith("mysql."):
                try:
                    db_in_params = params.get("database") if isinstance(params, dict) else None
                    need_fill = (db_in_params is None) or (
                        isinstance(db_in_params, str) and not db_in_params.strip()
                    )
                    if need_fill:
                        user_query = state.get("user_query", "")
                        db_name = None
                        if isinstance(user_query, str):
                            matches = re.findall(r"\b([A-Za-z0-9_]+_db)\b", user_query)
                            if matches:
                                unique_matches = []
                                for m in matches:
                                    if m not in unique_matches:
                                        unique_matches.append(m)
                                if len(unique_matches) == 1:
                                    db_name = unique_matches[0]
                        if db_name:
                            if not isinstance(params, dict):
                                params = {}
                            params["database"] = db_name
                            logger.info(
                                f"自动补全 mysql 工具的 database 参数: {db_name}"
                            )
                except Exception as e:
                    logger.warning(
                        f"自动补全 mysql database 参数时出现异常: {str(e)}"
                    )

            # 对 network 工具进行参数修正（LLM 可能输出错误的参数名）
            if tool_name.startswith("network."):
                try:
                    logger.debug(f"检查 network 工具参数修正: tool={tool_name}, params={params}")
                    if not isinstance(params, dict):
                        params = {}
                    
                    # 参数名映射：LLM 可能输出的错误名称 -> 正确名称
                    param_corrections = {
                        # ping/traceroute/nslookup/mtr 使用 target
                        "host": "target",      # LLM 可能错误使用 host
                        "hostname": "target",  # LLM 可能错误使用 hostname
                        "ip": "target",        # LLM 可能错误使用 ip
                        "address": "target",   # LLM 可能错误使用 address
                        "domain": "target",    # LLM 可能错误使用 domain
                    }
                    
                    # 需要 target 参数的工具
                    target_tools = ["network.ping", "network.traceroute", "network.nslookup", "network.mtr"]
                    
                    if tool_name in target_tools:
                        # 如果没有 target 参数，尝试从其他参数名中获取
                        if "target" not in params:
                            for wrong_name, correct_name in param_corrections.items():
                                if wrong_name in params:
                                    params[correct_name] = params.pop(wrong_name)
                                    logger.info(f"参数修正: {wrong_name} -> {correct_name} = {params[correct_name]}")
                                    break
                            else:
                                logger.debug(f"未找到需要修正的参数，当前参数: {list(params.keys())}")
                        else:
                            logger.debug(f"参数已包含 target，无需修正")
                except Exception as e:
                    logger.warning(f"修正 network 工具参数时出现异常: {str(e)}")

            # 对 diagram 工具进行参数修复（当 nodes/edges 缺失时尝试从原始输出中提取）
            if tool_name.startswith("diagram."):
                try:
                    params = _repair_diagram_params(tool_name, params, state)
                except Exception as e:
                    logger.warning(f"修复 diagram 参数时出现异常: {str(e)}")

            # 获取调用者 Agent 和会话信息
            caller_agent = state.get("target_agent", "unknown_agent")
            session_id = state.get("metadata", {}).get("session_id")

            logger.info(f"执行工具: {tool_name}, 参数: {params}, 调用者: {caller_agent}")

            # 获取 ToolGateway
            tool_gateway = await get_tool_gateway()

            # 通过 ToolGateway 调用工具
            try:
                # 使用物理工具名调用（向后兼容，ToolGateway 会自动处理映射）
                call_result = await tool_gateway.call_tool_by_physical_name(
                    physical_name=tool_name,
                    params=params,
                    caller_agent=caller_agent,
                    session_id=session_id,
                )

                # 检查调用状态
                from tool_gateway.models import ToolCallStatus
                if call_result.status == ToolCallStatus.SUCCESS:
                    # 解析结果
                    result = call_result.result
                    if isinstance(result, str):
                        try:
                            result_dict = json.loads(result)
                            result_str = json.dumps(
                                result_dict, ensure_ascii=False, indent=2
                            )
                        except json.JSONDecodeError:
                            result_str = result
                    else:
                        result_str = json.dumps(result, ensure_ascii=False, indent=2)

                    # 检测工具返回结果中是否包含错误信息
                    # 这些错误来自工具内部（如数据库连接失败），虽然工具调用成功，但实际执行失败
                    error_indicators = [
                        "Error executing tool",
                        "Connection not available",
                        "connection refused",
                        "Access denied",
                        "Unknown database",
                        "Table doesn't exist",
                        "Syntax error",
                    ]
                    result_lower = result_str.lower()
                    has_error = any(indicator.lower() in result_lower for indicator in error_indicators)

                    if has_error:
                        # 工具调用成功但返回错误结果
                        logger.warning(f"工具 {tool_name} 返回错误结果: {result_str[:200]}")
                        state["last_observation"] = (
                            f"工具 {tool_name} 执行失败。错误信息:\n{result_str}"
                        )
                    else:
                        logger.info(f"工具执行成功: {tool_name}")
                        logger.debug(f"工具结果:\n{result_str[:500]}...")
                        # 保存观察结果
                        state["last_observation"] = (
                            f"工具 {tool_name} 执行成功。结果:\n{result_str}"
                        )
                elif call_result.status == ToolCallStatus.PERMISSION_DENIED:
                    error_msg = f"权限不足: {call_result.error}"
                    logger.error(error_msg)
                    state["errors"].append(error_msg)
                    state["last_observation"] = f"错误: {error_msg}"
                else:
                    error_msg = f"工具调用失败: {tool_name}, 错误: {call_result.error}"
                    logger.error(error_msg)
                    state["errors"].append(error_msg)
                    state["last_observation"] = f"错误: {error_msg}"

            except Exception as e:
                error_msg = f"工具调用失败: {tool_name}, 错误: {str(e)}"
                logger.error(error_msg, exc_info=True)
                state["errors"].append(error_msg)
                state["last_observation"] = f"错误: {error_msg}"

        else:
            error_msg = f"未知的行动类型: {action_type}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["last_observation"] = f"错误: {error_msg}"

    except Exception as e:
        error_msg = f"ReAct Act 失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        state["errors"].append(error_msg)
        state["last_observation"] = f"错误: {error_msg}"

    return state

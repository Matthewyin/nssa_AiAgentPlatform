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

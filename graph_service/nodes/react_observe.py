"""
ReAct Observe Node
观察节点：记录执行历史，更新状态，提前终止判断
"""
from typing import Dict, Any, Optional
from loguru import logger
from ..state import GraphState
from datetime import datetime
import json


def _is_network_tool(tool_name: str) -> bool:
    """
    判断是否为网络探测工具
    
    Args:
        tool_name: 工具名称
        
    Returns:
        是否为网络探测工具
    """
    network_tools = [
        "network.nslookup", "network.dns", "nslookup", "dns",
        "network.tls", "tls",
        "network.http", "http",
        "network.mtr", "mtr",
        "network.diagnose", "diagnose",
        "network.ping", "ping",
        "network.tcp", "tcp",
        "network.traceroute", "traceroute"
    ]
    return tool_name.lower() in [t.lower() for t in network_tools]


def _extract_json_from_observation(observation: str) -> Optional[Dict[str, Any]]:
    """
    从观察结果中提取 JSON 数据
    
    Args:
        observation: 观察结果字符串
        
    Returns:
        解析后的 JSON 字典，如果解析失败则返回 None
    """
    if not observation:
        return None
    
    # 尝试从 "结果:" 后面提取 JSON
    result_markers = ["结果:", "结果：", "Result:", "result:"]
    json_str = observation
    
    for marker in result_markers:
        if marker in observation:
            json_str = observation.split(marker, 1)[1].strip()
            break
    
    # 尝试解析 JSON
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试找到 JSON 对象的开始和结束
        start_idx = json_str.find('{')
        if start_idx == -1:
            return None
        
        # 找到匹配的结束括号
        depth = 0
        end_idx = -1
        in_string = False
        escape_next = False
        
        for i, char in enumerate(json_str[start_idx:], start_idx):
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
                    end_idx = i + 1
                    break
        
        if end_idx > start_idx:
            try:
                return json.loads(json_str[start_idx:end_idx])
            except json.JSONDecodeError:
                return None
    
    return None


def _convert_to_markdown(tool_name: str, result: Dict[str, Any]) -> Optional[str]:
    """
    将工具结果转换为 Markdown 格式
    
    Args:
        tool_name: 工具名称
        result: 结构化的探测结果
        
    Returns:
        Markdown 格式的字符串，如果转换失败则返回 None
    """
    try:
        from ..report_builder import MarkdownConverter
        converter = MarkdownConverter()
        return converter.convert(tool_name, result)
    except Exception as e:
        logger.warning(f"Markdown 转换失败: {e}")
        return None


def _load_early_termination_config() -> Dict[str, Any]:
    """加载提前终止配置"""
    try:
        from utils import load_optimization_config
        config = load_optimization_config()
        return config.get("optimization", {}).get("early_termination", {})
    except Exception as e:
        logger.warning(f"加载提前终止配置失败: {e}")
        return {"enabled": False}


def _evaluate_task_completion(state: GraphState, observation: str) -> tuple[bool, float, str]:
    """
    评估任务是否已完成（提前终止判断）
    
    Args:
        state: 当前状态
        observation: 最新的观察结果
        
    Returns:
        (是否应该终止, 置信度, 原因)
    """
    config = _load_early_termination_config()
    
    if not config.get("enabled", False):
        logger.debug("提前终止: 功能未启用")
        return False, 0.0, "提前终止未启用"
    
    # 关键检查：如果 tool_queue 中还有待执行的工具，不能提前终止
    tool_queue = state.get("tool_queue", [])
    if tool_queue and len(tool_queue) > 0:
        logger.info(f"提前终止: 跳过，队列中还有 {len(tool_queue)} 个工具待执行")
        return False, 0.0, f"队列中还有 {len(tool_queue)} 个工具待执行"
    
    # 检查是否为多 Agent 场景
    agent_plan = state.get("agent_plan", [])
    is_multi_agent = len(agent_plan) > 1
    current_agent_index = state.get("current_agent_index", 0)
    
    logger.info(f"提前终止检查: is_multi_agent={is_multi_agent}, current_agent_index={current_agent_index}, total_agents={len(agent_plan)}, enable_for_multi_agent={config.get('enable_for_multi_agent', False)}")
    
    # 多 Agent 场景下，禁用提前终止（保守策略）
    # 因为多 Agent 场景下，每个 Agent 的任务可能是复杂的，提前终止可能导致任务未完成
    if is_multi_agent:
        logger.info("提前终止: 多Agent场景下禁用提前终止（保守策略）")
        return False, 0.0, "多Agent场景下禁用提前终止"
    
    confidence_threshold = config.get("confidence_threshold", 0.75)
    
    # 检查 0: 自动终止工具列表（最高优先级）
    next_action = state.get("next_action", {})
    tool_name = next_action.get("tool_name", "")
    auto_terminate_tools = config.get("auto_terminate_tools", [])
    
    if tool_name in auto_terminate_tools:
        # 检查是否执行成功（无错误）
        error_indicators = [
            "错误", "失败", "error", "failed", "exception",
            "无法", "不存在", "denied", "refused", "timeout"
        ]
        observation_lower = observation.lower()
        has_error = any(indicator in observation_lower for indicator in error_indicators)
        
        if not has_error:
            logger.info(f"自动终止: 工具 {tool_name} 在自动终止列表中且执行成功")
            return True, 1.0, f"工具 {tool_name} 在自动终止列表中"
    
    # 初始置信度
    confidence = 0.0
    reasons = []
    
    # 检查 1: 工具执行是否成功
    error_indicators = [
        "错误", "失败", "error", "failed", "exception",
        "无法", "不存在", "denied", "refused", "timeout"
    ]
    observation_lower = observation.lower()
    has_error = any(indicator in observation_lower for indicator in error_indicators)
    
    if has_error:
        # 有错误，不应提前终止，让 LLM 决定下一步
        return False, 0.0, "观察结果包含错误信息"
    
    # 检查 2: 是否有明确的结果数据
    success_indicators = [
        "执行成功", "成功", "结果:", "返回:",
        "success", "result:", "completed"
    ]
    has_success = any(indicator in observation_lower for indicator in success_indicators)
    
    if has_success:
        confidence += 0.3
        reasons.append("工具执行成功")
    
    # 检查 3: 结果是否包含实际数据（非空）
    # 排除只有状态信息没有实际数据的情况
    if len(observation) > 50:
        confidence += 0.2
        reasons.append("结果包含实际数据")
    
    # 检查 4: 单 Agent + 单工具场景
    current_step = state.get("current_step", 1)
    
    is_single_agent = len(agent_plan) <= 1
    is_early_step = current_step <= 2
    
    if is_single_agent and is_early_step:
        confidence += 0.3
        reasons.append("单Agent单工具场景")
    
    # 检查 5: 用户问题是否为简单查询类型
    user_query = state.get("user_query", "").lower()
    simple_query_patterns = [
        "ping ", "nslookup ", "查询", "列出", "显示", "获取",
        "list", "show", "get", "describe", "count"
    ]
    is_simple_query = any(pattern in user_query for pattern in simple_query_patterns)
    
    if is_simple_query:
        confidence += 0.2
        reasons.append("简单查询类型")
    
    # 检查 6: 是否需要进一步操作的指示词
    need_more_indicators = [
        "需要进一步", "请继续", "下一步", "然后",
        "need more", "continue", "next step", "further"
    ]
    needs_more = any(indicator in observation_lower for indicator in need_more_indicators)
    
    if needs_more:
        confidence -= 0.3
        reasons.append("结果提示需要进一步操作")
    
    # 最终判断
    should_terminate = confidence >= confidence_threshold
    reason = f"置信度={confidence:.2f}, 因素: {', '.join(reasons)}"
    
    if should_terminate:
        logger.info(f"提前终止判断: 是, {reason}")
    else:
        logger.debug(f"提前终止判断: 否, {reason}")
    
    return should_terminate, confidence, reason


async def react_observe_node(state: GraphState) -> GraphState:
    """
    ReAct 观察节点
    
    Args:
        state: 当前状态
        
    Returns:
        更新后的状态
    """
    state["current_node"] = "react_observe"
    
    try:
        # 获取当前步骤的信息
        next_action = state.get("next_action", {})
        last_observation = state.get("last_observation", "")
        
        # ========== Markdown 转换（网络探测工具） ==========
        tool_name = next_action.get("tool_name", "")
        markdown_output = None
        structured_result = None
        
        if next_action.get("action_type") == "TOOL" and _is_network_tool(tool_name):
            # 尝试从观察结果中提取 JSON
            structured_result = _extract_json_from_observation(last_observation)
            
            if structured_result:
                # 转换为 Markdown
                markdown_output = _convert_to_markdown(tool_name, structured_result)
                if markdown_output:
                    logger.info(f"成功将 {tool_name} 结果转换为 Markdown")
                else:
                    logger.debug(f"Markdown 转换返回空结果: {tool_name}")
        
        # 构建执行记录
        record = {
            "step": state["current_step"],
            "thought": next_action.get("thought", ""),
            "action": {
                "type": next_action.get("action_type", ""),
                "tool": next_action.get("tool_name"),
                "params": next_action.get("params", {})
            },
            "observation": last_observation,
            "timestamp": datetime.now().isoformat()
        }
        
        # 添加 Markdown 输出和结构化数据到记录中
        if markdown_output:
            record["markdown_output"] = markdown_output
        if structured_result:
            record["structured_result"] = structured_result
        
        # 添加到执行历史
        if "execution_history" not in state or state["execution_history"] is None:
            state["execution_history"] = []
        
        state["execution_history"].append(record)
        
        logger.info(f"记录步骤 {state['current_step']}: action={next_action.get('action_type')}, tool={next_action.get('tool_name')}, has_markdown={markdown_output is not None}")
        
        # ========== 提前终止判断（第三阶段优化） ==========
        # 如果工具执行成功且满足提前终止条件，直接标记完成，跳过下一次 Think
        action_type = next_action.get("action_type", "")
        
        if action_type == "TOOL" and not state.get("is_finished", False):
            should_terminate, confidence, reason = _evaluate_task_completion(state, last_observation)
            
            if should_terminate:
                state["is_finished"] = True
                # 记录提前终止信息到 metadata
                if "metadata" not in state:
                    state["metadata"] = {}
                state["metadata"]["early_termination"] = {
                    "enabled": True,
                    "confidence": confidence,
                    "reason": reason,
                    "step": state["current_step"]
                }
                logger.info(f"提前终止: 跳过后续 Think 循环, {reason}")
        
        # 增加步骤计数
        state["current_step"] += 1
        
    except Exception as e:
        error_msg = f"ReAct Observe 失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        state["errors"].append(error_msg)
    
    return state


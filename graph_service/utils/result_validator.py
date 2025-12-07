"""
结果质量验证模块
验证 LLM 输出的格式和内容正确性
"""
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger


def validate_router_response(response: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    验证 Router 的 LLM 响应
    
    Args:
        response: 解析后的响应字典
    
    Returns:
        (是否有效, 错误列表)
    """
    errors = []
    
    if not response:
        errors.append("响应为空")
        return False, errors
    
    agent_plan = response.get("agent_plan", [])
    
    if not agent_plan:
        errors.append("agent_plan 为空")
        return False, errors
    
    # 验证每个 agent
    for i, agent in enumerate(agent_plan):
        if not agent.get("name"):
            errors.append(f"agent[{i}] 缺少 name 字段")
        if not agent.get("task"):
            errors.append(f"agent[{i}] 缺少 task 字段")
    
    # 验证 first_action（如果有）
    first_action = response.get("first_action")
    if first_action:
        if not first_action.get("tool"):
            errors.append("first_action 缺少 tool 字段")
    
    return len(errors) == 0, errors


def validate_think_output(
    parsed: Dict[str, Any], 
    available_tools: List[str]
) -> Tuple[bool, List[str]]:
    """
    验证 ReAct Think 的输出
    
    Args:
        parsed: 解析后的输出字典
        available_tools: 可用工具列表
    
    Returns:
        (是否有效, 错误列表)
    """
    errors = []
    
    action_type = parsed.get("action_type", "UNKNOWN")
    
    if action_type == "UNKNOWN":
        errors.append("无法识别 action_type")
        return False, errors
    
    if action_type == "TOOL":
        tool_name = parsed.get("tool_name")
        
        if not tool_name:
            errors.append("action_type 为 TOOL 但缺少 tool_name")
            return False, errors
        
        # 幻觉检测：检查工具名称是否存在
        if available_tools and tool_name not in available_tools:
            # 尝试模糊匹配
            matched = False
            for available_tool in available_tools:
                if tool_name in available_tool or available_tool in tool_name:
                    matched = True
                    break
            
            if not matched:
                errors.append(f"工具 '{tool_name}' 不存在，可用工具: {available_tools}")
    
    return len(errors) == 0, errors


def validate_tool_params(
    tool_name: str, 
    params: Dict[str, Any],
    tool_schema: Optional[Dict[str, Any]] = None
) -> Tuple[bool, List[str]]:
    """
    验证工具参数
    
    Args:
        tool_name: 工具名称
        params: 参数字典
        tool_schema: 工具参数 schema（可选）
    
    Returns:
        (是否有效, 错误列表)
    """
    errors = []
    
    # 基本验证
    if params is None:
        params = {}
    
    if not isinstance(params, dict):
        errors.append(f"params 应该是字典，实际是 {type(params)}")
        return False, errors
    
    # 如果有 schema，进行详细验证
    if tool_schema:
        required_params = tool_schema.get("required", [])
        for param_name in required_params:
            if param_name not in params:
                errors.append(f"缺少必填参数: {param_name}")
    
    return len(errors) == 0, errors


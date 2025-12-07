"""
执行历史压缩模块
用于减少传递给 LLM 的历史信息量
"""
from typing import Dict, Any, List, Optional
from loguru import logger


def load_truncation_config() -> Dict[str, Any]:
    """加载截断配置"""
    try:
        from utils import load_optimization_config
        config = load_optimization_config()
        return config.get("optimization", {}).get("history_truncation", {})
    except Exception as e:
        logger.warning(f"加载历史截断配置失败: {e}")
        return {"enabled": True, "window_size": 3, "summary_max_length": 100}


def compress_execution_history(
    execution_history: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None
) -> str:
    """
    压缩执行历史，减少 token 消耗

    策略：
    1. 最近 N 步保留详细信息
    2. 历史步骤压缩为一句话摘要

    Args:
        execution_history: 执行历史列表
        config: 截断配置（可选）

    Returns:
        压缩后的历史描述字符串
    """
    if not execution_history:
        return ""

    # 加载配置
    if config is None:
        config = load_truncation_config()

    total_steps = len(execution_history)

    if not config.get("enabled", True):
        # 如果禁用压缩，返回原始格式
        full_history = _format_full_history(execution_history)
        logger.debug(f"历史压缩已禁用，返回完整历史: {total_steps} 步, {len(full_history)} 字符")
        return full_history

    window_size = config.get("window_size", 3)
    summary_max_length = config.get("summary_max_length", 100)

    if total_steps <= window_size:
        # 步骤数少于窗口大小，全部保留详细信息
        detailed_history = _format_detailed_history(execution_history, 0)
        logger.debug(f"历史压缩: 步骤数({total_steps}) ≤ 窗口({window_size})，保留全部详情: {len(detailed_history)} 字符")
        return detailed_history

    # 分割历史：压缩部分 + 详细部分
    compressed_steps = execution_history[:-window_size]
    detailed_steps = execution_history[-window_size:]

    history_desc = "\n\n执行历史:\n"

    # 压缩部分
    if compressed_steps:
        history_desc += f"\n[历史摘要] 步骤 1-{len(compressed_steps)}:\n"
        summaries = []
        for record in compressed_steps:
            summary = _generate_step_summary(record, summary_max_length)
            summaries.append(summary)
        history_desc += "  " + " → ".join(summaries) + "\n"

    # 详细部分
    start_step = len(compressed_steps) + 1
    history_desc += _format_detailed_history(detailed_steps, start_step - 1)

    # 计算压缩效果并记录日志
    original_history = _format_full_history(execution_history)
    original_len = len(original_history)
    compressed_len = len(history_desc)
    savings_percent = (1 - compressed_len / original_len) * 100 if original_len > 0 else 0

    logger.info(
        f"历史压缩: {total_steps} 步 | "
        f"压缩 {len(compressed_steps)} 步 + 详细 {len(detailed_steps)} 步 | "
        f"原始 {original_len} → 压缩后 {compressed_len} 字符 | "
        f"节省 {savings_percent:.1f}%"
    )

    return history_desc


def _format_full_history(execution_history: List[Dict[str, Any]]) -> str:
    """格式化完整历史（不压缩）"""
    return _format_detailed_history(execution_history, 0)


def _format_detailed_history(
    records: List[Dict[str, Any]], 
    start_index: int
) -> str:
    """格式化详细历史"""
    from ..utils import smart_truncate, get_tool_type, extract_result_summary
    
    history_desc = ""
    for i, record in enumerate(records, start_index + 1):
        history_desc += f"\n步骤 {i}:\n"
        history_desc += f"  思考: {record.get('thought', 'N/A')}\n"
        history_desc += f"  行动: {record.get('action', 'N/A')}\n"
        
        # 获取观察结果，使用智能截断
        observation = record.get('observation', 'N/A')
        action = record.get('action', {})
        tool_name = action.get('tool', '') if isinstance(action, dict) else ''
        
        # 尝试提取结构化摘要
        summary = extract_result_summary(tool_name, observation) if tool_name else None
        
        if summary:
            tool_type = get_tool_type(tool_name)
            truncated_obs = smart_truncate(observation, tool_type)
            history_desc += f"  摘要: {summary}\n"
            history_desc += f"  观察: {truncated_obs}\n"
        else:
            tool_type = get_tool_type(tool_name) if tool_name else "default"
            truncated_obs = smart_truncate(observation, tool_type)
            history_desc += f"  观察: {truncated_obs}\n"
    
    return history_desc


def _generate_step_summary(record: Dict[str, Any], max_length: int) -> str:
    """
    生成单步摘要
    
    格式：工具名(结果状态)
    例如：nslookup(成功:IP=1.2.3.4) → ping(成功:延迟10ms)
    """
    action = record.get('action', {})
    tool_name = action.get('tool', '未知工具') if isinstance(action, dict) else '未知工具'
    observation = record.get('observation', '')
    
    # 简化工具名
    if '.' in tool_name:
        tool_name = tool_name.split('.')[-1]
    
    # 判断结果状态
    if not observation or observation == 'N/A':
        status = "无结果"
    elif any(err in str(observation).lower() for err in ['error', 'failed', '失败', '错误']):
        status = "失败"
    else:
        # 尝试提取关键信息
        status = _extract_key_info(observation)
    
    summary = f"{tool_name}({status})"
    
    # 确保不超过最大长度
    if len(summary) > max_length:
        summary = summary[:max_length-3] + "..."
    
    return summary


def _extract_key_info(observation: str) -> str:
    """从观察结果中提取关键信息"""
    import re
    
    obs_str = str(observation)[:500]
    
    # 尝试提取 IP 地址
    ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', obs_str)
    if ip_match:
        return f"IP={ip_match.group()}"
    
    # 尝试提取延迟
    latency_match = re.search(r'(\d+(?:\.\d+)?)\s*ms', obs_str)
    if latency_match:
        return f"延迟{latency_match.group(1)}ms"
    
    # 尝试提取记录数
    count_match = re.search(r'(\d+)\s*(?:rows?|条|记录|结果)', obs_str)
    if count_match:
        return f"{count_match.group(1)}条记录"
    
    return "成功"


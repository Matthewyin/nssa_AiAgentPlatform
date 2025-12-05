"""
UserInput节点
接收用户输入并初始化状态
"""
from typing import Dict, Any
from loguru import logger
from ..state import GraphState
from utils import load_langgraph_config


def user_input_node(state: GraphState) -> GraphState:
    """
    用户输入节点

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    # 加载配置
    config = load_langgraph_config()
    node_config = config.get("langgraph", {}).get("nodes", {}).get("user_input", {})

    # 清理用户输入：移除 OpenWebUI 添加的 "Tools Available" 信息
    user_query = state["user_query"]

    # 查找 "#### Tools Available" 标记
    tools_marker = "#### Tools Available"
    if tools_marker in user_query:
        # 只保留标记之前的内容
        user_query = user_query.split(tools_marker)[0].strip()
        logger.info(f"已移除 OpenWebUI 的 Tools Available 信息")

    state["user_query"] = user_query

    # 验证输入
    if node_config.get("validate_input", True):
        max_length = node_config.get("max_length", 8000)
        if len(state["user_query"]) > max_length:
            logger.warning(f"用户输入过长,已截断: {len(state['user_query'])} > {max_length}")
            state["user_query"] = state["user_query"][:max_length]
    
    # 初始化状态
    state["current_node"] = "user_input"
    state["errors"] = []
    state["metadata"] = {
        "start_time": __import__("time").time()
    }
    
    logger.info(f"用户输入节点: {state['user_query'][:100]}...")
    
    return state

"""
ReAct Observe Node
观察节点：记录执行历史，更新状态
"""
from typing import Dict, Any
from loguru import logger
from ..state import GraphState
from datetime import datetime


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
        
        # 添加到执行历史
        if "execution_history" not in state or state["execution_history"] is None:
            state["execution_history"] = []
        
        state["execution_history"].append(record)
        
        logger.info(f"记录步骤 {state['current_step']}: action={next_action.get('action_type')}, tool={next_action.get('tool_name')}")
        
        # 增加步骤计数
        state["current_step"] += 1
        
    except Exception as e:
        error_msg = f"ReAct Observe 失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        state["errors"].append(error_msg)
    
    return state


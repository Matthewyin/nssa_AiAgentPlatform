"""
ReAct Act Node
行动节点：执行 LLM 决定的工具调用
"""
from typing import Dict, Any
from loguru import logger
from ..state import GraphState
from mcp_manager import McpClientManager
import json


# 全局 MCP Manager 实例
_mcp_manager = None


async def get_mcp_manager():
    """获取或创建 MCP Manager 实例"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = McpClientManager()
        await _mcp_manager.start_all_servers()
        logger.info("MCP Manager 初始化完成（ReAct Act）")
    return _mcp_manager


async def react_act_node(state: GraphState) -> GraphState:
    """
    ReAct 行动节点
    
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
            
            logger.info(f"执行工具: {tool_name}, 参数: {params}")
            
            # 获取 MCP Manager
            mcp_manager = await get_mcp_manager()
            
            # 调用工具
            try:
                result = await mcp_manager.call_tool(tool_name, params)
                
                # 解析结果
                if isinstance(result, str):
                    try:
                        result_dict = json.loads(result)
                        result_str = json.dumps(result_dict, ensure_ascii=False, indent=2)
                    except json.JSONDecodeError:
                        result_str = result
                else:
                    result_str = json.dumps(result, ensure_ascii=False, indent=2)
                
                logger.info(f"工具执行成功: {tool_name}")
                logger.debug(f"工具结果:\n{result_str[:500]}...")
                
                # 保存观察结果
                state["last_observation"] = f"工具 {tool_name} 执行成功。结果:\n{result_str}"
                
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


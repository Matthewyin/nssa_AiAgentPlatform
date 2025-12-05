"""
NetworkAgent节点
执行网络诊断
"""
from typing import Dict, Any
from loguru import logger
from ..state import GraphState
from agents import NetworkDiagAgent
from mcp_manager import McpClientManager, LangChainAdapter
from utils import load_langgraph_config


# 全局MCP Manager和Agent实例(避免重复初始化)
_mcp_manager = None
_network_agent = None


async def get_network_agent():
    """获取或创建NetworkAgent实例"""
    global _mcp_manager, _network_agent

    if _network_agent is None:
        # 初始化MCP Client Manager（使用新的 stdio 实现）
        _mcp_manager = McpClientManager()
        await _mcp_manager.start_all_servers()

        # 创建LangChain适配器
        adapter = LangChainAdapter(_mcp_manager)

        # 获取网络工具
        tools = adapter.build_langchain_tools(prefix="network")

        # 创建NetworkAgent
        _network_agent = NetworkDiagAgent(tools=tools)

        logger.info("NetworkAgent初始化完成（使用 MCP Stdio 连接）")

    return _network_agent


async def network_agent_node(state: GraphState) -> GraphState:
    """
    网络诊断Agent节点
    
    Args:
        state: 当前状态
        
    Returns:
        更新后的状态
    """
    state["current_node"] = "network_agent"
    
    # 加载配置
    config = load_langgraph_config()
    node_config = config.get("langgraph", {}).get("nodes", {}).get("network_agent", {})
    
    try:
        # 获取Agent
        agent = await get_network_agent()
        
        # 执行诊断
        logger.info(f"开始网络诊断: {state['user_query']}")
        result = await agent.run(state["user_query"])
        
        # 保存结果
        state["network_diag_result"] = result
        
        logger.info("网络诊断完成")
        
    except Exception as e:
        error_msg = f"网络诊断失败: {str(e)}"
        logger.error(error_msg)
        state["errors"].append(error_msg)
        state["network_diag_result"] = {
            "output": error_msg,
            "error": str(e)
        }
    
    return state

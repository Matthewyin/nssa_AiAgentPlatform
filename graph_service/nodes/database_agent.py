"""
DatabaseAgent节点
执行数据库查询
"""
from typing import Dict, Any
from loguru import logger
from ..state import GraphState
from agents import DatabaseAgent
from mcp_manager import McpClientManager, LangChainAdapter
from utils import load_langgraph_config


# 全局MCP Manager和Agent实例(避免重复初始化)
_mcp_manager = None
_database_agent = None


async def get_database_agent():
    """获取或创建DatabaseAgent实例"""
    global _mcp_manager, _database_agent

    if _database_agent is None:
        # 初始化MCP Client Manager（使用新的 stdio 实现）
        _mcp_manager = McpClientManager()
        await _mcp_manager.start_all_servers()

        # 创建LangChain适配器
        adapter = LangChainAdapter(_mcp_manager)

        # 获取数据库工具
        tools = adapter.build_langchain_tools(prefix="mysql")

        # 创建DatabaseAgent
        _database_agent = DatabaseAgent(tools=tools)

        logger.info("DatabaseAgent初始化完成（使用 MCP Stdio 连接）")

    return _database_agent


async def database_agent_node(state: GraphState) -> GraphState:
    """
    数据库查询Agent节点
    
    Args:
        state: 当前状态
        
    Returns:
        更新后的状态
    """
    state["current_node"] = "database_agent"
    
    # 加载配置
    config = load_langgraph_config()
    node_config = config.get("langgraph", {}).get("nodes", {}).get("database_agent", {})
    
    try:
        # 获取Agent
        agent = await get_database_agent()
        
        # 执行查询
        logger.info(f"开始数据库查询: {state['user_query']}")
        result = await agent.run(state["user_query"])
        
        # 保存结果
        state["database_query_result"] = result
        
        logger.info("数据库查询完成")
        
    except Exception as e:
        error_msg = f"数据库查询失败: {str(e)}"
        logger.error(error_msg)
        state["errors"].append(error_msg)
        state["database_query_result"] = {
            "output": error_msg,
            "error": str(e)
        }
    
    return state


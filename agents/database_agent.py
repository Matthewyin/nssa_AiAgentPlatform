"""
数据库查询Agent
专门处理MySQL数据库查询任务
"""
from typing import List, Optional, Dict, Any
from langchain_core.tools import Tool
from loguru import logger

from .base_agent import BaseAgent


class DatabaseAgent(BaseAgent):
    """数据库查询Agent"""
    
    def __init__(
        self,
        tools: List[Tool],
        llm_config: Optional[Dict[str, Any]] = None,
        agent_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化数据库查询Agent
        
        Args:
            tools: 数据库查询工具列表
            llm_config: LLM配置
            agent_config: Agent配置
        """
        super().__init__(
            agent_name="database",
            tools=tools,
            llm_config=llm_config,
            agent_config=agent_config
        )
    
    async def query(self, query_description: str) -> Dict[str, Any]:
        """
        执行数据库查询
        
        Args:
            query_description: 查询描述
            
        Returns:
            查询结果
        """
        logger.info(f"开始数据库查询: {query_description}")
        
        # 运行Agent
        result = await self.run(query_description)
        
        return {
            "query_description": query_description,
            "result": result.get("output", ""),
            "success": "error" not in result
        }


"""
网络诊断Agent
专门处理网络故障诊断任务
"""
from typing import List, Optional, Dict, Any
from langchain_core.tools import Tool
from loguru import logger

from .base_agent import BaseAgent


class NetworkDiagAgent(BaseAgent):
    """网络诊断Agent"""
    
    def __init__(
        self,
        tools: List[Tool],
        llm_config: Optional[Dict[str, Any]] = None,
        agent_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化网络诊断Agent
        
        Args:
            tools: 网络诊断工具列表
            llm_config: LLM配置
            agent_config: Agent配置
        """
        super().__init__(
            agent_name="network_diag",
            tools=tools,
            llm_config=llm_config,
            agent_config=agent_config
        )
    
    async def diagnose(self, target: str, issue_description: str = "") -> Dict[str, Any]:
        """
        执行网络诊断
        
        Args:
            target: 目标主机(IP或域名)
            issue_description: 问题描述
            
        Returns:
            诊断结果
        """
        # 构建查询
        if issue_description:
            query = f"诊断到 {target} 的网络问题: {issue_description}"
        else:
            query = f"诊断到 {target} 的网络连接情况"
        
        logger.info(f"开始网络诊断: {query}")
        
        # 运行Agent
        result = await self.run(query)
        
        return {
            "target": target,
            "issue_description": issue_description,
            "diagnosis": result.get("output", ""),
            "success": "error" not in result
        }

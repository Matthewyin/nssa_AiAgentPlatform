"""
MCP Manager 核心模块
管理多个MCP Server的连接和工具调用
"""
import asyncio
import subprocess
from typing import Dict, List, Any, Optional
from pathlib import Path
from loguru import logger

from .connection import McpConnection
from .error_handler import retry_on_error
from utils import load_mcp_config


class McpManager:
    """MCP Manager 主类,负责管理所有MCP Server"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化MCP Manager
        
        Args:
            config_path: MCP配置文件路径,如果为None则使用默认配置
        """
        self.servers: Dict[str, McpConnection] = {}  # {server_name: connection}
        self.tools: Dict[str, str] = {}  # {tool_name: server_name}
        self.config = load_mcp_config() if config_path is None else self._load_config(config_path)
        
        logger.info("MCP Manager 初始化完成")
    
    async def start_all_servers(self):
        """启动所有配置的MCP Server"""
        server_configs = self.config.get("mcp_servers", [])
        
        for server_config in server_configs:
            try:
                await self.start_server(server_config)
            except Exception as e:
                logger.error(f"启动MCP Server失败: {server_config['name']}, 错误: {e}")
    
    async def start_server(self, server_config: Dict[str, Any]):
        """
        启动单个MCP Server
        
        Args:
            server_config: Server配置字典
        """
        name = server_config["name"]
        command = server_config["command"]
        args = server_config.get("args", [])
        tools_prefix = server_config.get("tools_prefix", "")
        
        logger.info(f"启动MCP Server: {name}")
        
        # 创建连接
        connection = McpConnection(
            name=name,
            command=command,
            args=args,
            tools_prefix=tools_prefix
        )
        
        # 启动Server进程
        await connection.start()
        
        # 保存连接
        self.servers[name] = connection
        
        # 获取工具列表并注册
        tools = await connection.list_tools()
        for tool in tools:
            tool_name = tool["name"]
            self.tools[tool_name] = name
            logger.info(f"注册工具: {tool_name} -> {name}")
        
        logger.info(f"MCP Server {name} 启动成功,注册了 {len(tools)} 个工具")
    
    @retry_on_error(max_retries=1, delay=1.0)
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用指定的工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
            
        Raises:
            ValueError: 工具不存在
            RuntimeError: 工具调用失败
        """
        # 查找工具对应的Server
        server_name = self.tools.get(tool_name)
        if not server_name:
            raise ValueError(f"工具不存在: {tool_name}")
        
        # 获取连接
        connection = self.servers.get(server_name)
        if not connection:
            raise RuntimeError(f"Server连接不存在: {server_name}")
        
        # 调用工具
        logger.info(f"调用工具: {tool_name}, 参数: {arguments}")
        result = await connection.call_tool(tool_name, arguments)
        
        return result
    
    def get_tools_by_prefix(self, prefix: str) -> List[str]:
        """
        获取指定前缀的所有工具名称
        
        Args:
            prefix: 工具前缀,如 "network"
            
        Returns:
            工具名称列表
        """
        return [
            tool_name 
            for tool_name in self.tools.keys() 
            if tool_name.startswith(prefix + ".")
        ]
    
    async def stop_all_servers(self):
        """停止所有MCP Server"""
        for name, connection in self.servers.items():
            try:
                await connection.stop()
                logger.info(f"MCP Server {name} 已停止")
            except Exception as e:
                logger.error(f"停止MCP Server失败: {name}, 错误: {e}")
        
        self.servers.clear()
        self.tools.clear()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        from utils import load_yaml_config
        return load_yaml_config(config_path)

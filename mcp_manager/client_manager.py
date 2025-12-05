"""
MCP Client Manager
管理多个 MCP Stdio 连接
"""
import os
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from loguru import logger

from .stdio_connection import McpStdioConnection
from .error_handler import retry_on_error
from utils import load_mcp_config


class McpClientManager:
    """
    MCP Client Manager 主类
    负责管理所有 MCP Stdio 连接
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化 MCP Client Manager

        Args:
            config_path: MCP配置文件路径,如果为None则使用默认配置
        """
        self.connections: Dict[str, McpStdioConnection] = {}  # {server_name: connection}
        self.tools: Dict[str, str] = {}  # {tool_name: server_name}
        self.original_tool_names: Dict[str, str] = {}  # {full_tool_name: original_tool_name}
        self.config = load_mcp_config() if config_path is None else self._load_config(config_path)

        logger.info("MCP Client Manager 初始化完成")
    
    async def start_all_servers(self):
        """启动所有配置的 MCP Server"""
        server_configs = self.config.get("mcp_servers", [])
        
        for server_config in server_configs:
            try:
                await self.start_server(server_config)
            except Exception as e:
                logger.error(f"启动 MCP Server 失败: {server_config['name']}, 错误: {e}")
    
    async def start_server(self, server_config: Dict[str, Any]):
        """
        启动单个 MCP Server

        Args:
            server_config: Server配置字典
        """
        name = server_config["name"]
        command = server_config["command"]
        args = server_config.get("args", [])
        tools_prefix = server_config.get("tools_prefix", "")
        env = server_config.get("env", {})

        # 替换环境变量（支持 ${VAR} 和 $VAR 格式）
        env = {k: os.path.expandvars(v) for k, v in env.items()}

        logger.info(f"启动 MCP Server: {name}")
        
        # 创建连接
        connection = McpStdioConnection(
            name=name,
            command=command,
            args=args,
            tools_prefix=tools_prefix,
            env=env
        )
        
        # 启动 Server 并建立连接
        await connection.start()

        # 保存连接
        self.connections[name] = connection

        # 获取工具列表并注册
        tools = await connection.list_tools()
        for tool in tools:
            tool_name = tool["name"]
            # 添加工具前缀（如果工具名称还没有前缀）
            if tools_prefix:
                # 检查工具名称是否已经包含前缀
                if not tool_name.startswith(f"{tools_prefix}."):
                    full_tool_name = f"{tools_prefix}.{tool_name}"
                else:
                    # 工具名称已经包含前缀，不再添加
                    full_tool_name = tool_name
            else:
                full_tool_name = tool_name

            # 记录原始工具名称和完整工具名称的映射
            self.tools[full_tool_name] = name
            self.original_tool_names[full_tool_name] = tool_name
            logger.info(f"注册工具: {full_tool_name} -> {name} (原始名称: {tool_name})")

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
        connection = self.connections.get(server_name)
        if not connection:
            raise RuntimeError(f"Server连接不存在: {server_name}")

        # 获取原始工具名称
        original_tool_name = self.original_tool_names.get(tool_name, tool_name)

        # 调用工具
        logger.info(f"调用工具: {tool_name} (原始名称: {original_tool_name}), 参数: {arguments}")
        result = await connection.call_tool(original_tool_name, arguments)

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
        """停止所有 MCP Server"""
        for name, connection in self.connections.items():
            try:
                await connection.stop()
                logger.info(f"MCP Server {name} 已停止")
            except Exception as e:
                logger.error(f"停止 MCP Server 失败: {name}, 错误: {e}")
        
        self.connections.clear()
        self.tools.clear()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        from utils import load_yaml_config
        return load_yaml_config(config_path)


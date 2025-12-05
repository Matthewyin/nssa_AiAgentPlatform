"""
MCP Stdio Connection
基于官方 MCP Client SDK 实现的 stdio transport 连接
"""
import asyncio
from typing import Dict, List, Any, Optional
from contextlib import AsyncExitStack
from loguru import logger

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.types import Tool


class McpStdioConnection:
    """
    MCP Stdio 连接类
    使用官方 MCP Client SDK 通过 stdio 与 MCP Server 通信
    """
    
    def __init__(
        self,
        name: str,
        command: str,
        args: List[str],
        tools_prefix: str = "",
        env: Optional[Dict[str, str]] = None
    ):
        """
        初始化 MCP Stdio 连接
        
        Args:
            name: Server 名称
            command: 启动命令
            args: 命令参数
            tools_prefix: 工具前缀
            env: 环境变量
        """
        self.name = name
        self.command = command
        self.args = args
        self.tools_prefix = tools_prefix
        self.env = env or {}
        
        # 连接状态
        self.is_connected = False
        self.exit_stack: Optional[AsyncExitStack] = None
        self.session = None
        self.read = None
        self.write = None
        
        # 工具缓存
        self._tools_cache: Optional[List[Tool]] = None
        
        logger.info(f"创建 MCP Stdio 连接: {name}")
    
    async def start(self):
        """启动 MCP Server 并建立连接"""
        try:
            logger.info(f"启动 MCP Server: {self.name}")
            
            # 创建 Server 参数
            server_params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env if self.env else None
            )
            
            # 创建 exit stack 管理资源
            self.exit_stack = AsyncExitStack()
            
            # 创建 stdio client
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.read, self.write = stdio_transport
            
            # 创建 session
            from mcp.client.session import ClientSession
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.read, self.write)
            )
            
            # 初始化连接
            await self.session.initialize()
            
            self.is_connected = True
            logger.info(f"MCP Server {self.name} 启动成功")
            
        except Exception as e:
            logger.error(f"启动 MCP Server 失败: {self.name}, 错误: {e}")
            await self.stop()
            raise
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        获取工具列表
        
        Returns:
            工具列表
        """
        if not self.is_connected or not self.session:
            raise RuntimeError(f"MCP Server {self.name} 未连接")
        
        try:
            # 调用 list_tools
            response = await self.session.list_tools()
            
            # 缓存工具列表
            self._tools_cache = response.tools
            
            # 转换为字典格式
            tools = []
            for tool in response.tools:
                # 注意：工具名已经包含前缀（如 network.ping），不需要再添加
                tool_dict = {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema
                }
                tools.append(tool_dict)
            
            logger.info(f"获取到 {len(tools)} 个工具 (Server: {self.name})")
            return tools
            
        except Exception as e:
            logger.error(f"获取工具列表失败: {self.name}, 错误: {e}")
            raise
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用工具
        
        Args:
            tool_name: 工具名称（可能包含前缀）
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        if not self.is_connected or not self.session:
            raise RuntimeError(f"MCP Server {self.name} 未连接")
        
        try:
            # 工具名已经是完整的名称（如 network.ping），直接使用
            logger.info(f"调用工具: {tool_name}, 参数: {arguments}")

            # 调用 call_tool
            response = await self.session.call_tool(tool_name, arguments)

            # 提取结果
            if response.content:
                # 合并所有 content
                result_parts = []
                for content in response.content:
                    if hasattr(content, 'text'):
                        result_parts.append(content.text)
                    else:
                        result_parts.append(str(content))

                result = "\n".join(result_parts)
            else:
                result = ""

            logger.info(f"工具调用成功: {tool_name}")
            return result

        except Exception as e:
            logger.error(f"工具调用失败: {tool_name}, 错误: {e}")
            raise

    async def stop(self):
        """停止连接并清理资源"""
        try:
            if self.exit_stack:
                await self.exit_stack.aclose()
                self.exit_stack = None

            self.session = None
            self.read = None
            self.write = None
            self.is_connected = False
            self._tools_cache = None

            logger.info(f"MCP Server {self.name} 已停止")

        except Exception as e:
            logger.error(f"停止 MCP Server 失败: {self.name}, 错误: {e}")

    def __repr__(self) -> str:
        return f"McpStdioConnection(name={self.name}, connected={self.is_connected})"



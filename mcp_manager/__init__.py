"""MCP Manager模块"""
# 新的实现（基于官方 MCP SDK）
from .client_manager import McpClientManager
from .stdio_connection import McpStdioConnection

# 旧的实现（向后兼容）
from .manager_legacy import McpManager
from .connection_legacy import McpConnection

from .error_handler import retry_on_error, ToolCallError, ServerConnectionError
from .adapters.langchain_adapter import LangChainAdapter

__all__ = [
    # 新实现
    "McpClientManager",
    "McpStdioConnection",
    # 旧实现（向后兼容）
    "McpManager",
    "McpConnection",
    # 其他
    "retry_on_error",
    "ToolCallError",
    "ServerConnectionError",
    "LangChainAdapter",
]

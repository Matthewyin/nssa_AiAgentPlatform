"""
MCP连接封装
管理单个MCP Server的进程和通信
"""
import asyncio
import subprocess
from typing import Dict, List, Any, Optional
from loguru import logger
from utils import load_tools_config


class McpConnection:
    """MCP Server连接类"""
    
    def __init__(
        self,
        name: str,
        command: str,
        args: List[str],
        tools_prefix: str = ""
    ):
        """
        初始化MCP连接
        
        Args:
            name: Server名称
            command: 启动命令
            args: 命令参数
            tools_prefix: 工具前缀
        """
        self.name = name
        self.command = command
        self.args = args
        self.tools_prefix = tools_prefix
        self.process: Optional[subprocess.Popen] = None
        self._tools_cache: List[Dict[str, Any]] = []
    
    async def start(self):
        """启动MCP Server进程"""
        try:
            # 启动进程,使用stdio通信
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False  # 使用字节模式
            )
            
            logger.info(f"MCP Server进程已启动: {self.name}, PID: {self.process.pid}")
            
            # 等待进程初始化
            await asyncio.sleep(0.5)
            
            # 检查进程是否正常运行
            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
                raise RuntimeError(f"MCP Server启动失败: {stderr}")
                
        except Exception as e:
            logger.error(f"启动MCP Server失败: {self.name}, 错误: {e}")
            raise
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        获取工具列表,从配置文件读取
        
        Returns:
            工具列表
        """
        # 从配置文件加载工具信息
        tools_config = load_tools_config()
        all_tools = tools_config.get("tools", {})
        
        # 根据tools_prefix获取对应的工具
        if self.tools_prefix in all_tools:
            tools_dict = all_tools[self.tools_prefix]
            self._tools_cache = [
                {
                    "name": tool_config["name"],
                    "description": tool_config["description"]
                }
                for tool_key, tool_config in tools_dict.items()
            ]
        else:
            logger.warning(f"未找到工具前缀 {self.tools_prefix} 的配置")
            self._tools_cache = []
        
        return self._tools_cache
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        # 简化实现:直接调用本地工具函数
        # 在实际MCP协议中,这里应该通过stdio与Server通信
        
        if not self.process or self.process.poll() is not None:
            raise RuntimeError(f"MCP Server未运行: {self.name}")
        
        # 导入工具函数
        if tool_name == "network.ping":
            from mcp_servers.network_mcp.tools.ping import ping_tool
            result = await ping_tool(**arguments)
        elif tool_name == "network.traceroute":
            from mcp_servers.network_mcp.tools.traceroute import traceroute_tool
            result = await traceroute_tool(**arguments)
        elif tool_name == "network.nslookup":
            from mcp_servers.network_mcp.tools.nslookup import nslookup_tool
            result = await nslookup_tool(**arguments)
        elif tool_name == "network.mtr":
            from mcp_servers.network_mcp.tools.mtr import mtr_tool
            result = await mtr_tool(**arguments)
        else:
            raise ValueError(f"未知工具: {tool_name}")
        
        return result
    
    async def stop(self):
        """停止MCP Server进程"""
        if self.process:
            try:
                self.process.terminate()
                # 等待进程结束
                await asyncio.sleep(0.5)
                if self.process.poll() is None:
                    self.process.kill()  # 强制结束
                logger.info(f"MCP Server进程已停止: {self.name}")
            except Exception as e:
                logger.error(f"停止MCP Server进程失败: {self.name}, 错误: {e}")

"""
LangChain适配器
将MCP工具转换为LangChain Tool
"""
from typing import List, Dict, Any, Callable
from langchain_core.tools import Tool
from loguru import logger
from utils import load_tools_config


class LangChainAdapter:
    """LangChain工具适配器"""
    
    def __init__(self, mcp_manager):
        """
        初始化适配器
        
        Args:
            mcp_manager: McpManager实例
        """
        self.mcp_manager = mcp_manager
        # 加载工具配置
        self.tools_config = load_tools_config()
    
    def build_langchain_tools(self, prefix: str = "") -> List[Tool]:
        """
        构建LangChain工具列表
        
        Args:
            prefix: 工具前缀,如 "network"
            
        Returns:
            LangChain Tool列表
        """
        tools = []
        
        # 获取指定前缀的工具
        tool_names = self.mcp_manager.get_tools_by_prefix(prefix)
        
        for tool_name in tool_names:
            # 创建工具调用函数
            tool_func = self._create_tool_func(tool_name)
            
            # 创建LangChain Tool
            lc_tool = Tool(
                name=tool_name,
                description=self._get_tool_description(tool_name),
                func=tool_func
            )
            
            tools.append(lc_tool)
            logger.debug(f"创建LangChain工具: {tool_name}")
        
        logger.info(f"构建了 {len(tools)} 个LangChain工具 (前缀: {prefix})")
        return tools
    
    def _create_tool_func(self, tool_name: str) -> Callable:
        """
        创建工具调用函数
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具调用函数
        """
        async def tool_func(**kwargs) -> str:
            """
            工具调用函数
            
            Args:
                **kwargs: 工具参数
                
            Returns:
                工具执行结果
            """
            try:
                # 调用MCP工具
                result = await self.mcp_manager.call_tool(tool_name, kwargs)
                
                return str(result)
                
            except Exception as e:
                error_msg = f"工具调用失败: {tool_name}, 错误: {e}"
                logger.error(error_msg)
                return error_msg
        
        return tool_func
    
    def _get_tool_description(self, tool_name: str) -> str:
        """
        从配置文件获取工具描述
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具描述
        """
        # 解析工具名称,获取前缀和工具key
        # 例如: "network.ping" -> prefix="network", key="ping"
        parts = tool_name.split(".", 1)
        if len(parts) != 2:
            return f"MCP工具: {tool_name}"
        
        prefix, tool_key = parts
        
        # 从配置文件获取描述
        tools_dict = self.tools_config.get("tools", {}).get(prefix, {})
        tool_config = tools_dict.get(tool_key, {})
        
        if not tool_config:
            logger.warning(f"未找到工具 {tool_name} 的配置")
            return f"MCP工具: {tool_name}"
        
        # 构建完整的描述,包含参数信息
        description = tool_config.get("description", "")
        parameters = tool_config.get("parameters", {})
        
        # 添加参数说明
        if parameters:
            param_desc = []
            for param_name, param_config in parameters.items():
                param_type = param_config.get("type", "string")
                param_required = param_config.get("required", False)
                param_default = param_config.get("default")
                
                param_str = f"{param_name} ({param_type})"
                if param_required:
                    param_str += " [必需]"
                elif param_default is not None:
                    param_str += f" [默认: {param_default}]"
                
                param_desc.append(param_str)
            
            description += f"\n参数: {', '.join(param_desc)}"
        
        return description

"""
Network MCP Server
提供网络诊断工具集
"""
import asyncio
import sys
from typing import Any, Dict, List
from mcp.server import Server
from mcp.types import Tool, TextContent
from loguru import logger
from pathlib import Path
import yaml

# 导入工具实现
from .tools.ping import ping_tool
from .tools.traceroute import traceroute_tool
from .tools.nslookup import nslookup_tool
from .tools.mtr import mtr_tool


# 加载工具配置
def load_tools_config() -> Dict[str, Any]:
    """加载工具配置"""
    config_path = Path(__file__).parent.parent.parent / "config" / "tools_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 创建MCP Server实例
app = Server("network-mcp")


@app.list_tools()
async def list_tools() -> List[Tool]:
    """
    列出所有可用的网络诊断工具
    从配置文件读取工具定义
    
    Returns:
        工具列表
    """
    config = load_tools_config()
    network_tools = config.get("tools", {}).get("network", {})
    
    tools = []
    
    for tool_key, tool_config in network_tools.items():
        # 构建inputSchema
        properties = {}
        required = []
        
        for param_name, param_config in tool_config.get("parameters", {}).items():
            properties[param_name] = {
                "type": param_config.get("type"),
                "description": param_config.get("description")
            }
            
            # 添加默认值
            if "default" in param_config:
                properties[param_name]["default"] = param_config["default"]
            
            # 添加枚举值
            if "enum" in param_config:
                properties[param_name]["enum"] = param_config["enum"]
            
            # 添加到required列表
            if param_config.get("required", False):
                required.append(param_name)
        
        # 创建Tool对象
        tool = Tool(
            name=tool_config["name"],
            description=tool_config["description"],
            inputSchema={
                "type": "object",
                "properties": properties,
                "required": required
            }
        )
        
        tools.append(tool)
    
    return tools


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """
    调用指定的工具
    
    Args:
        name: 工具名称
        arguments: 工具参数
        
    Returns:
        工具执行结果
    """
    logger.info(f"调用工具: {name}, 参数: {arguments}")
    
    try:
        # 路由到对应的工具实现
        if name == "network.ping":
            result = await ping_tool(**arguments)
        elif name == "network.traceroute":
            result = await traceroute_tool(**arguments)
        elif name == "network.nslookup":
            result = await nslookup_tool(**arguments)
        elif name == "network.mtr":
            result = await mtr_tool(**arguments)
        else:
            raise ValueError(f"未知的工具: {name}")
        
        logger.info(f"工具 {name} 执行成功")
        return [TextContent(type="text", text=result)]
        
    except Exception as e:
        error_msg = f"工具 {name} 执行失败: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


async def main():
    """启动MCP Server"""
    logger.info("启动 Network MCP Server...")
    
    # 使用stdio传输
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    # 配置日志
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    # 运行服务器
    asyncio.run(main())

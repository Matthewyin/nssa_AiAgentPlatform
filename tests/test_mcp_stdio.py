"""
测试新的 MCP Stdio 连接
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_manager import McpClientManager
from loguru import logger


async def test_mcp_stdio_connection():
    """测试 MCP Stdio 连接"""
    logger.info("=" * 60)
    logger.info("开始测试 MCP Stdio 连接")
    logger.info("=" * 60)
    
    # 创建 Manager
    manager = McpClientManager()
    
    try:
        # 启动所有 Server
        logger.info("\n1. 启动 MCP Servers...")
        await manager.start_all_servers()
        
        # 列出所有工具
        logger.info("\n2. 列出所有工具...")
        for tool_name, server_name in manager.tools.items():
            logger.info(f"  - {tool_name} (Server: {server_name})")
        
        # 测试 ping 工具
        logger.info("\n3. 测试 ping 工具...")
        result = await manager.call_tool("network.ping", {
            "target": "baidu.com",
            "count": 3
        })
        logger.info(f"Ping 结果:\n{result}")
        
        # 测试 nslookup 工具
        logger.info("\n4. 测试 nslookup 工具...")
        result = await manager.call_tool("network.nslookup", {
            "target": "baidu.com",
            "record_type": "A"
        })
        logger.info(f"NSLookup 结果:\n{result}")
        
        logger.info("\n" + "=" * 60)
        logger.info("测试完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
    
    finally:
        # 停止所有 Server
        logger.info("\n5. 停止 MCP Servers...")
        await manager.stop_all_servers()


if __name__ == "__main__":
    asyncio.run(test_mcp_stdio_connection())


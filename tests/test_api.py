"""
简单的API测试脚本
测试Graph Service的基本功能
"""
import asyncio
import httpx
from loguru import logger


async def test_health():
    """测试健康检查接口"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/health")
            logger.info(f"健康检查: {response.status_code}")
            logger.info(f"响应: {response.json()}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False


async def test_chat(message: str):
    """测试聊天接口"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "http://localhost:8000/chat",
                json={
                    "message": message,
                    "session_id": "test"
                }
            )
            logger.info(f"聊天请求: {response.status_code}")
            result = response.json()
            logger.info(f"回复: {result.get('answer', '')[:200]}...")
            logger.info(f"元数据: {result.get('metadata', {})}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"聊天请求失败: {e}")
            return False


async def main():
    """主测试函数"""
    logger.info("=== 开始API测试 ===")
    
    # 测试健康检查
    logger.info("\n1. 测试健康检查接口")
    health_ok = await test_health()
    
    if not health_ok:
        logger.error("健康检查失败,请确保服务已启动")
        return
    
    # 测试聊天接口
    logger.info("\n2. 测试聊天接口")
    
    test_messages = [
        "帮我ping一下8.8.8.8",
        "traceroute到baidu.com",
        "查询google.com的DNS记录"
    ]
    
    for msg in test_messages:
        logger.info(f"\n测试消息: {msg}")
        await test_chat(msg)
        await asyncio.sleep(2)  # 等待2秒
    
    logger.info("\n=== 测试完成 ===")


if __name__ == "__main__":
    asyncio.run(main())

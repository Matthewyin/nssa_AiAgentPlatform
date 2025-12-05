"""
错误处理和重试机制
"""
import asyncio
from typing import Callable, Any
from functools import wraps
from loguru import logger


def retry_on_error(max_retries: int = 1, delay: float = 1.0):
    """
    装饰器:在函数执行失败时自动重试
    
    Args:
        max_retries: 最大重试次数
        delay: 重试间隔(秒)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"函数 {func.__name__} 执行失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        logger.info(f"等待 {delay} 秒后重试...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"函数 {func.__name__} 执行失败,已达最大重试次数: {e}"
                        )
            
            # 抛出最后一次的异常
            raise last_exception
        
        return wrapper
    return decorator


class ToolCallError(Exception):
    """工具调用错误"""
    pass


class ServerConnectionError(Exception):
    """Server连接错误"""
    pass

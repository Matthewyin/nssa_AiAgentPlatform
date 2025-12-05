"""
日志配置模块
使用 loguru 提供统一的日志记录功能
"""
import sys
from pathlib import Path
from loguru import logger
import os


def setup_logger(
    log_level: str = "INFO",
    log_file: str | None = None,
    rotation: str = "100 MB",
    retention: str = "7 days"
):
    """
    配置全局日志记录器
    
    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径,如果为None则只输出到控制台
        rotation: 日志轮转大小
        retention: 日志保留时间
    """
    # 移除默认的handler
    logger.remove()
    
    # 添加控制台输出
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True
    )
    
    # 如果指定了日志文件,添加文件输出
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=log_level,
            rotation=rotation,
            retention=retention,
            encoding="utf-8"
        )
    
    logger.info(f"日志系统初始化完成,日志级别: {log_level}")
    if log_file:
        logger.info(f"日志文件: {log_file}")


def get_logger(name: str):
    """
    获取指定名称的logger
    
    Args:
        name: logger名称,通常使用 __name__
        
    Returns:
        logger实例
    """
    return logger.bind(name=name)


# 从环境变量读取配置并初始化
if __name__ != "__main__":
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = os.getenv("LOG_FILE", "data/logs/app.log")
    setup_logger(log_level=log_level, log_file=log_file)

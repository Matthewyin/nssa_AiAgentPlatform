"""
日志配置模块
使用 loguru 提供统一的日志记录功能
支持按天轮转、分类存储
"""
import sys
from pathlib import Path
from loguru import logger
import os
import yaml
from string import Template
from typing import Dict, Any, Optional

# 日志配置缓存
_logging_config: Optional[Dict[str, Any]] = None


def load_logging_config() -> Dict[str, Any]:
    """加载日志配置"""
    global _logging_config
    if _logging_config is not None:
        return _logging_config

    config_path = Path(__file__).parent.parent / "config" / "logging_config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        template = Template(content)
        content = template.safe_substitute(os.environ)
        _logging_config = yaml.safe_load(content)
    else:
        _logging_config = {}

    return _logging_config


def setup_logger(
    log_level: str = "INFO",
    log_file: str | None = None,
    rotation: str = "00:00",
    retention: str = "30 days"
):
    """
    配置全局日志记录器（基于配置文件）

    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径（兼容旧接口，优先使用配置文件）
        rotation: 日志轮转策略
        retention: 日志保留时间
    """
    # 加载配置
    config = load_logging_config()
    logging_config = config.get("logging", {})

    # 移除默认的handler
    logger.remove()

    # 控制台配置
    console_config = logging_config.get("console", {})
    if console_config.get("enabled", True):
        console_format = console_config.get(
            "format",
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
        console_level = console_config.get("level", log_level)
        logger.add(
            sys.stderr,
            format=console_format,
            level=console_level,
            colorize=console_config.get("colorize", True)
        )

    # 基础目录
    base_dir = Path(logging_config.get("base_dir", "data/logs"))
    default_retention = logging_config.get("retention", retention)

    # 分类日志配置
    categories = logging_config.get("categories", {})

    # 应用日志
    app_config = categories.get("app", {})
    if app_config.get("enabled", True):
        app_dir = base_dir / app_config.get("dir", "app")
        app_dir.mkdir(parents=True, exist_ok=True)
        app_file = app_dir / app_config.get("filename_pattern", "app_{time:YYYY-MM-DD}.log")
        logger.add(
            str(app_file),
            format=app_config.get("format", "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"),
            level=app_config.get("level", log_level),
            rotation=app_config.get("rotation", "00:00"),
            retention=app_config.get("retention", default_retention),
            encoding="utf-8"
        )

    logger.info(f"日志系统初始化完成,日志级别: {log_level}")
    logger.info(f"日志目录: {base_dir}")


def get_logger(name: str):
    """
    获取指定名称的logger

    Args:
        name: logger名称,通常使用 __name__

    Returns:
        logger实例
    """
    return logger.bind(name=name)


def get_log_file_path(category: str) -> Path:
    """
    获取指定分类的日志文件路径

    Args:
        category: 日志分类 (app, graph_service, token_usage)

    Returns:
        日志目录路径
    """
    config = load_logging_config()
    logging_config = config.get("logging", {})
    base_dir = Path(logging_config.get("base_dir", "data/logs"))
    categories = logging_config.get("categories", {})

    category_config = categories.get(category, {})
    category_dir = category_config.get("dir", category)

    log_dir = base_dir / category_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    return log_dir


# 从环境变量读取配置并初始化
if __name__ != "__main__":
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logger(log_level=log_level)

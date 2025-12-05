"""
配置文件监听器
自动监听配置文件变化并触发重载
"""
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from loguru import logger
from .config_manager import ConfigManager


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变化处理器"""
    
    def __init__(self, config_manager: ConfigManager):
        """
        初始化处理器
        
        Args:
            config_manager: 配置管理器实例
        """
        super().__init__()
        self.config_manager = config_manager
        logger.info("配置文件变化处理器已初始化")
    
    def on_modified(self, event):
        """
        文件修改事件处理
        
        Args:
            event: 文件系统事件
        """
        # 只处理文件修改事件，忽略目录
        if event.is_directory:
            return
        
        # 只处理 .yaml 文件
        if not event.src_path.endswith('.yaml'):
            return
        
        # 提取配置名称
        config_path = Path(event.src_path)
        config_name = config_path.stem  # 去掉 .yaml 后缀
        
        logger.info(f"检测到配置文件变化: {config_path.name}")
        
        # 使缓存失效，下次使用时会自动重新加载
        self.config_manager.invalidate_cache(config_name)
        
        logger.info(f"配置 {config_name} 将在下次使用时自动重新加载")


def start_config_watcher(config_manager: ConfigManager) -> Observer:
    """
    启动配置文件监听器
    
    Args:
        config_manager: 配置管理器实例
        
    Returns:
        Observer 实例
    """
    # 获取配置文件目录
    config_dir = Path(__file__).parent.parent / "config"
    
    if not config_dir.exists():
        logger.error(f"配置目录不存在: {config_dir}")
        raise FileNotFoundError(f"配置目录不存在: {config_dir}")
    
    # 创建观察者
    observer = Observer()
    handler = ConfigFileHandler(config_manager)
    
    # 监听配置目录
    observer.schedule(handler, path=str(config_dir), recursive=False)
    
    # 启动观察者
    observer.start()
    
    logger.info(f"配置文件监听器已启动，监听目录: {config_dir}")
    
    return observer


def stop_config_watcher(observer: Observer):
    """
    停止配置文件监听器
    
    Args:
        observer: Observer 实例
    """
    if observer and observer.is_alive():
        observer.stop()
        observer.join()
        logger.info("配置文件监听器已停止")


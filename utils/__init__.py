"""工具模块"""
from .logger import setup_logger, get_logger
from .config_loader import (
    settings,
    load_yaml_config,
    load_mcp_config,
    load_llm_config,
    load_agent_config,
    load_tools_config,
    load_langchain_config,
    load_langgraph_config,
    load_router_prompt_config,
    load_agent_mapping_config,
    load_optimization_config,
)
from .config_manager import get_config_manager, ConfigManager
from .token_tracker import get_token_tracker, TokenTracker
from .query_cache import get_query_cache, QueryCache

# watchdog 是可选依赖，仅在需要配置热加载时使用
try:
    from .config_watcher import start_config_watcher, stop_config_watcher
except ImportError:
    # watchdog 未安装时，提供空实现
    def start_config_watcher(config_manager):
        return None

    def stop_config_watcher(watcher):
        pass

__all__ = [
    "setup_logger",
    "get_logger",
    "settings",
    "load_yaml_config",
    "load_mcp_config",
    "load_llm_config",
    "load_agent_config",
    "load_tools_config",
    "load_langchain_config",
    "load_langgraph_config",
    "load_router_prompt_config",
    "load_agent_mapping_config",
    "load_optimization_config",
    "get_config_manager",
    "ConfigManager",
    "start_config_watcher",
    "stop_config_watcher",
    "get_token_tracker",
    "TokenTracker",
    "get_query_cache",
    "QueryCache",
]

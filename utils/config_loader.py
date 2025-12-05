"""
配置加载模块
从YAML文件和环境变量加载配置
"""
import os
from pathlib import Path
from typing import Any, Dict
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from string import Template


class Settings(BaseSettings):
    """环境变量配置"""
    # Ollama 配置
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "deepseek-r1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    # Graph Service 配置
    graph_service_host: str = "0.0.0.0"
    graph_service_port: int = 30021

    # 日志配置
    log_level: str = "INFO"
    log_file: str = "data/logs/app.log"

    # ChromaDB 配置
    chroma_persist_dir: str = "data/vector_db"
    chroma_collection_name: str = "network_cases"

    class Config:
        # 使用绝对路径指定 .env 文件位置
        env_file = str(Path(__file__).parent.parent / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略额外的字段


def load_yaml_config(config_path: str | Path) -> Dict[str, Any]:
    """
    加载YAML配置文件,支持环境变量替换
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    # 读取YAML内容
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 替换环境变量 ${VAR_NAME}
    template = Template(content)
    env_dict = {k: v for k, v in os.environ.items()}
    content = template.safe_substitute(env_dict)
    
    # 解析YAML
    config = yaml.safe_load(content)
    return config


def get_config_dir() -> Path:
    """获取配置文件目录"""
    return Path(__file__).parent.parent / "config"


def load_mcp_config() -> Dict[str, Any]:
    """加载MCP配置"""
    return load_yaml_config(get_config_dir() / "mcp_config.yaml")


def load_llm_config() -> Dict[str, Any]:
    """加载LLM配置"""
    return load_yaml_config(get_config_dir() / "llm_config.yaml")


def load_agent_config() -> Dict[str, Any]:
    """加载Agent配置"""
    return load_yaml_config(get_config_dir() / "agent_config.yaml")


def load_tools_config() -> Dict[str, Any]:
    """加载工具配置"""
    return load_yaml_config(get_config_dir() / "tools_config.yaml")


def load_langchain_config() -> Dict[str, Any]:
    """加载LangChain配置"""
    return load_yaml_config(get_config_dir() / "langchain_config.yaml")


def load_langgraph_config() -> Dict[str, Any]:
    """加载LangGraph配置"""
    return load_yaml_config(get_config_dir() / "langgraph_config.yaml")


def load_router_prompt_config() -> Dict[str, Any]:
    """加载Router Prompt配置"""
    return load_yaml_config(get_config_dir() / "router_prompt.yaml")


# 全局配置实例
settings = Settings()

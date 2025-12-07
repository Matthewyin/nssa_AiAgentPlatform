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
from dotenv import dotenv_values


class Settings(BaseSettings):
    """
    环境变量配置

    注意：此类只包含基础设施配置（服务地址、端口、数据库连接等）
    LLM、Agent 等业务逻辑配置请在 config/*.yaml 文件中配置
    """

    # ============================================
    # 外部服务地址
    # ============================================

    # Ollama 服务地址
    ollama_base_url: str = "http://localhost:11434"

    # OpenWebUI 地址
    openwebui_url: str = "http://localhost:3000"

    # ============================================
    # Graph Service 配置
    # ============================================

    graph_service_host: str = "0.0.0.0"
    graph_service_port: int = 30021

    # ============================================
    # 日志配置
    # ============================================

    log_level: str = "INFO"
    log_file: str = "data/logs/app.log"

    # ============================================
    # ChromaDB 配置
    # ============================================

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

    # 构建环境变量字典，支持 .env 文件中的占位符
    env_dict = _build_env_dict()

    # 替换环境变量 ${VAR_NAME}
    template = Template(content)
    content = template.safe_substitute(env_dict)

    # 解析YAML
    config = yaml.safe_load(content)
    return config


def _build_env_dict() -> Dict[str, str]:
    """
    构建环境变量字典，支持 .env 文件中的占位符展开

    优先级：
    1. 系统环境变量（最高优先级）
    2. .env 文件中的值（如果包含占位符，会用系统环境变量展开）

    Returns:
        环境变量字典
    """
    # 1. 从系统环境变量开始
    env_dict = dict(os.environ)

    # 2. 读取 .env 文件
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        # 使用 dotenv_values 读取 .env 文件内容（不修改 os.environ）
        dotenv_dict = dotenv_values(env_path)

        # 3. 处理 .env 文件中的占位符
        for key, value in dotenv_dict.items():
            # 如果系统环境变量中没有这个键，或者值为空，且 .env 中有值
            if value is not None and (key not in env_dict or not env_dict.get(key)):
                if isinstance(value, str) and "${" in value:
                    # 如果值包含占位符，用系统环境变量展开
                    template = Template(value)
                    try:
                        expanded_value = template.safe_substitute(os.environ)
                        env_dict[key] = expanded_value
                    except Exception:
                        # 如果展开失败，使用原值
                        env_dict[key] = value
                else:
                    # 如果值不包含占位符，直接使用
                    env_dict[key] = value

    return env_dict


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


def load_agent_mapping_config() -> Dict[str, Any]:
    """加载Agent映射配置"""
    return load_yaml_config(get_config_dir() / "agent_mapping.yaml")


def load_optimization_config() -> Dict[str, Any]:
    """加载优化配置"""
    return load_yaml_config(get_config_dir() / "optimization_config.yaml")


# 全局配置实例
settings = Settings()

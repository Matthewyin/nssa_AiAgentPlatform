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
import json
import shutil
import os
from string import Template

# 加载工具配置
def load_tools_config() -> Dict[str, Any]:
    """
    加载工具配置，支持环境变量替换

    Returns:
        配置字典
    """
    config_path = Path(__file__).parent.parent.parent / "config" / "tools_config.yaml"

    # 读取 YAML 内容
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 使用环境变量替换 ${VAR_NAME} 占位符
    template = Template(content)
    content = template.safe_substitute(os.environ)

    # 解析 YAML
    return yaml.safe_load(content)


# 创建MCP Server实例
app = Server("network-mcp")

# 缓存配置，减少重复IO
TOOLS_CONFIG = load_tools_config()
NETWORK_TOOLS = TOOLS_CONFIG.get("tools", {}).get("network", {})
TOOL_CONFIG_MAP = {
    cfg.get("name"): cfg for cfg in NETWORK_TOOLS.values() if isinstance(cfg, dict) and cfg.get("name")
}


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
        # Skip tools that don't have a runner configuration (e.g., diagram tools)
        if "runner" not in tool_config:
            continue

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


def _build_netprobe_command(tool_config: Dict[str, Any], arguments: Dict[str, Any]) -> List[str]:
    """根据配置和参数构建 netprobe CLI 命令"""
    runner_cfg = tool_config.get("runner", {}) or {}
    command = runner_cfg.get("command") or "netprobe"

    # 如果 command 是相对路径，转换为绝对路径
    if "/" in command or "\\" in command:
        command_path = Path(command)
        if not command_path.is_absolute():
            # 相对路径，相对于项目根目录
            project_root = Path(__file__).parent.parent.parent
            command_path = project_root / command
            command = str(command_path)

    subcommand = runner_cfg.get("subcommand")
    args_map = runner_cfg.get("args", {}) or {}
    extra_args = runner_cfg.get("extra_args", []) or []
    use_sudo = runner_cfg.get("use_sudo", False)

    cmd: List[str] = []
    if use_sudo:
        cmd.append("sudo")
    cmd.append(command)
    if subcommand:
        cmd.append(subcommand)

    for param_key, flag in args_map.items():
        if param_key not in arguments or arguments[param_key] is None:
            continue
        value = arguments[param_key]

        # 布尔参数：仅在 True 时添加开关
        if isinstance(value, bool):
            if value:
                cmd.append(flag)
            continue

        # 列表参数：重复 flag
        if isinstance(value, list):
            for item in value:
                cmd.extend([flag, str(item)])
            continue

        # 字典参数：序列化为 JSON 字符串传递
        if isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)

        cmd.extend([flag, str(value)])

    if extra_args:
        cmd.extend([str(x) for x in extra_args])

    return cmd


async def _run_netprobe(tool_name: str, tool_config: Dict[str, Any], arguments: Dict[str, Any]) -> str:
    """运行 netprobe CLI 并返回 stdout"""
    timeout = tool_config.get("timeout", 60)
    cmd = _build_netprobe_command(tool_config, arguments)

    # 如果 command 为空，使用默认 netprobe
    if not cmd or not cmd[0]:
        cmd = ["netprobe"] + cmd[1:]

    # 记录命令（隐藏敏感信息的简单处理）
    safe_cmd = " ".join(cmd)
    logger.info(f"调用 netprobe: {safe_cmd}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            return json.dumps(
                {
                    "success": False,
                    "tool": tool_name,
                    "error": f"netprobe 超时({timeout}s)"
                },
                ensure_ascii=False,
                indent=2
            )

        if process.returncode != 0:
            return json.dumps(
                {
                    "success": False,
                    "tool": tool_name,
                    "error": f"netprobe 返回码 {process.returncode}",
                    "stdout": stdout.decode("utf-8", errors="ignore"),
                    "stderr": stderr.decode("utf-8", errors="ignore"),
                },
                ensure_ascii=False,
                indent=2
            )

        return stdout.decode("utf-8", errors="ignore")

    except FileNotFoundError:
        raise
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "tool": tool_name,
                "error": f"netprobe 执行异常: {str(e)}"
            },
            ensure_ascii=False,
            indent=2
        )


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

    tool_config = TOOL_CONFIG_MAP.get(name)
    if not tool_config:
        error_msg = f"未知的工具: {name}"
        logger.error(error_msg)
        return [TextContent(type="text", text=json.dumps({"success": False, "error": error_msg}, ensure_ascii=False))]

    runner_cfg = tool_config.get("runner", {}) or {}
    runner_type = runner_cfg.get("type", "netprobe").lower()

    try:
        if runner_type == "netprobe":
            command = runner_cfg.get("command")
            if command:
                # 检查命令是否存在
                # 1. 如果是路径（包含 / 或 \），检查文件是否存在
                # 2. 否则，在 PATH 中查找
                if "/" in command or "\\" in command:
                    # 相对路径或绝对路径
                    command_path = Path(command)
                    if not command_path.is_absolute():
                        # 相对路径，相对于项目根目录
                        project_root = Path(__file__).parent.parent.parent
                        command_path = project_root / command

                    if not command_path.exists():
                        logger.error(f"netprobe 命令 {command} 未找到（解析为: {command_path}）")
                        raise FileNotFoundError(str(command_path))
                else:
                    # 在 PATH 中查找
                    if shutil.which(command) is None:
                        logger.error(f"netprobe 命令 {command} 未在 PATH 中找到")
                        raise FileNotFoundError(command)

            result = await _run_netprobe(name, tool_config, arguments)
            logger.info(f"工具 {name} 通过 netprobe 执行完成")
            return [TextContent(type="text", text=result)]

        raise ValueError(f"不支持的 runner 类型: {runner_type}")

    except Exception as e:
        error_msg = f"工具 {name} 执行失败: {str(e)}"
        logger.error(error_msg)
        error_json = json.dumps(
            {
                "success": False,
                "tool": name,
                "error": str(e)
            },
            ensure_ascii=False,
            indent=2
        )
        return [TextContent(type="text", text=error_json)]


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

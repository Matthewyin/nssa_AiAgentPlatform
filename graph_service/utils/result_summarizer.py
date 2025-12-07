"""
工具结果摘要提取器
用于智能截断和结构化提取工具执行结果的关键信息
"""
import json
import re
from typing import Dict, Any, Optional
from loguru import logger


# 配置：不同类型的截断长度
TRUNCATION_CONFIG = {
    "default": {
        "max_length": 1500,      # 默认最大长度
        "head_length": 600,      # 保留开头的长度
        "tail_length": 600,      # 保留结尾的长度
    },
    "network": {
        "max_length": 1200,
        "head_length": 400,
        "tail_length": 600,      # 网络工具的统计信息通常在结尾
    },
    "database": {
        "max_length": 2000,
        "head_length": 800,
        "tail_length": 800,
    },
}


def smart_truncate(text: str, tool_type: str = "default") -> str:
    """
    智能截断文本，保留开头和结尾
    
    Args:
        text: 原始文本
        tool_type: 工具类型 (network, database, default)
        
    Returns:
        截断后的文本
    """
    if not text:
        return ""
    
    config = TRUNCATION_CONFIG.get(tool_type, TRUNCATION_CONFIG["default"])
    max_length = config["max_length"]
    head_length = config["head_length"]
    tail_length = config["tail_length"]
    
    if len(text) <= max_length:
        return text
    
    # 智能截断：保留开头和结尾
    head = text[:head_length]
    tail = text[-tail_length:]
    
    truncated_chars = len(text) - head_length - tail_length
    separator = f"\n\n... [已省略 {truncated_chars} 字符] ...\n\n"
    
    return head + separator + tail


def get_tool_type(tool_name: str) -> str:
    """根据工具名称获取工具类型"""
    if tool_name.startswith("network.") or tool_name in ["ping", "traceroute", "mtr", "nslookup"]:
        return "network"
    elif tool_name.startswith("mysql.") or "sql" in tool_name.lower() or "database" in tool_name.lower():
        return "database"
    return "default"


def extract_ping_summary(result: Dict[str, Any]) -> str:
    """提取 ping 结果的摘要"""
    try:
        target = result.get("target", "N/A")
        count = result.get("count", "N/A")
        success = result.get("success", False)
        raw_output = result.get("raw_output", "")
        
        # 提取统计信息
        stats = ""
        if raw_output:
            # 匹配 packet loss
            loss_match = re.search(r'(\d+(?:\.\d+)?%)\s*packet loss', raw_output)
            packet_loss = loss_match.group(1) if loss_match else "N/A"
            
            # 匹配 RTT 统计
            rtt_match = re.search(r'rtt\s+min/avg/max[^=]*=\s*([\d.]+)/([\d.]+)/([\d.]+)', raw_output)
            if rtt_match:
                stats = f"丢包率: {packet_loss}, RTT: min={rtt_match.group(1)}ms, avg={rtt_match.group(2)}ms, max={rtt_match.group(3)}ms"
            else:
                stats = f"丢包率: {packet_loss}"
        
        status = "✅ 成功" if success else "❌ 失败"
        summary = f"[Ping] 目标: {target}, 发包数: {count}, {status}"
        if stats:
            summary += f"\n统计: {stats}"
        
        return summary
    except Exception as e:
        logger.debug(f"提取 ping 摘要失败: {e}")
        return ""


def extract_database_summary(result: Dict[str, Any]) -> str:
    """提取数据库查询结果的摘要"""
    try:
        if isinstance(result, list):
            row_count = len(result)
            if row_count == 0:
                return "[数据库] 查询结果: 0 条记录"
            elif row_count <= 5:
                return f"[数据库] 查询结果: {row_count} 条记录"
            else:
                return f"[数据库] 查询结果: {row_count} 条记录 (仅显示部分)"
        elif isinstance(result, dict):
            if "rows" in result:
                row_count = len(result.get("rows", []))
                return f"[数据库] 查询结果: {row_count} 条记录"
        return "[数据库] 查询完成"
    except Exception as e:
        logger.debug(f"提取数据库摘要失败: {e}")
        return ""


def extract_result_summary(tool_name: str, observation: str) -> Optional[str]:
    """
    从观察结果中提取结构化摘要

    Args:
        tool_name: 工具名称
        observation: 完整的观察结果

    Returns:
        结构化摘要，如果无法提取则返回 None
    """
    try:
        # 尝试解析 JSON 结果
        if "结果:" in observation:
            json_str = observation.split("结果:")[1].strip()
            result = json.loads(json_str)

            # 根据工具类型提取摘要
            if "ping" in tool_name.lower():
                return extract_ping_summary(result)
            elif "mysql" in tool_name.lower() or "sql" in tool_name.lower():
                return extract_database_summary(result)

        return None
    except Exception as e:
        logger.debug(f"提取结果摘要失败: {e}")
        return None


def format_as_markdown_table(data: Any) -> str:
    """
    将数据格式化为 Markdown 表格

    Args:
        data: 数据，可以是列表、字典或字符串

    Returns:
        Markdown 格式的表格或代码块
    """
    try:
        # 如果是字符串，尝试解析为 JSON
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                # 不是 JSON，直接返回代码块
                return f"```\n{data}\n```"

        # 处理列表数据（如数据库查询结果）
        if isinstance(data, list):
            if not data:
                return "*无数据*"

            # 检查是否是元组列表（如 MySQL 返回的原始结果）
            if isinstance(data[0], (tuple, list)):
                # 没有列名，生成默认列名
                num_cols = len(data[0])
                headers = [f"列{i+1}" for i in range(num_cols)]
                rows = data
            elif isinstance(data[0], dict):
                # 字典列表，提取列名
                headers = list(data[0].keys())
                rows = [[str(row.get(h, "")) for h in headers] for row in data]
            else:
                # 简单列表
                return f"```\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"

            # 生成 Markdown 表格
            table = "| " + " | ".join(str(h) for h in headers) + " |\n"
            table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
            for row in rows:
                if isinstance(row, (tuple, list)):
                    table += "| " + " | ".join(str(cell) if cell is not None else "" for cell in row) + " |\n"
                else:
                    table += f"| {row} |\n"

            return table

        # 处理字典数据
        if isinstance(data, dict):
            # 检查是否有 mermaid 流程图
            if "mermaid" in data or "flowchart" in data or "graph" in data:
                mermaid_code = data.get("mermaid") or data.get("flowchart") or data.get("graph")
                if mermaid_code:
                    return f"```mermaid\n{mermaid_code}\n```"

            # 普通字典，格式化为键值对表格
            table = "| 字段 | 值 |\n"
            table += "| --- | --- |\n"
            for key, value in data.items():
                value_str = str(value) if not isinstance(value, (dict, list)) else json.dumps(value, ensure_ascii=False)
                # 截断过长的值
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                table += f"| {key} | {value_str} |\n"
            return table

        # 其他类型，直接转字符串
        return f"```\n{str(data)}\n```"

    except Exception as e:
        logger.debug(f"格式化为 Markdown 表格失败: {e}")
        return f"```\n{str(data)}\n```"


def _try_parse_python_literal(text: str) -> Any:
    """
    尝试解析 Python 字面量（如元组列表）

    Args:
        text: 可能是 Python 字面量的字符串

    Returns:
        解析后的 Python 对象，或 None 如果解析失败
    """
    import ast
    try:
        # 使用 ast.literal_eval 安全地解析 Python 字面量
        return ast.literal_eval(text.strip())
    except (ValueError, SyntaxError):
        return None


def format_full_result(tool_name: str, observation: str) -> str:
    """
    格式化完整的工具执行结果

    Args:
        tool_name: 工具名称
        observation: 完整的观察结果

    Returns:
        格式化后的 Markdown 内容
    """
    try:
        # 尝试从观察结果中提取结果数据
        result_data = None
        result_str = ""

        if "结果:" in observation:
            result_str = observation.split("结果:", 1)[1].strip()
        elif "结果：" in observation:
            result_str = observation.split("结果：", 1)[1].strip()
        else:
            result_str = observation.strip()

        # 尝试多种方式解析
        # 1. 尝试 JSON 解析
        try:
            result_data = json.loads(result_str)
        except json.JSONDecodeError:
            # 2. 尝试 Python 字面量解析（处理元组列表等）
            result_data = _try_parse_python_literal(result_str)

            if result_data is None:
                # 3. 无法解析，使用原始字符串
                result_data = result_str

        # 根据工具类型选择格式化方式
        tool_type = get_tool_type(tool_name)

        if tool_type == "database":
            # 数据库结果使用表格
            return format_as_markdown_table(result_data)
        else:
            # 其他结果，检查是否可以格式化
            if isinstance(result_data, (dict, list)):
                return format_as_markdown_table(result_data)
            else:
                # 纯文本结果
                return f"```\n{result_data}\n```"

    except Exception as e:
        logger.debug(f"格式化完整结果失败: {e}")
        return f"```\n{observation}\n```"


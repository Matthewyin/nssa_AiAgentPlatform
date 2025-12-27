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
        "max_length": 5000,
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


def extract_ping_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """提取 ping 结果的摘要 (返回 display_data 字典)"""
    try:
        target = result.get("target", "N/A")
        count = result.get("count", "N/A")
        success = result.get("success", False)
        raw_output = result.get("raw_output", "")
        
        display_data = {
            "测试状态": "✅ 成功" if success else "❌ 失败",
            "目标主机": target,
            "发包数量": count
        }

        if raw_output and success:
            # 1. 优先尝试从结构化的 summary 字段提取（如果存在）
            tool_summary = result.get("summary")
            if isinstance(tool_summary, dict):
                # 从 Go 工具预计算的 summary 中提取
                loss_line = tool_summary.get("packet_loss_line", "")
                rtt_line = tool_summary.get("rtt_line", "")
                
                # 从 loss_line 提取百分比 "0.0% packet loss"
                loss_match = re.search(r'(\d+(?:\.\d+)?%)\s*packet loss', loss_line)
                if loss_match:
                     display_data["丢包率"] = loss_match.group(1)
                
                # 从 rtt_line 提取 "min/avg/max/stddev = ..."
                # 简化提取，直接取等号后面的部分
                if "=" in rtt_line:
                    display_data["往返时延 (RTT)"] = rtt_line.split("=", 1)[1].strip()

            # 2. 如果没有结构化信息，回退到解析 raw_output
            if "丢包率" not in display_data:
                # 匹配 packet loss
                loss_match = re.search(r'(\d+(?:\.\d+)?%)\s*packet loss', raw_output)
                if loss_match:
                    display_data["丢包率"] = loss_match.group(1)
            
            if "往返时延 (RTT)" not in display_data:
                # 匹配 RTT 统计
                rtt_match = re.search(r'rtt\s+min/avg/max[^=]*=\s*([\d.]+)/([\d.]+)/([\d.]+)', raw_output)
                if rtt_match:
                    display_data["往返时延 (RTT)"] = f"Min/Avg/Max = {rtt_match.group(1)}/{rtt_match.group(2)}/{rtt_match.group(3)} ms"
        
        return display_data
    except Exception as e:
        logger.debug(f"提取 ping 摘要失败: {e}")
        return {}


def extract_nslookup_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """提取 nslookup 结果摘要"""
    try:
        success = result.get("success", False)
        domain = result.get("domain", "N/A")
        record_type = result.get("record_type", "A")
        raw_output = result.get("raw_output", "")

        display_data = {
            "查询状态": "✅ 成功" if success else "❌ 失败",
            "域名": domain,
            "记录类型": record_type
        }

        # 尝试从原始输出提取 IP
        if raw_output and success:
            import re
            ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
            ips = re.findall(ip_pattern, raw_output)
            # 过滤掉DNS服务器的IP
            if len(ips) > 1:
                display_data["解析结果"] = ', '.join(ips[1:])
            elif ips:
                display_data["解析结果"] = ips[0]
        
        return display_data
    except Exception as e:
        logger.debug(f"提取 nslookup 摘要失败: {e}")
        return {}


def extract_traceroute_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """提取 traceroute 结果摘要"""
    try:
        success = result.get("success", False)
        target = result.get("target", "N/A")
        max_hops = result.get("max_hops", 30)
        raw_output = result.get("raw_output", "")
        
        display_data = {
            "追踪状态": "✅ 完成" if success else "❌ 失败",
            "目标": target,
            "最大跳数": max_hops
        }

        if raw_output:
            hop_count = raw_output.count('\n')
            display_data["实际跳数"] = f"约 {hop_count} 跳"
        
        return display_data
    except Exception as e:
        logger.debug(f"提取 traceroute 摘要失败: {e}")
        return {}


def extract_mtr_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """提取 mtr 结果摘要"""
    try:
        success = result.get("success", False)
        target = result.get("target", "N/A")
        count = result.get("count", 10)
        summary = result.get("summary", {})

        display_data = {
            "测试状态": "✅ 完成" if success else "❌ 失败",
            "目标": target,
            "测试包数": count
        }

        if summary:
            hops = summary.get("hops", [])
            total_hops = summary.get("total_hops", 0)
            display_data["总跳数"] = f"{total_hops} 跳"

            if hops:
                has_loss = any(float(hop.get("loss_percent", "0%").rstrip('%')) > 0 for hop in hops)
                display_data["丢包检测"] = "⚠️ 检测到丢包" if has_loss else "✅ 全程无丢包"
        
        return display_data
    except Exception as e:
        logger.debug(f"提取 mtr 摘要失败: {e}")
        return {}



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
                data = extract_ping_summary(result)
                return f"[Ping] {data.get('目标主机', 'N/A')} - {data.get('测试状态', '')}"
            elif "nslookup" in tool_name.lower():
                data = extract_nslookup_summary(result)
                return f"[Nslookup] {data.get('域名', 'N/A')} - {data.get('查询状态', '')}"
            elif "mysql" in tool_name.lower() or "sql" in tool_name.lower():
                return extract_database_summary(result)

        return None
    except Exception as e:
        logger.debug(f"提取结果摘要失败: {e}")
        return None


def enhance_result(tool_name: str, result: Any) -> Dict[str, Any]:
    """
    增强工具结果，注入 summary 和 display_data
    
    Args:
        tool_name: 工具名称
        result: 原始工具结果 (Dict 或其他)
        
    Returns:
        增强后的结果字典，保证包含原始数据以及 'display_data'
    """
    # 如果是字符串，首先尝试解析为 JSON
    if isinstance(result, str):
        try:
            parsed_json = json.loads(result)
            # 如果解析成功，更新 result 为解析后的对象
            result = parsed_json
        except json.JSONDecodeError:
            # 不是 JSON，尝试解析为 Python 字面量 (如 SQL 结果)
            parsed = _try_parse_python_literal(result)
            if isinstance(parsed, list):
                return {
                    "result": parsed,
                    "display_data": {"查询结果": parsed}
                }
    
    # 再次检查：如果是列表（可能是原生返回或刚刚解析出来的）
    if isinstance(result, list):
        return {
            "result": result, 
            "display_data": {"查询结果": result}
        }
    
    # [Fix] 处理嵌套 JSON 字符串的情况 (例如 result["result"] 是一个 JSON 字符串)
    # 这种情况常见于某些工具将复杂对象序列化后放在 result 字段返回
    if isinstance(result, dict) and "result" in result and isinstance(result["result"], str):
        try:
            val = result["result"].strip()
            if val.startswith("{") and val.endswith("}"):
                inner_json = json.loads(val)
                if isinstance(inner_json, dict):
                    # 将解析出的内部 JSON 合并到顶层 result 中
                    result.update(inner_json)
        except:
            pass

    # [Global Fix] 全局清理 raw_output 中的转义字符 (针对 Go 工具常见的 \\n 问题)
    if isinstance(result, dict) and "raw_output" in result and isinstance(result["raw_output"], str):
        result["raw_output"] = result["raw_output"].replace("\\n", "\n").replace("\\t", "\t")

    if not isinstance(result, dict):
        return {"result": result, "display_data": {"Result": str(result)}}

    # 如果已经是 Scheme 3 格式，直接返回
    if "display_data" in result or "summary" in result:
        return result

    # 复制一份结果，避免修改入参
    enhanced = result.copy()
    display_data = {}

    # 根据工具名分发处理
    if tool_name == "network.ping":
        display_data = extract_ping_summary(result)
        enhanced["summary"] = f"[Ping] {display_data.get('目标主机', 'N/A')} - {display_data.get('测试状态', '')}"
    elif tool_name == "network.nslookup":
        display_data = extract_nslookup_summary(result)
        enhanced["summary"] = f"[Nslookup] {display_data.get('域名', 'N/A')} - {display_data.get('查询状态', '')}"
    elif tool_name == "network.traceroute":
        display_data = extract_traceroute_summary(result)
        enhanced["summary"] = f"[Traceroute] {display_data.get('目标', 'N/A')} - {display_data.get('追踪状态', '')}"
    elif tool_name == "network.mtr":
        display_data = extract_mtr_summary(result)
        enhanced["summary"] = f"[MTR] {display_data.get('目标', 'N/A')} - {display_data.get('测试状态', '')}"
    
    if display_data:
        enhanced["display_data"] = display_data
    
    return enhanced


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
                return f"```text\n{data}\n```"

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
        return f"```text\n{str(data)}\n```"

    except Exception as e:
        logger.debug(f"格式化为 Markdown 表格失败: {e}")
        return f"```text\n{str(data)}\n```"


def _try_parse_python_literal(text: str) -> Any:
    """
    尝试解析 Python 字面量（如元组列表）

    Args:
        text: 可能是 Python 字面量的字符串

    Returns:
        解析后的 Python 对象，或 None 如果解析失败
    """
    import ast
    import re
    try:
        # 预处理：将 datetime.date 等对象转换为字符串，使 ast.literal_eval 可以解析
        # 替换 datetime.date(2024, 8, 9) -> '2024-08-09'
        def replace_date(match):
            try:
                args = match.group(1).split(",")
                args = [int(a.strip()) for a in args]
                if len(args) == 3:
                     return f"'{args[0]}-{args[1]:02d}-{args[2]:02d}'"
            except:
                pass
            return match.group(0)

        # 匹配 datetime.date(Y, M, D)
        text = re.sub(r'datetime\.date\((.*?)\)', replace_date, text)
        
        # 替换 datetime.datetime(...) -> 简单的字符串表示
        text = re.sub(r'datetime\.datetime\((.*?)\)', r"'datetime(\1)'", text)

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

        # [Fix] 如果解析出的 result_data 是字典，且包含嵌套的 JSON 字符串 result，尝试解包
        if isinstance(result_data, dict) and "result" in result_data and isinstance(result_data["result"], str):
            try:
                val = result_data["result"].strip()
                if val.startswith("{") and val.endswith("}"):
                    inner = json.loads(val)
                    if isinstance(inner, dict):
                        result_data.update(inner)
            except:
                pass

        # 根据数据类型智能选择格式化方式
        # 1. 列表 -> 渲染为 Markdown 表格 (最适合 SQL 结果)
        if isinstance(result_data, list):
             return format_as_markdown_table(result_data)
        
        # 2. 字典 -> 渲染为 JSON 代码块 (适合查看完整结构)
        elif isinstance(result_data, dict):
            # 过滤掉一些不必要的系统字段，减少噪音
            if "display_data" in result_data:
                del result_data["display_data"] # 完整结果里不需要重复显示 display_data，只看 raw 即可
            
            return f"```json\n{json.dumps(result_data, ensure_ascii=False, indent=2)}\n```"

        # 3. 其他 -> 纯文本代码块
        else:
            return f"```text\n{result_data}\n```"

    except Exception as e:
        logger.debug(f"格式化完整结果失败: {e}")
        return f"```text\n{observation}\n```"


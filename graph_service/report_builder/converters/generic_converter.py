"""
Generic Converter

通用转换器，用于处理没有专用转换器的探测结果。
"""

import json
from typing import Any, Dict

from .base_converter import BaseConverter


class GenericConverter(BaseConverter):
    """通用探测结果转换器"""

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将通用探测结果转换为 Markdown 格式"""
        lines = []

        # 获取基本信息
        tool = result.get("tool", "unknown")
        success = result.get("success", False)
        duration_ms = result.get("duration_ms")
        target = result.get("target", {})

        # 标题
        status_icon = self.get_status_icon(success)
        lines.append(f"## {status_icon} {tool.upper()} 探测结果")
        lines.append("")

        # 目标信息
        target_str = self._format_target(target)
        if target_str:
            lines.append(f"**目标**: {target_str}")

        # 耗时
        if duration_ms is not None:
            lines.append(f"**耗时**: {self.format_duration(duration_ms)}")

        lines.append("")

        # 错误信息
        error = result.get("error")
        if error:
            lines.append("### 错误信息")
            lines.append("")
            lines.append(f"- **错误码**: `{error.get('code', 'UNKNOWN')}`")
            lines.append(f"- **错误信息**: {error.get('message', 'Unknown error')}")
            lines.append("")

        # 数据部分
        data = result.get("data")
        if data:
            lines.append("### 详细数据")
            lines.append("")
            lines.append(self.format_code(json.dumps(data, indent=2, ensure_ascii=False), "json"))
            lines.append("")

        return "\n".join(lines)

    def _format_target(self, target: Dict[str, Any]) -> str:
        """格式化目标信息"""
        parts = []
        if target.get("url"):
            parts.append(target["url"])
        elif target.get("domain"):
            domain = target["domain"]
            port = target.get("port")
            if port:
                parts.append(f"{domain}:{port}")
            else:
                parts.append(domain)
        elif target.get("ip"):
            ip = target["ip"]
            port = target.get("port")
            if port:
                parts.append(f"{ip}:{port}")
            else:
                parts.append(ip)
        return " ".join(parts) if parts else "N/A"

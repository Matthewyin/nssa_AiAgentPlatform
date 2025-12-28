"""
Traceroute Converter

将 Traceroute 探测结果转换为 Markdown 格式。
"""

from typing import Any, Dict

from .base_converter import BaseConverter


class TracerouteConverter(BaseConverter):
    """Traceroute 探测结果转换器"""

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将 Traceroute 探测结果转换为 Markdown 格式"""
        lines = []

        # 获取基本信息
        success = result.get("success", False)
        target = result.get("target", "N/A")
        max_hops = result.get("max_hops", 30)
        tool = result.get("tool", "network.traceroute")
        error = result.get("error")

        # 标题
        status_icon = self.get_status_icon(success)
        lines.append(f"## 🛤️ Traceroute 路径追踪")
        lines.append("")

        # 目标信息
        lines.append(f"**目标**: `{target}`")
        lines.append(f"**最大跳数**: {max_hops}")
        lines.append(f"**状态**: {status_icon} {'成功' if success else '失败'}")
        lines.append("")

        # 错误信息
        if error:
            lines.append("### 错误信息")
            lines.append("")
            lines.append(f"- **错误**: {error}")
            lines.append("")

        # 原始输出
        raw_output = result.get("raw_output")
        if raw_output and isinstance(raw_output, str) and raw_output.strip():
            lines.append("### 路径详情")
            lines.append("")
            lines.append(self.format_code(raw_output.strip(), ""))
            lines.append("")

        return "\n".join(lines)

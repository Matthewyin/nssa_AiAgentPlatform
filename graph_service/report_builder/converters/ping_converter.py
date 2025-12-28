"""
Ping Converter

将 Ping 探测结果转换为 Markdown 格式。
"""

from typing import Any, Dict

from .base_converter import BaseConverter


class PingConverter(BaseConverter):
    """Ping 探测结果转换器"""

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将 Ping 探测结果转换为 Markdown 格式"""
        lines = []

        # 获取基本信息
        success = result.get("success", False)
        target = result.get("target", "N/A")
        count = result.get("count", 4)
        tool = result.get("tool", "network.ping")
        error = result.get("error")

        # 标题
        status_icon = self.get_status_icon(success)
        lines.append(f"## {self.ICON_PING} Ping 连通性测试")
        lines.append("")

        # 目标信息
        lines.append(f"**目标**: `{target}`")
        lines.append(f"**探测次数**: {count}")
        lines.append(f"**状态**: {status_icon} {'成功' if success else '失败'}")
        lines.append("")

        # 错误信息
        if error:
            lines.append("### 错误信息")
            lines.append("")
            lines.append(f"- **错误**: {error}")
            lines.append("")

        # 统计摘要
        summary = result.get("summary", {})
        if summary:
            lines.append("### 统计摘要")
            lines.append("")

            # 丢包信息
            packet_loss_line = summary.get("packet_loss_line")
            if packet_loss_line:
                lines.append(f"- **丢包统计**: {packet_loss_line}")

            # RTT 信息
            rtt_line = summary.get("rtt_line")
            if rtt_line:
                lines.append(f"- **往返时间**: {rtt_line}")

            lines.append("")

        # 原始输出（可折叠）
        raw_output = result.get("raw_output")
        if raw_output and isinstance(raw_output, str) and raw_output.strip():
            lines.append("### 详细输出")
            lines.append("")
            lines.append(self.format_collapsible(
                "点击展开原始输出",
                self.format_code(raw_output.strip(), "")
            ))
            lines.append("")

        return "\n".join(lines)

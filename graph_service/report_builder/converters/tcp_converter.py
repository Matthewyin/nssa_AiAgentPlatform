"""
TCP Converter

将 TCP 连接探测结果转换为 Markdown 格式。
"""

from typing import Any, Dict

from .base_converter import BaseConverter


class TCPConverter(BaseConverter):
    """TCP 连接探测结果转换器"""

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将 TCP 连接探测结果转换为 Markdown 格式"""
        lines = []

        # 获取基本信息
        success = result.get("success", False)
        host = result.get("host", "N/A")
        port = result.get("port", "N/A")
        latency_ms = result.get("latency_ms")
        tool = result.get("tool", "network.tcp")
        error = result.get("error")

        # 标题
        status_icon = self.get_status_icon(success)
        lines.append(f"## {self.ICON_TCP} TCP 连接测试")
        lines.append("")

        # 目标信息
        lines.append(f"**目标**: `{host}:{port}`")
        lines.append(f"**状态**: {status_icon} {'连接成功' if success else '连接失败'}")
        
        if latency_ms is not None:
            lines.append(f"**连接耗时**: {self.format_duration(latency_ms)}")
        
        lines.append("")

        # 错误信息
        if error:
            lines.append("### 错误信息")
            lines.append("")
            lines.append(f"- **错误**: {error}")
            lines.append("")

        # 连接状态表格
        lines.append("### 连接详情")
        lines.append("")
        
        headers = ["属性", "值"]
        rows = [
            ["主机", f"`{host}`"],
            ["端口", str(port)],
            ["状态", "✅ 开放" if success else "❌ 关闭/不可达"],
        ]
        if latency_ms is not None:
            rows.append(["延迟", self.format_duration(latency_ms)])
        
        lines.append(self.format_table(headers, rows))
        lines.append("")

        return "\n".join(lines)

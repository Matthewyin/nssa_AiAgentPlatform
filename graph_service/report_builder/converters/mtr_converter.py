"""
MTR Converter

MTR 探测结果的 Markdown 转换器。
"""

from typing import Any, Dict, List

from .base_converter import BaseConverter


class MTRConverter(BaseConverter):
    """MTR 探测结果转换器"""

    HIGH_LOSS_THRESHOLD = 20.0

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将 MTR 探测结果转换为 Markdown 格式"""
        lines = []

        success = result.get("success", False)
        target = result.get("target", {})
        data = result.get("data", {})
        error = result.get("error")

        status_icon = self.get_status_icon(success)
        lines.append(f"## {self.ICON_MTR} 网络路径追踪 (MTR) {status_icon}")
        lines.append("")

        target_ip = target.get("ip") or target.get("domain", "N/A")
        lines.append(f"**目标**: `{target_ip}`")

        summary = data.get("summary", {})
        if summary:
            total_hops = summary.get("total_hops")
            avg_latency = summary.get("avg_latency_ms")
            overall_loss = summary.get("overall_loss_percent")
            target_reached = summary.get("target_reached", True)

            if total_hops is not None:
                lines.append(f"**总跳数**: {total_hops}")
            if avg_latency is not None:
                lines.append(f"**平均延迟**: {self.format_duration(avg_latency)}")
            if overall_loss is not None:
                loss_icon = self.ICON_SUCCESS if overall_loss < 5 else (
                    self.ICON_WARNING if overall_loss < 20 else self.ICON_FAILURE
                )
                lines.append(f"**整体丢包**: {overall_loss:.1f}% {loss_icon}")
            if not target_reached:
                lines.append(f"**状态**: 目标未到达 {self.ICON_FAILURE}")

        lines.append("")

        if not success and error:
            lines.append("### 错误信息")
            lines.append("")
            error_code = error.get("code", "UNKNOWN")
            error_msg = error.get("message", "Unknown error")
            lines.append(f"- **错误码**: `{error_code}`")
            lines.append(f"- **错误信息**: {error_msg}")
            lines.append("")
            lines.append(self._get_error_suggestion(error_code))
            return "\n".join(lines)

        hops = data.get("hops", [])
        if hops:
            lines.append(self._format_hops(hops, target_ip))
            lines.append("")

        issues = self._analyze_issues(hops, summary)
        if issues:
            lines.append(self._format_issues(issues))

        return "\n".join(lines)

    def _format_hops(self, hops: List[Dict[str, Any]], target_ip: str) -> str:
        """格式化跳点表格"""
        lines = ["### 路径详情", ""]

        headers = ["跳数", "IP", "主机名", "丢包率", "延迟 (avg)", "状态"]
        rows = []

        for hop in hops:
            hop_num = hop.get("hop_number", "?")
            ip = hop.get("ip", "*")
            hostname = hop.get("hostname", "")
            loss_percent = hop.get("loss_percent", 0)
            is_timeout = hop.get("is_timeout", False)

            latency = hop.get("latency_ms", {})
            if isinstance(latency, dict):
                avg_latency = latency.get("avg")
            else:
                avg_latency = latency

            if is_timeout or ip == "*":
                ip_str = "\\*"
            else:
                ip_str = f"`{ip}`"

            hostname_str = hostname if hostname and hostname != ip else "-"
            if len(hostname_str) > 20:
                hostname_str = hostname_str[:17] + "..."

            if is_timeout:
                loss_str = "100%"
            else:
                loss_str = f"{loss_percent:.0f}%"

            if is_timeout or avg_latency is None:
                latency_str = "-"
            else:
                latency_str = self.format_duration(avg_latency)

            status = self._get_hop_status(hop, target_ip)

            rows.append([str(hop_num), ip_str, hostname_str, loss_str, latency_str, status])

        lines.append(self.format_table(headers, rows))
        return "\n".join(lines)

    def _get_hop_status(self, hop: Dict[str, Any], target_ip: str) -> str:
        """获取跳点状态"""
        ip = hop.get("ip", "")
        is_timeout = hop.get("is_timeout", False)
        is_high_loss = hop.get("is_high_loss", False)
        loss_percent = hop.get("loss_percent", 0)

        is_target = ip == target_ip

        if is_timeout:
            return f"{self.ICON_TIMEOUT} 超时"
        elif is_high_loss or loss_percent >= self.HIGH_LOSS_THRESHOLD:
            return f"{self.ICON_WARNING} 高丢包"
        elif is_target:
            return f"{self.ICON_SUCCESS} 目标"
        else:
            return self.ICON_SUCCESS

    def _analyze_issues(
        self, hops: List[Dict[str, Any]], summary: Dict[str, Any]
    ) -> List[str]:
        """分析路径问题"""
        issues = []

        high_loss_hops = []
        for hop in hops:
            loss = hop.get("loss_percent", 0)
            is_high_loss = hop.get("is_high_loss", False)
            if is_high_loss or loss >= self.HIGH_LOSS_THRESHOLD:
                hop_num = hop.get("hop_number", "?")
                ip = hop.get("ip", "*")
                high_loss_hops.append((hop_num, ip, loss))

        if high_loss_hops:
            for hop_num, ip, loss in high_loss_hops:
                issues.append(
                    f"第 {hop_num} 跳 (`{ip}`) 丢包率较高 ({loss:.0f}%)，可能存在网络拥塞"
                )

        timeout_count = 0
        for hop in hops:
            if hop.get("is_timeout", False):
                timeout_count += 1
            else:
                timeout_count = 0

            if timeout_count >= 3:
                issues.append("存在连续多跳超时，可能是防火墙阻止 ICMP 或路由问题")
                break

        if summary.get("target_reached") is False:
            issues.append("未能到达目标，请检查目标地址是否正确或网络是否可达")

        overall_loss = summary.get("overall_loss_percent", 0)
        if overall_loss >= 10:
            issues.append(f"整体丢包率较高 ({overall_loss:.1f}%)，网络质量可能不稳定")

        return issues

    def _format_issues(self, issues: List[str]) -> str:
        """格式化问题分析"""
        lines = [f"### {self.ICON_WARNING} 问题分析", ""]

        for issue in issues:
            lines.append(f"- {self.ICON_WARNING} {issue}")

        return "\n".join(lines)

    def _get_error_suggestion(self, error_code: str) -> str:
        """根据错误码返回建议"""
        suggestions = {
            "COMMAND_NOT_FOUND": "> MTR 命令未找到，请确保系统已安装 mtr 工具。",
            "PERMISSION_DENIED": "> 权限不足，MTR 可能需要 root 权限运行。",
            "TCP_TIMEOUT": "> 连接超时，请检查目标地址是否正确。",
        }
        return suggestions.get(error_code, "> 请检查网络连接和目标地址。")

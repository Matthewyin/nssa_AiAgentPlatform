"""
Diagnose Converter

综合诊断结果的 Markdown 转换器。
"""

import json
from typing import Any, Dict, List

from .base_converter import BaseConverter


class DiagnoseConverter(BaseConverter):
    """综合诊断结果转换器"""

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将综合诊断结果转换为 Markdown 格式"""
        lines = []

        success = result.get("success", False)
        data = result.get("data", {})
        error = result.get("error")
        timestamp = result.get("timestamp", "")

        status_icon = self.get_status_icon(success)
        lines.append(f"## {self.ICON_DIAGNOSE} 网络诊断报告 {status_icon}")
        lines.append("")

        # 目标信息
        target = data.get("target", {})
        target_input = target.get("input") or target.get("domain", "N/A")
        lines.append(f"**目标**: `{target_input}`")

        if timestamp:
            ts_display = timestamp.split("T")[0] if "T" in timestamp else timestamp
            lines.append(f"**诊断时间**: {ts_display}")

        # 总耗时
        summary = data.get("summary", {})
        total_duration = summary.get("total_duration_ms")
        if total_duration:
            lines.append(f"**总耗时**: {self.format_duration(total_duration)}")

        lines.append("")

        # 错误处理
        if not success and error:
            lines.append("### 诊断失败")
            lines.append("")
            error_code = error.get("code", "UNKNOWN")
            error_msg = error.get("message", "Unknown error")
            lines.append(f"- **错误码**: `{error_code}`")
            lines.append(f"- **错误信息**: {error_msg}")
            return "\n".join(lines)

        # 诊断摘要
        lines.append(self._format_summary(data))
        lines.append("")

        # 建议
        recommendations = data.get("recommendations", [])
        if recommendations:
            lines.append(self._format_recommendations(recommendations))
            lines.append("")

        # 折叠详情
        lines.append(self._format_details(data))

        return "\n".join(lines)

    def _format_summary(self, data: Dict[str, Any]) -> str:
        """格式化诊断摘要"""
        lines = ["### 诊断摘要", ""]

        headers = ["项目", "状态", "详情"]
        rows = []

        # DNS 结果
        dns = data.get("dns")
        if dns:
            dns_success = dns.get("success", True)
            if dns_success:
                resolved_ips = dns.get("resolved_ips", [])
                resolution_time = dns.get("resolution_time_ms")
                detail = f"{self.format_duration(resolution_time)}"
                if resolved_ips:
                    detail += f", 解析到 `{resolved_ips[0]}`"
                rows.append(["DNS 解析", f"{self.ICON_SUCCESS} 成功", detail])
            else:
                error = dns.get("error", {})
                rows.append(["DNS 解析", f"{self.ICON_FAILURE} 失败", error.get("message", "解析失败")])

        # TCP 结果
        tcp_list = data.get("tcp", [])
        if tcp_list:
            tcp_success_count = sum(1 for t in tcp_list if t.get("success", False))
            total_tcp = len(tcp_list)
            if tcp_success_count == total_tcp:
                fastest = min(tcp_list, key=lambda x: x.get("connect_time_ms", float("inf")))
                detail = f"{self.format_duration(fastest.get('connect_time_ms'))}"
                rows.append(["TCP 连接", f"{self.ICON_SUCCESS} 成功", detail])
            elif tcp_success_count > 0:
                rows.append(["TCP 连接", f"{self.ICON_WARNING} 部分成功", f"{tcp_success_count}/{total_tcp} 成功"])
            else:
                rows.append(["TCP 连接", f"{self.ICON_FAILURE} 失败", "所有连接失败"])

        # TLS 结果
        tls = data.get("tls")
        if tls:
            tls_success = tls.get("success", True)
            if tls_success:
                connection = tls.get("connection", {})
                certificate = tls.get("certificate", {})
                timing = tls.get("timing", {})
                protocol = connection.get("protocol", "TLS")
                handshake_ms = timing.get("tls_handshake_ms")
                detail = f"{self.format_duration(handshake_ms)}, {protocol}"
                rows.append(["TLS 握手", f"{self.ICON_SUCCESS} 成功", detail])

                # 证书状态
                days_remaining = certificate.get("days_remaining")
                is_expired = certificate.get("is_expired", False)
                is_expiring_soon = certificate.get("is_expiring_soon", False)
                if is_expired:
                    rows.append(["证书状态", f"{self.ICON_FAILURE} 已过期", "证书已过期"])
                elif is_expiring_soon:
                    rows.append(["证书状态", f"{self.ICON_WARNING} 即将过期", f"剩余 {days_remaining} 天"])
                elif days_remaining:
                    rows.append(["证书状态", f"{self.ICON_SUCCESS} 有效", f"剩余 {days_remaining} 天"])
            else:
                error = tls.get("error", {})
                rows.append(["TLS 握手", f"{self.ICON_FAILURE} 失败", error.get("message", "握手失败")])

        # HTTP 结果
        http = data.get("http")
        if http:
            http_success = http.get("success", True)
            if http_success:
                response = http.get("response", {})
                timing = http.get("timing", {})
                status_code = response.get("status_code")
                total_ms = timing.get("total_ms")
                detail = f"{self.format_duration(total_ms)}"
                status_icon = self.ICON_SUCCESS if 200 <= status_code < 400 else self.ICON_WARNING
                rows.append(["HTTP 响应", f"{status_icon} {status_code}", detail])
            else:
                error = http.get("error", {})
                rows.append(["HTTP 响应", f"{self.ICON_FAILURE} 失败", error.get("message", "请求失败")])

        # 整体状态
        summary = data.get("summary", {})
        overall_status = summary.get("overall_status", "unknown")
        status_map = {
            "success": (self.ICON_SUCCESS, "正常"),
            "partial": (self.ICON_WARNING, "部分异常"),
            "failed": (self.ICON_FAILURE, "失败"),
        }
        icon, text = status_map.get(overall_status, ("", overall_status))

        if rows:
            lines.append(self.format_table(headers, rows))

        return "\n".join(lines)

    def _format_recommendations(self, recommendations: List[str]) -> str:
        """格式化建议"""
        lines = ["### 建议", ""]

        for rec in recommendations:
            if rec.startswith("✅") or rec.startswith("⭐"):
                lines.append(f"- {rec}")
            else:
                lines.append(f"- {self.ICON_INFO} {rec}")

        return "\n".join(lines)

    def _format_details(self, data: Dict[str, Any]) -> str:
        """格式化折叠详情"""
        lines = []

        # DNS 详情
        dns = data.get("dns")
        if dns:
            dns_detail = self._format_dns_detail(dns)
            lines.append(self.format_collapsible("DNS 解析详情", dns_detail))
            lines.append("")

        # TLS 详情
        tls = data.get("tls")
        if tls:
            tls_detail = self._format_tls_detail(tls)
            lines.append(self.format_collapsible("TLS 证书详情", tls_detail))
            lines.append("")

        # HTTP 详情
        http = data.get("http")
        if http:
            http_detail = self._format_http_detail(http)
            lines.append(self.format_collapsible("HTTP 响应详情", http_detail))
            lines.append("")

        # MTR 详情
        mtr = data.get("mtr")
        if mtr:
            mtr_detail = self._format_mtr_detail(mtr)
            lines.append(self.format_collapsible("MTR 路径详情", mtr_detail))

        return "\n".join(lines)

    def _format_dns_detail(self, dns: Dict[str, Any]) -> str:
        """格式化 DNS 详情"""
        lines = []

        dns_server = dns.get("dns_server", "N/A")
        lines.append(f"**DNS 服务器**: `{dns_server}`")

        resolution_chain = dns.get("resolution_chain", [])
        if resolution_chain:
            lines.append("")
            lines.append("**解析链路**:")
            for i, record in enumerate(resolution_chain, 1):
                rtype = record.get("type", "?")
                value = record.get("value", "N/A")
                ttl = record.get("ttl", "N/A")
                lines.append(f"  {i}. {rtype}: `{value}` (TTL: {ttl})")

        resolved_ips = dns.get("resolved_ips", [])
        if resolved_ips:
            lines.append("")
            lines.append(f"**解析 IP**: {', '.join(f'`{ip}`' for ip in resolved_ips)}")

        return "\n".join(lines)

    def _format_tls_detail(self, tls: Dict[str, Any]) -> str:
        """格式化 TLS 详情"""
        lines = []

        connection = tls.get("connection", {})
        certificate = tls.get("certificate", {})

        if connection:
            lines.append(f"**协议**: `{connection.get('protocol', 'N/A')}`")
            lines.append(f"**加密套件**: `{connection.get('cipher_suite', 'N/A')}`")
            lines.append("")

        if certificate:
            subject = certificate.get("subject", {})
            issuer = certificate.get("issuer", {})
            lines.append(f"**证书主题**: `{subject.get('cn', 'N/A')}`")
            lines.append(f"**颁发者**: `{issuer.get('cn', 'N/A')}`")
            lines.append(f"**有效期**: {certificate.get('not_before', 'N/A')} ~ {certificate.get('not_after', 'N/A')}")

            fingerprint = certificate.get("fingerprint_sha256", "")
            if fingerprint:
                lines.append(f"**指纹**: `{fingerprint[:32]}...`")

        return "\n".join(lines)

    def _format_http_detail(self, http: Dict[str, Any]) -> str:
        """格式化 HTTP 详情"""
        lines = []

        response = http.get("response", {})
        timing = http.get("timing", {})

        if response:
            lines.append(f"**状态码**: {response.get('status_code', 'N/A')}")
            lines.append(f"**Content-Type**: `{response.get('content_type', 'N/A')}`")
            lines.append(f"**Content-Length**: {response.get('content_length', 'N/A')} bytes")

            server = response.get("server")
            if server:
                lines.append(f"**Server**: `{server}`")

        if timing:
            lines.append("")
            lines.append("**时间分解**:")
            for key, label in [
                ("dns_lookup_ms", "DNS"),
                ("tcp_connect_ms", "TCP"),
                ("tls_handshake_ms", "TLS"),
                ("waiting_ms", "等待"),
                ("content_transfer_ms", "传输"),
            ]:
                value = timing.get(key)
                if value is not None:
                    lines.append(f"  - {label}: {self.format_duration(value)}")

        return "\n".join(lines)

    def _format_mtr_detail(self, mtr: Dict[str, Any]) -> str:
        """格式化 MTR 详情"""
        lines = []

        summary = mtr.get("summary", {})
        if summary:
            lines.append(f"**总跳数**: {summary.get('total_hops', 'N/A')}")
            lines.append(f"**平均延迟**: {self.format_duration(summary.get('avg_latency_ms'))}")
            lines.append(f"**整体丢包**: {summary.get('overall_loss_percent', 0):.1f}%")

        hops = mtr.get("hops", [])
        if hops:
            lines.append("")
            lines.append("**路径**:")
            for hop in hops[:10]:  # 只显示前 10 跳
                hop_num = hop.get("hop_number", "?")
                ip = hop.get("ip", "*")
                loss = hop.get("loss_percent", 0)
                latency = hop.get("latency_ms", {})
                avg = latency.get("avg") if isinstance(latency, dict) else latency
                avg_str = self.format_duration(avg) if avg else "-"
                lines.append(f"  {hop_num}. `{ip}` - {loss:.0f}% loss, {avg_str}")

            if len(hops) > 10:
                lines.append(f"  ... 还有 {len(hops) - 10} 跳")

        return "\n".join(lines)

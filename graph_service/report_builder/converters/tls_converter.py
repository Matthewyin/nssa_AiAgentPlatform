"""
TLS Converter

TLS 探测结果的 Markdown 转换器。

转换格式示例：
## 🔒 TLS 证书信息

### 证书详情
| 字段 | 值 |
|------|-----|
| 域名 (CN) | *.example.com |
| 颁发者 | DigiCert Inc |
| 有效期 | 2024-01-01 ~ 2025-01-01 |
| 剩余天数 | 180 天 ✅ |
| 指纹 (SHA256) | `abc123...` |

### 连接信息
- **协议**: TLSv1.3
- **加密套件**: TLS_AES_256_GCM_SHA384
- **双向认证**: 否

### ⏱️ 时间分解
| 阶段 | 耗时 |
|------|------|
| TCP 连接 | 35.2ms |
| TLS 握手 | 78.5ms |
| **总计** | **113.7ms** |
"""

from typing import Any, Dict, List

from .base_converter import BaseConverter


class TLSConverter(BaseConverter):
    """TLS 探测结果转换器"""

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将 TLS 探测结果转换为 Markdown 格式"""
        lines = []

        # 获取基本信息
        success = result.get("success", False)
        target = result.get("target", {})
        data = result.get("data", {})
        error = result.get("error")

        # 标题
        status_icon = self.get_status_icon(success)
        lines.append(f"## {self.ICON_TLS} TLS 证书信息 {status_icon}")
        lines.append("")

        # 目标信息
        target_str = self._format_target(target)
        if target_str:
            lines.append(f"**目标**: {target_str}")
            lines.append("")

        # 错误处理
        if not success and error:
            lines.append("### ❌ TLS 探测失败")
            lines.append("")
            error_code = error.get("code", "UNKNOWN")
            error_msg = error.get("message", "Unknown error")
            lines.append(f"- **错误码**: `{error_code}`")
            lines.append(f"- **错误信息**: {error_msg}")
            lines.append("")
            lines.append(self._get_error_suggestion(error_code))
            return "\n".join(lines)

        # 证书详情
        certificate = data.get("certificate", {})
        if certificate:
            lines.append(self._format_certificate(certificate))
            lines.append("")

        # 连接信息
        connection = data.get("connection", {})
        if connection:
            lines.append(self._format_connection(connection))
            lines.append("")

        # 时间分解
        timing = data.get("timing", {})
        if timing:
            lines.append(self._format_timing(timing))
            lines.append("")

        # 安全警告
        security = data.get("security", {})
        warnings = security.get("warnings", [])
        if warnings:
            lines.append(self._format_warnings(warnings))

        return "\n".join(lines)

    def _format_target(self, target: Dict[str, Any]) -> str:
        """格式化目标信息"""
        domain = target.get("domain", "")
        ip = target.get("ip", "")
        port = target.get("port", 443)

        if domain:
            return f"`{domain}:{port}`"
        elif ip:
            return f"`{ip}:{port}`"
        return ""

    def _format_certificate(self, cert: Dict[str, Any]) -> str:
        """格式化证书详情"""
        lines = ["### 📜 证书详情", ""]

        # 构建表格数据
        rows = []

        # 主题信息
        subject = cert.get("subject", {})
        cn = subject.get("cn", "N/A")
        rows.append(["域名 (CN)", f"`{cn}`"])

        org = subject.get("o")
        if org:
            rows.append(["组织 (O)", org])

        # 颁发者
        issuer = cert.get("issuer", {})
        issuer_cn = issuer.get("cn", "N/A")
        issuer_o = issuer.get("o", "")
        issuer_str = issuer_cn
        if issuer_o:
            issuer_str = f"{issuer_cn} ({issuer_o})"
        rows.append(["颁发者", issuer_str])

        # 有效期
        not_before = cert.get("not_before", "N/A")
        not_after = cert.get("not_after", "N/A")
        # 简化日期格式
        if isinstance(not_before, str) and "T" in not_before:
            not_before = not_before.split("T")[0]
        if isinstance(not_after, str) and "T" in not_after:
            not_after = not_after.split("T")[0]
        rows.append(["有效期", f"{not_before} ~ {not_after}"])

        # 剩余天数
        days_remaining = cert.get("days_remaining")
        is_expired = cert.get("is_expired", False)
        is_expiring_soon = cert.get("is_expiring_soon", False)

        if days_remaining is not None:
            if is_expired:
                days_str = f"**已过期** {self.ICON_FAILURE}"
            elif is_expiring_soon:
                days_str = f"{days_remaining} 天 {self.ICON_WARNING} 即将过期"
            else:
                days_str = f"{days_remaining} 天 {self.ICON_SUCCESS}"
            rows.append(["剩余天数", days_str])

        # 指纹
        fingerprint = cert.get("fingerprint_sha256", "")
        if fingerprint:
            # 截断显示
            fp_short = fingerprint[:16] + "..." if len(fingerprint) > 16 else fingerprint
            rows.append(["指纹 (SHA256)", f"`{fp_short}`"])

        # DNS 名称
        dns_names = cert.get("dns_names", [])
        if dns_names:
            if len(dns_names) <= 3:
                dns_str = ", ".join(f"`{n}`" for n in dns_names)
            else:
                dns_str = ", ".join(f"`{n}`" for n in dns_names[:3]) + f" (+{len(dns_names) - 3} more)"
            rows.append(["备用名称", dns_str])

        # 密钥信息
        key_algo = cert.get("key_algorithm")
        key_size = cert.get("key_size")
        if key_algo:
            key_str = key_algo
            if key_size:
                key_str = f"{key_algo} {key_size} bits"
            rows.append(["密钥算法", key_str])

        lines.append(self.format_table(["字段", "值"], rows))
        return "\n".join(lines)

    def _format_connection(self, conn: Dict[str, Any]) -> str:
        """格式化连接信息"""
        lines = ["### 🔗 连接信息", ""]

        protocol = conn.get("protocol", "N/A")
        cipher_suite = conn.get("cipher_suite", "N/A")
        is_mtls = conn.get("is_mutual_tls", False)
        alpn = conn.get("alpn")
        server_name = conn.get("server_name")

        lines.append(f"- **协议**: `{protocol}`")
        lines.append(f"- **加密套件**: `{cipher_suite}`")
        lines.append(f"- **双向认证 (mTLS)**: {'是' if is_mtls else '否'}")

        if alpn:
            lines.append(f"- **ALPN**: `{alpn}`")
        if server_name:
            lines.append(f"- **SNI**: `{server_name}`")

        return "\n".join(lines)

    def _format_timing(self, timing: Dict[str, Any]) -> str:
        """格式化时间分解"""
        lines = ["### ⏱️ 时间分解", ""]

        rows = []

        tcp_ms = timing.get("tcp_connect_ms")
        tls_ms = timing.get("tls_handshake_ms")
        total_ms = timing.get("total_ms")

        if tcp_ms is not None:
            rows.append(["TCP 连接", self.format_duration(tcp_ms)])
        if tls_ms is not None:
            rows.append(["TLS 握手", self.format_duration(tls_ms)])
        if total_ms is not None:
            rows.append(["**总计**", f"**{self.format_duration(total_ms)}**"])

        if rows:
            lines.append(self.format_table(["阶段", "耗时"], rows))

        return "\n".join(lines)

    def _format_warnings(self, warnings: List[str]) -> str:
        """格式化安全警告"""
        lines = [f"### {self.ICON_WARNING} 安全警告", ""]

        for warning in warnings:
            lines.append(f"- {self.ICON_WARNING} {warning}")

        return "\n".join(lines)

    def _get_error_suggestion(self, error_code: str) -> str:
        """根据错误码返回建议"""
        suggestions = {
            "TLS_HANDSHAKE_FAILED": "> 💡 **建议**: TLS 握手失败，请检查目标是否支持 TLS，或证书配置是否正确。",
            "TLS_CERT_EXPIRED": "> 💡 **建议**: 证书已过期，请联系服务管理员更新证书。",
            "TLS_CERT_INVALID": "> 💡 **建议**: 证书无效，可能是自签名证书或证书链不完整。",
            "TCP_TIMEOUT": "> 💡 **建议**: TCP 连接超时，请检查目标地址和端口是否正确。",
            "TCP_REFUSED": "> 💡 **建议**: 连接被拒绝，请检查目标端口是否开放。",
        }
        return suggestions.get(error_code, "> 💡 **建议**: 请检查网络连接和目标服务状态。")

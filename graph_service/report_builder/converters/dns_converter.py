"""
DNS Converter

DNS 解析结果的 Markdown 转换器。

转换格式示例：
## 🔍 DNS 解析结果

**目标域名**: example.com
**DNS 服务器**: 8.8.8.8
**解析耗时**: 45.2ms

### 解析链路
| 步骤 | 类型 | 值 | TTL |
|------|------|-----|-----|
| 1 | CNAME | cdn.example.com | 300 |
| 2 | A | 1.2.3.4 | 60 |

**最终 IP**: 1.2.3.4
"""

from typing import Any, Dict, List

from .base_converter import BaseConverter


class DNSConverter(BaseConverter):
    """DNS 解析结果转换器"""

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将 DNS 解析结果转换为 Markdown 格式"""
        lines = []

        # 获取基本信息
        success = result.get("success", False)
        target = result.get("target", {})
        data = result.get("data", {})
        error = result.get("error")
        duration_ms = result.get("duration_ms")

        # 标题
        status_icon = self.get_status_icon(success)
        lines.append(f"## {self.ICON_DNS} DNS 解析结果 {status_icon}")
        lines.append("")

        # 目标域名
        domain = target.get("domain") or data.get("query_name", "N/A")
        lines.append(f"**目标域名**: {domain}")

        # DNS 服务器
        dns_server = data.get("dns_server", "N/A")
        lines.append(f"**DNS 服务器**: {dns_server}")

        # 解析耗时
        resolution_time = data.get("resolution_time_ms", duration_ms)
        if resolution_time is not None:
            lines.append(f"**解析耗时**: {self.format_duration(resolution_time)}")

        # 查询类型
        query_type = data.get("query_type")
        if query_type:
            lines.append(f"**查询类型**: {query_type}")

        lines.append("")

        # 错误处理
        if not success and error:
            lines.append("### ❌ 解析失败")
            lines.append("")
            error_code = error.get("code", "UNKNOWN")
            error_msg = error.get("message", "Unknown error")
            lines.append(f"- **错误码**: `{error_code}`")
            lines.append(f"- **错误信息**: {error_msg}")
            lines.append("")
            lines.append(self._get_error_suggestion(error_code))
            return "\n".join(lines)

        # 解析链路
        resolution_chain = data.get("resolution_chain", [])
        if resolution_chain:
            lines.append("### 解析链路")
            lines.append("")
            lines.append(self._format_resolution_chain(resolution_chain))
            lines.append("")

        # 最终 IP
        resolved_ips = data.get("resolved_ips", [])
        if resolved_ips:
            if len(resolved_ips) == 1:
                lines.append(f"**最终 IP**: `{resolved_ips[0]}`")
            else:
                lines.append(f"**最终 IP**: {', '.join(f'`{ip}`' for ip in resolved_ips)}")
            lines.append("")

        # 统计信息
        if resolution_chain:
            lines.append(self._format_statistics(resolution_chain, resolved_ips))

        return "\n".join(lines)

    def _format_resolution_chain(self, chain: List[Dict[str, Any]]) -> str:
        """格式化解析链路为表格"""
        headers = ["步骤", "类型", "值", "TTL"]
        rows = []

        for i, record in enumerate(chain, 1):
            record_type = record.get("type", "?")
            value = record.get("value", "N/A")
            ttl = record.get("ttl", "N/A")

            # 格式化 TTL
            if isinstance(ttl, (int, float)):
                ttl_str = self._format_ttl(ttl)
            else:
                ttl_str = str(ttl)

            # 类型图标
            type_icon = self._get_record_type_icon(record_type)

            rows.append([str(i), f"{type_icon} {record_type}", f"`{value}`", ttl_str])

        return self.format_table(headers, rows)

    def _get_record_type_icon(self, record_type: str) -> str:
        """获取记录类型图标"""
        icons = {
            "A": "🅰️",
            "AAAA": "6️⃣",
            "CNAME": "🔗",
            "MX": "📧",
            "TXT": "📝",
            "NS": "🏷️",
            "SOA": "📋",
            "PTR": "↩️",
        }
        return icons.get(record_type.upper(), "📄")

    def _format_ttl(self, ttl: int) -> str:
        """格式化 TTL 显示"""
        if ttl < 60:
            return f"{ttl}s"
        elif ttl < 3600:
            return f"{ttl // 60}m {ttl % 60}s" if ttl % 60 else f"{ttl // 60}m"
        else:
            hours = ttl // 3600
            minutes = (ttl % 3600) // 60
            if minutes:
                return f"{hours}h {minutes}m"
            return f"{hours}h"

    def _format_statistics(
        self, chain: List[Dict[str, Any]], resolved_ips: List[str]
    ) -> str:
        """格式化统计信息"""
        lines = ["### 📊 统计信息", ""]

        # CNAME 跳转次数
        cname_count = sum(1 for r in chain if r.get("type", "").upper() == "CNAME")
        if cname_count > 0:
            lines.append(f"- **CNAME 跳转**: {cname_count} 次")

        # A 记录数量
        a_count = sum(1 for r in chain if r.get("type", "").upper() in ("A", "AAAA"))
        if a_count > 0:
            lines.append(f"- **地址记录**: {a_count} 条")

        # 解析到的 IP 数量
        if resolved_ips:
            lines.append(f"- **解析 IP 数**: {len(resolved_ips)} 个")

        # 最小 TTL
        ttls = [r.get("ttl") for r in chain if isinstance(r.get("ttl"), (int, float))]
        if ttls:
            min_ttl = min(ttls)
            lines.append(f"- **最小 TTL**: {self._format_ttl(int(min_ttl))}")

        return "\n".join(lines)

    def _get_error_suggestion(self, error_code: str) -> str:
        """根据错误码返回建议"""
        suggestions = {
            "DNS_TIMEOUT": "> 💡 **建议**: DNS 解析超时，请检查 DNS 服务器是否可达，或尝试更换 DNS 服务器。",
            "DNS_NXDOMAIN": "> 💡 **建议**: 域名不存在，请检查域名拼写是否正确。",
            "DNS_SERVFAIL": "> 💡 **建议**: DNS 服务器错误，请尝试更换 DNS 服务器或稍后重试。",
            "DNS_REFUSED": "> 💡 **建议**: DNS 查询被拒绝，请检查 DNS 服务器配置。",
        }
        return suggestions.get(error_code, "> 💡 **建议**: 请检查网络连接和 DNS 配置。")

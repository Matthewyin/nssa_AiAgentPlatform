"""
HTTP Converter

HTTP 探测结果的 Markdown 转换器。

转换格式示例：
## 🌐 HTTP 探测结果

**请求**: GET https://example.com/api
**状态**: 200 OK ✅

### 响应信息
| 字段 | 值 |
|------|-----|
| Content-Type | application/json |
| Content-Length | 1234 bytes |
| Server | nginx/1.18.0 |
| 压缩 | gzip |

### ⏱️ 时间分解
DNS 解析  ██░░░░░░░░░░░░░░░░░░  12.3ms (8%)
TCP 连接  ████░░░░░░░░░░░░░░░░  35.2ms (23%)
TLS 握手  ████████░░░░░░░░░░░░  78.5ms (51%)
等待响应  ██░░░░░░░░░░░░░░░░░░  15.6ms (10%)
内容传输  ██░░░░░░░░░░░░░░░░░░  12.1ms (8%)
──────────────────────────────────
总计: 153.7ms
"""

from typing import Any, Dict, List

from .base_converter import BaseConverter


class HTTPConverter(BaseConverter):
    """HTTP 探测结果转换器"""

    # 时间分解阶段配置
    TIMING_PHASES = [
        ("dns_lookup_ms", "DNS 解析"),
        ("tcp_connect_ms", "TCP 连接"),
        ("tls_handshake_ms", "TLS 握手"),
        ("waiting_ms", "等待响应"),
        ("content_transfer_ms", "内容传输"),
    ]

    def to_markdown(self, result: Dict[str, Any]) -> str:
        """将 HTTP 探测结果转换为 Markdown 格式"""
        lines = []

        # 获取基本信息
        success = result.get("success", False)
        target = result.get("target", {})
        data = result.get("data", {})
        error = result.get("error")

        # 标题
        status_icon = self.get_status_icon(success)
        lines.append(f"## {self.ICON_HTTP} HTTP 探测结果 {status_icon}")
        lines.append("")

        # 请求信息
        request = data.get("request", {})
        method = request.get("method", "GET")
        url = request.get("url") or target.get("url", "N/A")
        lines.append(f"**请求**: `{method} {url}`")

        # 响应状态
        response = data.get("response", {})
        status_code = response.get("status_code")
        status_text = response.get("status_text", "")

        if status_code:
            status_str = f"{status_code} {status_text}".strip()
            status_emoji = self._get_status_emoji(status_code)
            lines.append(f"**状态**: {status_str} {status_emoji}")

        lines.append("")

        # 错误处理
        if not success and error:
            lines.append("### ❌ 请求失败")
            lines.append("")
            error_code = error.get("code", "UNKNOWN")
            error_msg = error.get("message", "Unknown error")
            lines.append(f"- **错误码**: `{error_code}`")
            lines.append(f"- **错误信息**: {error_msg}")
            lines.append("")
            lines.append(self._get_error_suggestion(error_code))
            return "\n".join(lines)

        # 响应信息
        if response:
            lines.append(self._format_response(response))
            lines.append("")

        # 重定向链
        redirects = data.get("redirects", [])
        if redirects:
            lines.append(self._format_redirects(redirects))
            lines.append("")

        # 时间分解
        timing = data.get("timing", {})
        if timing:
            lines.append(self._format_timing(timing))

        return "\n".join(lines)

    def _get_status_emoji(self, status_code: int) -> str:
        """根据状态码返回对应 emoji"""
        if 200 <= status_code < 300:
            return self.ICON_SUCCESS
        elif 300 <= status_code < 400:
            return "↪️"  # 重定向
        elif 400 <= status_code < 500:
            return self.ICON_WARNING
        elif status_code >= 500:
            return self.ICON_FAILURE
        return ""

    def _format_response(self, response: Dict[str, Any]) -> str:
        """格式化响应信息"""
        lines = ["### 📋 响应信息", ""]

        rows = []

        # Content-Type
        content_type = response.get("content_type")
        if content_type:
            rows.append(["Content-Type", f"`{content_type}`"])

        # Content-Length
        content_length = response.get("content_length")
        if content_length is not None:
            rows.append(["Content-Length", self._format_size(content_length)])

        # Server
        server = response.get("server")
        if server:
            rows.append(["Server", f"`{server}`"])

        # Content-Encoding
        encoding = response.get("content_encoding")
        if encoding:
            rows.append(["压缩", f"`{encoding}`"])

        # 其他重要头
        headers = response.get("headers", {})
        important_headers = ["Cache-Control", "X-Cache", "CF-Ray", "X-Request-Id"]
        for header in important_headers:
            # 不区分大小写查找
            for k, v in headers.items():
                if k.lower() == header.lower():
                    rows.append([header, f"`{v}`"])
                    break

        if rows:
            lines.append(self.format_table(["字段", "值"], rows))

        return "\n".join(lines)

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} MB"

    def _format_redirects(self, redirects: List[Dict[str, Any]]) -> str:
        """格式化重定向链"""
        lines = ["### ↪️ 重定向链", ""]

        rows = []
        for i, redirect in enumerate(redirects, 1):
            status_code = redirect.get("status_code", "?")
            location = redirect.get("location", "N/A")
            # 截断过长的 URL
            if len(location) > 50:
                location = location[:47] + "..."
            rows.append([str(i), str(status_code), f"`{location}`"])

        lines.append(self.format_table(["步骤", "状态码", "目标"], rows))
        return "\n".join(lines)

    def _format_timing(self, timing: Dict[str, Any]) -> str:
        """格式化时间分解为 ASCII 条形图"""
        lines = ["### ⏱️ 时间分解", ""]

        # 收集有效的时间数据
        phases = []
        total_ms = timing.get("total_ms", 0)

        for key, label in self.TIMING_PHASES:
            value = timing.get(key)
            if value is not None and value > 0:
                phases.append((label, value))

        if not phases:
            # 如果没有详细分解，只显示总时间
            if total_ms:
                lines.append(f"**总耗时**: {self.format_duration(total_ms)}")
            return "\n".join(lines)

        # 计算最大值用于条形图比例
        max_value = max(v for _, v in phases) if phases else 1

        # 生成 ASCII 条形图
        lines.append("```")
        bar_width = 20
        label_width = 8

        for label, value in phases:
            # 计算百分比
            percent = (value / total_ms * 100) if total_ms > 0 else 0
            # 生成条形
            bar = self.format_ascii_bar(value, max_value, bar_width)
            # 格式化输出
            lines.append(
                f"{label:<{label_width}} {bar}  {self.format_duration(value):>8} ({percent:>4.1f}%)"
            )

        # 分隔线
        lines.append("─" * (label_width + bar_width + 20))

        # 总计
        lines.append(f"{'总计':<{label_width}} {' ' * bar_width}  {self.format_duration(total_ms):>8}")
        lines.append("```")

        return "\n".join(lines)

    def _get_error_suggestion(self, error_code: str) -> str:
        """根据错误码返回建议"""
        suggestions = {
            "HTTP_TIMEOUT": "> 💡 **建议**: HTTP 请求超时，请检查目标服务是否响应缓慢或网络延迟过高。",
            "HTTP_ERROR": "> 💡 **建议**: HTTP 请求错误，请检查请求参数和目标服务状态。",
            "TCP_TIMEOUT": "> 💡 **建议**: TCP 连接超时，请检查目标地址和端口是否正确。",
            "TCP_REFUSED": "> 💡 **建议**: 连接被拒绝，请检查目标端口是否开放。",
            "TLS_HANDSHAKE_FAILED": "> 💡 **建议**: TLS 握手失败，请检查目标是否支持 HTTPS。",
            "DNS_TIMEOUT": "> 💡 **建议**: DNS 解析超时，请检查域名是否正确。",
        }
        return suggestions.get(error_code, "> 💡 **建议**: 请检查网络连接和目标服务状态。")

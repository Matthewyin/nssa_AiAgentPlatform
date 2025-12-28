"""
Markdown 转换器单元测试

验证各转换器输出格式正确，包括 Emoji 和表格格式。
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from graph_service.report_builder import MarkdownConverter
from graph_service.report_builder.converters import (
    BaseConverter,
    DNSConverter,
    TLSConverter,
    HTTPConverter,
    MTRConverter,
    DiagnoseConverter,
    GenericConverter,
)


class TestBaseConverter:
    """基础转换器测试"""

    def test_format_duration_microseconds(self):
        """测试微秒级耗时格式化"""
        converter = GenericConverter()
        assert "μs" in converter.format_duration(0.5)

    def test_format_duration_milliseconds(self):
        """测试毫秒级耗时格式化"""
        converter = GenericConverter()
        assert "ms" in converter.format_duration(45.2)

    def test_format_duration_seconds(self):
        """测试秒级耗时格式化"""
        converter = GenericConverter()
        assert "s" in converter.format_duration(1500)

    def test_format_table(self):
        """测试表格格式化"""
        converter = GenericConverter()
        headers = ["列1", "列2"]
        rows = [["A", "B"], ["C", "D"]]
        table = converter.format_table(headers, rows)

        assert "| 列1 | 列2 |" in table
        assert "| --- | --- |" in table
        assert "| A | B |" in table
        assert "| C | D |" in table

    def test_format_ascii_bar(self):
        """测试 ASCII 进度条"""
        converter = GenericConverter()
        bar = converter.format_ascii_bar(50, 100, 10)
        assert "█" in bar
        assert "░" in bar
        assert len(bar) == 10

    def test_format_collapsible(self):
        """测试折叠内容格式化"""
        converter = GenericConverter()
        result = converter.format_collapsible("标题", "内容")
        assert "<details>" in result
        assert "<summary>标题</summary>" in result
        assert "内容" in result
        assert "</details>" in result

    def test_get_status_icon(self):
        """测试状态图标"""
        converter = GenericConverter()
        assert converter.get_status_icon(True) == "✅"
        assert converter.get_status_icon(False) == "❌"


class TestDNSConverter:
    """DNS 转换器测试"""

    def test_dns_success_result(self):
        """测试 DNS 成功结果转换"""
        converter = DNSConverter()
        result = {
            "tool": "nslookup",
            "success": True,
            "duration_ms": 45.2,
            "target": {"domain": "example.com"},
            "data": {
                "dns_server": "8.8.8.8",
                "resolution_time_ms": 45.2,
                "resolution_chain": [
                    {"name": "example.com", "type": "CNAME", "value": "cdn.example.com", "ttl": 300},
                    {"name": "cdn.example.com", "type": "A", "value": "1.2.3.4", "ttl": 60},
                ],
                "resolved_ips": ["1.2.3.4"],
            },
        }
        markdown = converter.to_markdown(result)

        assert "🔍" in markdown  # DNS 图标
        assert "✅" in markdown  # 成功图标
        assert "example.com" in markdown
        assert "8.8.8.8" in markdown
        assert "CNAME" in markdown
        assert "1.2.3.4" in markdown

    def test_dns_failure_result(self):
        """测试 DNS 失败结果转换"""
        converter = DNSConverter()
        result = {
            "tool": "nslookup",
            "success": False,
            "target": {"domain": "nonexistent.example.com"},
            "error": {
                "code": "DNS_NXDOMAIN",
                "message": "Domain does not exist",
            },
        }
        markdown = converter.to_markdown(result)

        assert "❌" in markdown  # 失败图标
        assert "DNS_NXDOMAIN" in markdown
        assert "建议" in markdown


class TestTLSConverter:
    """TLS 转换器测试"""

    def test_tls_success_result(self):
        """测试 TLS 成功结果转换"""
        converter = TLSConverter()
        result = {
            "tool": "tls",
            "success": True,
            "target": {"domain": "example.com", "port": 443},
            "data": {
                "connection": {
                    "protocol": "TLSv1.3",
                    "cipher_suite": "TLS_AES_256_GCM_SHA384",
                    "is_mutual_tls": False,
                },
                "certificate": {
                    "subject": {"cn": "*.example.com", "o": "Example Inc"},
                    "issuer": {"cn": "DigiCert", "o": "DigiCert Inc"},
                    "not_before": "2024-01-01T00:00:00Z",
                    "not_after": "2025-01-01T00:00:00Z",
                    "days_remaining": 180,
                    "is_expired": False,
                    "is_expiring_soon": False,
                    "fingerprint_sha256": "abc123def456",
                    "dns_names": ["*.example.com", "example.com"],
                },
                "timing": {
                    "tcp_connect_ms": 35.2,
                    "tls_handshake_ms": 78.5,
                    "total_ms": 113.7,
                },
            },
        }
        markdown = converter.to_markdown(result)

        assert "🔒" in markdown  # TLS 图标
        assert "✅" in markdown  # 成功图标
        assert "TLSv1.3" in markdown
        assert "*.example.com" in markdown
        assert "DigiCert" in markdown
        assert "180 天" in markdown

    def test_tls_expiring_soon_warning(self):
        """测试证书即将过期警告"""
        converter = TLSConverter()
        result = {
            "tool": "tls",
            "success": True,
            "target": {"domain": "example.com", "port": 443},
            "data": {
                "connection": {"protocol": "TLSv1.3", "cipher_suite": "TLS_AES_256_GCM_SHA384"},
                "certificate": {
                    "subject": {"cn": "example.com"},
                    "issuer": {"cn": "DigiCert"},
                    "days_remaining": 15,
                    "is_expired": False,
                    "is_expiring_soon": True,
                },
                "timing": {"total_ms": 100},
                "security": {"warnings": ["Certificate expires in 15 days"]},
            },
        }
        markdown = converter.to_markdown(result)

        assert "⚠️" in markdown  # 警告图标
        assert "即将过期" in markdown


class TestHTTPConverter:
    """HTTP 转换器测试"""

    def test_http_success_result(self):
        """测试 HTTP 成功结果转换"""
        converter = HTTPConverter()
        result = {
            "tool": "http",
            "success": True,
            "target": {"url": "https://example.com/api"},
            "data": {
                "request": {"method": "GET", "url": "https://example.com/api"},
                "response": {
                    "status_code": 200,
                    "status_text": "OK",
                    "content_type": "application/json",
                    "content_length": 1234,
                    "server": "nginx/1.18.0",
                },
                "timing": {
                    "dns_lookup_ms": 12.3,
                    "tcp_connect_ms": 35.2,
                    "tls_handshake_ms": 78.5,
                    "waiting_ms": 15.6,
                    "content_transfer_ms": 12.1,
                    "total_ms": 153.7,
                },
            },
        }
        markdown = converter.to_markdown(result)

        assert "🌐" in markdown  # HTTP 图标
        assert "✅" in markdown  # 成功图标
        assert "200" in markdown
        assert "application/json" in markdown
        assert "nginx" in markdown
        # 检查时间分解
        assert "DNS" in markdown or "dns" in markdown.lower()

    def test_http_redirect_chain(self):
        """测试 HTTP 重定向链"""
        converter = HTTPConverter()
        result = {
            "tool": "http",
            "success": True,
            "target": {"url": "http://example.com"},
            "data": {
                "request": {"method": "GET", "url": "http://example.com"},
                "response": {"status_code": 200, "status_text": "OK"},
                "redirects": [
                    {"status_code": 301, "location": "https://example.com"},
                    {"status_code": 302, "location": "https://www.example.com"},
                ],
                "timing": {"total_ms": 200},
            },
        }
        markdown = converter.to_markdown(result)

        assert "重定向" in markdown
        assert "301" in markdown
        assert "302" in markdown


class TestMTRConverter:
    """MTR 转换器测试"""

    def test_mtr_success_result(self):
        """测试 MTR 成功结果转换"""
        converter = MTRConverter()
        result = {
            "tool": "mtr",
            "success": True,
            "target": {"ip": "1.2.3.4"},
            "data": {
                "hops": [
                    {
                        "hop_number": 1,
                        "ip": "192.168.1.1",
                        "hostname": "router.local",
                        "loss_percent": 0,
                        "latency_ms": {"min": 1.0, "max": 2.0, "avg": 1.5, "std_dev": 0.3},
                        "is_timeout": False,
                        "is_high_loss": False,
                    },
                    {
                        "hop_number": 2,
                        "ip": "10.0.0.1",
                        "loss_percent": 0,
                        "latency_ms": {"avg": 5.3},
                        "is_timeout": False,
                        "is_high_loss": False,
                    },
                    {
                        "hop_number": 3,
                        "ip": "*",
                        "loss_percent": 100,
                        "is_timeout": True,
                        "is_high_loss": False,
                    },
                    {
                        "hop_number": 4,
                        "ip": "1.2.3.4",
                        "loss_percent": 0,
                        "latency_ms": {"avg": 45.6},
                        "is_timeout": False,
                        "is_high_loss": False,
                    },
                ],
                "summary": {
                    "total_hops": 4,
                    "target_reached": True,
                    "avg_latency_ms": 45.6,
                    "overall_loss_percent": 2.5,
                },
            },
        }
        markdown = converter.to_markdown(result)

        assert "🛤️" in markdown  # MTR 图标
        assert "✅" in markdown  # 成功图标
        assert "192.168.1.1" in markdown
        assert "⏱️" in markdown  # 超时图标
        assert "4" in markdown  # 总跳数

    def test_mtr_high_loss_warning(self):
        """测试 MTR 高丢包警告"""
        converter = MTRConverter()
        result = {
            "tool": "mtr",
            "success": True,
            "target": {"ip": "1.2.3.4"},
            "data": {
                "hops": [
                    {
                        "hop_number": 1,
                        "ip": "192.168.1.1",
                        "loss_percent": 25,
                        "latency_ms": {"avg": 10},
                        "is_timeout": False,
                        "is_high_loss": True,
                    },
                ],
                "summary": {
                    "total_hops": 1,
                    "target_reached": True,
                    "avg_latency_ms": 10,
                    "overall_loss_percent": 25,
                },
            },
        }
        markdown = converter.to_markdown(result)

        assert "⚠️" in markdown  # 警告图标
        assert "高丢包" in markdown or "丢包" in markdown


class TestDiagnoseConverter:
    """Diagnose 转换器测试"""

    def test_diagnose_success_result(self):
        """测试 Diagnose 成功结果转换"""
        converter = DiagnoseConverter()
        result = {
            "tool": "diagnose",
            "success": True,
            "timestamp": "2024-01-15T10:30:00Z",
            "data": {
                "target": {"input": "https://example.com", "domain": "example.com", "port": 443},
                "dns": {
                    "success": True,
                    "dns_server": "8.8.8.8",
                    "resolution_time_ms": 45.2,
                    "resolved_ips": ["1.2.3.4"],
                },
                "tcp": [{"success": True, "connect_time_ms": 35.2}],
                "tls": {
                    "success": True,
                    "connection": {"protocol": "TLSv1.3"},
                    "certificate": {"days_remaining": 180, "is_expired": False, "is_expiring_soon": False},
                    "timing": {"tls_handshake_ms": 78.5},
                },
                "http": {
                    "success": True,
                    "response": {"status_code": 200},
                    "timing": {"total_ms": 153.7},
                },
                "summary": {
                    "overall_status": "success",
                    "total_duration_ms": 2500,
                },
                "recommendations": ["✅ 网络连接正常", "⭐ 推荐 IP: 1.2.3.4"],
            },
        }
        markdown = converter.to_markdown(result)

        assert "📊" in markdown  # Diagnose 图标
        assert "✅" in markdown  # 成功图标
        assert "example.com" in markdown
        assert "DNS" in markdown
        assert "TLS" in markdown
        assert "HTTP" in markdown
        assert "<details>" in markdown  # 折叠详情


class TestMarkdownConverter:
    """主转换器测试"""

    def test_converter_routing(self):
        """测试转换器路由"""
        converter = MarkdownConverter()

        # 测试各种工具名称的路由
        assert isinstance(converter._get_converter("network.nslookup"), DNSConverter)
        assert isinstance(converter._get_converter("dns"), DNSConverter)
        assert isinstance(converter._get_converter("tls"), TLSConverter)
        assert isinstance(converter._get_converter("http"), HTTPConverter)
        assert isinstance(converter._get_converter("mtr"), MTRConverter)
        assert isinstance(converter._get_converter("diagnose"), DiagnoseConverter)
        assert isinstance(converter._get_converter("unknown"), GenericConverter)

    def test_convert_dns(self):
        """测试 DNS 结果转换"""
        converter = MarkdownConverter()
        result = {
            "tool": "nslookup",
            "success": True,
            "target": {"domain": "example.com"},
            "data": {
                "dns_server": "8.8.8.8",
                "resolved_ips": ["1.2.3.4"],
            },
        }
        markdown = converter.convert("network.nslookup", result)
        assert "DNS" in markdown

    def test_get_supported_tools(self):
        """测试获取支持的工具列表"""
        converter = MarkdownConverter()
        tools = converter.get_supported_tools()
        assert len(tools) > 0
        assert "dns" in tools or "network.dns" in tools


class TestGenericConverter:
    """通用转换器测试"""

    def test_generic_success_result(self):
        """测试通用成功结果转换"""
        converter = GenericConverter()
        result = {
            "tool": "ping",
            "success": True,
            "duration_ms": 100,
            "target": {"ip": "1.2.3.4"},
            "data": {"packets_sent": 4, "packets_received": 4},
        }
        markdown = converter.to_markdown(result)

        assert "PING" in markdown
        assert "✅" in markdown
        assert "1.2.3.4" in markdown

    def test_generic_failure_result(self):
        """测试通用失败结果转换"""
        converter = GenericConverter()
        result = {
            "tool": "tcp",
            "success": False,
            "target": {"ip": "1.2.3.4", "port": 80},
            "error": {"code": "TCP_TIMEOUT", "message": "Connection timed out"},
        }
        markdown = converter.to_markdown(result)

        assert "❌" in markdown
        assert "TCP_TIMEOUT" in markdown


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

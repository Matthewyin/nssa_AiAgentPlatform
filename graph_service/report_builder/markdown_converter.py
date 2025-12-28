"""
Markdown Converter

将结构化探测结果转换为 Markdown 格式，用于 Open WebUI 展示。
"""

from typing import Any, Dict, Optional

from .converters.base_converter import BaseConverter
from .converters.generic_converter import GenericConverter


class MarkdownConverter:
    """
    Markdown 转换器主类。

    根据工具类型选择对应的转换器，将结构化探测结果转换为 Markdown 格式。
    """

    def __init__(self):
        """初始化转换器映射"""
        self._converters: Dict[str, BaseConverter] = {}
        self._generic_converter = GenericConverter()
        self._init_converters()

    def _init_converters(self):
        """初始化各类型转换器"""
        # 延迟导入避免循环依赖
        from .converters.dns_converter import DNSConverter
        from .converters.tls_converter import TLSConverter
        from .converters.http_converter import HTTPConverter
        from .converters.mtr_converter import MTRConverter
        from .converters.diagnose_converter import DiagnoseConverter
        from .converters.ping_converter import PingConverter
        from .converters.traceroute_converter import TracerouteConverter
        from .converters.tcp_converter import TCPConverter

        self._converters = {
            # 网络探测工具
            "network.nslookup": DNSConverter(),
            "network.dns": DNSConverter(),
            "nslookup": DNSConverter(),
            "dns": DNSConverter(),
            # TLS 探测
            "network.tls": TLSConverter(),
            "tls": TLSConverter(),
            # HTTP 探测
            "network.http": HTTPConverter(),
            "http": HTTPConverter(),
            # MTR 探测
            "network.mtr": MTRConverter(),
            "mtr": MTRConverter(),
            # 综合诊断
            "network.diagnose": DiagnoseConverter(),
            "diagnose": DiagnoseConverter(),
            # Ping 探测
            "network.ping": PingConverter(),
            "ping": PingConverter(),
            # Traceroute 探测
            "network.traceroute": TracerouteConverter(),
            "traceroute": TracerouteConverter(),
            # TCP 连接探测
            "network.tcp": TCPConverter(),
            "tcp": TCPConverter(),
        }

    def convert(self, tool_name: str, result: Dict[str, Any]) -> str:
        """
        将探测结果转换为 Markdown 格式。

        Args:
            tool_name: 工具名称
            result: 结构化的探测结果字典

        Returns:
            Markdown 格式的字符串
        """
        converter = self._get_converter(tool_name)
        return converter.to_markdown(result)

    def _get_converter(self, tool_name: str) -> BaseConverter:
        """
        根据工具名称获取对应的转换器。

        Args:
            tool_name: 工具名称

        Returns:
            对应的转换器实例
        """
        # 尝试精确匹配
        if tool_name in self._converters:
            return self._converters[tool_name]

        # 尝试小写匹配
        tool_lower = tool_name.lower()
        if tool_lower in self._converters:
            return self._converters[tool_lower]

        # 尝试从结果中获取工具类型
        return self._generic_converter

    def register_converter(self, tool_name: str, converter: BaseConverter):
        """
        注册自定义转换器。

        Args:
            tool_name: 工具名称
            converter: 转换器实例
        """
        self._converters[tool_name] = converter

    def get_supported_tools(self) -> list:
        """获取支持的工具列表"""
        return list(set(self._converters.keys()))

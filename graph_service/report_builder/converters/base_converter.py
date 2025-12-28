"""
Base Converter

所有转换器的基类，定义通用接口和辅助方法。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseConverter(ABC):
    """探测结果转换器基类"""

    # 状态图标
    ICON_SUCCESS = "✅"
    ICON_FAILURE = "❌"
    ICON_WARNING = "⚠️"
    ICON_TIMEOUT = "⏱️"
    ICON_STAR = "⭐"
    ICON_INFO = "ℹ️"

    # 工具图标
    ICON_DNS = "🔍"
    ICON_TLS = "🔒"
    ICON_HTTP = "🌐"
    ICON_MTR = "🛤️"
    ICON_DIAGNOSE = "📊"
    ICON_TCP = "🔌"
    ICON_PING = "📡"

    @abstractmethod
    def to_markdown(self, result: Dict[str, Any]) -> str:
        """
        将探测结果转换为 Markdown 格式。

        Args:
            result: 结构化的探测结果字典

        Returns:
            Markdown 格式的字符串
        """
        pass

    def get_status_icon(self, success: bool) -> str:
        """根据成功状态返回对应图标"""
        return self.ICON_SUCCESS if success else self.ICON_FAILURE

    def format_duration(self, duration_ms: Optional[float]) -> str:
        """格式化耗时显示"""
        if duration_ms is None:
            return "N/A"
        if duration_ms < 1:
            return f"{duration_ms * 1000:.1f}μs"
        if duration_ms < 1000:
            return f"{duration_ms:.1f}ms"
        return f"{duration_ms / 1000:.2f}s"

    def format_table(self, headers: list, rows: list) -> str:
        """
        生成 Markdown 表格。

        Args:
            headers: 表头列表
            rows: 数据行列表，每行是一个列表

        Returns:
            Markdown 表格字符串
        """
        if not headers or not rows:
            return ""

        # 表头
        header_line = "| " + " | ".join(str(h) for h in headers) + " |"
        # 分隔线
        separator = "| " + " | ".join("---" for _ in headers) + " |"
        # 数据行
        data_lines = []
        for row in rows:
            data_lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

        return "\n".join([header_line, separator] + data_lines)

    def format_key_value(self, key: str, value: Any) -> str:
        """格式化键值对"""
        return f"**{key}**: {value}"

    def format_code(self, text: str, language: str = "") -> str:
        """格式化代码块"""
        return f"```{language}\n{text}\n```"

    def format_collapsible(self, summary: str, content: str) -> str:
        """格式化可折叠内容"""
        return f"<details>\n<summary>{summary}</summary>\n\n{content}\n\n</details>"

    def format_ascii_bar(
        self, value: float, max_value: float, width: int = 20
    ) -> str:
        """
        生成 ASCII 进度条。

        Args:
            value: 当前值
            max_value: 最大值
            width: 进度条宽度（字符数）

        Returns:
            ASCII 进度条字符串
        """
        if max_value <= 0:
            return "░" * width
        ratio = min(value / max_value, 1.0)
        filled = int(ratio * width)
        return "█" * filled + "░" * (width - filled)

    def safe_get(self, data: Dict, *keys, default: Any = None) -> Any:
        """安全获取嵌套字典值"""
        result = data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key, default)
            else:
                return default
        return result if result is not None else default

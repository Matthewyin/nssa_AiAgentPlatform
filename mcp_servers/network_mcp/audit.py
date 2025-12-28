"""
Audit Logger for Network MCP Server
记录每次工具调用的耗时和结果摘要
"""
import json
from datetime import datetime
from typing import Any, Dict, Optional
from loguru import logger


class AuditLogger:
    """
    工具调用审计日志
    
    记录每次工具调用的：
    - 时间戳
    - 工具名称
    - 参数（脱敏处理）
    - 执行结果摘要
    - 耗时
    """
    
    # 需要脱敏的参数名
    SENSITIVE_PARAMS = {
        "password", "secret", "token", "key", "credential",
        "client_key", "client_cert", "ca_cert"
    }
    
    def __init__(self, log_file: Optional[str] = None):
        """
        初始化审计日志
        
        Args:
            log_file: 日志文件路径（可选，默认使用 loguru）
        """
        self.log_file = log_file
    
    async def log_call(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any], 
        result: Dict[str, Any], 
        duration_ms: float
    ) -> None:
        """
        记录工具调用
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            result: 执行结果
            duration_ms: 执行耗时（毫秒）
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tool": tool_name,
            "arguments": self._sanitize_args(arguments),
            "success": result.get("success", False),
            "duration_ms": round(duration_ms, 2),
            "summary": self._extract_summary(tool_name, result),
        }
        
        # 如果有错误，记录错误信息
        if not result.get("success", False):
            error = result.get("error")
            if error:
                log_entry["error"] = str(error)[:200]  # 截断过长的错误信息
            
            validation_errors = result.get("validation_errors")
            if validation_errors:
                log_entry["validation_errors"] = validation_errors
        
        # 记录日志
        log_json = json.dumps(log_entry, ensure_ascii=False)
        logger.info(f"[AUDIT] {log_json}")
    
    def _sanitize_args(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        脱敏处理参数
        
        Args:
            arguments: 原始参数
            
        Returns:
            脱敏后的参数
        """
        sanitized = {}
        for key, value in arguments.items():
            if key.lower() in self.SENSITIVE_PARAMS:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_args(value)
            elif isinstance(value, list):
                # 对于列表，只记录长度
                sanitized[key] = f"[{len(value)} items]" if len(value) > 5 else value
            else:
                sanitized[key] = value
        return sanitized
    
    def _extract_summary(self, tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取结果摘要
        
        Args:
            tool_name: 工具名称
            result: 执行结果
            
        Returns:
            结果摘要
        """
        summary = {}
        
        # 批量探测摘要
        if result.get("batch"):
            summary["batch"] = True
            summary["total"] = result.get("total", 0)
            summary["success_count"] = result.get("success_count", 0)
            summary["failure_count"] = result.get("failure_count", 0)
            return summary
        
        # 根据工具类型提取不同的摘要信息
        if tool_name == "network.ping":
            data = result.get("data", {})
            if isinstance(data, dict):
                summary["packets_sent"] = data.get("packets_sent")
                summary["packets_received"] = data.get("packets_received")
                summary["avg_latency_ms"] = data.get("avg_latency_ms")
        
        elif tool_name == "network.nslookup":
            data = result.get("data", {})
            if isinstance(data, dict):
                resolved_ips = data.get("resolved_ips", [])
                summary["resolved_ips_count"] = len(resolved_ips) if isinstance(resolved_ips, list) else 0
                summary["resolution_time_ms"] = data.get("resolution_time_ms")
        
        elif tool_name == "network.tls":
            data = result.get("data", {})
            if isinstance(data, dict):
                cert = data.get("certificate", {})
                summary["days_remaining"] = cert.get("days_remaining")
                summary["is_expiring_soon"] = cert.get("is_expiring_soon")
                conn = data.get("connection", {})
                summary["protocol"] = conn.get("protocol")
        
        elif tool_name == "network.http":
            data = result.get("data", {})
            if isinstance(data, dict):
                response = data.get("response", {})
                summary["status_code"] = response.get("status_code")
                timing = data.get("timing", {})
                summary["total_ms"] = timing.get("total_ms")
        
        elif tool_name == "network.mtr":
            data = result.get("data", {})
            if isinstance(data, dict):
                mtr_summary = data.get("summary", {})
                summary["total_hops"] = mtr_summary.get("total_hops")
                summary["target_reached"] = mtr_summary.get("target_reached")
                summary["overall_loss_percent"] = mtr_summary.get("overall_loss_percent")
        
        elif tool_name == "network.diagnose":
            diag_summary = result.get("summary", {})
            if isinstance(diag_summary, dict):
                summary["overall_status"] = diag_summary.get("overall_status")
                summary["total_duration_ms"] = diag_summary.get("total_duration_ms")
                issues = diag_summary.get("issues", [])
                summary["issues_count"] = len(issues) if isinstance(issues, list) else 0
        
        elif tool_name in ("network.tcp", "network.traceroute"):
            # 简单工具，只记录成功状态
            summary["success"] = result.get("success", False)
        
        return summary

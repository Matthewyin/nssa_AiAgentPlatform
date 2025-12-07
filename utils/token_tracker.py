"""
Token 使用统计模块
记录和统计 LLM 调用的 token 消耗
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger
from threading import Lock


class TokenTracker:
    """Token 使用统计器"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._config = None
        self._current_request: Optional[Dict[str, Any]] = None
        self._log_file: Optional[Path] = None
        self._pricing: Dict[str, Dict[str, float]] = {}
        
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        try:
            from utils import load_optimization_config
            config = load_optimization_config()
            self._config = config.get("optimization", {}).get("token_tracking", {})
            
            if not self._config.get("enabled", False):
                return
            
            # 设置日志文件
            log_file = self._config.get("log_file", "data/logs/token_usage.log")
            self._log_file = Path(log_file)
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 加载定价
            self._pricing = self._config.get("pricing", {})
            
            logger.info(f"Token 统计已启用，日志文件: {self._log_file}")
        except Exception as e:
            logger.warning(f"加载 Token 统计配置失败: {e}")
            self._config = {"enabled": False}
    
    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._config.get("enabled", False) if self._config else False
    
    def start_request(self, request_id: str, user_query: str):
        """开始记录一个请求"""
        if not self.enabled:
            return
        
        self._current_request = {
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
            "user_query": user_query[:200],  # 截断查询
            "llm_calls": [],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "estimated_cost_usd": 0.0
        }
    
    def record_call(
        self,
        node: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: Optional[float] = None
    ):
        """记录一次 LLM 调用"""
        if not self.enabled or not self._current_request:
            return
        
        # 计算成本
        pricing = self._pricing.get(model, self._pricing.get("default", {}))
        input_price = pricing.get("input", 1.0)
        output_price = pricing.get("output", 3.0)
        cost = (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
        
        call_record = {
            "node": node,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "duration_ms": duration_ms
        }
        
        self._current_request["llm_calls"].append(call_record)
        self._current_request["total_input_tokens"] += input_tokens
        self._current_request["total_output_tokens"] += output_tokens
        self._current_request["estimated_cost_usd"] += cost
    
    def end_request(self) -> Optional[Dict[str, Any]]:
        """结束请求并返回统计信息"""
        if not self.enabled or not self._current_request:
            return None
        
        # 四舍五入成本
        self._current_request["estimated_cost_usd"] = round(
            self._current_request["estimated_cost_usd"], 6
        )
        
        # 写入日志文件
        if self._log_file:
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(self._current_request, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"写入 Token 统计日志失败: {e}")
        
        result = self._current_request
        self._current_request = None
        
        # 输出摘要日志
        logger.info(
            f"Token 统计 | 调用次数: {len(result['llm_calls'])} | "
            f"Input: {result['total_input_tokens']} | "
            f"Output: {result['total_output_tokens']} | "
            f"成本: ${result['estimated_cost_usd']:.6f}"
        )
        
        return result
    
    def get_current_stats(self) -> Optional[Dict[str, Any]]:
        """获取当前请求的统计信息"""
        return self._current_request


# 全局单例
_tracker: Optional[TokenTracker] = None


def get_token_tracker() -> TokenTracker:
    """获取 Token 统计器单例"""
    global _tracker
    if _tracker is None:
        _tracker = TokenTracker()
    return _tracker


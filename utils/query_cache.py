"""
查询缓存模块
缓存相同问题的路由决策和结果
"""
import hashlib
import time
from typing import Any, Dict, Optional
from loguru import logger


class QueryCache:
    """查询缓存类"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._router_cache: Dict[str, Dict[str, Any]] = {}
        self._result_cache: Dict[str, Dict[str, Any]] = {}
        self._config = self._load_config()
        self._initialized = True
        
        if self._config.get("enabled", False):
            logger.info("查询缓存已启用")
    
    def _load_config(self) -> Dict[str, Any]:
        """加载缓存配置"""
        try:
            from .config_loader import load_optimization_config
            config = load_optimization_config()
            return config.get("optimization", {}).get("query_cache", {})
        except Exception as e:
            logger.warning(f"加载缓存配置失败: {e}")
            return {"enabled": False}
    
    @property
    def enabled(self) -> bool:
        return self._config.get("enabled", False)
    
    def _hash_query(self, query: str) -> str:
        """生成查询的哈希值"""
        return hashlib.md5(query.strip().lower().encode()).hexdigest()
    
    def get_router_cache(self, query: str) -> Optional[Dict[str, Any]]:
        """
        获取路由缓存
        
        Args:
            query: 用户查询
        
        Returns:
            缓存的路由结果，如果没有或已过期则返回 None
        """
        if not self.enabled:
            return None
        
        query_hash = self._hash_query(query)
        cached = self._router_cache.get(query_hash)
        
        if cached:
            ttl = self._config.get("router_cache_ttl", 3600)
            if time.time() - cached["timestamp"] < ttl:
                logger.info(f"QueryCache: 命中路由缓存 (hash={query_hash[:8]})")
                return cached["data"]
            else:
                # 过期，删除
                del self._router_cache[query_hash]
        
        return None
    
    def set_router_cache(self, query: str, data: Dict[str, Any]):
        """
        设置路由缓存
        
        Args:
            query: 用户查询
            data: 路由结果
        """
        if not self.enabled:
            return
        
        query_hash = self._hash_query(query)
        self._router_cache[query_hash] = {
            "data": data,
            "timestamp": time.time()
        }
        logger.info(f"QueryCache: 缓存路由结果 (hash={query_hash[:8]})")
    
    def get_result_cache(self, query: str) -> Optional[Dict[str, Any]]:
        """
        获取结果缓存
        
        Args:
            query: 用户查询
        
        Returns:
            缓存的结果，如果没有或已过期则返回 None
        """
        if not self.enabled:
            return None
        
        query_hash = self._hash_query(query)
        cached = self._result_cache.get(query_hash)
        
        if cached:
            ttl = self._config.get("result_cache_ttl", 300)
            if time.time() - cached["timestamp"] < ttl:
                logger.info(f"QueryCache: 命中结果缓存 (hash={query_hash[:8]})")
                return cached["data"]
            else:
                del self._result_cache[query_hash]
        
        return None
    
    def set_result_cache(self, query: str, data: Dict[str, Any]):
        """设置结果缓存"""
        if not self.enabled:
            return
        
        query_hash = self._hash_query(query)
        self._result_cache[query_hash] = {
            "data": data,
            "timestamp": time.time()
        }
        logger.info(f"QueryCache: 缓存结果 (hash={query_hash[:8]})")
    
    def clear(self):
        """清空所有缓存"""
        self._router_cache.clear()
        self._result_cache.clear()
        logger.info("QueryCache: 缓存已清空")


def get_query_cache() -> QueryCache:
    """获取查询缓存单例"""
    return QueryCache()


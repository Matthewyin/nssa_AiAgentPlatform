"""
任务复杂度分析模块
根据用户查询评估任务复杂度，用于自适应 Think 深度
"""
from typing import Dict, Any, Tuple
from loguru import logger


def analyze_complexity(user_query: str, agent_plan: list = None) -> Tuple[str, int]:
    """
    分析任务复杂度
    
    Args:
        user_query: 用户查询
        agent_plan: Agent 执行计划（可选）
    
    Returns:
        (复杂度级别, 建议的最大迭代次数)
        复杂度级别: "low", "medium", "high"
    """
    try:
        from utils import load_optimization_config
        config = load_optimization_config()
        adaptive_config = config.get("optimization", {}).get("adaptive_depth", {})
        
        if not adaptive_config.get("enabled", False):
            # 未启用，返回默认值
            return "medium", 10
        
        low_max = adaptive_config.get("low_complexity_max_iterations", 3)
        medium_max = adaptive_config.get("medium_complexity_max_iterations", 6)
        high_max = adaptive_config.get("high_complexity_max_iterations", 10)
        
        # 复杂度评估规则
        complexity_score = 0
        
        # 规则 1: 查询长度
        query_length = len(user_query)
        if query_length < 20:
            complexity_score += 0
        elif query_length < 50:
            complexity_score += 1
        else:
            complexity_score += 2
        
        # 规则 2: 多 Agent 任务
        if agent_plan and len(agent_plan) > 1:
            complexity_score += len(agent_plan)
        
        # 规则 3: 关键词检测
        high_complexity_keywords = [
            "分析", "诊断", "排查", "对比", "比较", "综合",
            "多个", "所有", "全部", "详细", "完整",
            "analyze", "diagnose", "compare", "comprehensive"
        ]
        medium_complexity_keywords = [
            "查询", "检查", "测试", "获取",
            "query", "check", "test", "get"
        ]
        low_complexity_keywords = [
            "ping", "nslookup", "列出", "显示",
            "list", "show", "简单"
        ]
        
        query_lower = user_query.lower()
        
        for kw in high_complexity_keywords:
            if kw in query_lower:
                complexity_score += 2
                break
        
        for kw in medium_complexity_keywords:
            if kw in query_lower:
                complexity_score += 1
                break
        
        for kw in low_complexity_keywords:
            if kw in query_lower:
                complexity_score -= 1
                break
        
        # 规则 4: 多步骤指示词
        multi_step_keywords = ["然后", "接着", "之后", "再", "并且", "同时", "and then", "after that"]
        for kw in multi_step_keywords:
            if kw in query_lower:
                complexity_score += 1
        
        # 确定复杂度级别
        if complexity_score <= 1:
            complexity = "low"
            max_iterations = low_max
        elif complexity_score <= 4:
            complexity = "medium"
            max_iterations = medium_max
        else:
            complexity = "high"
            max_iterations = high_max
        
        logger.info(f"任务复杂度分析: score={complexity_score}, level={complexity}, max_iterations={max_iterations}")
        return complexity, max_iterations
        
    except Exception as e:
        logger.warning(f"复杂度分析失败: {e}")
        return "medium", 6


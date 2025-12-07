"""
LLM 调用包装器
提供统一的 LLM 调用接口，支持 token 统计
"""
import time
from typing import Any, Optional
from loguru import logger


def invoke_llm_with_tracking(
    llm: Any,
    prompt: str,
    node_name: str,
    model_name: Optional[str] = None
) -> Any:
    """
    带 token 统计的 LLM 调用
    
    Args:
        llm: LLM 实例
        prompt: 提示词
        node_name: 节点名称（用于统计）
        model_name: 模型名称（可选，用于成本估算）
    
    Returns:
        LLM 响应
    """
    from .token_tracker import get_token_tracker
    
    tracker = get_token_tracker()
    start_time = time.time()
    
    # 调用 LLM
    response = llm.invoke(prompt)
    
    duration_ms = (time.time() - start_time) * 1000
    
    # 尝试获取 token 使用信息
    input_tokens = 0
    output_tokens = 0
    
    # 尝试从响应中获取 token 使用信息
    if hasattr(response, 'response_metadata'):
        metadata = response.response_metadata
        
        # OpenAI / DeepSeek 格式
        if 'token_usage' in metadata:
            usage = metadata['token_usage']
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)
        # Gemini 格式
        elif 'usage_metadata' in metadata:
            usage = metadata['usage_metadata']
            input_tokens = usage.get('prompt_token_count', 0)
            output_tokens = usage.get('candidates_token_count', 0)
    
    # 如果无法从响应获取，估算 token 数
    if input_tokens == 0:
        # 粗略估算：中文约 2 字符/token，英文约 4 字符/token
        input_tokens = len(prompt) // 3
    
    if output_tokens == 0:
        response_text = response.content if hasattr(response, 'content') else str(response)
        output_tokens = len(response_text) // 3
    
    # 获取模型名称
    if model_name is None:
        model_name = getattr(llm, 'model_name', None) or getattr(llm, 'model', 'unknown')
    
    # 记录 token 使用
    if tracker.enabled:
        tracker.record_call(
            node=node_name,
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms
        )
    
    return response


def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量
    
    Args:
        text: 文本
    
    Returns:
        估算的 token 数
    """
    # 粗略估算：中文约 2 字符/token，英文约 4 字符/token
    # 混合文本取平均值约 3 字符/token
    return len(text) // 3


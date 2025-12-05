"""
OpenAI兼容的API接口
用于集成OpenWebUI
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, AsyncIterator
from loguru import logger
import time
import json

from .graph import compile_graph
from .state import GraphState


router = APIRouter()

# 编译图(复用main.py中的)
graph = None


def get_graph():
    """获取或创建图实例"""
    global graph
    if graph is None:
        graph = compile_graph()
    return graph


class Message(BaseModel):
    """消息模型"""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI聊天补全请求"""
    model: str
    messages: List[Message]
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2000


class ChatCompletionResponse(BaseModel):
    """OpenAI聊天补全响应"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


@router.get("/v1/models")
async def list_models():
    """
    列出可用模型
    OpenAI兼容接口
    """
    return {
        "object": "list",
        "data": [
            {
                "id": "aiagent-network-tools",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "aiagent",
                "permission": [],
                "root": "aiagent-network-tools",
                "parent": None,
            }
        ]
    }


@router.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    """
    获取单个模型信息
    OpenAI兼容接口
    """
    if model_id == "aiagent-network-tools":
        return {
            "id": "aiagent-network-tools",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "aiagent",
            "permission": [],
            "root": "aiagent-network-tools",
            "parent": None,
        }
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    聊天补全接口
    OpenAI兼容接口
    """
    try:
        # 提取最后一条用户消息
        user_message = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            user_message = request.messages[-1].content if request.messages else ""
        
        logger.info(f"OpenAI API收到请求: {user_message[:100]}...")
        
        # 初始化状态
        initial_state: GraphState = {
            "user_query": user_message,
            "current_node": "",
            "target_agent": "",
            "network_diag_result": None,
            "rag_result": None,
            "final_answer": "",
            "errors": [],
            "metadata": {}
        }
        
        # 执行图（增加递归限制，支持多 Agent 串行执行）
        graph_instance = get_graph()
        final_state = await graph_instance.ainvoke(
            initial_state,
            config={"recursion_limit": 100}  # 增加递归限制到 100，支持多 Agent 串行执行
        )
        
        # 构建响应
        response_text = final_state["final_answer"]
        
        logger.info(f"OpenAI API准备返回响应,长度: {len(response_text)} 字符")
        logger.debug(f"响应内容: {response_text[:200]}...")
        
        if request.stream:
            # 流式响应 - 使用StreamingResponse包装
            return StreamingResponse(
                _stream_response(response_text, request.model),
                media_type="text/event-stream"
            )
        else:
            # 非流式响应 - 使用JSONResponse确保Content-Type正确
            response_data = {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": response_text
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": len(user_message.split()),
                    "completion_tokens": len(response_text.split()),
                    "total_tokens": len(user_message.split()) + len(response_text.split())
                }
            }
            logger.info("OpenAI API响应已构建,准备返回")
            return JSONResponse(content=response_data)
    
    except Exception as e:
        logger.error(f"OpenAI API处理失败: {e}")
        error_response = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"处理失败: {str(e)}"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
        return JSONResponse(content=error_response)


async def _stream_response(text: str, model: str) -> AsyncIterator[str]:
    """
    生成流式响应
    
    Args:
        text: 响应文本
        model: 模型名称
        
    Yields:
        SSE格式的数据块
    """
    # 简化实现:一次性返回所有内容
    chunk = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": text
                },
                "finish_reason": None
            }
        ]
    }
    
    yield f"data: {json.dumps(chunk)}\n\n"
    
    # 发送结束标记
    end_chunk = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }
        ]
    }
    
    yield f"data: {json.dumps(end_chunk)}\n\n"
    yield "data: [DONE]\n\n"

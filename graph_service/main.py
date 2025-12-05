"""
FastAPI服务主程序
提供HTTP API接口
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
from loguru import logger

from .graph import compile_graph
from .state import GraphState
from .openai_api import router as openai_router
from utils import settings, setup_logger

# 加载 .env 文件到环境变量
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 初始化日志
setup_logger(
    log_level=settings.log_level,
    log_file=settings.log_file
)

# 创建FastAPI应用
app = FastAPI(
    title="AI Agent Network Tools",
    description="基于LangGraph的智能网络诊断系统",
    version="0.1.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册OpenAI兼容的API路由
app.include_router(openai_router, tags=["OpenAI Compatible API"])

# 编译LangGraph图
graph = compile_graph()


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    """聊天响应模型"""
    answer: str
    metadata: Dict[str, Any] = {}


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "graph_service",
        "version": "0.1.0"
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    聊天接口
    
    Args:
        request: 聊天请求
        
    Returns:
        聊天响应
    """
    try:
        logger.info(f"收到聊天请求: {request.message[:100]}...")
        
        # 初始化状态
        initial_state: GraphState = {
            "user_query": request.message,
            "current_node": "",
            "target_agent": "",
            "network_diag_result": None,
            "rag_result": None,
            "final_answer": "",
            "errors": [],
            "metadata": {}
        }
        
        # 执行图
        final_state = await graph.ainvoke(initial_state)
        
        # 返回结果
        response = ChatResponse(
            answer=final_state["final_answer"],
            metadata=final_state.get("metadata", {})
        )
        
        logger.info("聊天请求处理完成")
        
        return response
        
    except Exception as e:
        logger.error(f"聊天请求处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "AI Agent Network Tools API",
        "docs": "/docs",
        "health": "/health",
        "openai_compatible": {
            "models": "/v1/models",
            "chat": "/v1/chat/completions"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    # 启动服务
    uvicorn.run(
        app,
        host=settings.graph_service_host,
        port=settings.graph_service_port,
        log_level=settings.log_level.lower()
    )

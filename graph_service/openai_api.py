"""
OpenAI兼容的API接口
用于集成OpenWebUI
"""
import uuid
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, AsyncIterator
from loguru import logger
import time
import json

from .graph import compile_graph
from .state import GraphState
from .utils import extract_result_summary
from utils import get_token_tracker


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

        # 开始 Token 统计
        request_id = str(uuid.uuid4())[:8]
        token_tracker = get_token_tracker()
        token_tracker.start_request(request_id, user_message)

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

        # 执行图
        graph_instance = get_graph()

        if request.stream:
            # 流式响应 - 使用 astream() 实时返回
            logger.info("使用流式模式执行图")
            return StreamingResponse(
                _stream_response(graph_instance, initial_state, request.model, request_id, token_tracker),
                media_type="text/event-stream"
            )
        else:
            # 非流式响应 - 使用 ainvoke() 等待完成
            logger.info("使用非流式模式执行图")
            final_state = await graph_instance.ainvoke(
                initial_state,
                config={"recursion_limit": 100}  # 增加递归限制到 100，支持多 Agent 串行执行
            )

            # 构建响应
            response_text = final_state["final_answer"]

            logger.info(f"OpenAI API准备返回响应,长度: {len(response_text)} 字符")
            logger.debug(f"响应内容: {response_text[:200]}...")

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

            # 结束 Token 统计
            token_tracker.end_request()

            logger.info("OpenAI API响应已构建,准备返回")
            return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"OpenAI API处理失败: {e}")
        # 结束 Token 统计（即使出错也要记录）
        token_tracker.end_request()
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


async def _stream_response(
    graph,
    initial_state: GraphState,
    model: str,
    request_id: str = None,
    token_tracker = None
) -> AsyncIterator[str]:
    """
    生成流式响应

    Args:
        graph: LangGraph 图实例
        initial_state: 初始状态
        model: 模型名称
        request_id: 请求 ID（用于 token 统计）
        token_tracker: Token 统计器

    Yields:
        SSE格式的数据块
    """
    try:
        chat_id = f"chatcmpl-{int(time.time())}"
        created_time = int(time.time())

        # 用于累积最终答案
        accumulated_content = ""

        # 使用 astream() 流式执行图
        async for chunk in graph.astream(
            initial_state,
            stream_mode="updates",  # 获取状态更新
            config={"recursion_limit": 100}
        ):
            # chunk 格式: {node_name: state_update}
            for node_name, state_update in chunk.items():
                logger.info(f"流式输出 - 节点: {node_name}, 更新: {list(state_update.keys())}")
                logger.debug(f"流式输出 - 完整更新: {state_update}")

                # 格式化节点输出
                content = _format_node_output(node_name, state_update)

                if content:
                    accumulated_content += content

                    # 发送内容块
                    response_chunk = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "content": content
                                },
                                "finish_reason": None
                            }
                        ]
                    }

                    yield f"data: {json.dumps(response_chunk, ensure_ascii=False)}\n\n"

        # 发送结束标记
        end_chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
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

        # 结束 Token 统计并发送统计信息
        token_stats = None
        if token_tracker and request_id:
            token_stats = token_tracker.end_request()

        # 在 [DONE] 之前发送 Token 统计信息（作为特殊消息）
        if token_stats and token_stats.get("total_input_tokens", 0) > 0:
            stats_content = _format_token_stats(token_stats)
            stats_chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": stats_content
                        },
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(stats_chunk, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

        logger.info(f"流式响应完成，总长度: {len(accumulated_content)} 字符")

    except Exception as e:
        logger.error(f"流式响应生成失败: {e}")

        # 结束 Token 统计（即使出错也要记录）
        if token_tracker and request_id:
            token_tracker.end_request()

        # 发送错误信息
        error_chunk = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": f"\n\n❌ 错误: {str(e)}\n"
                    },
                    "finish_reason": "stop"
                }
            ]
        }
        yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


def _format_token_stats(stats: Dict[str, Any]) -> str:
    """
    格式化 Token 统计信息为可视化输出

    Args:
        stats: Token 统计字典

    Returns:
        格式化的 Markdown 文本
    """
    if not stats:
        return ""

    llm_calls = len(stats.get("llm_calls", []))
    input_tokens = stats.get("total_input_tokens", 0)
    output_tokens = stats.get("total_output_tokens", 0)
    total_tokens = input_tokens + output_tokens
    cost = stats.get("estimated_cost_usd", 0)

    # 格式化为紧凑的统计信息
    output = "\n\n---\n\n"
    output += "<details>\n"
    output += "<summary>📊 <b>Token 统计</b></summary>\n\n"
    output += f"| 指标 | 数值 |\n"
    output += f"|------|------|\n"
    output += f"| LLM 调用次数 | {llm_calls} |\n"
    output += f"| 输入 Token | {input_tokens:,} |\n"
    output += f"| 输出 Token | {output_tokens:,} |\n"
    output += f"| 总 Token | {total_tokens:,} |\n"
    output += f"| 预估成本 | ${cost:.4f} |\n"
    output += "\n</details>\n"

    return output


def _format_node_output(node_name: str, state_update: Dict[str, Any]) -> str:
    """
    格式化节点输出

    Args:
        node_name: 节点名称
        state_update: 状态更新

    Returns:
        格式化后的输出文本
    """
    try:
        # 路由节点
        if node_name == "router":
            agent_plan = state_update.get("agent_plan", [])
            if agent_plan:
                output = "\n🔀 **路由决策**\n\n"
                for i, plan in enumerate(agent_plan, 1):
                    agent_name = plan.get("agent", "")
                    task = plan.get("task", "")
                    output += f"{i}. **{agent_name}**: {task}\n"
                output += "\n"
                return output
            return ""

        # ReAct 思考节点 - 从 next_action 读取当前思考结果
        elif node_name == "react_think":
            next_action = state_update.get("next_action", {})
            if next_action:
                thought = next_action.get("thought", "")
                action_type = next_action.get("action_type", "")
                tool_name = next_action.get("tool_name", "")
                params = next_action.get("params", {})

                if thought:
                    # 使用纯 Markdown 格式，默认展开
                    output = "\n#### 🤔 思考中...\n\n"
                    output += f"```\n{thought}\n```\n\n"

                    # 如果有行动决策，也显示出来
                    if action_type == "TOOL":
                        output += f"🔧 **准备执行工具**: `{tool_name}`\n"
                        if params:
                            output += f"**参数**: `{json.dumps(params, ensure_ascii=False)}`\n"
                        output += "\n"
                    elif action_type == "FINISH":
                        output += "✅ **准备完成任务**\n\n"

                    return output
            return ""

        # ReAct 观察节点
        elif node_name == "react_observe":
            execution_history = state_update.get("execution_history", [])
            if execution_history:
                last_record = execution_history[-1]
                observation = last_record.get("observation", "")
                action = last_record.get("action", {})

                if observation:
                    # 获取工具名称
                    tool_name = action.get("tool", "") if isinstance(action, dict) else ""

                    # 尝试提取结构化摘要
                    summary = extract_result_summary(tool_name, observation) if tool_name else None

                    # 使用纯 Markdown 格式，默认展开
                    output = "\n#### 📊 观察结果\n\n"

                    # 如果有摘要，先显示摘要
                    if summary:
                        output += f"> 📌 **摘要**: {summary}\n\n"

                    # 前端流式展示：不截断，显示完整结果
                    # 使用代码块包裹，保持格式
                    output += f"```\n{observation}\n```\n\n"

                    return output
            return ""

        # 最终答案节点
        elif node_name == "final_answer":
            final_answer = state_update.get("final_answer", "")
            if final_answer:
                return final_answer
            return ""

        # 其他节点（例如 switch_agent_node）
        else:
            # 检查是否有 Agent 切换信息
            current_agent_index = state_update.get("current_agent_index")
            agent_plan = state_update.get("agent_plan", [])

            if current_agent_index is not None and agent_plan:
                if current_agent_index < len(agent_plan):
                    current_plan = agent_plan[current_agent_index]
                    agent_name = current_plan.get("agent", "")
                    return f"\n🔄 **切换到 Agent**: {agent_name}\n\n"

            return ""

    except Exception as e:
        logger.error(f"格式化节点输出失败 ({node_name}): {e}")
        return ""

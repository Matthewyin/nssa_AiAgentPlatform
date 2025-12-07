"""
Gemini RAG MCP Server
提供 Gemini File Search RAG 工具集
"""
import asyncio
import sys
import os
import json
from typing import Any, Dict, List
from mcp.server import Server
from mcp.types import Tool, TextContent
from loguru import logger
from pathlib import Path
import yaml
from string import Template

# 加载 LLM 配置获取 Gemini API Key
def load_llm_config() -> Dict[str, Any]:
    """加载 LLM 配置"""
    config_path = Path(__file__).parent.parent.parent / "config" / "llm_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    template = Template(content)
    content = template.safe_substitute(os.environ)
    return yaml.safe_load(content)

def get_gemini_rag_config() -> dict:
    """
    获取 Gemini RAG 独立配置

    优先使用 llm_config.yaml 中的 gemini_rag 配置节
    如果不存在，回退到 providers.gemini 配置
    """
    config = load_llm_config()

    # 优先使用独立的 gemini_rag 配置
    rag_config = config.get("gemini_rag", {})
    if rag_config:
        return rag_config

    # 回退到 providers.gemini 配置（兼容旧配置）
    gemini_config = config.get("providers", {}).get("gemini", {})
    return {
        "api_key": gemini_config.get("api_key", ""),
        "model": gemini_config.get("rag_model", "") or gemini_config.get("model", "gemini-2.5-flash")
    }

def get_gemini_api_key() -> str:
    """获取 Gemini RAG API Key"""
    rag_config = get_gemini_rag_config()
    api_key = rag_config.get("api_key", "")

    # 如果配置值是环境变量占位符，从环境变量读取
    if not api_key or api_key.startswith("${"):
        api_key = os.environ.get("GEMINI_API_KEY", "")

    if not api_key:
        raise ValueError("未配置 GEMINI_API_KEY，请在 .env 或环境变量中设置")
    return api_key

def get_gemini_rag_model() -> str:
    """获取 Gemini RAG 检索使用的模型"""
    rag_config = get_gemini_rag_config()
    return rag_config.get("model", "gemini-2.5-flash")

# 创建 MCP Server 实例
app = Server("gemini-rag-mcp")

# 初始化 Gemini Client（延迟初始化）
_genai_client = None

def get_genai_client():
    """获取 Gemini GenAI Client（延迟初始化）"""
    global _genai_client
    if _genai_client is None:
        from google import genai
        api_key = get_gemini_api_key()
        _genai_client = genai.Client(api_key=api_key)
        logger.info("Gemini GenAI Client 初始化完成")
    return _genai_client

@app.list_tools()
async def list_tools() -> List[Tool]:
    """列出所有可用的 Gemini RAG 工具"""
    tools = [
        Tool(
            name="gemini_rag.list_stores",
            description="列出所有 Gemini File Search Store（知识库）",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="gemini_rag.list_documents",
            description="列出指定知识库中的所有文档",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_name": {
                        "type": "string",
                        "description": "知识库名称，如 fileSearchStores/xxx 或简短名称"
                    }
                },
                "required": ["store_name"]
            }
        ),
        Tool(
            name="gemini_rag.search",
            description="在指定知识库中进行 RAG 语义检索",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_name": {
                        "type": "string",
                        "description": "知识库名称，如 fileSearchStores/xxx 或简短名称"
                    },
                    "query": {
                        "type": "string",
                        "description": "检索查询内容"
                    }
                },
                "required": ["store_name", "query"]
            }
        ),
    ]
    return tools

async def _list_stores() -> str:
    """列出所有知识库"""
    try:
        client = get_genai_client()
        stores = []
        for store in client.file_search_stores.list():
            stores.append({
                "name": store.name,
                "display_name": getattr(store, "display_name", "") or "",
                "create_time": str(getattr(store, "create_time", "")) if hasattr(store, "create_time") else ""
            })
        return json.dumps({"success": True, "stores": stores, "count": len(stores)}, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"列出知识库失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

async def _list_documents(store_name: str) -> str:
    """列出指定知识库中的文档"""
    try:
        client = get_genai_client()
        if not store_name.startswith("fileSearchStores/"):
            store_name = f"fileSearchStores/{store_name}"
        documents = []
        for doc in client.file_search_stores.documents.list(parent=store_name):
            documents.append({
                "name": doc.name,
                "display_name": getattr(doc, "display_name", "") or "",
                "size_bytes": getattr(doc, "size_bytes", 0),
                "create_time": str(getattr(doc, "create_time", "")) if hasattr(doc, "create_time") else ""
            })
        return json.dumps({"success": True, "documents": documents, "count": len(documents)}, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"列出文档失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


async def _search(store_name: str, query: str) -> str:
    """在指定知识库中进行 RAG 检索"""
    try:
        client = get_genai_client()
        from google.genai import types

        if not store_name.startswith("fileSearchStores/"):
            store_name = f"fileSearchStores/{store_name}"

        # 使用 file_search 工具进行 RAG 检索
        rag_model = get_gemini_rag_model()
        logger.info(f"使用模型 {rag_model} 进行 RAG 检索")
        response = client.models.generate_content(
            model=rag_model,
            contents=query,
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[store_name]
                        )
                    )
                ]
            )
        )

        # 提取检索结果
        result_text = response.text if hasattr(response, "text") else ""

        # 提取引用来源
        grounding_chunks = []
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "grounding_metadata") and candidate.grounding_metadata:
                metadata = candidate.grounding_metadata
                if hasattr(metadata, "grounding_chunks"):
                    for chunk in metadata.grounding_chunks:
                        grounding_chunks.append({
                            "source": getattr(chunk, "source", "") or "",
                            "content": getattr(chunk, "content", "") or ""
                        })

        return json.dumps({
            "success": True,
            "query": query,
            "store": store_name,
            "answer": result_text,
            "sources": grounding_chunks
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"RAG 检索失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """调用指定的工具"""
    logger.info(f"调用工具: {name}, 参数: {arguments}")

    try:
        if name == "gemini_rag.list_stores":
            result = await _list_stores()
        elif name == "gemini_rag.list_documents":
            store_name = arguments.get("store_name", "")
            if not store_name:
                result = json.dumps({"success": False, "error": "缺少 store_name 参数"}, ensure_ascii=False)
            else:
                result = await _list_documents(store_name)
        elif name == "gemini_rag.search":
            store_name = arguments.get("store_name", "")
            query = arguments.get("query", "")
            if not store_name or not query:
                result = json.dumps({"success": False, "error": "缺少 store_name 或 query 参数"}, ensure_ascii=False)
            else:
                result = await _search(store_name, query)
        else:
            result = json.dumps({"success": False, "error": f"未知工具: {name}"}, ensure_ascii=False)

        return [TextContent(type="text", text=result)]

    except Exception as e:
        error_msg = f"工具 {name} 执行失败: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))]


async def main():
    """启动 MCP Server"""
    logger.info("启动 Gemini RAG MCP Server...")
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    asyncio.run(main())

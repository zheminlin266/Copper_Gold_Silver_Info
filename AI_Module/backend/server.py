"""
AI_Module — FastAPI 服务

主要端点:
  POST /api/chat      — 流式聊天（RAG 检索 + OpenRouter LLM）
  POST /api/suggest   — 追问建议
  GET  /api/health    — 健康检查
  POST /api/rebuild-index — 重建知识库索引

启动:
  python -m backend.server
  uvicorn backend.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.chat_util import (
    ChatMessage,
    friendly_error,
    get_openrouter_client,
    is_allowed_origin,
    sanitize,
    session_id_of,
    validate_last_user,
)
from backend.config import (
    CORS_ORIGIN,
    MAX_TOKENS,
    OPENROUTER_API_KEY,
    PORT,
    SUGGEST_MAX_TOKENS,
    SUGGEST_TEMPERATURE,
    TEMPERATURE,
    ensure_dirs,
    models,
)
from backend.persona import (
    SUGGEST_SYSTEM,
    build_suggest_prompt,
    build_system_prompt,
    parse_suggestions,
)
from backend.rag_engine import build_index, get_index_stats, search

# ── 日志 ────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_module")

# ── 启动/关闭 ───────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时自动构建知识库索引。"""
    ensure_dirs()
    logger.info("Building knowledge base index...")
    try:
        count = build_index(force=False)
        logger.info(f"Index ready: {count} chunks")
    except Exception as e:
        logger.warning(f"Index build skipped: {e}")
    yield


app = FastAPI(
    title="AI_Module",
    description="RAG-powered personal AI chat module",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGIN.split(",") if CORS_ORIGIN != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── 健康检查 ─────────────────────────────────────────


@app.get("/api/health")
async def health():
    """健康检查 + 索引状态。"""
    stats = get_index_stats()
    return {
        "status": "ok",
        "has_index": stats["has_index"],
        "chunk_count": stats["chunk_count"],
        "models": models(),
    }


# ── 重建索引 ─────────────────────────────────────────


@app.post("/api/rebuild-index")
async def rebuild_index():
    """强制重建知识库索引。"""
    try:
        count = build_index(force=True)
        return {"status": "ok", "chunk_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 聊天 ─────────────────────────────────────────────


@app.post("/api/chat")
async def chat(request: Request):
    """
    流式聊天端点。

    Request body:
      { messages: [{ role: "user"|"assistant", content: string }], sessionId?: string }

    Response: text/plain 流式输出，每个 chunk 是 LLM 生成的 token。
    """
    # 1. Origin 校验
    if not is_allowed_origin(request):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not set")

    # 2. 解析请求
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 3. 净化消息
    messages = sanitize(body.get("messages"))
    if not validate_last_user(messages):
        raise HTTPException(status_code=400, detail="Last message must be from the user")

    # 4. RAG 检索
    query = messages[-1]["content"]
    retrieved_chunks = search(query)

    # 5. 构建 prompt
    system_prompt = build_system_prompt(retrieved_chunks)

    # 6. 组装消息
    api_messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]
    for m in messages:
        api_messages.append({"role": m["role"], "content": m["content"]})

    logger.info(f"Chat: query='{query[:80]}...', chunks={len(retrieved_chunks)}, history={len(messages)}")

    return StreamingResponse(
        _stream_chat(api_messages, request),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_chat(
    messages: list[dict],
    request: Request,
) -> AsyncGenerator[str, None]:
    """
    调用 OpenRouter API 流式生成，带模型故障转移。
    参考 pedromello.cc 的 streamReply 逻辑。
    """
    client = get_openrouter_client()
    model_list = models()
    last_error: Exception | None = None
    produced = False

    async def try_model(model: str) -> AsyncGenerator[str, None]:
        nonlocal produced
        try:
            async with client.stream(
                "POST",
                "/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "stream": True,
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise _http_error(response.status_code, body.decode())

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]  # strip "data: "
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            produced = True
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except Exception as e:
            raise

    for model in model_list:
        try:
            async for token in try_model(model):
                yield token
            if produced:
                return  # 成功，退出故障转移循环
        except Exception as e:
            last_error = e
            if produced:
                # 已产出部分内容，追加错误提示
                msg = friendly_error(e)
                yield msg
                return
            # 未产出内容，继续下一个模型
            logger.warning(f"Model {model} failed (no output yet): {e}")

    # 所有模型都失败
    if last_error:
        yield friendly_error(last_error)
    else:
        yield "\n\n[No models available. Try again later.]"


def _http_error(status: int, body: str) -> Exception:
    """构造带状态码的异常。"""
    err = Exception(body)
    err.status_code = status  # type: ignore[attr-defined]
    return err


# ── 追问建议 ─────────────────────────────────────────


@app.post("/api/suggest")
async def suggest(request: Request):
    """
    追问建议端点。

    Request body:
      { messages: [...], sessionId?: string }

    Response: { suggestions: string[] }
    """
    if not is_allowed_origin(request):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not OPENROUTER_API_KEY:
        return {"suggestions": []}

    try:
        body = await request.json()
    except Exception:
        return {"suggestions": []}

    messages = sanitize(body.get("messages"))
    if not messages:
        return {"suggestions": []}

    prompt = build_suggest_prompt(messages)
    model_list = models()
    client = get_openrouter_client()

    for model in model_list:
        try:
            response = await client.post(
                "/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SUGGEST_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": SUGGEST_TEMPERATURE,
                    "max_tokens": SUGGEST_MAX_TOKENS,
                },
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                suggestions = parse_suggestions(text)
                if suggestions:
                    return {"suggestions": suggestions}
        except Exception:
            continue

    return {"suggestions": []}


# ── 启动入口 ─────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

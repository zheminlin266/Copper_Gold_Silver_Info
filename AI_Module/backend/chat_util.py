"""
Chat 工具函数 — Origin 校验、消息净化、HTTP 客户端。

参考 pedromello.cc 的 lib/chat-util.ts，适配 Python/FastAPI 环境。
"""

from __future__ import annotations

import re
from typing import TypedDict
from urllib.parse import urlparse

import httpx
from fastapi import Request

from backend.config import MAX_HISTORY, MAX_CHARS, CORS_ORIGIN, OPENROUTER_API_KEY

# ── 类型 ────────────────────────────────────────────

class ChatMessage(TypedDict):
    role: str  # "user" | "assistant"
    content: str


# ── Origin 校验 ─────────────────────────────────────


def is_allowed_origin(request: Request) -> bool:
    """
    轻量滥用防护：仅服务同源浏览器请求。

    Origin 头由浏览器在跨域和 POST 请求中发送；
    我们接受其 host 匹配请求 host（覆盖生产 + 预览部署）或 localhost。
    """
    origin = request.headers.get("origin")
    if not origin:
        return False

    try:
        origin_host = urlparse(origin).hostname
    except Exception:
        return False

    if origin_host is None:
        return False

    # 本地开发
    if origin_host in ("localhost", "127.0.0.1", "::1"):
        return True

    # 匹配请求 host
    host = request.headers.get("host", "")
    allowed = {host}
    # 也允许 CORS_ORIGIN 中配置的域名
    if CORS_ORIGIN and CORS_ORIGIN != "*":
        for u in CORS_ORIGIN.split(","):
            try:
                h = urlparse(u.strip()).hostname
                if h:
                    allowed.add(h)
            except Exception:
                pass

    return origin_host in allowed


# ── 消息净化 ────────────────────────────────────────


def sanitize(raw: object) -> list[ChatMessage]:
    """
    校验并清理消息数组。
    - 过滤非法结构
    - 单条截断到 MAX_CHARS
    - 只保留最后 MAX_HISTORY 轮
    """
    if not isinstance(raw, list):
        return []

    cleaned: list[ChatMessage] = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        cleaned.append(ChatMessage(
            role=str(role),
            content=content[:MAX_CHARS],
        ))

    return cleaned[-MAX_HISTORY:]


def validate_last_user(messages: list[ChatMessage]) -> bool:
    """验证最后一条消息来自用户。"""
    return len(messages) > 0 and messages[-1]["role"] == "user"


# ── OpenRouter 客户端 ────────────────────────────────


def get_openrouter_client() -> httpx.AsyncClient:
    """返回配置了 OpenRouter 认证的 HTTP 客户端。"""
    return httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": CORS_ORIGIN if CORS_ORIGIN != "*" else "http://localhost:8000",
            "X-Title": "AI_Module",
        },
        timeout=60.0,
    )


# ── 错误处理 ────────────────────────────────────────


def friendly_error(err: Exception, contact_email: str = "") -> str:
    """
    将 OpenRouter 错误转为用户友好文案。
    参考 pedromello.cc 的 friendlyError()。
    """
    msg = str(err).lower()

    # 检查 HTTP 状态码
    status = getattr(err, "status_code", None) or getattr(err, "status", None)

    if status == 429 or "rate" in msg and "limit" in msg:
        return "\n\n[I'm getting a lot of questions right now — give it a moment and try again.]"
    if status == 402 or any(w in msg for w in ("credit", "quota", "insufficient", "payment")):
        contact = f" — reach me at {contact_email}" if contact_email else ""
        return f"\n\n[My chat is out of credit at the moment{contact}.]"
    if status == 404 or any(w in msg for w in ("not found", "no endpoints", "no allowed")):
        return "\n\n[That model isn't available right now. Try again shortly.]"

    return "\n\n[Sorry — I hit a snag answering that. Try again in a moment.]"


# ── Session ID ──────────────────────────────────────


def session_id_of(raw: object) -> str | None:
    """将客户端提供的 session id clamp 到安全长度。"""
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:200]
    return None

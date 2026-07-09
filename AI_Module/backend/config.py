"""
AI_Module 配置模块。所有可配置项集中管理，通过环境变量覆盖默认值。
"""

import os
from pathlib import Path

# ── 路径 ───────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge-base"
CHROMA_DB_DIR = KNOWLEDGE_BASE_DIR / ".chroma_db"

# ── RAG ────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers 模型
CHUNK_SIZE = 500                       # 每个 chunk 的 token 估算上限
CHUNK_OVERLAP = 50                     # chunk 之间的重叠 token
RETRIEVAL_K = 5                        # 检索返回的 chunk 数量

# ── LLM ────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

DEFAULT_MODELS = [
    "anthropic/claude-sonnet-4.6",
    "google/gemini-2.0-flash-001",
]

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "")

MAX_TOKENS = 1024
TEMPERATURE = 0.6
SUGGEST_MAX_TOKENS = 200
SUGGEST_TEMPERATURE = 0.7

# ── 安全 ───────────────────────────────────────────
MAX_HISTORY = 20       # 历史消息最大轮数
MAX_CHARS = 4000       # 单条消息最大字符数
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "*")

# ── 服务 ───────────────────────────────────────────
PORT = int(os.getenv("PORT", "8000"))


def models() -> list[str]:
    """返回模型列表：环境变量覆盖 > 默认值。"""
    env = OPENROUTER_MODEL.strip()
    if env:
        return [m.strip() for m in env.split(",") if m.strip()]
    return DEFAULT_MODELS


def ensure_dirs() -> None:
    """确保必要的目录存在。"""
    KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

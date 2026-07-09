"""
RAG 引擎 — 文档加载、分块、向量化、检索。

数据流:
  knowledge-base/*.md → Chunks → Embeddings → ChromaDB
  用户 query → Embedding → ChromaDB.search → Top-K Chunks

依赖: sentence-transformers, chromadb
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TypedDict

import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer

from backend.config import (
    KNOWLEDGE_BASE_DIR,
    CHROMA_DB_DIR,
    EMBEDDING_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    RETRIEVAL_K,
)

logger = logging.getLogger(__name__)

# ── 类型 ────────────────────────────────────────────

class Chunk(TypedDict):
    """知识库中的一个文本块。"""
    id: str
    text: str
    metadata: dict[str, str]


# ── 嵌入模型（单例） ────────────────────────────────

# sentence-transformers 模型，用于向量化文本
# all-MiniLM-L6-v2: 384维，~80MB，速度快，适合本地运行
_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


# ── ChromaDB（单例） ────────────────────────────────

_chroma_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None


def _get_collection() -> chromadb.Collection:
    global _chroma_client, _collection
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    if _collection is None:
        _collection = _chroma_client.get_or_create_collection(
            name="knowledge",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


# ── 文档加载 ────────────────────────────────────────


def _load_markdown_files(directory: Path) -> list[dict]:
    """
    递归加载目录下的所有 .md 文件。
    返回 [{path, content}, ...]。
    """
    files = []
    for md_file in sorted(directory.rglob("*.md")):
        # 跳过隐藏目录
        if any(part.startswith(".") for part in md_file.parts):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            if content.strip():
                files.append({
                    "path": str(md_file.relative_to(directory)),
                    "content": content,
                })
        except Exception:
            logger.warning(f"Cannot read {md_file}, skipping")
    return files


# ── 分块 ────────────────────────────────────────────


def _split_into_chunks(
    text: str,
    source: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    将文本按段落+标题分割为 chunk。
    策略: 优先按 ## 标题分段；过长的段落再按句子切分。

    ponytail: 使用简单字符估算 token 数（英文 ~4 char/token，中文 ~1.5 char/token），
    不引入 tiktoken 依赖。对于个人知识库规模来说精度足够。
    上限: 混合中英文时估算有偏差，但对于 500 token 的 chunk 目标误差在可接受范围。
    """
    chunks: list[Chunk] = []
    # 按 ## 标题分段
    sections = _split_by_headings(text)

    for heading, section_text in sections:
        # 估算 token 数 (简单平均: 英文 4 char/token, 中文 1.5 char/token)
        est_tokens = _estimate_tokens(section_text)

        if est_tokens <= chunk_size:
            chunk_id = _make_chunk_id(source, heading, section_text)
            chunks.append(Chunk(
                id=chunk_id,
                text=f"{heading}\n\n{section_text}".strip() if heading else section_text.strip(),
                metadata={"source": source, "heading": heading or ""},
            ))
        else:
            # 段落过长，按句子切分
            sub_chunks = _split_long_section(
                heading, section_text, source, chunk_size, overlap
            )
            chunks.extend(sub_chunks)

    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """按 ## 标题分割文本，返回 [(heading, body), ...]。"""
    import re
    # 匹配 ## 开头的标题行
    pattern = r"^## .+$"
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        if re.match(pattern, line):
            if current_body:
                body = "\n".join(current_body).strip()
                if body:
                    sections.append((current_heading, body))
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)

    if current_body:
        body = "\n".join(current_body).strip()
        if body:
            sections.append((current_heading, body))

    # 如果没有找到任何标题，整篇作为一个 section
    if not sections:
        sections.append(("", text.strip()))

    return sections


def _split_long_section(
    heading: str,
    text: str,
    source: str,
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    """将过长的段落按句子切分为多个 chunk，保留 overlap。"""
    import re
    # 按句子分割（中英文兼容）
    sentences = re.split(r"(?<=[。！？.!?\n])\s*", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0

    for i, sentence in enumerate(sentences):
        sent_tokens = _estimate_tokens(sentence)
        if current_tokens + sent_tokens > chunk_size and current:
            # 保存当前 chunk
            chunk_text = "\n".join(current)
            chunk_id = _make_chunk_id(source, heading, chunk_text)
            full_heading = f"{heading} (part {len(chunks) + 1})" if heading else f"(part {len(chunks) + 1})"
            chunks.append(Chunk(
                id=chunk_id,
                text=f"{full_heading}\n\n{chunk_text}".strip(),
                metadata={"source": source, "heading": heading or ""},
            ))
            # overlap: 保留最后几句
            overlap_sentences = _calc_overlap_sentences(current, overlap)
            current = overlap_sentences
            current_tokens = sum(_estimate_tokens(s) for s in current)

        current.append(sentence)
        current_tokens += sent_tokens

    if current:
        chunk_text = "\n".join(current)
        chunk_id = _make_chunk_id(source, heading, chunk_text)
        full_heading = f"{heading} (part {len(chunks) + 1})" if (heading and chunks) else heading
        chunks.append(Chunk(
            id=chunk_id,
            text=f"{full_heading}\n\n{chunk_text}".strip() if full_heading else chunk_text.strip(),
            metadata={"source": source, "heading": heading or ""},
        ))

    return chunks


def _calc_overlap_sentences(sentences: list[str], overlap_tokens: int) -> list[str]:
    """从句子列表末尾选取 overlap 数量的句子。"""
    result: list[str] = []
    total = 0
    for s in reversed(sentences):
        total += _estimate_tokens(s)
        result.insert(0, s)
        if total >= overlap_tokens:
            break
    return result


def _estimate_tokens(text: str) -> int:
    """
    简单 token 估算。
    ponytail: 不引入 tiktoken。英文 ~4 char/token，中文 ~1.5 char/token。
    对于知识库管理场景足够——chunk 大小影响的是检索粒度，而非模型上下文窗口。
    """
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    english_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + english_chars / 4)


def _make_chunk_id(source: str, heading: str, text: str) -> str:
    """基于内容生成稳定的 chunk ID，避免重复索引。"""
    raw = f"{source}|{heading}|{text[:200]}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ── 公共 API ────────────────────────────────────────


def build_index(force: bool = False) -> int:
    """
    加载知识库，分块，向量化，存入 ChromaDB。
    返回索引的 chunk 总数。
    如果 force=False 且索引已存在，则跳过。
    """
    collection = _get_collection()

    # 检查是否已有索引
    existing = collection.count()
    if existing > 0 and not force:
        logger.info(f"Index already has {existing} chunks, skipping rebuild")
        return existing

    # 清空重建
    if existing > 0:
        logger.info(f"Clearing {existing} existing chunks...")
        # ChromaDB 没有 delete_collection 的简便方法，重建 collection
        global _chroma_client, _collection
        _chroma_client.delete_collection("knowledge")
        _collection = None
        _collection = _chroma_client.get_or_create_collection(
            name="knowledge",
            metadata={"hnsw:space": "cosine"},
        )
        collection = _collection

    # 加载文件
    files = _load_markdown_files(KNOWLEDGE_BASE_DIR)
    if not files:
        logger.warning(f"No markdown files found in {KNOWLEDGE_BASE_DIR}")
        return 0

    logger.info(f"Found {len(files)} markdown files")

    # 分块
    all_chunks: list[Chunk] = []
    for f in files:
        chunks = _split_into_chunks(f["content"], f["path"])
        all_chunks.extend(chunks)

    logger.info(f"Created {len(all_chunks)} chunks from {len(files)} files")

    if not all_chunks:
        return 0

    # 向量化并存入
    model = get_embedding_model()
    texts = [c["text"] for c in all_chunks]
    ids = [c["id"] for c in all_chunks]
    metadatas = [c["metadata"] for c in all_chunks]

    logger.info(f"Generating embeddings for {len(texts)} chunks...")
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    # 批量写入 ChromaDB
    collection.add(
        ids=ids,
        embeddings=embeddings,  # type: ignore[arg-type]
        documents=texts,
        metadatas=metadatas,  # type: ignore[arg-type]
    )

    logger.info(f"Index built: {len(all_chunks)} chunks")
    return len(all_chunks)


def search(query: str, k: int = RETRIEVAL_K) -> list[Chunk]:
    """
    检索与 query 最相关的 k 个知识库 chunk。
    返回按相似度降序排列的 Chunk 列表。
    """
    collection = _get_collection()
    if collection.count() == 0:
        logger.warning("Index is empty, returning no results")
        return []

    model = get_embedding_model()
    query_embedding = model.encode([query], show_progress_bar=False).tolist()

    results = collection.query(
        query_embeddings=query_embedding,  # type: ignore[arg-type]
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    chunks: list[Chunk] = []
    if results["ids"] and results["ids"][0]:
        for i, chunk_id in enumerate(results["ids"][0]):
            chunks.append(Chunk(
                id=chunk_id,
                text=results["documents"][0][i] if results["documents"] else "",
                metadata=results["metadatas"][0][i] if results["metadatas"] else {},
            ))

    return chunks


def get_index_stats() -> dict:
    """返回索引统计信息。"""
    collection = _get_collection()
    return {
        "chunk_count": collection.count(),
        "knowledge_base_dir": str(KNOWLEDGE_BASE_DIR),
        "has_index": collection.count() > 0,
    }

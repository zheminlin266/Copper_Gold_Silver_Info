# AI_Module — 架构设计文档

## 概述

AI_Module 是一个可嵌入个人网站的 AI 聊天模块，通过 RAG（检索增强生成）技术，让访客可以跟你"对话"——AI 基于你提供的知识库回答关于你的工作、经历、项目等问题。

**核心理念**（参考 pedromello.cc）：AI 就是"你的数字分身"，以第一人称、用你的声音回答来访者的问题。

## 与 pedromello.cc 的关键差异

| 维度 | pedromello.cc | AI_Module |
|------|--------------|-----------|
| LLM 网关 | OpenRouter | OpenRouter（相同） |
| 知识来源 | 硬编码 Persona + Substack RSS | **RAG 从本地 Markdown 知识库检索** |
| 外部信息 | 动态拉取 Substack 文章 | **不使用任何外部/网络信息** |
| 部署方式 | Vercel (Next.js API Routes) | 独立 Python 后端 + 可嵌入前端 |
| 可观测性 | Langfuse | 可选，推荐 OpenTelemetry |

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      用户网站                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │              ai-chat.tsx (前端浮窗)                 │  │
│  │  · FAB 按钮 → 聊天面板                              │  │
│  │  · 流式渲染回复                                     │  │
│  │  · 会话管理（多轮对话）                              │  │
│  │  · 建议追问                                         │  │
│  └──────────────┬────────────────────────────────────┘  │
│                 │ POST /api/chat                        │
│                 │ POST /api/suggest                     │
└─────────────────┼──────────────────────────────────────┘
                  │
┌─────────────────▼──────────────────────────────────────┐
│            backend/server.py (FastAPI)                  │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Origin 校验   │  │ 消息 Sanitize│  │ 流式响应      │ │
│  │ (同源保护)    │  │ (长度/数量)   │  │ (SSE)        │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                         │                               │
│         ┌───────────────┼───────────────┐              │
│         ▼               ▼               ▼              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Persona  │  │ RAG Engine   │  │  OpenRouter  │     │
│  │ 人设+护栏 │  │ 检索相关上下文│  │  LLM 调用    │     │
│  └──────────┘  └──────┬───────┘  └──────────────┘     │
│                       │                                 │
└───────────────────────┼─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              RAG Engine (rag_engine.py)                  │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐   │
│  │ Document │   │  Chunk   │   │  Embed + Store   │   │
│  │ Loader   │──▶│  Splitter│──▶│  (ChromaDB)      │   │
│  │ .md 文件  │   │ 按标题分段│   │  sentence-       │   │
│  └──────────┘   └──────────┘   │  transformers     │   │
│                                 └────────┬─────────┘   │
│                                          │              │
│                              查询时: embed → search     │
│                                          │              │
│                                 ┌────────▼─────────┐   │
│                                 │  Retrieve Top-K  │   │
│                                 │  相关 Chunk       │   │
│                                 └──────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 数据流

```
1. 用户提问
   ↓
2. server.py 接收请求 → 校验 Origin → sanitize 消息
   ↓
3. 用户 query → rag_engine.search(query, k=5)
   ↓ (embedding)
4. ChromaDB 向量检索 → 返回 Top-K 相关 chunk
   ↓
5. persona.py.build_system_prompt(retrieved_chunks)
   → 组装: 人设 + 知识库上下文 + 护栏规则
   ↓
6. 调用 OpenRouter API（流式）
   ↓
7. 逐 token 返回前端 → ai-chat.tsx 渲染
   ↓
8. 流结束后 → 调用 /api/suggest 生成 3 条追问
```

## 技术选型

### 后端
- **框架**: FastAPI（轻量、异步、原生支持流式响应）
- **嵌入模型**: sentence-transformers `all-MiniLM-L6-v2`（384维，<100MB，本地运行）
- **向量数据库**: ChromaDB（嵌入式、持久化、Python 原生）
- **LLM 网关**: OpenRouter（模型故障转移、统一 API）
- **默认模型**: `anthropic/claude-sonnet-4.6` → `google/gemini-2.0-flash-001`

### 前端
- **框架无关**: 纯 TypeScript/JSX 组件，可嵌入任何 React/Next.js 项目
- **动画**: Framer Motion（与 pedromello.cc 一致）
- **样式**: Tailwind CSS（与 pedromello.cc 一致）

## 安全设计

| 层级 | 措施 |
|------|------|
| 传输层 | Origin 校验（仅允许同源请求） |
| 输入层 | 消息数组类型校验 + 单条 ≤4000 字符 + 历史 ≤20 轮 |
| 模型层 | Guardrails 提示词（禁止越狱、禁止代写代码、禁止私人问题） |
| 部署层 | API_KEY 仅存于服务端环境变量，前端不可见 |

## 部署方案

### 方案 A: 本地开发 / 自托管
```bash
cd backend
pip install -r requirements.txt
python server.py  # 默认 http://localhost:8000
```

### 方案 B: 与前端网站集成
- 前端网站通过 `/api/chat` 和 `/api/suggest` 代理到 Python 后端
- 或 CORS 配置允许前端域名

### 方案 C: 单一仓库部署
- 将 Python 后端作为子进程或 Docker 容器
- 前端网站同级部署

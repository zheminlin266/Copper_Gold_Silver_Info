# AI_Module — 工作流详解

## 完整请求处理流程

### 第一阶段：用户提问 → 上下文检索

```
用户输入: "你做过哪些增长设计的项目？"
              │
              ▼
┌─────────────────────────────────────────────┐
│ 1. 前端 ai-chat.tsx                         │
│    · 构造 POST /api/chat                    │
│    · body: { messages: [...], sessionId }   │
│    · 携带当前会话完整历史                     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 2. server.py POST /api/chat                 │
│    · isAllowedOrigin(req) → 校验同源         │
│    · sanitize(body.messages) → 清理输入       │
│    · 提取最后一条 user message 作为 query     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 3. rag_engine.py search(query, k=5)         │
│    · 用 sentence-transformers 将 query 向量化 │
│    · ChromaDB 相似度检索                     │
│    · 返回 Top-5 最相关的知识库 chunk          │
│                                                 │
│    示例返回:                                    │
│    ┌──────────────────────────────────────┐    │
│    │ Chunk 1 (相似度 0.89)                │    │
│    │ ## Jusbrasil 增长设计               │    │
│    │ 2021-2025，负责增长与商业化设计...   │    │
│    │                                      │    │
│    │ Chunk 2 (相似度 0.82)                │    │
│    │ ## 项目：设备管控                    │    │
│    │ 遏制律师事务所账号共享，提升 20%...  │    │
│    │                                      │    │
│    │ Chunk 3-5 ...                        │    │
│    └──────────────────────────────────────┘    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
          (进入第二阶段)
```

### 第二阶段：组装 Prompt → LLM 生成

```
┌─────────────────────────────────────────────┐
│ 4. persona.py build_system_prompt(chunks)    │
│                                                 │
│    组装顺序:                                    │
│    ┌──────────────────────────────────────┐    │
│    │ [1] PERSONA — 你是谁、怎么说话        │    │
│    │     "你是张三，一名资深后端工程师..."   │    │
│    │                                      │    │
│    │ [2] KNOWLEDGE_BASE — 检索到的上下文   │    │
│    │     "以下是你知识库中相关的部分：       │    │
│    │      ---                             │    │
│    │      ## Jusbrasil 增长设计           │    │
│    │      2021-2025...                    │    │
│    │      ---                             │    │
│    │      ## 项目：设备管控..."            │    │
│    │                                      │    │
│    │ [3] CITING — 引用规则                 │    │
│    │     "引用时提及来源文件名..."          │    │
│    │                                      │    │
│    │ [4] GUARDRAILS — 护栏规则             │    │
│    │     · 只用知识库内容回答              │    │
│    │     · 不知道就说不知道               │    │
│    │     · 不写代码、不聊无关话题          │    │
│    │     · ...                            │    │
│    └──────────────────────────────────────┘    │
│                                                 │
│    将 system prompt + 历史消息组装为:            │
│    messages = [                                 │
│      { role: "system", content: systemPrompt }, │
│      ...history,  // 历史对话                    │
│      { role: "user", content: "你做过哪些..." }  │
│    ]                                            │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 5. OpenRouter API 调用（模型故障转移）        │
│                                                 │
│    for model in [claude-sonnet-4.6,             │
│                  gemini-2.0-flash-001]:          │
│      try:                                       │
│        stream = openrouter.chat.completions     │
│          .create(                               │
│            model=model,                         │
│            messages=messages,                   │
│            stream=True,                         │
│            temperature=0.6,                     │
│            max_tokens=1024                      │
│          )                                      │
│        → 第一个成功产生输出的模型获胜             │
│      except → 下一个模型                         │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
          (进入第三阶段)
```

### 第三阶段：流式返回 → 前端渲染 → 追问建议

```
┌─────────────────────────────────────────────┐
│ 6. 流式返回 (SSE via ReadableStream)          │
│                                                 │
│    server.py:                                  │
│    for chunk in stream:                       │
│      if chunk.choices[0].delta.content:       │
│        yield chunk                            │
│                                                 │
│    返回: Content-Type: text/plain              │
│          Transfer-Encoding: chunked            │
│          X-Accel-Buffering: no                 │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 7. 前端 ai-chat.tsx 流式渲染                 │
│                                                 │
│    · ReadableStream.getReader() 逐块读取       │
│    · 每收到一个 chunk:                         │
│      - 创建/更新 response activity             │
│      - 标记 streaming: true                   │
│      - 显示闪烁光标 ▎                          │
│    · 流结束:                                   │
│      - 标记 streaming: false                   │
│      - 显示 Copy 按钮                          │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 8. 生成追问建议 POST /api/suggest             │
│                                                 │
│    · 将完整对话发送给 LLM                       │
│    · 使用专门的 SUGGEST_SYSTEM prompt          │
│    · LLM 返回 JSON: ["问题1", "问题2", "问题3"]│
│    · 前端渲染为可点击的建议按钮                  │
│                                                 │
│    示例:                                       │
│    ┌──────────────────────────────────────┐    │
│    │ Keep exploring                       │    │
│    │ ┌────────────────────────────────┐   │    │
│    │ │ Jusbrasil 期间最有挑战的项目是？│   │    │
│    │ └────────────────────────────────┘   │    │
│    │ ┌────────────────────────────────┐   │    │
│    │ │ 你是怎么用数据驱动设计决策的？   │   │    │
│    │ └────────────────────────────────┘   │    │
│    │ ┌────────────────────────────────┐   │    │
│    │ │ 设备管控项目的具体方案是什么？   │   │    │
│    │ └────────────────────────────────┘   │    │
│    └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

## RAG 索引构建流程

知识库更新后，需要重建索引：

```
knowledge-base/*.md
       │
       ▼
┌──────────────────────────────┐
│ Document Loader              │
│ · 遍历所有 .md 文件           │
│ · 按 --- 或 ## 标题分段       │
│ · 保留文件名作为来源          │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Chunk Splitter               │
│ · 每个段落作为一个 chunk      │
│ · chunk_size: ~500 tokens    │
│ · chunk_overlap: 50 tokens   │
│ · 保留 metadata:             │
│   {source, heading, position} │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Embedding + Storage          │
│ · all-MiniLM-L6-v2 向量化    │
│ · 存入 ChromaDB (持久化)      │
│ · collection: "knowledge"    │
└──────────────────────────────┘

索引文件位置: knowledge-base/.chroma_db/
```

## 会话管理

```
前端维护:
{
  sessions: [
    {
      id: "abc123",
      title: "增长设计项目",      // 首条消息截断
      createdAt: 1234567890,
      updatedAt: 1234567999,
      activities: [
        { id, type: "prompt", body: "你做过哪些..." },
        { id, type: "response", text: "我在 Jusbrasil...", streaming: false },
        { id, type: "prompt", body: "Jusbrasil 最有挑战的..." },
        { id, type: "response", text: "最有挑战的是...", streaming: false },
      ]
    },
    // ...更多会话
  ],
  currentId: "abc123"
}
```

- 会话存储在前端内存（关闭即丢失，类似 pedromello.cc 的极简设计）
- sessionId 传给后端用于 Langfuse 追踪（可选）
- 历史消息随每次请求发送，后端不存储会话

## 模型故障转移策略

```
请求 → claude-sonnet-4.6
         ├── 成功 → 返回结果
         └── 失败 (429/402/404/网络错误)
              └── 已产生输出? 
                   ├── 是 → 追加错误提示，结束
                   └── 否 → gemini-2.0-flash-001
                              ├── 成功 → 返回结果
                              └── 失败 → 返回友好错误信息
```

## 环境变量

```env
# 必需
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxx

# 可选
OPENROUTER_MODEL=anthropic/claude-sonnet-4.6,google/gemini-2.0-flash-001  # 覆盖默认模型列表
CORS_ORIGIN=https://your-site.com                                          # CORS 允许的域名
PORT=8000                                                                  # 服务端口
```

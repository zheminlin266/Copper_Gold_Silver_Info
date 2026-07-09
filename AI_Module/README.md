# AI_Module

一个可嵌入个人网站的 AI 聊天模块，基于 RAG（检索增强生成）技术，用你自己的知识库回答问题。

**参考**: [pedromello.cc](https://www.pedromello.cc/) 的 "Ask me anything" 模块架构，但知识来源从硬编码 Persona 改为本地 Markdown 知识库检索。

## 特性

- **RAG 驱动** — 从本地 Markdown 知识库检索相关上下文，不依赖外部信息
- **流式响应** — SSE 逐 token 返回，体验丝滑
- **模型故障转移** — 第一个模型失败自动切换（默认 Claude Sonnet → Gemini Flash）
- **护栏规则** — 严格的回答边界：只谈知识库内容、不写代码、不聊私人话题
- **多轮对话** — 前端会话管理，支持历史记录
- **追问建议** — 每轮对话后自动生成 3 条后续问题
- **同源保护** — Origin 校验，防止 API 被外部滥用
- **自适应 UI** — 移动端全屏、桌面端右下角浮窗

## 文件结构

```
AI_Module/
├── README.md                    # 本文件
├── ARCHITECTURE.md              # 架构设计文档
├── WORKFLOW.md                  # 工作流详解
├── .env.example                 # 环境变量模板 → 复制为 .env
├── requirements.txt             # Python 依赖
│
├── knowledge-base/              # 你的知识库（Markdown 文件）
│   └── example-profile.md       # 示例 → 替换为你的内容
│
├── backend/                     # Python 后端
│   ├── server.py                # FastAPI 主服务（/api/chat, /api/suggest, /api/health）
│   ├── rag_engine.py            # RAG 引擎（文档加载 → 分块 → 向量化 → 检索）
│   ├── persona.py               # 人设定义 + 护栏规则 + 提示词构建
│   ├── chat_util.py             # 工具函数（Origin 校验、消息净化、错误处理）
│   └── config.py                # 配置中心
│
└── frontend/                    # 前端组件
    └── ai-chat.tsx              # React 聊天浮窗（可直接嵌入 Next.js 项目）
```

## 快速开始

### 1. 安装依赖

```bash
cd AI_Module

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 OPENROUTER_API_KEY
```

### 3. 编写知识库

在 `knowledge-base/` 目录下创建 Markdown 文件：

```
knowledge-base/
├── about-me.md         # 个人介绍
├── work-experience.md  # 工作经历
├── projects.md         # 项目经验
└── ...                 # 任意 .md 文件
```

建议使用 `##` 标题分隔不同主题，每个段落作为独立的检索单元。

参考 `example-profile.md` 的格式。

### 4. 启动服务

```bash
cd AI_Module
python -m backend.server
```

服务启动后：
- 自动构建知识库索引（首次）
- API 在 `http://localhost:8000` 可用

### 5. 验证

```bash
# 健康检查
curl http://localhost:8000/api/health

# 测试聊天
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"介绍一下你自己"}]}'
```

### 6. 集成到网站

#### Next.js 项目

将 `frontend/ai-chat.tsx` 复制到你的 `components/` 目录，然后在 layout 中引入：

```tsx
import { AiChat } from "@/components/ai-chat";

export default function Layout({ children }) {
  return (
    <>
      {children}
      <AiChat
        apiBase="http://localhost:8000"  // 后端地址（生产环境用同域代理）
        label="Ask me anything"
        suggestions={[
          "What do you work on?",
          "Tell me about your projects",
          "What's your approach?",
        ]}
        emptyMessage="Ask me about my work, experience, and projects."
      />
    </>
  );
}
```

#### 生产环境

建议配置 Nginx 或其他反向代理，将 `/api/chat` 和 `/api/suggest` 代理到 Python 后端，避免跨域问题：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/api/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
    proxy_buffering off;  # 关键：支持流式响应
}
```

## 更新知识库

修改 `knowledge-base/` 下的 Markdown 文件后，重建索引：

```bash
curl -X POST http://localhost:8000/api/rebuild-index
```

## 自定义人设

编辑 `backend/persona.py` 中的 `PERSONA` 变量，修改 AI 的说话风格和行为：

```python
PERSONA = """
You are [你的名字/角色]...
How you talk:
- [描述你的风格]
- [描述你的语气]
"""
```

`GUARDRAILS` 中的护栏规则通常不需要修改，但可以根据需要调整边界。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | 流式聊天（SSE） |
| `POST` | `/api/suggest` | 追问建议（返回 3 条） |
| `GET` | `/api/health` | 健康检查 + 索引状态 |
| `POST` | `/api/rebuild-index` | 强制重建知识库索引 |

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI | 异步、原生流式支持 |
| LLM 网关 | OpenRouter | 统一 API + 模型故障转移 |
| 嵌入模型 | all-MiniLM-L6-v2 | 384维，本地运行，<100MB |
| 向量数据库 | ChromaDB | 嵌入式、持久化 |
| 前端 | React + Framer Motion + Tailwind | 与 pedromello.cc 一致的技术选型 |

## 参考

- [pedromello.cc](https://www.pedromello.cc/) — 原始参考实现
- [GitHub: mellosilvapedro-eng/portfolio](https://github.com/mellosilvapedro-eng/portfolio) — pedromello.cc 源代码
- [OpenRouter API Docs](https://openrouter.ai/docs) — LLM API 文档

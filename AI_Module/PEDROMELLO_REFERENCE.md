# pedromello.cc 源码参考笔记

本文档记录了 pedromello.cc AI 聊天模块的关键实现细节，供开发和优化 AI_Module 时参考。

源码仓库: https://github.com/mellosilvapedro-eng/portfolio

## 核心文件对照

| pedromello.cc | AI_Module | 说明 |
|---------------|-----------|------|
| `components/ai-chat.tsx` | `frontend/ai-chat.tsx` | 前端聊天浮窗 |
| `app/api/chat/route.ts` | `backend/server.py` (`/api/chat`) | 流式聊天 API |
| `app/api/suggest/route.ts` | `backend/server.py` (`/api/suggest`) | 追问建议 API |
| `lib/persona.ts` | `backend/persona.py` | 人设 + 护栏 |
| `lib/chat-util.ts` | `backend/chat_util.py` | 工具函数 |
| `lib/site.ts` | 知识库 `knowledge-base/*.md` | **差异点**: 硬编码 vs RAG 检索 |
| `lib/projects.ts` | 知识库 `knowledge-base/*.md` | **差异点**: 硬编码 vs RAG 检索 |
| `lib/substack.ts` | 无（不使用外部数据） | **差异点**: RSS 拉取 vs 无外部数据 |

## pedromello.cc 中值得关注的设计决策

### 1. 模型故障转移策略
```typescript
// chat/route.ts — 多模型 fallback
for (const model of models()) {
  try {
    // 流式调用
    // 第一个产生任何输出的模型获胜
    if (produced) return;
  } catch {
    // 未产出输出 → 下一个模型
    // 已产出输出 → 追加错误提示，不切换
  }
}
```

### 2. [[case:slug]] 内联案例链接
pedromello.cc 的 AI 回复中支持 `[[case:device-control]]` 语法，前端自动渲染为项目卡片。
AI_Module 未实现此功能（因知识库结构不同），但可参考其 `parseSegments()` + `CaseCard` 实现。

### 3. AbortController + turnSeq 竞态保护
```typescript
const turnSeq = useRef(0);
// 每次发送 turnSeq += 1
// 收到响应时检查 turnSeq 是否匹配，防止旧请求覆盖新结果
```

### 4. streaming 状态处理
```typescript
// 流式传输中不移除 layout prop，避免高度弹跳
// 流式结束后添加 Copy 按钮
if (content.streaming) {
  // 闪烁光标
}
```

### 5. Origin 校验
```typescript
export function isAllowedOrigin(req: Request): boolean {
  // 只允许 localhost 或请求 host 匹配 origin host
  // 覆盖 Vercel 预览部署的随机域名
}
```

### 6. 环境变量设计
- `OPENROUTER_API_KEY` — 必需
- `OPENROUTER_MODEL` — 可选，覆盖默认模型列表
- `LANGFUSE_*` — 可选，O11y 追踪

### 7. Langfuse 可观测性
pedromello.cc 通过 `instrumentation.ts` + `@langfuse/tracing` 实现了完整的 LLM 追踪。
AI_Module 可后续按需添加，当前版本未包含。

## AI_Module 相比 pedromello.cc 的改进/差异

| 维度 | pedromello.cc | AI_Module |
|------|--------------|-----------|
| **知识来源** | 硬编码 PERSONA + CV + caseStudies() | **RAG 从 Markdown 检索**，更灵活 |
| **更新方式** | 改代码 + 重新部署 | **改 Markdown + rebuild-index**，无需重启 |
| **知识扩展** | 需修改 persona.ts 代码 | **新增 .md 文件即可** |
| **外部数据** | Substack RSS 动态拉取 | **不使用外部数据**，隐私更安全 |
| **后端语言** | TypeScript (Next.js API Routes) | **Python (FastAPI)** |
| **部署** | 与 Next.js 网站一体 | **独立服务**，通过反向代理集成 |
| **语言支持** | 仅英文 | **支持中英文**（护栏规则中有多语言处理） |
| **可观测性** | Langfuse 完整追踪 | 当前未实现，预留扩展点 |

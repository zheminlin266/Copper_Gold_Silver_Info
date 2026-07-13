# Copper Gold Silver Info

黄金、白银和铜矿业供需信号的每日研究站点。内容由 Workbuddy 辅助收集和整理，Next.js 在构建时读取结构化 JSON，并由 Vercel 随 `main` 分支更新自动发布。

## 内容工作流

1. Workbuddy 完成公开信息收集、去重、事实核验和供需判断。
2. 将日报写入 `data/YYYY-MM-DD.json`；JSON 是页面唯一内容源。
3. 运行内容校验和本地预览。
4. 提交并推送 `main`，Vercel 自动构建和发布。

不使用 GitHub Actions、Vercel Cron 或网页 AI 模块生成日报内容。

## 本地运行

```bash
npm install
npm run validate:content
npm test
npm run dev
```

生产构建：

```bash
npm run build
```

## 页面

- `/`：最新日报摘要、供需信号和最近日报
- `/daily/YYYY-MM-DD`：每日完整信息页
- `/archive`：历史日报搜索和金属筛选

旧的 `Historical_Daily_Reports/*.html` 地址会永久重定向到新的日报路由。

## 内容约束

- 不手写日报 HTML；页面统一由 Next.js 组件生成。
- 首页和日报页不使用新闻配图。
- 不包含 AI 聊天和 WebGL 灯光效果。
- 外部事实、数字和判断必须保留来源 URL、日期、单位和上下文。
- `npm run validate:content` 失败时不得发布。

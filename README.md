# 金银铜供需信息

面向黄金、白银和铜的每日供需研究站点。内容由 Workbuddy 调用 DeepSeek-V4 PRO 收集、筛选和整理；Next.js 读取结构化 JSON，由 Vercel 随 `main` 分支更新自动发布。

生产站点：<https://copper-gold-silver-info.vercel.app>

## 更新频率与时间

- 每日更新一次，包括周末和节假日。
- Workbuddy 在北京时间（Asia/Shanghai）每天 07:00 开始执行。
- 当次日报的 `date` 是前一自然日。例如 7 月 14 日 07:00 执行时，生成 `data/2026-07-13.json`。
- 访谈检索覆盖报告日及此前两日，共三个自然日；X 原帖和新闻只覆盖报告日 00:00:00–23:59:59。
- 07:00 是任务开始时间，不是承诺上线时间。完成研究、来源核验、内容校验、构建和推送后，Vercel 才会发布。
- GitHub Actions 只运行内容校验、测试和构建，不生成日报。日报必须由 Workbuddy 执行研究流程。

## 信息如何收集

Workbuddy 负责工具调用和文件操作，DeepSeek-V4 PRO 负责候选信息分析与写作。完整步骤以 [Daily_Report_Workflow.md](./Daily_Report_Workflow.md) 为准。

信息分三部分收集：

1. 访谈：Podcast、Webcast、YouTube、会议访谈、Panel 和 Keynote，覆盖三个自然日。
2. X 原帖：只收录能够打开并确认作者、发布时间和正文的原始帖子，覆盖报告日。
3. 新闻：同时检索英文和中文来源，覆盖报告日。

信源优先级为：监管文件、交易所公告、公司公告、官方统计等一手来源；其次是 Reuters、Mining.com 等可靠媒体。种子 CSV 用于提高发现效率，不是硬性白名单；发现可靠的新来源时可以纳入，并记录在 `search_log.new_sources_discovered`。

## 筛选方法论

每条内容必须同时满足以下要求：

- 与黄金、白银或铜存在明确关系。
- 能解释供给、需求或两者的变化路径，而不只是泛泛谈价格。
- 发布时间落在对应窗口内；转载按原始事件或原始发布日判断。
- 使用可定位到具体内容的直接 URL，并核对标题、日期、主体和核心数字。
- 数字保留期间、单位、币种和口径；明确区分实际值、估计、市场一致预期、公司指引和分析判断。
- 同一事件只保留信息最完整、最接近一手来源的版本；访谈还要与此前两份日报去重。

纯价格复述、无供需因果的宏观评论、未经证实的传闻、无法核验的社交媒体内容和重复转载不进入正文。若某一部分没有合格内容，保留空数组，并在 `search_log` 记录检索范围和失败原因，不能编造内容填充版面。

## 呈现方法论

`data/YYYY-MM-DD.json` 是网站唯一内容源。页面按金属和供需方向组织信号，并把来源事实、研究解释和重要性分开呈现。首页自动展示最新日报和最近日期；日报页、搜索和归档也都由同一批 JSON 自动生成，因此每日更新不需要手写 HTML、首页卡片或搜索索引。

网站不包含 AI 聊天模块、新闻配图或 WebGL 灯光效果。

## 本地检查

```bash
npm install
npm run validate:content
npm test
npm run build
npm run dev
```

`npm run validate:content`、`npm test` 或 `npm run build` 任一失败时，不得推送发布。

## 页面与文件

- `/`：最新日报摘要、供需信号和最近日报
- `/daily/YYYY-MM-DD`：每日完整信息页
- `/archive`：全量日报搜索和金属筛选
- `data/daily_report_schema.json`：日报字段规范
- `Daily_Report_Workflow.md`：Workbuddy 每日执行规范
- `mining_people_broadcast_x_articles.csv`：人物与来源种子表

旧的 `Historical_Daily_Reports/*.html` 地址会永久重定向到对应的新日报路由。2026-06-30 至 2026-07-05 的 JSON 由旧 HTML 迁移：为保持旧链接，`date` 沿用旧版页面日期，实际覆盖窗口以各文件中的 `windows` 为准；原始 HTML 保留不改。

# 金银铜供需信息

面向黄金、白银和铜的每日供需研究站。将访谈、X 原帖与新闻整理为结构化日报，聚焦矿山、冶炼、库存、项目、政策与终端需求等可验证信号，不构成投资建议。

生产站点：https://metals.zhemin.ltd

## 功能

- 首页与 `/daily/YYYY-MM-DD` 展示日报；`/archive` 支持日期、关键词和金属检索。
- `TC` 提供外部铜库存、SMM 指数和本地 `Historical TC` 周度图表。
- 日报存于 `data/YYYY-MM-DD.json`；铜精矿 TC 存于 `data/smm_copper_concentrate_index_2026.csv`。

## 信息源

访谈覆盖 Podcast、Webcast、YouTube、会议访谈、Panel、Keynote 和公司演示，关注矿业管理层、研究者与官方机构。X 原帖只收录可核验作者、正文、时间和原帖链接的原创内容。新闻覆盖中英文，优先官方一手资料，其次可靠媒体和标明出处的行业转载。TC 用 SMM 周度评估与公开页面交叉核对，写入年度 CSV。

## 筛选方法

每条信号必须说明事件、金属、供需方向和关注理由，发布时间在日报窗口内，并附具体来源。纳入供给、需求、库存、项目和政策等有明确供需路径的变化。

保留数字的期间、单位、币种和口径，区分事实、估计、预期与研究判断。排除纯价格复述、无因果宏观评论、股价或估值观点、传闻、旧闻和重复转载。同一事件优先保留一手且完整版本；`importance` 补充规模、机制、时间、对比或不确定性判断。

## 更新与校验

日报内容以 JSON/CSV 为源，经过内容校验后由 Next.js 构建网页，Vercel 自动部署。详见 `Daily_Report_Workflow.md`。

本地检查：

```bash
npm install
npm run validate:content
npm test
npm run build
```

任一校验失败不得发布。

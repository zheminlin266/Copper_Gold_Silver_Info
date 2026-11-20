# 铜金供给信息跟踪

每周跟踪铜矿供给动态、产量影响与黄金行业要闻。

生产站点：https://metals.zhemin.ltd

维护：[Zhemin Lin（Zhemin）](https://www.zhemin.ltd/)。个人网站收录基本面研究、文章与其他项目。

## 功能

- 首页展示最新周报。`/weekly/YYYY-MM-DD` 以报告周的周一为日期。
- `/archive` 提供历期周报和历史日报检索，原日报链接为 `/daily/YYYY-MM-DD`。
- `TC` 提供外部铜库存、SMM 指数和本地 `Historical TC` 周度图表。
- 周报存于 `data/weekly/YYYY-MM-DD.json`，历史日报存于 `data/YYYY-MM-DD.json`。铜精矿 TC 存于 `data/smm_copper_concentrate_index_2026.csv`。

## 信息源

优先核对矿企公告、交易所和监管披露及可靠中英文行业报道。TC 使用可核验的 SMM 周度评估。

## 筛选方法

完整收录本周首次披露或有实质进展的重要铜矿事件。同一事件合并，保留来源、期间、单位和数字口径。综合分析注明产量影响的时间和兑现条件。

## 更新与校验

每周一北京时间 08:00 开始采集，覆盖前一周周一至周日。周报和 TC 经过校验后由 Next.js 构建并由 Vercel 自动部署。见[周报工作流](Weekly_Report_Workflow.md)。

本地检查：

```bash
npm install
npm run validate:content
npm test
npm run build
```

任一校验失败不得发布。

历史日报的数据规则见[日报工作流](Daily_Report_Workflow.md)。

# Copper Gold Silver Info

全球金银铜矿业供需信号每日跟踪系统。

## 项目结构

### 核心内容

- `index.html`：GitHub Pages 首页，列出每日信息页链接、标题和当日总结。
- `Historical_Daily_Reports/`：每日 HTML 日报存档。
- `mining_people_broadcast_x_articles.csv`：种子关注名单（人物、渠道、会议、背景与擅长方向）。

### 工作流定义

- `Daily_Report_Workflow.md`：日报固定产出流程（时间窗口、三 Part 采集规范、去重规则、校验标准）。

### 结构化数据层

- `data/daily_report_schema.json`：每日日报 JSON 结构定义。
- `data/conference_calendar.json`：从 CSV 提取的会议日历，用于高频搜索模式。
- `data/sources_discovered.json`：搜索过程中自动发现的新来源。
- `data/raw/`：采集脚本输出的原始数据（RSS、YouTube 监控结果）。
- `data/YYYY-MM-DD.json`：每日日报的结构化数据镜像。

### 采集脚本

- `scripts/rss_fetcher.py`：抓取 Reuters、Mining.com 和中文信源（SMM、SHMET）的 RSS，按金属和供需关键词筛选。
- `scripts/youtube_monitor.py`：用 YouTube Data API 或 RSS 监控 CSV 频道的新视频。
- `scripts/report_builder.py`：从 7 天 JSON 数据生成周度趋势简报。
- `scripts/requirements.txt`：Python 依赖清单。

### 资源

- `Sources/`：日报配图（Mining.com / Reuters / SMM 新闻原文图）。
- `x_outputs/`：X 搜索 raw materials 文本文件。

## 自动更新口径

日报按北京时间每日 07:00 更新。

- **Part 1（访谈）**：72 小时滚动窗口（T-3 至 T-1），覆盖 CSV 名单人物的公开 podcast、broadcast、webcast、YouTube interview 或视频访谈。连续日报间执行去重，避免同一访谈重复出现。
- **Part 2（X 原帖）**：单日窗口（T-1），纳入 CSV 中明确 X 账号发布、且涉及金银铜供需的原帖。主通道为 Browser Use + Chrome，备用通道为 Nitter RSS。
- **Part 3（新闻）**：单日窗口（T-1），同时搜索英文信源（Reuters、Mining.com）和中文信源（SMM、SHMET、中国黄金协会等），两者优先级一致。

每篇日报同步输出 JSON 结构化数据（`data/YYYY-MM-DD.json`），用于跨日查询和周度趋势简报生成。

## 数据采集脚本使用

```bash
# 安装依赖
pip install -r scripts/requirements.txt

# 抓取 RSS 新闻（默认取昨天北京时间）
python scripts/rss_fetcher.py

# 监控 YouTube 新视频（需要 YOUTUBE_API_KEY 环境变量）
YOUTUBE_API_KEY=your_key python scripts/youtube_monitor.py

# 生成周度趋势简报
python scripts/report_builder.py
```

脚本采集结果保存在 `data/raw/` 目录，作为 AI 会话生成日报时的输入参考。脚本失败不阻塞日报流程。

## 公开页面

<https://zheminlin266.github.io/Copper_Gold_Silver_Info/>

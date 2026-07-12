# Daily Report Workflow

本文档记录"每日金属矿业"日报的固定产出流程。日报目标是跟踪金、银、铜矿业的供给和需求信号，而不是只跟踪某一个固定名单。

## 0\. 定期任务计划

WorkBuddy 自动化任务 `每日矿业信息页更新（07:00 北京）` 每天 `07:00 Asia/Shanghai` 触发，执行完整的日报产出流程（搜索 → JSON → HTML → 首页更新 → Git push）。自动化 ID：`automation-1783322566762`，调度规则：`FREQ=DAILY;BYHOUR=7;BYMINUTE=0`。

GitHub Actions 的 `.github/workflows/pages.yml` 使用 UTC cron；与北京时间每天早上 7 点等价的表达式是：

`0 23 \* \* \*`

注意：`23:00 UTC` 对应下一自然日 `07:00 Asia/Shanghai`。不要把人工完成时间、日志写入时间或 UTC 7 点误认为日报计划触发时间。

### 0.1 数据采集脚本（可选预处理）

在 AI 会话启动前，可优先运行 `scripts/` 目录下的采集脚本，预先获取结构化数据：

* `scripts/rss\_fetcher.py`：抓取 Reuters、Mining.com 和中文信源的 RSS，按金属和供需关键词筛选，输出到 `data/raw/YYYY-MM-DD\_rss.json`
* `scripts/youtube\_monitor.py`：监控 CSV 中 YouTube 频道的新视频，输出到 `data/raw/YYYY-MM-DD\_youtube.json`

脚本采集结果作为 AI 会话的输入参考，减少手动浏览时间。脚本失败时不阻塞日报流程，AI 会话仍可手动搜索。

## 1\. 确定报告时间窗口

日报每天北京时间 07:00 生成。不同 Part 使用不同时间窗口：

### Part 1（访谈）：72 小时窗口

访谈内容使用 **72 小时滚动窗口**，覆盖报告日前三天的完整北京时间：

`T-3 00:00:00 至 T-1 23:59:59 Asia/Shanghai`

例如，`2026-07-06 07:00` 生成的报告，Part 1 覆盖：

`2026-07-03 00:00:00 至 2026-07-05 23:59:59 北京时间`

理由：访谈、播客和会议视频不是"每日"频率的内容，单日窗口导致大量合格内容被排除。

#### 72 小时窗口去重规则

由于窗口扩展到 72 小时，同一访谈可能在连续两到三天的日报中出现。必须执行去重：

1. **链接去重**：若某条访谈的 URL 已出现在 `data/` 目录下最近 2 天的 JSON 日报中，不再重复纳入当天正文。
2. **内容去重**：若同一嘉宾在同一事件中接受多个渠道采访（如 PDAC 期间的 CEO 访谈分别上传到 Mining Stock Daily 和 Soar Financial），只选择信息密度最高的一条纳入正文，其余在来源说明中提及。
3. **更新例外**：若同一访谈在窗口内更新了版本（如从无字幕版变为有字幕版），可以重新纳入，但需标注"更新版"。
4. **去重检查**：生成日报前，读取最近 2 天的 `data/YYYY-MM-DD.json` 中的 `part1\_broadcasts\[].url` 字段，作为去重参照。

### Part 2（X 原帖）：单日窗口

保持报告日前一天的完整北京时间窗口：

`T-1 00:00:00 至 T-1 23:59:59 Asia/Shanghai`

### Part 3（新闻）：单日窗口

保持报告日前一天的完整北京时间窗口：

`T-1 00:00:00 至 T-1 23:59:59 Asia/Shanghai`

## 2\. 确定信息范围

### 2.1 种子名单

`mining\_people\_broadcast\_x\_articles.csv` 是种子关注池，不是硬过滤器。

可纳入对象包括：

* CSV 中的矿业投资人、研究者、媒体人、企业家和高管
* CSV 中的矿业 conference、panel、访谈栏目和媒体信息源
* 金、银、铜矿业公司高管
* 中国矿业专家、地质/工程专家、协会和研究机构专家
* 项目负责人、地质专家、研究者、播客嘉宾
* 矿业媒体、可信数据账号和行业专家

只要内容明确涉及金、银、铜矿业供需，就可以纳入。若人物不在 CSV 中，必须补充：

* 人物姓名与职务
* 所属公司、机构或项目
* 涉及金属
* 与供给或需求的关系
* 信息来源链接

若来源是 conference / panel / 访谈栏目，也要补充到 CSV：

* 会议或栏目名称
* 官方网站、YouTube、媒体中心或 agenda 链接
* 主要覆盖金属和地区
* 应搜索的内容类型：interview、panel、keynote、webcast、company presentation、daily highlights、transcript
* 适合放入 Part 1 还是 Part 3；会议访谈、panel、webcast 和视频回放优先放入 Part 1

CSV 人物当前主要分为六类，搜索时不要只盯 X：

* 资源股投资人和通讯作者：Sprott、Katusa、Resource Maven、Gold Newsletter、The Daily Gold 等体系
* 地质/工程专家：Exploration Insights、Mercenary Geologist、Sprott 地质顾问、独立经济地质学家
* 媒体和访谈主持：Mining Stock Daily、Resource Talks、Soar Financial、Arcadia Economics 等
* 北美/欧洲/澳洲矿企高管：Barrick、Newmont、Agnico Eagle、Freeport、Ivanhoe、Rio Tinto、Glencore、Codelco、Teck 等
* 中国矿业专家和高管：紫金矿业、CMOC、江西铜业、山东黄金、招金矿业、中国黄金、铜陵有色、赤峰黄金等
* 会议和 panel 信息源：PDAC、Denver Gold Forum、Precious Metals Summit、Mining Indaba、Future Minerals Forum、Diggers \& Dealers、CHINA MINING、SMM 有色会展等

### 2.2 自动发现来源

搜索过程中发现的新人物、媒体或信息源，若不在 CSV 中，记录到 `data/sources\_discovered.json`：

```json
{
  "entries": \[
    {
      "name": "人物或来源名称",
      "type": "person | media | conference | company",
      "affiliation": "所属公司或机构",
      "metal\_focus": \["gold", "silver", "copper"],
      "discovered\_date": "2026-07-05",
      "discovered\_via": "通过哪条信号发现的",
      "source\_url": "信息来源链接",
      "verified": false
    }
  ]
}
```

`sources\_discovered.json` 中的条目经过人工确认后，合并回 `mining\_people\_broadcast\_x\_articles.csv` 种子名单。

## 3\. Part 1：Broadcast / Podcast / Webcast / YouTube 访谈

搜索 72 小时窗口内的新公开视频、音频访谈、conference panel、webcast、keynote、company presentation 或会议回放。

优先搜索入口：

* CSV 中标记为 `会议/Panel/访谈源` 的 conference 官方网站、agenda、media center、YouTube、LinkedIn 和 daily highlights
* Mining Stock Daily
* Resource Talks
* Soar Financial
* Sprott Insights / videos / webcasts
* YouTube
* 相关矿业公司官网、频道页和媒体页
* CSV 种子人物及延伸嘉宾

会议源搜索顺序：

1. 先看会议官方 agenda / speakers / media center / video / daily highlights。
2. 再搜会议名 + `gold` / `silver` / `copper` / `mining` / `CEO interview` / `panel` / `keynote` / `presentation`。
3. 对已发现的公司或嘉宾，回到公司官网和 YouTube 搜同日 replay、webcast、PDF presentation。
4. 若会议内容由媒体转发，优先保留官方链接；官方链接不存在时可用可信媒体链接，并在 source 里说明来源层级。

纳入条件：

* 发布时间在 72 小时窗口内
* **未出现在最近 2 天日报中**（去重检查，参见第 1 节）
* 内容为公开 podcast、broadcast、webcast、YouTube interview、conference interview、panel、keynote、company presentation 或会议视频回放
* 主题与金、银、铜矿业供需相关
* 能取得 transcript、caption、页面字幕，或可执行人工转录
* panel 或 keynote 至少要能识别发言人、会议名称、发布时间和核心供需观点

若找到合格访谈，页面需包含：

* 标题链接
* 发布日期
* 来源类型：podcast / webcast / YouTube / conference interview / panel / keynote / company presentation
* 一句话总结
* 嘉宾详细背景
* 涉及公司、项目和金属
* 供需重要性
* 深度总结
* 每 1-5 分钟中英文对应摘要，说明话题和主要观点

Transcript 优先级：

1. 官方 transcript
2. YouTube caption
3. 页面字幕
4. 人工转录音频或视频

若发现访谈但无公开 transcript，应执行人工转录。若环境缺少转录工具或网络权限，应先请求必要权限，不用占位内容冒充摘要。

若当天没有合格访谈（72 小时窗口内无新内容或所有内容已在前两天日报中出现过），Part 1 只显示：

`过去 72 小时内没有发现新的公开 podcast / broadcast / YouTube / conference panel 视频访谈。`

## 4\. Part 2：X / Twitter 原帖

X 内容只纳入可核验原帖，不根据截图、传言或无法读取的页面编写内容。

### 4.1 采集通道（主备双路）

#### 主通道：Browser Use / Chrome

当前标准方法是用 Browser Use 连接已经登录 X 的本地 Chrome，会话内直接做站内搜索，再逐条打开原帖核验。

使用独立 Chrome profile 做 X 搜索，避免每次连接主浏览器时弹出人工点击 Allow 的要求。

首次设置：

1. 启动专用 Chrome profile。端口值不要写死在公开报告或页面里；本地执行时用环境变量保存：

```powershell
$env:X\_CDP\_PORT='<local-debug-port>'
$env:X\_CHROME\_PROFILE='<local-x-chrome-profile-dir>'
Start-Process -FilePath 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' -ArgumentList @("--remote-debugging-port=$env:X\_CDP\_PORT","--user-data-dir=$env:X\_CHROME\_PROFILE",'https://x.com/home')
```

2. 在打开的 Chrome 窗口里手动登录 X。这个 profile 会保存登录态。

后续每次执行 X 搜索前：

1. 确认这个专用 Chrome 窗口仍然开着；如果关掉了，用上面的启动命令重新打开。
2. 在当前 shell 里指定 Browser Use 连接端口：

```powershell
$env:BU\_CDP\_URL='<local-cdp-url>'
```

3. 验证连接：

```powershell
browser-use --doctor
```

期望结果：

* `chrome running` 为 ok
* `daemon alive` 为 ok
* `active browser connections` 至少为 1
4. 验证 X 登录态：

```powershell
@'
new\_tab('https://x.com/home')
wait\_for\_load()
print(page\_info())
'@ | browser-use
```

页面应显示 `https://x.com/home`，并能在页面文本中看到已登录账号。若登录态失效，先在该专用 Chrome profile 里重新登录，不要用不可验证内容代替 X 原帖。

安全注记：remote debugging 端口打开时，本机其它进程理论上也能控制这个专用浏览器。只把它用于 X 搜索；搜索完成后可以关闭该 Chrome 窗口，下次按同一 profile 重启。该 profile 目录保存登录态，必须留在 `.gitignore` 中，不要提交到 public repo。

#### 备用通道：RSS / Nitter

当主通道（Browser Use）不可用——Chrome 窗口关闭、登录态失效、X 反爬升级或端口被占用——时，切换到备用通道：

1. 使用 Nitter 实例（如 `nitter.net`）的 RSS 端点获取公开推文：

```
   https://nitter.net/<handle>/rss
   ```

2. 对 CSV 中明确 X 账号的人物，批量请求 RSS feed。
3. RSS 获取的内容作为候选，仍需按第 4.2 节标准筛选。
4. 若 Nitter 也不可用，使用 `scripts/rss\_fetcher.py` 中的 X RSS 聚合功能（若已配置）。
5. 备用通道采集的帖子，在日报中标注 `source\_channel: "rss\_fallback"`。

**降级原则**：备用通道采集不到内容时，Part 2 写"当天无法验证 X 原帖"。不要伪造内容。备用通道的主要价值是保证采集通道不单一依赖 Browser Use。

### 4.2 搜索范围与筛选

搜索范围：

* CSV 中明确 X 账号
* 金、银、铜矿业公司官方账号
* 公司高管、项目负责人、研究者、矿业媒体和可信数据账号

执行顺序：

1. 先按种子账号池分批搜索，优先用 `from:handle` 组合查询，再叠加金 / 银 / 铜、mining、mine、project、production、supply、demand、permit、smelter、mill 等关键词。
2. 搜索结果先全部记入一个 raw materials 文本文件，保留：

   * 搜索 query
   * 账号
   * 原推链接
   * 搜索结果页可见文本
   * 原帖页面 `time datetime` 原始 UTC 时间
   * 换算后的北京时间
   * 初步筛选备注
   * 采集通道（browser\_use / rss\_fallback）
3. 对准备写入日报的候选帖，必须逐条打开状态页，再读取页面里的精确 `time datetime`。不要只看搜索结果页显示的"7月3日"之类日期，也不要只信 `since:` / `until:` 命中结果。
4. 最终是否归入当天日报，以北京时间窗口为准，不以 X 搜索命中窗口为准。

合格推文必须同时满足：

* 原帖可核验
* 原帖精确时间落在报告窗口内（单日 T-1）
* 内容涉及金、银、铜供需

供需主题包括：

* 矿山供给
* 库存
* 产量
* 项目建设
* 品位
* 融资
* 许可
* 工业需求
* 央行、ETF 或投资需求
* 冶炼、精炼、交割和物流约束

排除内容：

* 纯价格喊单
* 泛宏观情绪
* 无供需含义的转发
* 纯段子或情绪表达
* 无法验证的原帖文本
* 时间戳不在当天北京时间窗口内的命中结果

每条合格推文做成卡片，字段包括：

* 作者
* 账号
* 发布时间
* 金 / 银 / 铜标签
* 供给 / 需求标签
* 简短摘录
* 中文解读
* 为什么对供需重要
* 原推链接
* 采集通道

当搜索连接失败、读不到登录态或打不开原帖时，Part 2 写：

`当天无法验证 X 原帖。`

当搜索已完成，但 raw materials 最终没有筛出合格帖子时，Part 2 写：

`已完成 X 搜索，但当天未筛出符合条件的原帖。`

不得伪造推文内容，也不要把原始搜索命中和最终入选结果混为一谈。

## 5\. Part 3：金银铜供需新闻（英文 + 中文信源）

这是当前最稳定的信息来源模块。Part 3 同时覆盖英文和中文信源，两者优先级一致。

### 5.1 英文信源

优先检查：

* Reuters commodities
* Mining.com Copper
* Mining.com Gold
* Mining.com Silver
* Mining.com 上的 Reuters / Bloomberg 转载

### 5.2 中文信源

与英文信源同等优先级检查：

* **SMM 有色网**（`smm.cn`）：铜精矿 TC/RC、库存数据、冶炼动态、下游需求
* **中国黄金协会**（`cngold.org`）：黄金产量、矿山安全、技改公告
* **紫金矿业官网**（`zklymining.com` / `zijn.com.cn`）：投资者演示、业绩公告、项目进展
* **CMOC 官网**（`cmoc.com`）：产量数据、刚果铜钴动态
* **江西铜业官网**：铜冶炼、自产铜矿口径
* **山东黄金 / 招金矿业 / 中国黄金 / 铜陵有色官网**：金铜矿山运营动态
* **SHMET 上海有色金属网**（`shmet.com`）：铜、白银现货市场和产业链数据
* **中国矿业网 / 中国有色金属工业协会**：政策、行业统计

中文信源纳入主题与英文一致（见下方），但额外关注：

* 中国铜冶炼加工费（TC/RC）变化
* 中国黄金矿山安全检查和停产整顿
* 中国矿企海外并购和项目进展
* 中国进口铜精矿港口库存
* 中国白银工业需求（光伏、电子）

### 5.3 纳入条件

只纳入发布时间落在同一北京时间窗口内（单日 T-1），且与供需直接相关的新闻。

纳入主题包括：

* 新矿投产
* 老矿重启
* 扩产
* 许可推进
* 冶炼与精炼能力
* LME / COMEX 交割资格
* 库存变化
* 产量指导
* 项目融资
* 勘探、资源量、可研和资源转化
* ETF、央行、实物和投资需求
* 工业需求变化

每条新闻卡包含：

* 来源
* 标题链接
* 发布时间
* 金 / 银 / 铜标签
* 供给 / 需求标签
* 简短摘录
* 中文解读
* 为什么对供需重要
* 语言标记（`en` / `zh`）

若某一金属没有窗口内合格新闻，明确写：

`当天没有发现窗口内强供需新闻。`

不要用旧闻凑数。

### 5.4 信号去重

同一供需事件可能同时出现在英文和中文信源中（如 Codelco 铜矿停产同时被 Reuters 和 SMM 报道）。处理方式：

1. **同一事件**：若两条新闻报道同一事件（同一公司、同一项目、同一供需方向），选择信息更完整的一条作为主条目，另一条作为"也被报道"附注。
2. **判断标准**：同一公司名 + 同一项目/矿名 + 同一供需方向（供给或需求）= 同一事件。
3. **不同角度**：若英文侧重全球市场影响、中文侧重中国产业链影响，两条都保留，但分别标注视角差异。

## 6\. 结构化数据输出

每天生成日报 HTML 时，同步输出一份 JSON 结构化数据文件，保存到 `data/YYYY-MM-DD.json`。

JSON 结构定义见 `data/daily\_report\_schema.json`，核心字段：

```json
{
  "date": "2026-07-05",
  "report\_time": "2026-07-06T07:00:00+08:00",
  "windows": {
    "part1": {"start": "2026-07-03T00:00:00+08:00", "end": "2026-07-05T23:59:59+08:00"},
    "part2": {"start": "2026-07-05T00:00:00+08:00", "end": "2026-07-05T23:59:59+08:00"},
    "part3": {"start": "2026-07-05T00:00:00+08:00", "end": "2026-07-05T23:59:59+08:00"}
  },
  "part1\_broadcasts": \[
    {
      "title": "访谈标题",
      "url": "链接",
      "publish\_date": "2026-07-04",
      "source\_type": "podcast / webcast / YouTube / conference",
      "guest": {"name": "姓名", "background": "背景"},
      "metal\_tags": \["gold", "copper"],
      "supply\_demand": "supply / demand",
      "summary": "一句话总结",
      "detail": "深度总结",
      "companies": \["公司名"],
      "projects": \["项目名"]
    }
  ],
  "part2\_x\_posts": \[
    {
      "author": "作者",
      "handle": "账号",
      "publish\_time": "2026-07-05T14:30:00+08:00",
      "metal\_tags": \["copper"],
      "supply\_demand": "supply",
      "excerpt": "简短摘录",
      "interpretation": "中文解读",
      "importance": "为什么对供需重要",
      "url": "原推链接",
      "source\_channel": "browser\_use / rss\_fallback"
    }
  ],
  "part3\_news": \[
    {
      "source": "来源",
      "title": "标题",
      "url": "链接",
      "publish\_time": "2026-07-05T10:00:00+08:00",
      "metal\_tags": \["gold"],
      "supply\_demand": "demand",
      "excerpt": "简短摘录",
      "interpretation": "中文解读",
      "importance": "为什么对供需重要",
      "language": "en / zh",
      "duplicate\_of": null
    }
  ],
  "search\_log": {
    "part1\_searched": true,
    "part2\_searched": true,
    "part2\_channel": "browser\_use / rss\_fallback / failed",
    "part3\_sources\_checked": \["Reuters", "Mining.com", "SMM", "中国黄金协会"],
    "new\_sources\_discovered": \[]
  },
  "dedup\_log": {
    "part1\_deduped\_urls": \[],
    "part3\_deduped\_events": \[]
  }
}
```

JSON 文件是 HTML 日报的结构化镜像。AI 会话在生成 HTML 前，先构建 JSON，再从 JSON 生成 HTML。这样做的好处：

* 跨日数据可查询（如"过去 30 天铜供给信号有哪些"）
* 去重检查可直接读取 JSON 的 URL 字段
* 周度简报可从 7 天 JSON 聚合生成

## 7\. HTML 日报生成规范

### 7.1 基准模板

所有日报 HTML **必须严格套用** `Historical_Daily_Reports/mining_people_broadcast_x_digest_2026-07-07.html` 的结构格式。该文件是唯一基准模板（canonical template）。

页头品牌“每日金属矿业”的链接必须固定为以下绝对地址，不得改用 `../index.html`、`../../index.html` 或站点根目录的 `/index.html`：

```html
<a class="brand" href="https://zheminlin266.github.io/Copper_Gold_Silver_Info/">每日金属矿业</a>
```

生成新日报时只做三件事：
- 替换日期和覆盖日期
- 替换所有 Part 1/2/3 的内容文字
- 更新首页配图

**不改变任何 HTML 标签结构、class 名称、嵌套层级或区块顺序。**

### 7.2 强制结构要求

日报 HTML 必须包含以下结构，缺一不可：

| 区块 | 必须使用的标签/class | 说明 |
|------|---------------------|------|
| 语言 | `<html lang="zh-CN">` | 固定在 html 标签 |
| 导航 | `<nav class="topbar">` 含 6 个锚点 | brand + broadcast/xstream/news/tracker/sources |
| Hero | `<header class="hero">` 含 eyebrow/h1/hero-sub/meta-row/data-link-box | 覆盖窗口 + 金属 pill + JSON 链接 |
| 摘要 | `<section class="summary">` → `<div class="brief">` → `<h2>本期摘要</h2>` | 一段话覆盖 Part 1/2/3 核心发现 |
| Part 1 | `<section id="broadcast" class="section">` | section-head + section-note + pending 段落（或 grid 卡片） |
| Part 2 | `<section id="xstream" class="section">` | section-head + channel-badge + section-note + 内容 |
| Part 3 | `<section id="news" class="section">` | section-head + section-note + grid 卡片 + theme 金属总结 |
| Tracker | `<section id="tracker" class="section">` | section-head + theme ×3（Part 1/2/3） |
| Sources | `<section id="sources" class="section">` | section-head + theme ×3（英文/中文/结构化数据） |
| 字体 | Inter 400-800 via Google Fonts | 固定在 head |
| 样式 | `../assets/report.css` + `../assets/report-detail.css` | 两个 link |

### 7.3 卡片子结构

Part 2/3 的每条内容使用 `.card` 容器，内部子结构如下：

**Part 3 新闻卡片**（每条）：
```html
<div class="card">               <!-- 头条用 card feature -->
  <div class="tag">              <!-- 金属标签 + SUPPLY/DEMAND + 语言 pill -->
    <span>Au 金</span>
    <span>SUPPLY</span>
    <span class="pill lang-en">EN</span>   <!-- 或 lang-zh: ZH -->
  </div>
  <h3><a href="...">标题</a></h3>
  <p>正文（含 <strong> 加粗关键数据）</p>
  <div class="importance">
    <strong>供需重要性：</strong>中文解读和供需影响分析
  </div>
  <div class="source-meta">
    来源：<a href="...">来源名称</a> · YYYY-MM-DD HH:MM 北京时间
  </div>
</div>
```

**Part 2 X 帖子卡片**（每条）：
```html
<div class="card">
  <div class="tag">
    <span>Ag 银</span>
    <span>DEMAND</span>
  </div>
  <h3><a href="原推链接">标题</a></h3>
  <p><strong>@handle</strong>（人物背景）· YYYY-MM-DD HH:MM 北京时间</p>
  <p>原帖摘录</p>
  <div class="importance">
    <strong>中文解读：</strong>...
  </div>
  <div class="importance">
    <strong>供需重要性：</strong>...
  </div>
</div>
```

### 7.4 金属主题总结

Part 3 的 `.grid` 卡片列表后，必须追加三条 `<div class="theme">` 金属总结：

```html
<div class="theme">
  <h3>Au · GOLD</h3>
  <p>当日金供给/需求信号一句话汇总…</p>
</div>
<div class="theme">
  <h3>Ag · SILVER</h3>
  <p>当日银供给/需求信号一句话汇总…</p>
</div>
<div class="theme">
  <h3>Cu · COPPER</h3>
  <p>当日铜供给/需求信号一句话汇总…</p>
</div>
```

### 7.5 严禁使用的元素

日报 HTML **不得出现**以下结构（与 07-07 基准模板对比）：

| 禁止项 | 07-09 曾错误使用 | 正确做法 |
|--------|-----------------|---------|
| 语言标签缺 `pill` class | `<span class="lang-en">英文</span>` | `<span class="pill lang-en">EN</span>` |
| 双 importance div | 每条卡片两个独立 `importance` | 合并在一个 `importance` 内 |
| 缺 source-meta | 来源信息写在 `<p>` 标签内 | 使用独立 `<div class="source-meta">` |
| Part 3 标题不一致 | `金银铜供需新闻（英文 + 中文信源）` | `News · 金银铜供需新闻` |
| Tracker 用 grid+card | `<div class="grid"><div class="card">` | `<div class="theme"><h3>Part N · …</h3>` |
| Sources 用 grid+card | 同上 | 同上，用 three 分组 |
| Footer | `<footer>…</footer>` | 不需要 footer |
| 旧占位词 | `待补抓` / `Pending transcript` / `TODAY WEATHER` / `核心账号卡` | 该写什么写什么，无内容时用规定文案 |

### 7.6 Part 1/2 空内容文案

当某 Part 无内容时，使用固定文案，不改变结构：

- **Part 1 空**：段落用 `<p class="pending">`，内容为 `过去 72 小时内没有发现新的公开 podcast / broadcast / YouTube / conference panel 视频访谈。` 后附搜索来源说明。
- **Part 2 空**：段落用 `<p class="pending">`，内容为 `已完成 X 搜索（Playwright + Chrome），搜索了 N 个种子账号 + M 个官方公司账号，但当天未筛出涉及金银铜供需的可核验原帖。`
- **Part 2 失败**：段落用 `<p class="pending">`，内容为 `当天无法验证 X 原帖。主通道 Playwright 不可用，RSS 备用通道也无结果。`

### 7.7 生成校验清单

HTML 生成后必须通过以下检查（对齐第 11 节静态校验）：

- [ ] 5 个 id 齐全：`broadcast` / `xstream` / `news` / `tracker` / `sources`
- [ ] 页头“每日金属矿业”的 `href` 为 `https://zheminlin266.github.io/Copper_Gold_Silver_Info/`
- [ ] 语言标签使用 `pill lang-en` / `pill lang-zh`（不是裸 `lang-en` / `lang-zh`）
- [ ] 每条 Part 3 新闻有 `source-meta` div
- [ ] Tracker 和 Sources 用 `theme` 结构（非 grid+card）
- [ ] Part 3 标题为 `News · 金银铜供需新闻`
- [ ] Tracker 标题为 `信号跟踪`
- [ ] Sources 标题为 `来源与数据`
- [ ] Part 3 卡片末尾有三条金属 theme 总结（Au / Ag / Cu）
- [ ] 无 `<footer>` 元素
- [ ] 无任何旧占位词

---

## 8. 首页更新规则

首页 `index.html` 是日报目录页，采用参考图式纵向新闻列表布局。

每个日报占一个独立模块：

* 左侧：当天新闻配图
* 右侧：日报标题
* 小结独立成段
* 底部：Daily / 日期 / 主题标签
* 最右：箭头

日报标题统一为：

`YYYY-MM-DD 矿业人物 Broadcast \& 金银铜供需`

首页摘要必须覆盖：

* 当天有没有新访谈或视频，以及主要内容
* X 上是否有可验证供需原帖
* 英文和中文信源在金、银、铜供需上有什么新闻

首页不保留：

* 栏目结构板块
* 单独 Archive 板块
* 参考资料 Sources 板块
* Featured Reports 字样

## 9\. 图片处理

每条日报使用一张本地新闻配图。**严禁复用旧图，每一期日报必须使用当日独有的图片。**

### 9.1 图片来源优先级（严格按序，遇成立项即停止）

1. **当天新闻原文 `og:image`**：打开当天最重要的 Part 3 新闻原文（如 MINING.com、Reuters、SMM），检查页面 `<meta property="og:image">` 或文章主配图，下载保存
2. **当天新闻原文内嵌图**：若无 `og:image`，从原文正文中提取第一张有意义的配图（非 logo、非广告）
3. **同一金属/公司/项目的近期来源图**：从 `Sources/` 中已有的同主题图片选择，但必须是当天窗口内相关新闻的配图
4. **AI 生成（最后手段）**：仅当前三步均无可用的新闻图片时，才使用 ImageGen 生成。生成主题必须与当天最重要的一条供需新闻直接对应

图片保存到 `Sources/`，命名格式 `mining_{YYYY-MM-DD}_{slug}.{ext}`。

### 9.2 禁止项

- **禁止跳过前两步直接用 AI 生成**。除非当天所有新闻原文确实没有任何可用的配图
- **禁止复用旧日报的配图**（即使主题相近）
- 若最终使用 AI 生成，在日报 HTML 中不得暴露图片来源为 AI（图片本身无需标注，但 HTML 的 `alt` 属性应描述新闻主题而非生成方式）

### 9.3 记录

在 JSON 的 `search_log` 中记录图片来源：

```json
"image_source": {
  "method": "og_image | inline_image | existing_source | ai_generated",
  "source_url": "原图所在新闻 URL（og_image/inline_image 时填写）",
  "prompt": "若为 ai_generated，记录生成所用的 prompt"
}
```

## 10\. 链接内容校验

在 HTML 日报和 JSON 数据文件写入磁盘后，**必须**对每条带 URL 的内容执行链接校验：逐条打开链接，确认页面正文与已采集的信息一致。

### 10.1 校验范围

所有 Part 1/2/3 中对外部 URL 的引用，包括但不限于：

* Part 1 broadcast 的 `url` 字段（播客页面 / YouTube / 会议回放）
* Part 2 X 原帖的 `url` 字段（原推链接）
* Part 3 新闻的 `url` 字段（新闻正文链接）
* 首页 `index.html` 中各日报条目的 `href`
* HTML 日报中所有 `<a href>` 的外部链接

不需要校验的：项目内部相对路径（如 `../../data/`、`../assets/`）、锚点链接（`#broadcast`）、已在前一日校验过的引用。

### 10.2 校验标准

每条链接打开后，必须验证：

1. **URL 可访问**：HTTP 状态码 200，非 404/403/重定向到无关页面
2. **页面类型正确**：是新闻正文 / 播客页面 / X 原帖页面，而非聚合页、市场数据页或侧边栏摘要
3. **核心事实匹配**：页面正文中至少包含我们在日报中引用的核心数据或事件描述。例如：
   - 若日报写"智利5月铜产量 -12.9%"，原文中必须出现该百分比数字
   - 若日报写"Codelco 产量同比 -18.3%"，原文中必须出现对应的矿企名和降幅
   - 若日报引用某 CEO 访谈，页面中必须出现该 CEO 姓名和访谈内容

4. **未发生链接漂移**：URL 指向的页面标题/主题与日报中的标题一致或高度相关。如果打开后是一个完全不相关的页面（如钴市场数据页、网站首页），判定为链接错误

### 10.3 校验方法

对每条需要校验的链接，使用 WebFetch 工具获取页面内容，给定 prompt 提取关键事实（标题、核心数据、来源日期），与日报中已记录的信息对比。

若链接较多（>10 条），可以分批校验，或只校验"高优先级"链接：
- **高优先级**：Part 3 新闻链接（容易出错——聚合页 vs 原文）、新发现的网站
- **中优先级**：Part 2 X 原帖链接（X 链接通常稳定，但仍需确认可打开）
- **低优先级**：Part 1 播客/YouTube 链接、经常引用的已知网站（如 Mining Stock Daily）

### 10.4 校验失败处理

| 失败类型 | 处理方式 |
|---------|---------|
| URL 404/403 | 搜索正确链接替换；若找不到正确链接，标记 `[链接失效]` 并从 HTML 中去掉 `<a href>`，保留纯文本引用 |
| 页面类型错误（聚合页而非原文） | 从聚合页找到原文链接替换 |
| 核心事实不匹配 | 以原文为准修正日报中的数据和描述 |
| 链接漂移到不相关页面 | 同"页面类型错误"处理 |

所有校验失败和修正记录写入 `search_log` 的 `url_verification` 字段。

### 10.5 校验记录格式

在 JSON 的 `search_log` 中追加：

```json
"url_verification": {
  "checked": 12,
  "passed": 11,
  "failed": 1,
  "failures": [
    {
      "original_url": "https://www.mining.com/markets/commodity/cobalt/",
      "failure_type": "wrong_page_type",
      "detail": "链接指向钴商品市场聚合页，非新闻正文",
      "fixed_url": "https://www.mining.com/web/chiles-copper-output-manufacturing-production-plummet-in-may/",
      "fixed": true
    }
  ]
}
```

## 11\. 静态校验

生成后检查日报页：

* 文件存在
* 包含 `id="broadcast"`
* 包含 `id="xstream"`
* 包含 `id="news"`
* 包含 `id="tracker"`
* 包含 `id="sources"`
* 语言标签使用 `pill lang-en` / `pill lang-zh`（非裸 `lang-en` / `lang-zh`）
* 每条 Part 3 新闻有 `<div class="source-meta">`
* Tracker 和 Sources 使用 `<div class="theme">`（非 grid+card）
* Part 3 标题为 `News · 金银铜供需新闻`
* Tracker 标题为 `信号跟踪`，Sources 标题为 `来源与数据`
* Part 3 末尾有三条金属 theme 总结（Au / Ag / Cu）
* 无 `<footer>` 元素

检查首页：

* 包含"每日金属矿业"
* 包含 `Daily Reports`
* 包含每日信息页链接
* 包含当日总结
* 使用本地图片

检查 JSON 数据文件：

* `data/YYYY-MM-DD.json` 文件存在
* 包含 `date`、`part1\_broadcasts`、`part2\_x\_posts`、`part3\_news` 字段
* `part1\_broadcasts` 中的 URL 不在最近 2 天 JSON 的同字段中（去重验证）
* `part3\_news` 中的 `duplicate\_of` 字段已正确填写

首页不得包含：

* `Featured Reports`
* `栏目结构`
* `参考资料`
* `ARCHIVE`

日报不得包含旧占位词：

* `待补抓`
* `Pending transcript`
* `TODAY WEATHER`
* `核心账号卡`

## 12\. 搜索索引重建

日报 HTML 和首页更新后，**必须**重建搜索索引，确保首页搜索框能匹配到所有日报内容：

```bash
python scripts/build_search_index.py --check
```

`--check` 参数会在写入后运行完整性校验，确保：
- 所有非备份日报 HTML 都在索引中
- 无备份文件被意外索引
- 已知关键词（如 Codelco、KatusaResearch）可被搜索到

索引文件为 `data/search-index.json`，首页搜索框通过 `fetch("./data/search-index.json")` 加载。

## 13\. 发布流程

校验通过后：

1. 确认第 10 节链接内容校验已通过，无未修复的链接错误
2. 重建搜索索引：`python scripts/build_search_index.py --check`
3. 提交 Git commit（包含 HTML 日报、JSON 数据文件 和 search-index.json）
4. 推送 `main`
5. 检查公开页面是否返回 200

公开首页：

[https://zheminlin266.github.io/Copper\_Gold\_Silver\_Info/](https://zheminlin266.github.io/Copper_Gold_Silver_Info/)

GitHub Pages 配置为从 `main` 分支根目录直接提供，无需额外 `gh-pages` 分支。若页面返回旧内容，检查 `main` 分支 raw 文件是否已更新；若 raw 文件正确，通常是 Pages CDN 延迟，等待数分钟后再用 cache-bust 参数验证。

## 14\. 周度趋势简报

每周一日报附带一份周度趋势简报，保存到 `Weekly\_Reports/YYYY-WW.md`。

简报从过去 7 天的 `data/YYYY-MM-DD.json` 文件聚合生成，包含：

* 本周金、银、铜各金属的供需信号数量
* 本周最重要的 3-5 个供需事件
* 本周新发现的人物或来源（从 `sources\_discovered.json` 提取）
* 本周采集通道可用率（Part 2 成功天数 / 7）
* 与上周的简要对比

周度简报同时在首页以独立模块展示，链接格式：

`YYYY-WW 周度趋势简报`

## 15\. 会议日历

`data/conference\_calendar.json` 记录 CSV 中所有会议的日期和状态。

会议期间（会议日开始前 1 天至结束后 7 天），Part 1 搜索进入高频模式：

* 每天检查会议官方 agenda / media center / YouTube
* 会议回放和 transcript 上线后立即纳入（不受 72 小时窗口限制，但仍执行去重）
* 会议简报作为独立模块在首页展示

会议结束后 7 天内仍持续搜索会后发布的访谈和 transcript。


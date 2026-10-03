# 每日信息工作流

本文是 生成“金银铜供需信息”日报及执行每周 TC 更新的唯一执行规范。网站代码只负责展示；每日任务新增一份日报 JSON，周六任务还可以按第 9A 节追加一条 TC CSV 数据，不生成 HTML，不手工更新首页。页面用中文，如原文是英文请翻译成地道中文，在专有名词、术语时保留英文原词。

## 1. 不变量

- 时区统一为 `Asia/Shanghai`（UTC+8）。
- 每日 07:00 开始任务，全年执行。
- `RUN_DATE` 是任务开始日，`REPORT_DATE = RUN_DATE - 1 个自然日`。
- 日报输出文件只能是 `data/REPORT_DATE.json`，其中 `date` 必须等于文件名；北京时间周六可另外按第 9A 节追加 `data/smm_copper_concentrate_index_2026.csv`。
- `report_time` 写实际完成报告的北京时间 ISO 8601 时间，不伪造为 07:00。
- JSON 是首页、日报、归档和搜索的唯一内容源；TC 历史页只读取 `data/smm_copper_concentrate_index_2026.csv`。
- 生产站点固定为 `https://metals.zhemin.ltd`。
- Part 1/Part 3 采集未完成或本地检查失败时不得推送；X partial/failed 仅在第 5.2 节的真实 coverage 审计完整时允许降级发布。单条来源未核验时可以发布，但必须按第 7、9 节标注为“来源未核验”，不得伪装成已核验来源。

## 2. 时间窗口

以 `REPORT_DATE = R` 为例：

- Part 1 访谈：`R-2 00:00:00+08:00` 至 `R 23:59:59+08:00`，即三个完整自然日。
- Part 2 X 原帖：`R 00:00:00+08:00` 至 `R 23:59:59+08:00`。
- Part 3 新闻：`R 00:00:00+08:00` 至 `R 23:59:59+08:00`。

跨时区来源先按来源显示的时区解析，再换算为北京时间判断是否入窗。只有日期而没有可靠时刻的历史或公开来源，可以把 `publish_time` 写成 `YYYY-MM-DD`，不得自行补成午夜或 07:00。

## 3. 开始前检查

1. 读取本文件、`data/daily_report_schema.json`、最近三份 `data/*.json`、`mining_people_broadcast_x_articles.csv`、`data/sources_discovered.json` 和 `data/conference_calendar.json`。
2. 检查 `git status`，保留用户已有修改；不要覆盖或删除不属于本次日报的文件。用户已确认：`.pi/schedule-prompts.json`、`x_outputs/2026-09-28_x_raw_materials_rerun_20260929.json`、同名 `.txt` 以及已完成日报的按日期 X 原始材料是需要保留的无关工作，不得仅因这些文件未提交而停止。本次用户授权维护的 `Daily_Report_Workflow.md`、`Daily_Task_Prompt.md`、`scripts/run_scheduled_daily.py` 和 `tests/test_scheduled_daily.py` 的待提交改动也有明确来源，不是日报阻塞；不得由每日任务编辑或提交这些文件。将以上文件排除于本次编辑和提交范围。其他修改先只读检查；能确定与本次目标无关的改动同样保留并排除，只有与目标日报、TC、执行脚本发生冲突、存在并发写入或无法安全隔离时才停止。
3. 确认 `data/REPORT_DATE.json` 不存在。若已存在，停止并先判断是重跑、纠错还是日期计算错误。
4. 记录三个时间窗口，后续每条候选都据此筛选。
5. 若 `RUN_DATE` 是北京时间周六，同时读取 `data/smm_copper_concentrate_index_2026.csv`，按第 9A 节判断是否需要追加前一日（周五）的 TC；其他星期不得修改该 CSV。

种子 CSV 是发现入口，不是白名单。可靠的新人物、公司、媒体或监管来源可以纳入，写入 `search_log.new_sources_discovered`，并在核验后追加到 `data/sources_discovered.json`，不得覆盖原有记录。会议窗口内还要按 `data/conference_calendar.json` 增加主办方、演讲者和回放检索。

## 4. 工具与职责

代码是确定性边界，负责日期窗口、preflight、来源 registry、各采集器、规范化、技术核验、通道审计、最终 JSON 写入、schema/内容校验、测试、构建和发布。用户已授权本定时任务在全部检查通过后自动执行精确范围的 Git 提交和推送，无需逐次确认；该授权不允许夹带其他文件或绕过失败边界。统一入口为：

```bash
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/daily_pipeline.py YYYY-MM-DD --dry-run
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/daily_pipeline.py YYYY-MM-DD --collect-mining
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/daily_pipeline.py YYYY-MM-DD --collect-x
```

这些命令是采集与流程入口；不表示已经存在 AI API 集成。流水线对同日同一采集器加跨进程锁；不同采集器可以独立运行，X 另有跨日期的共享账号锁。stdout/stderr 实时写入运行目录，每个完成的采集器立即保存 `*.result.json`、候选和清单；Mining 各分类完成后还保存各自候选文件。进程心跳保存在 `*.process.json`，清单未完成不代表零结果。

定时主流程必须等待所有采集命令和委派任务结束、读取其最终结果后再汇总、生成日报及发布；不能以“仍在等待采集”的进度汇报结束主流程。定时任务的关键路径委派使用前台执行，不启动无人收尾的后台研究。恢复时先确认旧采集进程已退出，复用已有候选、sidecar 和已生成日报，不重复 X 采集，不覆盖原始材料或日报。

AI 只接收代码产出的规范化候选，返回严格的分析决策和证据字段（事实提取、供需判断、去重、中文摘要等）。日报 JSON 的最终写入仍必须由代码完成，AI 不得手工写入 `data/YYYY-MM-DD.json`；在本次已授权的定时任务范围内，AI 可在全部研究和校验通过后运行精确路径的 Git add/commit/push。只可提交本次日报、周六按第 9A 节更新的 TC CSV、必要的按日期原始材料及明确纠错，不得提交其他文件，也不得把采集器失败静默当成零结果；Part 1/Part 3 失败阻止发布，X partial/failed 按第 5.2 节保留审计并降级。普通公开网页优先使用搜索和网页读取工具。Browser Use 只用于需要真实浏览器交互、登录会话或动态页面的任务，主要是 X；困难原文核验可按第 7.1 节使用已授权的 PiChrome 现有会话，不扩大为所有页面抓取。网站本身不调用模型，也不保存模型密钥。

## 5. 收集流程

### 5.1 Part 1：访谈

检索 Podcast、Webcast、YouTube、会议访谈、Panel、Keynote 和公司演示。重点关注矿业从业者、公司管理层、行业研究者和官方机构。

纳入条件：

- 发布时间在 Part 1 窗口内。
- 内容包含可归因的金、银或铜供需信息，例如产量、品位、回收率、扩建、停产、许可、资本开支、库存、工业消费或投资需求。
- 能打开原始节目页、视频页或主办方页面并核对标题和日期。

若只有音视频而无文字稿，只能总结实际听取或可靠字幕中可确认的内容；不得根据标题补写观点。与前两份日报 URL 相同或实质内容相同的访谈不重复纳入，并记录在 `dedup_log.part1_deduped_urls`。

### 5.2 Part 2：X 原帖

**X 采集外层超时预算固定为 60 分钟（3600 秒）**：执行 `scripts/daily_pipeline.py YYYY-MM-DD --collect-x` 或直接执行 `scripts/x_search.py` 时，命令执行工具的总超时必须显式设置为 `3600` 秒；工具以毫秒计时则设置为 `3600000`。该预算覆盖完整的 `Playwright -> twscrape` 采集链，不是单账号、单次页面导航或整份日报的超时。外层委派或包装调用不得设置更短的超时，不得沿用历史运行的 1000 秒预算。保持账号间 25–30 秒安全等待和现有单次请求超时不变；认证、限流或其他安全停止仍须立即停止。若达到 60 分钟仍未完成，保留现场并报告超时，不自动重试 X；先确认旧进程已退出并核查已有材料，不得把未完成采集记为完整零结果。

X 的本地采集统一由当前仓库 `scripts/x_search.py` 负责，并必须按 `Playwright -> twscrape` 顺序尝试。Playwright 先按注册表顺序串行处理全部账号，账号间默认随机等待 25–30 秒；完整成功（包括真实零结果）即结束。普通通道不可用、普通失败或账号级失败只把未完成账号交给 twscrape。Playwright 路径使用日报固定的 Python 3.12.x（`C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe`）、项目内 `.browser_profile/chromium-data` 持久化会话和明确的 `C:/Program Files/Google/Chrome/Application/chrome.exe` 路径。401/403/429、登录墙、challenge、CAPTCHA、停权、No account available 或账号耗尽等安全停止不得启动后续通道。本任务仅使用该环境中的 Python、Playwright 和 twscrape 包，不调用 browser-use 的自动发现/本地 daemon 启动路径，也不要通过 `webbrowser.open("chrome://inspect/#remote-debugging")` 打开浏览器；后者在 Windows 上可能触发 Microsoft Store 的 Chrome 安装提示。运行前可使用 `C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/x_search.py --check-login --headless` 验证 Playwright 回退会话。

在已授权的浏览器会话中检索种子账号和新发现的可靠账号。只收录原作者帖子，必须核对作者、handle、正文、原帖 URL 和发布时间。

以下内容不纳入：搜索摘要、截图转述、无法打开的帖子、无新增事实的转发、纯口号、纯价格目标和未经证实的传闻。每次运行必须保留 X 原始材料中的 `选定通道`、`尝试通道`、`不可用通道`和 sidecar 审计，并记录 `accounts_completed/accounts_total/accounts_failed`。新报告的 `search_log.part2_coverage` 必须记录状态、路径和失败原因；截至 `2026-08-19` 的历史报告继续接受旧路径，`2026-08-20` 起只接受 `Playwright -> twscrape` 有序前缀及 `null`、`playwright`、`twscrape`、`playwright+twscrape`。完整状态要求所有账号完成、`part2_searched=true`；partial/failed 仍可随 Part 1 和 Part 3 的完整结果发布，`part2_searched=false`、`part2_result` 必须包含覆盖审计，页面显示 n/N，不能写成完整零结果。

### 5.3 Part 3：新闻

同时检索英文和中文来源。优先顺序：

1. 监管文件、交易所公告、公司新闻稿、政府或官方统计。
2. Reuters、Mining.com 等可靠媒体。
3. 能明确标注原始出处的行业媒体或转载页。

对同一事件，优先保留一手来源；一手来源缺失时使用最接近原始事件、信息最完整的可靠报道。转载发布日期在窗口内、但原始事件已经在旧日报出现的，按重复事件排除。

### 5.3A mining.com 强制抓取规则

mining.com 对自动化请求启用了 CloudFront 反爬：普通 HTTP 客户端、`site:mining.com` Google 搜索和 WebFetch 均无法可靠获取 `/commodity/copper/` 页面的实际文章列表——Google 搜索返回的是首页/SEO 内容而非铜分类页文章。本节为每次 Part 3 检索的强制路径，必须按顺序执行：

1. **Playwright 直接抓取铜分类页**（日报固定 Python 3.12.x + Chromium headless + 反检测）。这是铜分类页完整发现的强制主路径，不排除第 7.1 节的已验证文章核验回退。每次 Part 3 检索必须完成该分类发现；恢复时可按第 12 节复用同日、同注册表且分类完整的已保存结果及 provenance，无需重新采集：
   ```
   C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe
   ```
   脚本参数：
   - 目标 URL：`https://www.mining.com/commodity/copper/`
   - 浏览器：Chromium headless，添加 `--disable-blink-features=AutomationControlled` 和 `--no-sandbox`
   - 上下文：user_agent 设为 Chrome 131 Windows、viewport 1920x1080、locale en-US
   - 反检测：`add_init_script` 设置 `navigator.webdriver=false`、`navigator.plugins` 非空、`window.chrome={runtime:{}}`
   - 提取：`page.evaluate()` 从 DOM 中提取所有包含 "July DD, 2026" 等当期日期的文章标题和链接
   - **禁止** `site:mining.com` Google 搜索替代此步骤——该搜索在页面 403 时返回首页/SEO 内容而非铜分类页的实际文章列表，已在 2026-07-22 验证为不可靠

2. **逐篇核验**。Playwright 提取的候选列表每条都要：
   - 优先尝试 WebFetch 抓取文章 URL 完整正文（部分 `/web/` URL 对 WebFetch 较友好）
   - 若文章 URL 返回 403 或超时，可用 Playwright 同一会话或按第 7.1 节使用已授权 PiChrome 现有 profile 核验可见正文；遇到登录墙、challenge 或安全停止不得继续提取或重试
   - 若仍不可读，寻找中文转载源（SMM、新浪财经、东方财富网等）交叉核验
   - 在 `mining_com_source_note` 字段明确记录核验路径

3. **辅助渠道**。除 Playwright 抓取铜分类页外，仍需执行：
   - Google `site:mining.com gold July DD 2026` 和 `site:mining.com silver July DD 2026`（金/银分类页同样可能 403，site:搜索作为辅助发现手段）
   - 尝试 WebFetch `https://www.mining.com/commodity/gold/` 和 `https://www.mining.com/commodity/silver/`；若 403，亦使用 Playwright

4. **搜索日志记录**。在 `search_log.part3_sources_checked` 中，必须单独记录：
   - mining.com `/commodity/copper/` Playwright 抓取状态和文章数
   - 各篇文章的核验路径（WebFetch 成功 / Playwright 抓取 / 已授权 PiChrome 可见原文核验 / 中文转载交叉核验）
   - site:mining.com 金/银搜索命中数（辅助参考）

5. **不采用** sitemap、Wayback Machine、RSS feed 等方法。`site:mining.com` 搜索仅作为金/银分类页的辅助发现手段，不得作为铜分类页的主要信息源。

## 6. 内容筛选

每条信号必须回答：发生了什么、影响哪种金属、影响供给还是需求、为什么值得关注。每条信号必须填写一个 `primary_metal`，用于决定正文中的唯一展示板块；它必须同时出现在 `metal_tags` 中。`metal_tags` 保留所有具有实质供需关联的金属，不要仅因正文提到某种金属或价格就添加标签。主金属按最重要的未来供需变化或催化剂确定，不按标题出现顺序确定。

可以纳入的典型主题：

- 供给：产量、品位、回收率、投产、扩建、停产、事故、罢工、许可、制裁、矿权、冶炼、库存和资本开支。
- 需求：制造业用量、铜箔与电网投资、珠宝和实物购买、ETF 与央行购买、融资环境，以及有明确需求传导路径的政策。

默认排除：

- 没有供需因果的价格涨跌复述或宏观评论。
- 只有公司股价、估值或交易观点，且没有实物供需信息。
- 无法追溯来源的数字、传闻和匿名社交媒体说法。
- 超出窗口的旧事件、周报复述和重复转载。

所有数字必须保留期间、单位、币种和统计口径。正文要明确区分实际值、估计、市场一致预期、公司指引和分析判断。`excerpt` 只写来源可支持的事实；`interpretation` 和 `importance` 是研究判断，不得伪装成来源原话。

### 6.1 重要性判断质量标准

`importance` 不是标题改写，也不是“这是一个重要信号”的标签，更不能把上面的正文事实再复述一遍。它必须在正文基础上提供新增的研究判断：这条信息相对于已有信息改变了什么，以及为什么值得关注。

完整研究卡可以填写 `importance`；只保留标题和来源的精简卡可以省略。只要填写 `importance`，就必须满足：

- 使用 2–4 个中文句子，建议 80–300 字；
- 先给出结论，不能只复述标题或事实；
- 至少覆盖以下五项中的三项：
  1. 规模：影响多少产量、库存、需求、产能或项目价值；
  2. 机制：通过什么路径影响矿山、精矿、冶炼、库存或终端需求；
  3. 时间：影响是即时、短期、中期还是长期，何时可能兑现；
  4. 对比：相对于前期数据、公司指引、历史水平或同类事件的变化；
  5. 不确定性：主要风险、前置条件和下一步需要跟踪的验证点；
- 至少包含一个具体锚点：数字、单位、日期、时间表、前后变化或明确项目里程碑；
- 与同一信号的 `summary`、`detail`、`excerpt` 或 `interpretation` 去重：已经在正文中完整说明的事实不再整句复述；如确需保留数字或日期作为锚点，只保留支撑结论所必需的最小信息，并把篇幅用于新增影响、比较、条件或验证判断；
- 如果来源没有数字，不得编造数字，但必须说明影响机制、时间节点、证据强度或后续验证条件；
- “不是实际产量”“需要继续跟踪”“这是供给信号”等免责声明不能单独构成重要性判断，必须放在具体分析之后；
- 不得只写“这是一个重要的供给/需求信号”或同义句。

`interpretation` 负责展开事实如何传导、有哪些假设和限制；`importance` 负责压缩成面向读者的新增研究结论，不能退化为泛化标签或正文摘要。写作时应先删去与正文重复的事实，再保留对供需判断真正新增的结论。对 X 帖子或分析观点可以降低证据等级，但仍须说明新增事实、可能影响和验证条件。

## 7. 链接与事实核验

每个入选 URL 都要完成以下检查：

1. 使用 `http` 或 `https`，并尽量链接具体文章、公告、帖子或节目，而不是站点首页。
2. 页面可打开，且标题、发布日期、主体和核心数字与 JSON 一致。
3. 若媒体报道引用公司或监管文件，应继续寻找一手来源并优先采用。
4. 页面暂时不可访问时，优先寻找可信替代来源；找不到时可以保留仅含标题、来源和必要分类元数据的精简卡，但必须设置 `verification_status: "unverified"`、填写 `verification_note`，页面会显示“来源未核验”。不得在未核验卡中补写无法确认的事实、解释或重要性判断。
5. 已打开并核对的卡片设置 `verification_status: "verified"`；不得发明 URL、引文、发布时间、管理层评论或缺失数字。

在 `search_log.url_verification` 记录检查数量、通过数、失败数、失败项和简短说明。未核验来源计入 `failed`，但只要采集流程完整并按上述规则逐卡标注，不会单独阻止发布。

### 7.1 困难原文的 PiChrome 核验回退

普通搜索/网页读取仍优先。此前普通读取返回 403 的 Mining 文章、FCX 原文和用户已登录的 SMM 页面已通过 PiChrome 现有 profile 成功读取；当前普通 Mining 读取仍可能 403，Firecrawl 缓存可能出现 lockdown miss，不得关闭 lockdown。PiChrome 是允许的原文核验回退，不替代强制分类发现，也不证明所有页面可读。

- 使用用户已授权的现有 Chrome profile；允许读取用户预先登录且实际可见的正文，不自动填写凭据、不登录、不绕过登录墙、付费墙、challenge 或安全机制。先检查访问状态并截图，再提取正文；访问门禁后的 DOM、嵌入数据或网络响应不是证据，不得宣称为公开内容。截图失败须记录，不能宣称完成视觉核验。
- 同一时刻只由一个 actor 操作；使用少量 inactive 自有工作标签，以准确 tab ID 定位。保留且不读取无关私人标签，只清理本次自有标签。截图/证据保存在 git 忽略的本地 `.runtime/browser-verification/` 新目录；截图可能含账号名称，不提交或共享。
- 每页保存请求/最终 URL、标题、发布日期及其精度、关键原文精确引文和定位、capture time、访问状态及证据/截图 artifact 引用；capture time 不得充当 publication time。保存已完成和 pending 页面，恢复只处理未完成项。
- 设置有限导航次数和超时，不盲目 reload。浏览器授权失败、登录失效或 challenge 时立即停止浏览器路径，保存 pending 并请求用户处理；单条不可读来源可按第 7 节标记未核验，分类发现未完成仍阻止 Part 3 发布。
- 不修改 VPN、DNS、SSRF/TLS，不复制 profile/cookies、不重启 Chrome、不直接调用 bridge 绕过授权。CUA 需要独立的 existing-profile grant，未授权时不能自动替换 PiChrome。
- 用户已确认的 `/chrome authorize indefinite` 仅在当前 live Pi **进程生命周期**内有效；同进程 `/reload` 和加载扩展的新 scheduled session 可继承，实际一次性 scheduled 测试已通过。Pi 或 PC 重启后必须由用户重新授权；不得自动授予或修改权限检查。这不是重启持久授权或网站访问权益，也未证明重启后、锁屏桌面可用。

## 8. 去重

- 先规范 URL：移除无意义的追踪参数和片段，再比较。
- 同一公司、项目、事件和核心数字即使来自不同媒体，也视为同一事件。
- 同一事件只保留一条，优先顺序为一手来源、信息完整度、可访问性。
- Part 1 还要与前两份日报比较 URL 和实质内容。
- 被排除的重复项写入 `dedup_log`，不要作为正文卡片保留。

## 9. 写入 JSON

复制最近一份 JSON 的结构作为参考，但所有内容必须来自本次研究。字段定义以 `data/daily_report_schema.json` 为准。新日期报告必须写入 X `search_log.part2_coverage`；历史报告可保持旧结构。原始材料写入前保留 sidecar 的账号覆盖、尝试路径、选定路径和失败原因。新采集输出不得写入已移除的旧通道标识。

最低要求：

- `date`、`report_time`、三个 `windows` 和中文 `summary`。`summary` 不超过 300 个字符，只按金属概括当日供给增加/减少、需求增加/减少等方向，不逐条罗列事实，不写检索过程、渠道状态或收录数量。
- `part1_broadcasts`、`part2_x_posts`、`part3_news` 三个数组；没有结果时写 `[]`。
- 每条信号都有唯一主金属、全部实质相关金属标签、供需方向和直接来源 URL。
- 完整研究卡可以包含 `excerpt`、`interpretation` 和有实质内容的 `importance`；也允许只显示标题和来源的精简卡。精简卡不得用推测补齐内容。
- 每条新信号都填写 `verification_status`；未核验时还要填写 `verification_note`，并在 URL 核验失败数中计数。
- `search_log` 记录实际检查过的来源、各部分结果、新发现来源和 URL 核验结果。`part1_searched`、`part2_searched`、`part3_searched` 只有在相应采集完整结束时才写 `true`；成功完成但来源数或合格信号数为 0 时，来源数组可以为 `[]`，但结果说明不得为空。采集失败必须写 `false`，不得冒充零结果。
- `dedup_log` 记录去重情况。

不要修改旧 HTML、首页组件、搜索代码或归档列表。新增 JSON 后，Next.js 会自动更新所有页面。不要生成图片或 AI 模块。

`report_builder.py` 在最终原子写入之前，调用现有 Node/AJV schema 和语义校验；`--validate-only` 使用同一道校验。需先安装仓库既有 npm 依赖；Node 不可用、验证超时或验证失败时不创建、不替换目标 JSON。修正 analysis bundle 后再验证，不用直接编辑成品绕过校验。

原始材料应保留且不得覆盖：X 候选继续写入按日期命名的 `x_outputs/REPORT_DATE_x_raw_materials.txt`；其他确有复核价值的原始材料使用带日期的新文件。原始材料不直接渲染到网站，也不能代替 JSON 中的来源 URL 和核验记录。

## 9A. 每周六 TC 更新（公开来源或用户已授权登录会话）

此任务与日报研究相互独立。TC 获取失败时不得写入猜测值或部分记录，但应继续完成日报，并在最终汇报中单独列出 TC 状态和失败证据。

### 9A.1 日期与幂等检查

1. 仅当 `RUN_DATE` 是北京时间周六时执行；`TARGET_FRIDAY` 为紧邻该周六之前的星期五，即 `RUN_DATE - 1 个自然日`，不得写死日期。
2. 目标文件固定为 `data/smm_copper_concentrate_index_2026.csv`。先确认表头仍为 `assessment_date,value_usd_per_dmt,change_usd_per_dmt,source_url,source_note`，并读取最后一条记录。
3. 若 CSV 已有相同 `assessment_date` 且数值一致，视为幂等成功并跳过写入；若相同日期的数值不同，停止 TC 更新并报告冲突，不得覆盖历史数据。

### 9A.2 单一合格来源数据路径

SMM 指数页 `https://www.metal.com/copper/201910240001` 和部分 SMM 周评正文可能需要登录。不得尝试代替用户登录，也不得把锁定页面中的空白字段当作零值。按第 7.1 节核验的用户已授权、已登录且可见的 SMM 页面也可作为单一合格来源，必须记录 authenticated-visible 访问状态，不得标为公开或使用访问门禁后隐藏的正文。只要该页面或以下任一公开来源明确提供当期评估日期和 TC 值，即可进入第 9A.3 节校验，不要求完整周评正文或第二个独立来源：

- SMM 官方公开报价页、数据表、行情页或其他公开页面；
- 任意一个可打开的第三方媒体、行业网站或公开报告，且页面明确把数值归属于 SMM 进口铜精矿指数（周）。

按以下路径发现来源：

1. 优先打开 SMM Copper Concentrate Index 页面 `https://www.metal.com/copper/201910240001`、SMM 铜矿数据页 `https://hq.smm.cn/h5/copper-ore-data`、SMM 铜页面 `https://hq.smm.cn/copper` 或市场周评列表 `https://hq.smm.cn/copper/list/14013`。页面中的报价表、数据卡片、标题或正文均可作为取值位置；周评文章身份可作为辅助记录，但其正文登录受限不得阻止使用其他合格来源。
2. 若官方公开页面及已授权登录会话均未提供可见当期值，使用网页搜索逐条执行动态日期查询，不得只搜索固定示例：
   - `"M月D日，SMM进口铜精矿指数（周）报"`
   - `"TARGET_FRIDAY SMM 进口铜精矿指数 周"`
   - `"完整的 SMM 铜精矿现货周评标题"`
3. 搜索结果摘要只能用于发现候选 URL，不能脱离具体来源 URL 单独写入。候选页面不要求是完整正文，但必须能在页面标题、正文、表格、数据卡片或公开报告中识别指标名称、评估日期、本期 TC 值和单位。
4. 来源不必提供上一期值或周变化。若来源同时给出这些字段，只作为辅助核对和 `source_note` 记录，不作为写入前提；`change_usd_per_dmt` 统一按第 9A.3 节由 CSV 最新值计算。

### 9A.3 数据校验与节假日

写入前只需同时满足：

- 来源明确指向 SMM 进口铜精矿指数（周），而不是铜阳极、粗铜、月度指数或其他 TC/RC 指标。
- `assessment_date` 是来源显示的实际评估日期，晚于 CSV 最后一条日期；节假日例外按本节末尾处理。
- `value_usd_per_dmt` 是来源显示的有限数字，保留两位小数，单位为美元/干吨（USD/dmt）。
- `PRIOR` 固定取 CSV 最后一条 `value_usd_per_dmt`，`change_usd_per_dmt = round(VALUE - PRIOR, 2)`。即使来源没有公布上一期值或周变化，也必须按此公式写入。
- 若来源公布的上一期值或周变化与 CSV 算术结果不同，将差异写入 `source_note`，但只要当期评估日期、指标身份、单位和当期值明确，就不因此阻止更新，也不得用来源中的周变化覆盖 CSV 算术结果。
- `source_url` 指向实际显示当期日期和值的单一合格来源。使用第三方媒体时，`source_note` 写明媒体名称、其对 SMM 的归属说明、CSV 上期值和计算后的周变化；使用 SMM 官方页面时，记录页面类型、公开或 authenticated-visible 访问状态、CSV 上期值和计算结果。未能读取的登录受限周评 URL 只能作为可选辅助身份信息。

若 `TARGET_FRIDAY` 因中国节假日没有发布，查找自 CSV 最后一条记录之后、`TARGET_FRIDAY` 当日或之前最近一次由 SMM 明确发布的周度评估；使用来源中的实际日期，并在 `source_note` 写明 holiday schedule。不得用周五日期替代周四等实际发布日期。若没有找到新的明确评估，跳过写入并报告，不得沿用旧值制造新行。

### 9A.4 写入、页面同步与失败边界

1. 只追加一条经过核验的新记录，保持日期升序。按 CSV 规则转义包含逗号或双引号的字段，不得重写或重新格式化历史行。
2. 写入后重新读取 CSV，确认表头、字段数、日期唯一性和最后一行数值正确。
3. `/historical-tc` 在 Next.js 构建时直接读取该 CSV；不得手改图表组件、首页、HTML 或缓存来“同步”数据。
4. 按第 10 节运行全部校验和构建，并在本地检查 `/historical-tc` 的最新日期、最新值、周变化、折线位置、鼠标提示和完整数据表。
5. 只有找不到任何一个能明确提供当期指标身份、评估日期、TC 值和单位的合格来源，或出现相同日期不同当期值、日期无法确认、数值/单位无效等情况，才属于 TC 更新失败。另一个页面或完整周评存在登录墙不构成失败。保留 CSV 不变，记录检查过的 URL 和失败原因，然后继续日报流程。

## 10. 本地校验

构建前清除当前 PowerShell 进程继承的 `NODE_OPTIONS`，避免环境参数传入 Next.js 的 Node.js Worker：

```powershell
Remove-Item Env:NODE_OPTIONS -ErrorAction SilentlyContinue
```

生产构建必须离线可用。页面字体只能通过 `next/font/local` 或 CSS `@font-face` 从仓库内的 `assets/fonts/` 加载；禁止使用 `next/font/google`，也不得让构建阶段请求 `fonts.googleapis.com` 或 `fonts.gstatic.com`。若构建日志出现 `Failed to fetch`、`Google Fonts` 或 `next/font/google`，应按应用配置/外部网络依赖故障处理，不得删除 `.next` 来掩盖问题。

正常构建不得预先删除 `.next`，也不得在 `prebuild` 中强制清缓存。`.next` 由 Next.js 管理，保留它可复用增量构建缓存。

依次运行：

```bash
npm run validate:content
npm run typecheck
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe -B -m unittest discover -s tests -p "test_*.py"
npm test
npm run build
```

然后本地打开并检查：

- `/` 的最新日报日期、摘要和信号数量。
- `/daily/REPORT_DATE` 的标题、分组、来源链接和空状态；“黄金 / 白银 / 铜 / 来源审计”内导航属于正文普通流，向下滚动后必须随正文离开视口，不得固定或悬浮在内容上方。
- `/archive` 能找到新日期，并能按中文关键词和金属搜索。
- `/historical-tc` 可正常打开，摘要、折线图、鼠标提示和完整数据表读取同一份 CSV；横轴按实际评估日期间隔绘制，纵轴单位为 `USD/dmt`。周六追加 TC 时，页面必须显示新的实际评估日期、指数值和周变化。
- 新日报每条已填写的 `importance` 都通过 2–4 句、80–300 字、具体锚点和非泛化结论检查；精简卡允许省略，历史日报按历史兼容规则保留，不因本次规则回填。
- 页头 `TC` 是双入口悬浮菜单。鼠标移到 `TC` 后菜单应平滑向下出现，菜单顶边与页头分隔线贴合；鼠标从 `TC` 向左下方移动到菜单时不得提前消失。菜单必须包含外部 `SMM Copper Concentrate Index` 和内部 `Historical TC`，两个链接均可打开。
- 800px 以下视口没有横向滚动，键盘焦点可见。

若本次变更只包含日报 JSON 或 TC CSV，可对上述固定页面行为做快速冒烟检查；若本次变更包含 `app/`、`components/` 或样式文件，必须使用真实浏览器逐项操作，并确认没有 Next.js 错误覆盖层、浏览器控制台错误或失败的站内请求。

任一检查失败，修复后从第一条命令重新运行。校验失败时不得提交或推送。

只有在构建错误明确指向 `.next` 缓存损坏、陈旧构建产物，或者上一次构建在写入 `.next` 时被中断，才执行一次缓存恢复：

1. 确认当前目录是仓库根目录，删除目标只能是该目录下的 `.next`。
2. 使用下面的 PowerShell 目录守卫和精确路径执行清理：

   ```powershell
   $expectedRoot = 'D:\Projects\Copper_Gold_Silver_Info'
   if ((Get-Location).Path -ne $expectedRoot) { throw "Refusing to clean outside $expectedRoot" }
   Remove-Item -LiteralPath (Join-Path $expectedRoot '.next') -Recurse -Force
   ```

   Workbuddy 若触发 safe-delete，人工确认或安全例外只能精确授权 `D:\Projects\Copper_Gold_Silver_Info\.next`，不得授权项目根目录、`data`、`.git` 或通配路径。
3. 再次清除当前进程的 `NODE_OPTIONS`。
4. 从 `npm run validate:content` 开始完整重跑一次。
5. 若重试仍失败，立即停止，不再重复清缓存；保留错误输出和工作区现场供诊断。

## 11. 提交与发布

用户已授权本定时任务在满足完成定义后自动提交并推送到 `main`，无需逐次确认。授权范围仅限本次日报、周六按第 9A 节更新的 TC CSV、必要的按日期原始材料和明确纠错；不覆盖其他文件、删除操作或失败状态下的发布。

确认变更范围只包含本次日报、周六按第 9A 节更新的 TC CSV 及必要的纠错后：

1. 未更新 TC 时提交信息使用 `Add YYYY-MM-DD daily report`；同一提交包含周六 TC 更新时使用 `Add YYYY-MM-DD daily report and update TC`。
2. 推送到 `main`。
3. GitHub Actions 运行校验、测试和构建；它不收集或生成内容。
4. Vercel 监听 `main` 并自动部署。
5. 部署完成后检查 `https://metals.zhemin.ltd/`、`https://metals.zhemin.ltd/daily/REPORT_DATE`、`https://metals.zhemin.ltd/archive` 和 `https://metals.zhemin.ltd/historical-tc`。
6. 检查站点导航中的库存和 TC 悬浮菜单。TC 菜单必须同时显示外部 `SMM Copper Concentrate Index` 和内部 `Historical TC`；外部页面需要用户自行登录，只确认链接及登录提示正常，不代替用户登录。

   MacroMicro 铜库存外链 `https://sc.macromicro.me/charts/40914/tong-ku-cun-jia-ge` 按用户要求不再执行外站访问验证：不得为每日或每周任务对该目标发起 HTTP 请求、打开 Chrome/headless Chrome 或执行安全验证检查；只确认站内菜单和 href 保持正确，最终状态写“按用户要求跳过外站验证”，不得写成访问通过。其他已有外部库存/SMM 链接，检查站内菜单及 href 正确即可；外站的登录墙、Cloudflare 验证、403/429 或临时不可用需保留 URL、检查结果和限制说明，但不单独阻止纯日报/TC 数据发布，也不代表外站内容已核验。不得绕过验证、反复重试挑战、修改既有导航目标或把限制当成站内故障。站内页面、目标日期、来源卡核验规则及构建检查仍须通过；外站访问限制不放宽 Part 1/3 完整采集要求。
7. 周六写入 TC 后，确认生产 `Historical TC` 页面的最新日期和值与 CSV 一致。
8. 若提交包含页面或样式代码，必须在生产站用真实浏览器复核：TC 菜单动画及左下安全移动区有效、菜单顶边与页头分隔线贴合、Historical TC Tooltip 能跟随鼠标显示准确数据、日报内导航随正文滚走。只验证 HTTP 200 或页面 HTML 不足以替代这一步。

07:00 是任务开始时间。只有生产页可访问、日期正确且来源链接正常，才算发布完成。

日常任务不得自行改写或提交工作流文档。用户明确授权的手动维护可在专用分支纳入日报及已验证的方法文档，精确暂存授权路径并完成本地校验，经 PR 的 CI/Preview 检查后合并，再核验 main 对应生产页面，最后清理本次分支并回到 main；不夹带无关文件。

## 12. 失败与恢复

X 每完成或失败一个账号就保存 `.runtime/x/REPORT_DATE/checkpoint.json`。存在 checkpoint、原始 TXT 或 sidecar 时默认拒绝新增采集，即使指定 `--overwrite` 也不重采集。确认旧进程退出后，可执行 `x_search.py REPORT_DATE --recover-checkpoint` 离线导出已保存结果，再执行 `daily_pipeline.py REPORT_DATE --import-x` 校验导入；两者不增加 X 流量。未完成、在途或未访问账号一律标注未知/未完成，仅把已有持久化证据的账号计为完成，不按运行时长估算进度。离线导出的 partial/failed 仍返回非零，不能因此自动重试。

已完成的 Mining 结果可用 `daily_pipeline.py REPORT_DATE --reuse-mining .runtime/pipeline/REPORT_DATE/RUN_ID` 复用。流水线只接受同日、同注册表的完整结果，并写入新清单，不修改旧运行；不同日期、损坏材料或原始文件与 sidecar 哈希冲突必须停止。原始文件对中断只允许补齐与 checkpoint 一致的缺失半份，不覆盖任何已有文件。新的 X `--output-suffix` 仅供用户明确授权的新采集，每日任务不能自行使用它绕过保护。操作示例和状态路径见 `scripts/README.md`。

- 某一部分完整检索后没有合格内容：保留空数组，把对应 `*_searched` 写为 `true` 并写清检索范围，仍可发布“无合格信号”的日报。
- Part 1 或 Part 3 采集失败：把对应 `*_searched` 写为 `false` 并停止发布。X partial/failed：保留候选和 sidecar 审计，Part 2 写 `part2_searched=false` 与 coverage，继续完成其他部分；只要 Part 1 和 Part 3 完整，报告仍可发布，不能把缺失账号写成完整零结果。安全停止后不增加 X 流量。
- 来源冲突：优先一手、时间更近且口径更完整的来源，并在解释中说明口径差异。
- 任务延迟或补跑：明确指定目标 `REPORT_DATE`，窗口仍按该日期计算，不能直接用当前日期覆盖。
- 目标文件已存在：停止写入，判断重复运行或发布恢复；已发布且核验通过则幂等成功，不覆盖。工作区改动按第 3 节隔离；不能安全隔离、与目标冲突或存在并发写入时才停止危险操作，不把无关未提交文件一律当作阻塞。
- TC 找不到任何一个能明确提供当期指标身份、评估日期、TC 值和单位的合格来源，或相同日期出现不同当期值、日期/单位无效：保留 CSV 不变并报告，继续完成日报，不用搜索摘要或旧值填补。其他页面受登录限制不构成失败。
- 构建疑似缓存故障：按第 10 节精确清理 `.next` 并且只重试一次；不得用自定义分批删除脚本绕过 safe-delete。
- 推送后构建失败：不要新增另一份日报掩盖问题；修复原提交并重新完成全部检查。

## 13. 历史例外

`2026-06-30` 至 `2026-07-05` 从旧 HTML 迁移。为保持历史 URL，这六份 JSON 的 `date` 沿用旧页面日期，而 `windows` 记录旧页面实际覆盖的前一自然日；旧版 Part 1 也是单日窗口。该例外只用于历史迁移，未来日报必须遵守本文的 `REPORT_DATE` 和三日访谈窗口规则。

## 14. 完成定义

当前正式入口是已有 Pi 定时任务，已启用 `extensions: true`；浏览器访问仍受第 7.1 节 live Pi 进程授权、profile 可用性及网站会话条件约束。推送后执行 `scripts/run_scheduled_daily.py --verify-only --report-date YYYY-MM-DD` 检查实际发布。独立 Windows 计划任务尚未注册；另行授权并配置后才会定时执行，不能与当前 Pi 入口同时启用。OpenCode 正常退出不等于日报成功：入口还检查目标 JSON、内容校验、类型检查、Python/Node 测试、构建、远程 main 报告和 TC 内容、该 SHA 的 push 校验工作流以及四个生产页面。CI 排队、暂时网络失败和页面仍旧时有期限地等待；CI 明确失败或权限错误立即失败。页面内容验证不等于 Vercel 部署 SHA 证明，也不替代涉及页面改动时的真实浏览器测试。

入口使用全局 OS 锁，按日期原子记录 `.runtime/scheduled/YYYY-MM-DD.state.json`，命令日志保存在 `.runtime/scheduled/runs/`；Windows 原生 Job Object 会在包装进程退出或被强杀时清理其子进程树。锁文件保持原位，OS 在进程退出后自动解锁，不要通过删除锁文件解除并发保护。默认 AI 阶段预算 3 小时、单个校验命令 30 分钟、发布等待 30 分钟；这不改变 X 单次采集的 60 分钟预算。任何失败返回非零，不自动重采集或覆盖日报。

目标报告已存在时，普通入口和 `--resume --report-date YYYY-MM-DD` 都跳过 AI，仅重新验证现有报告及发布；`--verify-only` 也不会采集或写报告。曾启动 AI 但未留下成品的任务不能自动重启，需要先恢复已有材料并完成 analysis bundle/report builder。尚未推送的成品必须由已授权的发布流程提交/推送，包装入口不会替用户执行新的 Git 写入。

- [ ] 日期和三个窗口计算正确。
- [ ] Part 1 和 Part 3 完成检索且对应 `*_searched=true`；Part 2 有严格 coverage 审计，complete 为全账号完成，partial/failed 显示 n/N 和原因；空结果也有检索范围记录，采集失败没有冒充零结果。
- [ ] 每个正文来源都有 `verification_status`；未核验来源显示明确标注和原因，没有虚构链接或未经确认的正文事实。
- [ ] 事实、数字、口径和研究判断明确分开。
- [ ] 每条已填写的重要性判断都说明规模、机制、时间、对比或不确定性中的至少三项并通过内容校验；精简卡没有用推测补齐正文。
- [ ] 重复事件已排除并记录。
- [ ] 网站内容只新增 `data/REPORT_DATE.json`；若为周六，只按第 9A 节额外追加最多一条 TC CSV 记录；必要的原始材料和来源登记按日期追加，没有手改首页、HTML 或图片。
- [ ] 内容校验、测试和生产构建全部通过。
- [ ] 推送后 GitHub Actions、Vercel 和 `https://metals.zhemin.ltd` 的四个生产页面检查通过。
- [ ] 库存和 TC 站内导航及外链 href 正确；TC 悬浮菜单有两个入口，Historical TC 正常显示；外站登录/验证/访问限制单独记录，未尝试代替用户登录或绕过验证。
- [ ] 新页面行为符合基线：TC 菜单可稳定移入、顶边对齐，Historical TC 图表与 CSV 一致，日报内导航不悬浮；涉及页面代码时已用真实浏览器验证且无错误覆盖层或控制台错误。

# 每日信息工作流

本文是 Workbuddy 调用 DeepSeek-V4 PRO 生成“金银铜供需信息”日报及执行每周 TC 更新的唯一执行规范。网站代码只负责展示；每日任务新增一份日报 JSON，周一任务还可以按第 9A 节追加一条 TC CSV 数据，不生成 HTML，不手工更新首页。

## 1. 不变量

- 时区统一为 `Asia/Shanghai`（UTC+8）。
- 每日 07:00 开始任务，全年执行。
- `RUN_DATE` 是任务开始日，`REPORT_DATE = RUN_DATE - 1 个自然日`。
- 日报输出文件只能是 `data/REPORT_DATE.json`，其中 `date` 必须等于文件名；北京时间周一可另外按第 9A 节追加 `data/smm_copper_concentrate_index_2026.csv`。
- `report_time` 写实际完成报告的北京时间 ISO 8601 时间，不伪造为 07:00。
- JSON 是首页、日报、归档和搜索的唯一内容源；TC 历史页只读取 `data/smm_copper_concentrate_index_2026.csv`。
- 生产站点固定为 `https://metals.zhemin.ltd`。
- 研究不完整、来源未核验或本地检查失败时不得推送。

## 2. 时间窗口

以 `REPORT_DATE = R` 为例：

- Part 1 访谈：`R-2 00:00:00+08:00` 至 `R 23:59:59+08:00`，即三个完整自然日。
- Part 2 X 原帖：`R 00:00:00+08:00` 至 `R 23:59:59+08:00`。
- Part 3 新闻：`R 00:00:00+08:00` 至 `R 23:59:59+08:00`。

跨时区来源先按来源显示的时区解析，再换算为北京时间判断是否入窗。只有日期而没有可靠时刻的历史或公开来源，可以把 `publish_time` 写成 `YYYY-MM-DD`，不得自行补成午夜或 07:00。

## 3. 开始前检查

1. 读取本文件、`data/daily_report_schema.json`、最近三份 `data/*.json`、`mining_people_broadcast_x_articles.csv`、`data/sources_discovered.json` 和 `data/conference_calendar.json`。
2. 检查 `git status`，保留用户已有修改；不要覆盖或删除不属于本次日报的文件。
3. 确认 `data/REPORT_DATE.json` 不存在。若已存在，停止并先判断是重跑、纠错还是日期计算错误。
4. 记录三个时间窗口，后续每条候选都据此筛选。
5. 若 `RUN_DATE` 是北京时间周一，同时读取 `data/smm_copper_concentrate_index_2026.csv`，按第 9A 节判断是否需要追加上周 TC；其他星期不得修改该 CSV。

种子 CSV 是发现入口，不是白名单。可靠的新人物、公司、媒体或监管来源可以纳入，写入 `search_log.new_sources_discovered`，并在核验后追加到 `data/sources_discovered.json`，不得覆盖原有记录。会议窗口内还要按 `data/conference_calendar.json` 增加主办方、演讲者和回放检索。

## 4. 工具与职责

- Workbuddy：编排检索、打开来源、文件修改、校验、Git 和发布检查。
- DeepSeek-V4 PRO：分析候选内容、提取事实、判断供需关系、去重和生成中文摘要。
- 普通公开网页优先使用搜索和网页读取工具。
- Browser Use 只用于需要真实浏览器交互、登录会话或动态页面的任务，主要是 X；不要为了普通静态网页启动浏览器自动化。
- 网站本身不调用模型，也不保存模型密钥。

## 5. 收集流程

### 5.1 Part 1：访谈

检索 Podcast、Webcast、YouTube、会议访谈、Panel、Keynote 和公司演示。重点关注矿业从业者、公司管理层、行业研究者和官方机构。

纳入条件：

- 发布时间在 Part 1 窗口内。
- 内容包含可归因的金、银或铜供需信息，例如产量、品位、回收率、扩建、停产、许可、资本开支、库存、工业消费或投资需求。
- 能打开原始节目页、视频页或主办方页面并核对标题和日期。

若只有音视频而无文字稿，只能总结实际听取或可靠字幕中可确认的内容；不得根据标题补写观点。与前两份日报 URL 相同或实质内容相同的访谈不重复纳入，并记录在 `dedup_log.part1_deduped_urls`。

### 5.2 Part 2：X 原帖

在已授权的浏览器会话中检索种子账号和新发现的可靠账号。只收录原作者帖子，必须核对作者、handle、正文、原帖 URL 和发布时间。

以下内容不纳入：搜索摘要、截图转述、无法打开的帖子、无新增事实的转发、纯口号、纯价格目标和未经证实的传闻。通道失败时 `part2_x_posts` 保持空数组，把 `part2_channel` 设为 `failed` 并记录原因；不得因此阻塞 Part 1 和 Part 3。

### 5.3 Part 3：新闻

同时检索英文和中文来源。优先顺序：

1. 监管文件、交易所公告、公司新闻稿、政府或官方统计。
2. Reuters、Mining.com 等可靠媒体。
3. 能明确标注原始出处的行业媒体或转载页。

对同一事件，优先保留一手来源；一手来源缺失时使用最接近原始事件、信息最完整的可靠报道。转载发布日期在窗口内、但原始事件已经在旧日报出现的，按重复事件排除。

### 5.3A mining.com 强制抓取规则

mining.com 对自动化请求启用了 CloudFront 反爬：普通 HTTP 客户端、`site:mining.com` Google 搜索和 WebFetch 均无法可靠获取 `/commodity/copper/` 页面的实际文章列表——Google 搜索返回的是首页/SEO 内容而非铜分类页文章。本节为每次 Part 3 检索的强制路径，必须按顺序执行：

1. **Playwright 直接抓取铜分类页**（Python 3.13.12 + Chromium headless + 反检测）。这是唯一可靠的 mining.com 信息采集路径。每次 Part 3 检索必须执行：
   ```
   C:/Users/Zhemin/.workbuddy/binaries/python/versions/3.13.12/python.exe
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
   - 若文章 URL 返回 403 或超时，用 Playwright 同一会话打开该文章 URL 提取正文
   - 若仍受限，寻找中文转载源（SMM、新浪财经、东方财富网等）交叉核验
   - 在 `mining_com_source_note` 字段明确记录核验路径

3. **辅助渠道**。除 Playwright 抓取铜分类页外，仍需执行：
   - Google `site:mining.com gold July DD 2026` 和 `site:mining.com silver July DD 2026`（金/银分类页同样可能 403，site:搜索作为辅助发现手段）
   - 尝试 WebFetch `https://www.mining.com/commodity/gold/` 和 `https://www.mining.com/commodity/silver/`；若 403，亦使用 Playwright

4. **搜索日志记录**。在 `search_log.part3_sources_checked` 中，必须单独记录：
   - mining.com `/commodity/copper/` Playwright 抓取状态和文章数
   - 各篇文章的核验路径（WebFetch 成功 / Playwright 抓取 / 中文转载交叉核验）
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

## 7. 链接与事实核验

每个入选 URL 都要完成以下检查：

1. 使用 `http` 或 `https`，并尽量链接具体文章、公告、帖子或节目，而不是站点首页。
2. 页面可打开，且标题、发布日期、主体和核心数字与 JSON 一致。
3. 若媒体报道引用公司或监管文件，应继续寻找一手来源并优先采用。
4. 页面暂时不可访问时，寻找可信替代来源；找不到则不纳入正文，并在 `search_log` 说明。
5. 不得发明 URL、引文、发布时间、管理层评论或缺失数字。

在 `search_log.url_verification` 记录检查数量、通过数、失败数、失败项和简短说明。

## 8. 去重

- 先规范 URL：移除无意义的追踪参数和片段，再比较。
- 同一公司、项目、事件和核心数字即使来自不同媒体，也视为同一事件。
- 同一事件只保留一条，优先顺序为一手来源、信息完整度、可访问性。
- Part 1 还要与前两份日报比较 URL 和实质内容。
- 被排除的重复项写入 `dedup_log`，不要作为正文卡片保留。

## 9. 写入 JSON

复制最近一份 JSON 的结构作为参考，但所有内容必须来自本次研究。字段定义以 `data/daily_report_schema.json` 为准。

最低要求：

- `date`、`report_time`、三个 `windows` 和中文 `summary`。`summary` 不超过 300 个字符，只按金属概括当日供给增加/减少、需求增加/减少等方向，不逐条罗列事实，不写检索过程、渠道状态或收录数量。
- `part1_broadcasts`、`part2_x_posts`、`part3_news` 三个数组；没有结果时写 `[]`。
- 每条信号都有唯一主金属、全部实质相关金属标签、供需方向和直接来源 URL。
- 新闻包含 `source`、`title`、`publish_time`、`language`、`excerpt` 和 `interpretation`。
- `search_log` 记录实际检查过的来源、各部分结果、新发现来源和 URL 核验结果。
- `dedup_log` 记录去重情况。

不要修改旧 HTML、首页组件、搜索代码或归档列表。新增 JSON 后，Next.js 会自动更新所有页面。不要生成图片或 AI 模块。

原始材料应保留且不得覆盖：X 候选继续写入按日期命名的 `x_outputs/REPORT_DATE_x_raw_materials.txt`；其他确有复核价值的原始材料使用带日期的新文件。原始材料不直接渲染到网站，也不能代替 JSON 中的来源 URL 和核验记录。

## 9A. 每周一 TC 更新（无需 SMM 登录）

此任务与日报研究相互独立。TC 获取失败时不得写入猜测值或部分记录，但应继续完成日报，并在最终汇报中单独列出 TC 状态和失败证据。

### 9A.1 日期与幂等检查

1. 仅当 `RUN_DATE` 是北京时间周一时执行；`TARGET_FRIDAY` 为紧邻该周一之前的星期五，不得写死日期。
2. 目标文件固定为 `data/smm_copper_concentrate_index_2026.csv`。先确认表头仍为 `assessment_date,value_usd_per_dmt,change_usd_per_dmt,source_url,source_note`，并读取最后一条记录。
3. 若 CSV 已有相同 `assessment_date` 且数值一致，视为幂等成功并跳过写入；若相同日期的数值不同，停止 TC 更新并报告冲突，不得覆盖历史数据。

### 9A.2 无登录数据路径

SMM 指数页 `https://www.metal.com/copper/201910240001` 和部分 SMM 周评正文需要登录，Workbuddy 不得尝试代替用户登录，也不得把锁定页面中的空白字段当作零值。按以下公开路径获取：

1. 打开 SMM 铜页面 `https://hq.smm.cn/copper` 或市场周评列表 `https://hq.smm.cn/copper/list/14013`，找到 `TARGET_FRIDAY` 对应的“〖SMM铜精矿现货周评〗”标题、发布日期和官方文章 URL。此步骤用于确认文章身份；即使正文受限，也保留该官方页面用于交叉核验。
2. 使用网页搜索逐条执行动态日期查询，不得只搜索固定示例：
   - `"M月D日，SMM进口铜精矿指数（周）报"`
   - `"TARGET_FRIDAY SMM 进口铜精矿指数 周"`
   - `"完整的 SMM 铜精矿现货周评标题"`
3. 来源优先级如下：
   - 无需登录且正文明确显示完整数值的 SMM 新闻、评论、分析或关键词页面；
   - 完整转载并明确标注来源为 SMM、今日有色或 SMM 作者的可靠公开页面，例如新浪财经；
   - 期货公司或行业机构的公开周报只能作为第二项交叉核验，不得在缺少前两类来源时单独写入。
4. 搜索结果摘要只能用于发现候选 URL，不能单独作为写入证据。必须实际打开至少一个无需登录的完整正文，找到类似“X月X日，SMM进口铜精矿指数（周）报 VALUE 美元/干吨，较上一期的 PRIOR 美元/干吨上升/下降 CHANGE 美元/干吨”的明确句子。
5. 同时打开当期 SMM 官方周度报价页或铜页面，核对评估日期、单位以及公开显示的涨跌方向/变化值。官方报价页即使隐藏指数均值，仍可用于确认日期和变化值。

已验证的 `2026-07-17` 路径只用于理解方法，不得在未来任务中写死：SMM 铜页面列出的官方周评为 `https://hq.smm.cn/copper/content/104011499`（正文登录受限）；当期官方报价页为 `https://hq.smm.cn/copper/content/104010843`；无需登录的完整 SMM 周评转载为 `https://finance.sina.com.cn/wm/2026-07-17/doc-iniickay1390391.shtml`，正文明确给出 `-146.15` 美元/干吨、上一期 `-132.84` 和下降 `13.31`。未来每周必须重新发现当期 URL，不得沿用这个示例。

### 9A.3 数据校验与节假日

写入前必须同时满足：

- `assessment_date` 是来源明确写出的实际评估日期；`value_usd_per_dmt` 和 `change_usd_per_dmt` 是有限数字，保留两位小数，单位为美元/干吨（USD/dmt）。
- 公开正文中的 `PRIOR` 与 CSV 最后一条 `value_usd_per_dmt` 一致。
- 按两位小数计算 `VALUE - PRIOR = CHANGE`。若来源用“下降 X”，CSV 的 `CHANGE` 写负数；用“上升 X”则写正数。
- 至少两个独立页面相互吻合：一个是上述公开完整正文，另一个是 SMM 官方报价/铜页面或可靠机构周报。
- `source_url` 必须指向实际提供完整数值、无需登录即可打开的具体正文。若使用公开转载，`source_note` 明确写明原始来源为 SMM、转载平台以及官方 SMM 页面已交叉核验；不要把登录受限的 SMM URL 伪装成直接取值来源。

若上周五因中国节假日没有发布，查找自 CSV 最后一条记录之后、`TARGET_FRIDAY` 当日或之前最近一次由 SMM 明确发布的周度评估；使用来源中的实际日期，并在 `source_note` 写明 holiday schedule。不得用周五日期替代周四等实际发布日期。若没有找到新的明确评估，跳过写入并报告，不得沿用旧值制造新行。

### 9A.4 写入、页面同步与失败边界

1. 只追加一条经过核验的新记录，保持日期升序。按 CSV 规则转义包含逗号或双引号的字段，不得重写或重新格式化历史行。
2. 写入后重新读取 CSV，确认表头、字段数、日期唯一性和最后一行数值正确。
3. `/historical-tc` 在 Next.js 构建时直接读取该 CSV；不得手改图表组件、首页、HTML 或缓存来“同步”数据。
4. 按第 10 节运行全部校验和构建，并在本地检查 `/historical-tc` 的最新日期、最新值、周变化、折线位置、鼠标提示和完整数据表。
5. 登录墙、找不到公开完整正文、数值冲突或算术不一致都属于 TC 更新失败。保留 CSV 不变，记录检查过的 URL 和失败原因，然后继续日报流程。

## 10. 本地校验

构建前清除当前 PowerShell 进程继承的 `NODE_OPTIONS`，避免 Workbuddy 环境参数传入 Next.js 的 Node.js Worker：

```powershell
Remove-Item Env:NODE_OPTIONS -ErrorAction SilentlyContinue
```

正常构建不得预先删除 `.next`，也不得在 `prebuild` 中强制清缓存。`.next` 由 Next.js 管理，保留它可复用增量构建缓存。

依次运行：

```bash
npm run validate:content
npm test
npm run build
```

然后本地打开并检查：

- `/` 的最新日报日期、摘要和信号数量。
- `/daily/REPORT_DATE` 的标题、分组、来源链接和空状态；“黄金 / 白银 / 铜 / 来源审计”内导航属于正文普通流，向下滚动后必须随正文离开视口，不得固定或悬浮在内容上方。
- `/archive` 能找到新日期，并能按中文关键词和金属搜索。
- `/historical-tc` 可正常打开，摘要、折线图、鼠标提示和完整数据表读取同一份 CSV；横轴按实际评估日期间隔绘制，纵轴单位为 `USD/dmt`。周一追加 TC 时，页面必须显示新的实际评估日期、指数值和周变化。
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

确认变更范围只包含本次日报、周一按第 9A 节更新的 TC CSV 及必要的纠错后：

1. 未更新 TC 时提交信息使用 `Add YYYY-MM-DD daily report`；同一提交包含周一 TC 更新时使用 `Add YYYY-MM-DD daily report and update TC`。
2. 推送到 `main`。
3. GitHub Actions 运行校验、测试和构建；它不收集或生成内容。
4. Vercel 监听 `main` 并自动部署。
5. 部署完成后检查 `https://metals.zhemin.ltd/`、`https://metals.zhemin.ltd/daily/REPORT_DATE`、`https://metals.zhemin.ltd/archive` 和 `https://metals.zhemin.ltd/historical-tc`。
6. 检查站点导航中的库存和 TC 悬浮菜单。TC 菜单必须同时显示外部 `SMM Copper Concentrate Index` 和内部 `Historical TC`；外部页面需要用户自行登录，只确认链接及登录提示正常，不代替用户登录。
7. 周一写入 TC 后，确认生产 `Historical TC` 页面的最新日期和值与 CSV 一致。
8. 若提交包含页面或样式代码，必须在生产站用真实浏览器复核：TC 菜单动画及左下安全移动区有效、菜单顶边与页头分隔线贴合、Historical TC Tooltip 能跟随鼠标显示准确数据、日报内导航随正文滚走。只验证 HTTP 200 或页面 HTML 不足以替代这一步。

07:00 是任务开始时间。只有生产页可访问、日期正确且来源链接正常，才算发布完成。

## 12. 失败与恢复

- 某一部分没有合格内容：保留空数组，写清检索范围；只要检索完整，仍可发布“无合格信号”的日报。
- X 登录失效：记录失败并继续其他部分，不以搜索摘要代替原帖。
- 来源冲突：优先一手、时间更近且口径更完整的来源，并在解释中说明口径差异。
- 任务延迟或补跑：明确指定目标 `REPORT_DATE`，窗口仍按该日期计算，不能直接用当前日期覆盖。
- 文件已存在或工作区有不明修改：停止写入，先确认修改来源，避免数据丢失。
- TC 来源受登录限制、缺少公开完整正文或数值冲突：保留 CSV 不变并报告，继续完成日报，不用搜索摘要或旧值填补。
- 构建疑似缓存故障：按第 10 节精确清理 `.next` 并且只重试一次；不得用自定义分批删除脚本绕过 safe-delete。
- 推送后构建失败：不要新增另一份日报掩盖问题；修复原提交并重新完成全部检查。

## 13. 历史例外

`2026-06-30` 至 `2026-07-05` 从旧 HTML 迁移。为保持历史 URL，这六份 JSON 的 `date` 沿用旧页面日期，而 `windows` 记录旧页面实际覆盖的前一自然日；旧版 Part 1 也是单日窗口。该例外只用于历史迁移，未来日报必须遵守本文的 `REPORT_DATE` 和三日访谈窗口规则。

## 14. 完成定义

- [ ] 日期和三个窗口计算正确。
- [ ] 三部分都完成检索，空结果也有记录。
- [ ] 每个正文来源都已打开核验，没有站点首页或虚构链接。
- [ ] 事实、数字、口径和研究判断明确分开。
- [ ] 重复事件已排除并记录。
- [ ] 网站内容只新增 `data/REPORT_DATE.json`；若为周一，只按第 9A 节额外追加最多一条 TC CSV 记录；必要的原始材料和来源登记按日期追加，没有手改首页、HTML 或图片。
- [ ] 内容校验、测试和生产构建全部通过。
- [ ] 推送后 GitHub Actions、Vercel 和 `https://metals.zhemin.ltd` 的四个生产页面检查通过。
- [ ] 库存和 TC 导航可打开；TC 悬浮菜单有两个入口，Historical TC 正常显示；外部 SMM 页面显示正常登录入口，未尝试代替用户登录。
- [ ] 新页面行为符合基线：TC 菜单可稳定移入、顶边对齐，Historical TC 图表与 CSV 一致，日报内导航不悬浮；涉及页面代码时已用真实浏览器验证且无错误覆盖层或控制台错误。

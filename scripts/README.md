# 支持的脚本

- `pipeline_contracts.py`：标准库数据类和严格校验，定义采集、分析和运行清单边界。
- `daily_pipeline.py`：安全的日期窗口预检和显式采集编排；默认不启动浏览器或外部采集。
- `report_builder.py`：唯一可以写入 `data/YYYY-MM-DD.json` 的分析结果投影器，默认拒绝覆盖。
- `setup_x_login.py`：设置 X 的 Playwright 登录会话。
- `x_search.py`：按权威工作流采集 X 原始候选。
- `mining_com_search.py`：按日期从 Mining.com 金、银、铜分类页采集候选。
- `validate-content.mjs`：校验日报内容；无参数时也校验 TC CSV 的日期顺序、两位小数和相邻变化值。支持成品路径和 `--stdin YYYY-MM-DD.json`，供 report builder 写前调用。
- `runtime_support.py`：标准库 OS 锁、实时命令日志、超时及子进程树清理；不自动重试。
- `run_scheduled_daily.py`：独立调度入口，记录阶段/心跳并验证发布；脚本存在不代表 Windows 计划任务已注册。
- `check_daily_health.py`：只读检查最近应有日报及本地保存的业务验证证据，JSON 告警和非零退出不触发补跑、网络请求或任何外部通知。

## 确定性流水线

```bash
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/daily_pipeline.py 2026-08-17 --dry-run
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/daily_pipeline.py 2026-08-17 --collect-mining --collect-x
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/report_builder.py .runtime/pipeline/2026-08-17/<run-id>/analysis.json
```

预检会读取 `data/source_registry.json`、计算北京时区窗口并创建运行清单，但不会调用 AI、浏览器或采集器。采集开关必须显式提供；采集失败会记录为失败，不能变成零结果成功。分析完成后只把完整、带证据的 bundle 交给 `report_builder.py`。

安装 Python 依赖：

```bash
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe -m pip install -r scripts/requirements.txt
```

可选 X 通道不会改变基线依赖，按需安装：

```bash
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe -m pip install -r scripts/requirements-optional.txt
```

运行日报采集脚本时固定使用 `C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe`（Python 3.12.x）；不要使用 `python`、`py` 或 `.workbuddy` Python，以免与已安装的 twscrape 环境分离。

`x_search.py` 固定按 `Playwright -> twscrape` 顺序尝试。Playwright 先按注册表顺序串行处理全部账号；完整成功（包括真实零结果）即结束。普通通道不可用、普通失败或账号级失败只把未完成账号交给 twscrape。401/403/429、登录墙、challenge、CAPTCHA、停权、No account available 或账号耗尽等安全停止立即结束整条链路。未设置 `X_TWSCRAPE_ENABLED`（或设置为其他值）时 twscrape 保持启用；设置为 `0`、`false`、`no` 或 `off` 会将 twscrape 标记为不可用。twscrape 只使用一个 `auth_token`/`ct0` cookie 账号，不使用密码登录。账号请求严格串行，默认每个账号间随机等待 `uniform(25.0, 30.0)` 秒；可用 `X_SAFE_DELAY_MIN_SECONDS` 和 `X_SAFE_DELAY_MAX_SECONDS` 配置范围（各为 5-300 秒），旧版 `X_SAFE_DELAY_SECONDS` 可固定覆盖。每个查询默认最多返回 20 条结果，可用 `X_MAX_RESULTS_PER_QUERY` 调整（1-500）。这些设置不保证不会触发 X 限制；不启用代理轮换、账号轮换或自动登录。

可用 `CHROME_EXECUTABLE` 覆盖 Chrome 路径；未设置或系统 Chrome 不存在时使用 Playwright Chromium。

原始采集失败必须非零退出，不能伪装成零结果。退出码 4 表示已写入审计文件的部分结果；其他非零退出均为失败。采集完整完成但没有窗口内合格候选时，可以成功返回空结果。X partial/failed 仍保留候选与 sidecar 覆盖审计，日报页面显示完成账户数/总账户数及原因；只有 Part 1 或 Part 3 失败才阻止发布。

## 中断与离线恢复

- X 整条采集链预算固定 3600 秒；流水线另有独立的进程级 3600 秒硬期限。命令工具的外层预算也应显式设置为 3600 秒，不得更短。直接运行 X 的 asyncio 期限属于协作式取消，阻塞清理仍需外层进程监督；不要把它当作进程硬杀保证。
- `.runtime/x/REPORT_DATE/checkpoint.json` 在流量开始前及每个账号完成/失败后原子保存。默认输出、sidecar 或 checkpoint 已存在就拒绝新采集，`--overwrite` 也不授予重采集权限。安全停止、超时及强杀后都不自动查询剩余账号。
- 真正需要重新采集时，须获得用户明确授权并选择新的 `--output-suffix NAME`；对应 checkpoint 为 `checkpoint_NAME.json`，恢复时使用同一 suffix。每日任务不得自行生成 suffix 绕过保护。
- 空 DOM 但没有明确“无结果”标记、命中结果上限或作者不匹配，都不能算该账号完整成功。仍不包含分页：非空、未触顶的单页搜索覆盖存在既有局限。
- 原始 TXT 与 sidecar 通过 SHA-256 绑定。离线恢复只补齐与 checkpoint 完全一致的缺失文件；不会覆盖冲突文件。未开始任何通道的 checkpoint 不能冒充有效失败 coverage。

确认旧进程已退出后，仅恢复持久化证据，不产生 X 请求：

```bash
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/x_search.py YYYY-MM-DD --recover-checkpoint
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/daily_pipeline.py YYYY-MM-DD --import-x
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/daily_pipeline.py YYYY-MM-DD --reuse-mining .runtime/pipeline/YYYY-MM-DD/RUN_ID
```

`.gitattributes` 将按日期保存的 X 原始 TXT/JSON 固定为 LF，防止 Windows `core.autocrlf` 改写 TXT 字节后破坏 sidecar 的 SHA-256；不要对历史材料运行全仓库换行重整。

前两条命令使用默认日期输出；带 suffix 的恢复保留独立材料，不会自动替换默认材料。离线恢复的退出码仍反映覆盖情况：partial 为 4、failed 为 5（登录错误可为 2），不意味着应重跑采集。`--import-x` 校验现有 raw/sidecar 后导入；`--reuse-mining` 只复用同日、同注册表的完整 `mining_com_search.result.json`。新运行保存自己的清单，不改旧运行。

流水线 stdout/stderr 实时写入每次运行目录，`*.process.json` 记录心跳/终态。每个完成采集器立即保存 `*.result.json` 和候选，后续失败不会抹去前面结果。Mining 每个分类的候选也单独落盘；分类页完整性与逐篇核验仍按工作流执行，缓存不代替事实核验。强制分类发现可由同日、同注册表且分类完整的保存结果及 provenance 满足，恢复不要求重新采集；逐篇困难原文允许按工作流第 7.1 节使用 PiChrome 现有 profile 回退。

## PiChrome 困难原文核验（不改采集器）

普通搜索/网页读取优先；此前 Mining 403 文章、FCX 原文和用户已登录 SMM 的可见页面已通过现有 profile 读取。当前普通 Mining 403、Firecrawl 缓存 lockdown miss 不证明原文无法通过已授权浏览器核验，也不允许关闭 lockdown。此回退只用于困难原文，不替代分类发现或扩大为全页面抓取；不新增采集器或 TC CSV 逻辑。

- 先检查访问状态/截图，再读可见正文；登录墙、付费墙或 challenge 后的 DOM/嵌入数据/响应不作证据。允许用户预先登录的可见会话，不自动填写凭据或绕过安全机制。已授权登录 SMM 可作为 TC 单一合格来源，记录 authenticated-visible；指标身份、实际评估日期、USD/dmt、CSV 上期值算术及节假日规则保持不变。
- 单 actor、少量 inactive 自有标签、准确 tab ID；不读私人标签，仅清理自有标签。证据保存在 ignored `.runtime/browser-verification/` 新目录，截图可能含账号名称，不提交或共享。逐页记录 URL、标题、publication precision、精确引文/定位、capture time、access status 和 artifact 引用；capture time 不替代发布日期，截图失败如实记录。
- 有限导航/超时，不盲目 reload；保存 completed/pending，恢复只处理 pending。授权失败、登录失效或 challenge 停止浏览器路径；单条未核验可降级，分类发现不完整仍阻止 Part 3 发布。
- 不改 VPN/DNS/SSRF/TLS，不复制 profile/cookies、不重启 Chrome、不直接调用 bridge 绕过授权。CUA 需要独立 existing-profile grant，未授权不自动替换。
- `/chrome authorize indefinite` 是用户确认的 live Pi **进程生命周期**授权；同进程 `/reload` 和加载扩展的新 scheduled session 可继承，实际一次性 scheduled 测试已通过。Pi/PC 重启需用户重新授权，不自动授予或修改检查；不是重启持久权限或网站权益，重启/锁屏桌面未验证。

## 写入与发布验证

先安装既有 npm 依赖。`report_builder.py --validate-only`、`build_report()` 和最终 `write_report()` 共用 Node/AJV schema 与语义校验；验证失败或 Node 不可用时不写目标文件。既有成品始终不可覆盖，兼容的 `--overwrite` 参数不再允许替换日报；明确授权的内容纠错另行处理。`project_report()` 仅供纯投影，不代表最终验证通过。未核验卡的候选和决策均不得携带 `excerpt`、`detail`、`interpretation`、`importance` 或非空 `claims`（不要写 null/空字符串）；访谈必填 `summary` 只能原样使用卡片 `title`，前端隐藏该占位正文。builder 立即执行这些规则；Node 成品校验从 `2026-10-03` 起执行，历史文件不回填。

已核验完整研究卡的 X/新闻事实须显式写 `excerpt`，不再回退复制 `interpretation`。显示为中文摘要和可选的不重复补充段，内部原文引句与研究判断保持分离。

### 引句与捕获文本绑定

每条 `claims.evidence` 必须在同一 `claims.source_url` 的捕获文本中出现，只规范化空白，不忽略大小写、标点或替换词。候选原 URL 使用非空 `text` 或 `raw_text`；同时提供时必须一致。另一来源（例如媒体引用的公司公告）可在候选中加 `evidence_documents`：

```json
{"artifact_path": ".runtime/browser-verification/RUN_ID/issuer.json", "sha256": "替换为该文件字节的64位SHA-256"}
```

该对象须放在 `evidence_documents` 数组中（最多 32 个）。每个引用的 UTF-8 JSON 至少包含：

```json
{
  "source_url": "https://example.com/issuer-release",
  "text": "实际读取并保存的原文全文或相关连续段落",
  "captured_at": "2026-10-03T09:00:00+08:00",
  "access_status": "public"
}
```

`artifact_path` 相对仓库根目录，仅允许 `.runtime/` 或 `x_outputs/` 内的普通文件，禁止绝对路径、`..`、符号链接和 junction；文件上限 2 MiB，SHA-256 按原始字节核对。`access_status` 仅接受 `public` 或 `authenticated-visible`。同一 URL 的文本冲突、哈希冲突、引句跨源错配或找不到引句都会在写入前失败，不联网补全，不创建成品。

该约束证明文本匹配、URL 绑定和引用文件字节一致，不能证明来源真实性、实际访问权限或结论成立；仍需人工/AI 按工作流核验语义、数值和可见页面，不能把搜索摘要或访问门禁后的隐藏内容包装为 capture。证据 artifact 不写入最终 JSON，不提交账号截图或私有会话信息。旧 analysis bundle 可能因缺少文本/引用而失败；只能从已有材料补齐证据，不能因此自动重采集。

```bash
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/report_builder.py analysis.json --validate-only
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/run_scheduled_daily.py --verify-only --report-date YYYY-MM-DD
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/run_scheduled_daily.py --resume --report-date YYYY-MM-DD
```

独立入口在目标报告存在时跳过 AI；首次正常运行才启动已安装的 OpenCode，可用 `--model` 明确指定其模型。默认 AI 3 小时、单个校验 30 分钟、发布等待 30 分钟，均有限期。已开始 AI 的中断任务缺少成品时拒绝自动重新调用，需先完成材料恢复与报告生成。`--resume` 仅重新校验现有成品，不负责自动 Git 提交或推送。

状态在 `.runtime/scheduled/YYYY-MM-DD.state.json`，日志在 `.runtime/scheduled/runs/`；旧日志不改写。新成功状态包含 `verified_report_sha256` 和 `verified_tc_sha256`，验证期间文件变化将失败；修正成品后旧成功不能继续作为当前内容的验证证据。GitHub 检查绑定 remote main SHA，CI pending/临时故障/生产旧页面有限退避等待，CI 明确失败和权限错误停止。四个生产路由检查日期、来源 href、导航及最新 TC 日期/值；不访问 MacroMicro 外站，也不声称验证了 Vercel 部署 SHA。

保留 `.runtime/locks/` 下的锁文件；锁由 OS 在进程退出时释放，不靠删除文件解锁。Windows 使用原生 Job Object 约束子进程树，监督进程被强杀也会清理后代；POSIX 使用进程组，监督进程自身遭 SIGKILL 时仍需子级锁/checkpoint 防止重复操作。当前正式 Pi 定时任务已启用 `extensions: true`，浏览器仍需上述进程授权及有效网站会话；推送后使用 `run_scheduled_daily.py --verify-only --report-date YYYY-MM-DD` 检查实际发布。独立 Windows 计划任务尚未注册，不能与当前 Pi 入口同时启用；切换入口及外部告警服务需要另行授权配置，本次代码不会自动启用它们。

### 本地导航边缘回归（不访问外站）

在 `npm run build` 后启动本地 `npm run start -- --hostname 127.0.0.1 --port 3000`，另一个终端运行：

```bash
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe -B tests/check_nav_menu.py --base-url http://127.0.0.1:3000 --executable-path "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

该检查使用隔离的 headless Chrome，在 1440/800/390px 下实际操作 TC 菜单左/中/右斜向移入、切换库存、键盘导航与关闭，并校验顶边对齐和无横向溢出。只接受 loopback HTTP 地址，阻止外站请求，不使用已有 profile。它是显式本地检查，不加入日常采集或新调度。

### 只读健康检查与尚未覆盖的监督边界

```bash
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe -B scripts/check_daily_health.py
# 可重放指定时刻；时间必须带时区
C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe -B scripts/check_daily_health.py --now 2026-10-03T12:00:00+08:00 --grace-minutes 240
```

按北京时间 07:00 选择最近应执行周期，默认完成宽限 4 小时。缺报告、超期、失败/损坏状态、缺少成功阶段或当前内容与保存哈希不符时返回非零。`pending` 在宽限内不告警；`verified` 只表示当前本地文件匹配保存的成功验证，不是实时生产检查。历史成功 state 无哈希时返回 `verification_required`，需要仅验证已有成品，不重采集。工具不设置任何新 cron/OS 任务或外部告警通道。

正式 Pi 任务只在尾部调用 `--verify-only`，现有 wrapper 的锁、开始标记、deadline 尚未覆盖前面的 Pi AI；缺少 state 不能证明 AI 从未启动。不要在 Pi 任务内调用普通 wrapper 来嵌套 OpenCode。完整 Pi 监督需在 SDK 启动前接入；隔离 worker 无法继承当前 Chrome 进程授权，切换入口、替换调度扩展或激活新行为须另行确认。Pi/PC 重启仍需用户重新授权，当前未变更该边界。

日常任务不自行改写或提交工作流文档。明确授权的手动维护可在专用分支精确提交日报及已验证的方法文档；先通过本地校验和 PR/CI/Preview，再合并并核验 main 生产页面，最后清理本次分支并回到 main。无关文件始终排除。

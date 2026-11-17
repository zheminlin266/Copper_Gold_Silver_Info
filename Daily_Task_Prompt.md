# Grok bot 每日任务入口

你是“金银铜供需信息”日报的 Grok bot 执行者。完成研究、代码校验、提交和实际生产验证，或报告有证据的阻塞。当前仓库的 Daily_Report_Workflow.md 是唯一权威规范，先完整读取；本入口、旧 memory、旧调度提示冲突时，以当前工作流为准。每次读取最新文件，不沿用聊天中的旧副本。

## 预检

1. 确认实际仓库根目录、最新远程 main、git status、Python 3.12/3.13、Node.js 24 和所需 GitHub 权限。保留并隔离无关改动，不覆盖、回滚、删除或提交用户已有文件。使用当前云端真实解释器与路径，不照搬 Windows 路径、不启动 Pi/Codex/OpenCode 等其他 AI runner。
2. 读取 schema、data/research_policy.json、data/source_registry.json、已发现来源、会议日历和最近三份日报。记录实际工具能力：搜索、网页、X、PDF、浏览器；只使用可用且已授权的工具，不把无法调用的工具写成已执行。
3. 按 Asia/Shanghai 冻结 RUN_DATE、REPORT_DATE=RUN_DATE-1 和工作流三个窗口，跨午夜不重算。若入口已给目标日期则核对后沿用。report_time 写实际完成时刻。
4. 目标日报已存在时停止采集和写入，只恢复现有成品的校验/发布。存在同日 collection、冻结清单或 analysis 时先确认旧进程停止，读取已有材料后恢复，不另起重复采集。

## 研究与交接

报告日期从 2026-11-17 起使用以下入口；以下 python 表示预检确认的当前解释器：

```bash
python scripts/grok_research.py init YYYY-MM-DD
```

按输出路径填写 collection.json。先完成来源发现，再核验和写研究卡；逐源、逐账号、逐批保存真实工具结果。

- 每个策略来源都要有检查记录。required 来源完整结束才能发布；可选来源失败必须保留 partial/failed、实际 URL 和具体原因。Newsfile 正确分页到窗口边界，ASX 检查完整日期索引，Mining.com 三个分类真实读取，SMM 库存读取正文。搜索摘要不能代替正文或完整列表。
- 访谈必查 KE Report、Crux、Resource Talks、Mining Stock Daily，并补查业绩电话会及活动日历。RSS 日期先换算为北京；音频未听、视频无可靠字幕时不根据标题编造观点。
- X 主路径为已授权 Grok 原生工具，通道名 grok_x。逐账号核对用户 ID、handle 和主体，记录真实查询范围、分页终止及原帖。错误主体、查询失败、未翻完不能算零帖完成。只在普通工具不可用且备用环境已确认时按 grok_x -> playwright -> twscrape 顺序补查；限流、门禁或 challenge 停止，不绕过限制。
- 登记所有窗口内列表候选，包括之后会被排除的条目。正文超时、解码失败等保留为待核验；依次寻找原站、发行人 IR、交易所 PDF、明确署名转载。不把技术失败记作不相关。

字段和完整可复制样例见 scripts/README.md。确认发现清单完整后执行：

```bash
python scripts/grok_research.py prepare .runtime/grok/YYYY-MM-DD/collection.json
```

该命令生成不可覆盖的 collection.frozen.json 和 analysis.json。只在 analysis 中完善 summary、decisions、url_verification 和 dedup_log；保留 collection_manifest、完整 candidates 和真实覆盖审计。不得删改候选、改哈希或修改校验规则来通过任务。

每条候选都有 accept、reject 或 pending_verification 决策。reject 使用明确的内容原因码并写具体原因；技术失败不能使用内容原因码。发布前复查排除项中的钻探、资源、许可、建设、库存和项目融资，按供需路径与阶段判断，不能仅因没有新增产量排除，不设入选配额。

完整卡必须符合工作流第 6、7 节：中文事实摘要、可选且不重复的解释、真实引句、数字期间/单位/口径和有新增研究结论的重要性判断。claims.evidence 必须在同 URL 保存文本中逐字出现；其他来源使用带哈希的 evidence_documents。无法核验可按第 7 节接受 unverified 精简卡，禁止补写正文、importance 或非空 claims。所有 pending 必须先处理，不能静默消失。

## 写入、发布与完成条件

```bash
python scripts/report_builder.py .runtime/grok/YYYY-MM-DD/analysis.json --validate-only
python scripts/report_builder.py .runtime/grok/YYYY-MM-DD/analysis.json
```

最终日报只能由 report_builder 写入。代码会绑定冻结清单，检查来源覆盖、候选去向和真实 X 通道；不手工写 data/YYYY-MM-DD.json，不覆盖历史。研究审计摘要随日报保存，完整正文与截图按既有权限留在 ignored .runtime。

若 RUN_DATE 是周六，另按工作流第 9A 节处理 TC，指标身份、实际评估日期和值缺一不可；找不到合格值时不改 CSV，单独报告，不影响继续完成日报研究。

按工作流第 10 节完成内容校验、类型检查、Python/Node 测试和构建。清除继承的 NODE_OPTIONS；字体使用本地文件，不删除构建目录掩盖错误。通过后按第 11 节精确暂存授权路径并提交/推送 main；用户已授权此范围日常发布，无需逐次确认。授权不含代码、工作流、调度配置或其他无关文件。

推送后前台执行并等待退出：

```bash
python scripts/run_scheduled_daily.py --verify-only --report-date YYYY-MM-DD
```

只使用 verify-only 模式，不调用旧 AI runner。该命令预算至少 10800 秒，X 单段上限仍为 3600 秒。只有退出码 0、保存 state=success，且实际远程 main 对应 push CI 与生产内容验证通过，才宣告完成。纯维护验证现有报告，不生成新日报或 TC。

最终简要报告三个板块的入选数、覆盖缺口/待核验情况、TC 状态（周六）、提交 SHA 和生产验证结果。已推送、CI通过、生产通过分别如实报告；不要在仍等待工具或部署时结束并宣称完成。

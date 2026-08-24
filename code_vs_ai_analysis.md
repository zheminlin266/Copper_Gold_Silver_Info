可以。对这个仓库中**决定实际运行行为的代码、配置、schema、采集脚本、测试、CI、工作流文档、来源结构和近期日报样本**，我已经做完系统性阅读。先说明边界：`app/`、`components/`、`lib/`、`scripts/`、`tests/`、GitHub Actions、Next/TS 配置和核心数据结构我都覆盖了；图片、字体、`package-lock.json` 以及几十份同 schema 的历史日报/旧 HTML，我没有逐字逐份做内容审读，因为它们不会改变“哪些工作可代码化、哪些需要 AI”的判断。历史 JSON 本身已有测试统一加载校验。

## 一、核心结论

这个项目最适合演进成：

> **确定性代码外壳 + 小而集中的 AI 研究内核**

而不是继续让一个 AI Agent 从头到尾负责“算日期 → 搜索 → 浏览 → 判断 → 写 JSON → 校验 → Git → 发布”。

目前工作流明确把检索编排、来源打开、文件修改、校验、Git、发布，以及候选分析、事实提取、供需判断、去重和中文摘要统统交给 `gpt-luna`。 但代码实际上已经证明，大量规则都能稳定程序化：日期窗口、JSON Schema、发布时间窗口、URL 格式、`primary_metal` 一致性、来源核验计数、采集完整性、TC CSV、内容格式、测试、构建等都已经变成硬规则。 

我的判断是：

**按“流程节点数量”计算，大约 75%–85% 可以进一步纯代码化；真正需要 AI 的可能只有 15%–25%。但这 15%–25% 正是研究价值最高的部分。**

也就是说，AI 不应该消失，而应该从“执行整个流水线的人”变成“处理少数需要语义理解和研究判断的函数”。

---

# 二、现在项目实际上由四层组成

| 层 | 当前状态 | 是否需要 AI |
|---|---|---|
| Next.js 展示层 | 已经高度代码化 | **不需要** |
| 采集层 | X、Mining.com 部分代码化，其他主要靠 Agent | **绝大部分可继续代码化** |
| 研究分析层 | 主要由 Agent 完成 | **核心部分需要 AI** |
| 校验/发布层 | 已有较强代码化 | **基本不需要 AI** |

前端已经非常明确：本地 JSON/CSV 是唯一数据源，Next.js 负责读取、排序、统计、搜索、渲染和静态页面。首页只是取最新报告并按 `primaryMetal` 分组；日报页、归档页和 TC 页面也全部是确定性逻辑。  

所以**网站这一侧没有任何理由加入 AI**。README 里“网站本身不调用模型”的方向是正确的。

---

# 三、逐环节判断：哪些应该纯代码化

## 1. REPORT_DATE 和时间窗口

**100% 代码化。**

现在：

- `RUN_DATE`
- `REPORT_DATE = RUN_DATE - 1`
- Part 1 = R-2 到 R
- Part 2 = R
- Part 3 = R
- 北京时间
- 周六 TC
- 节假日实际发布日期

这些都是严格规则。工作流已经把它们定义得非常清楚。

而 validator 甚至已经检查窗口必须精确等于这些值。

**AI 完全不应该参与日期计算。**

---

## 2. 每日任务 preflight

同样 **100% 代码化**：

- 检查 `git status`
- 检查目标 JSON 是否已存在
- 加载最近三日报
- 加载 schema
- 加载来源注册表
- 加载会议日历
- 检查 X 登录
- 计算是否周六
- 检查 TC 上一次记录
- 创建运行目录
- 禁止覆盖已有 raw materials

这些现在散落在 Prompt 和不同脚本中。

尤其 `script_utils.py` 已经有严格日期解析、Chrome 解析和 atomic write，说明项目实际上已经在朝这个方向走。

应当最终变成类似：

```text
python scripts/daily_pipeline.py 2026-08-15
```

然后代码自己进入：

```text
PRECHECK
→ COLLECT
→ NORMALIZE
→ AI_ANALYZE
→ VERIFY
→ DEDUP
→ BUILD_REPORT
→ VALIDATE
→ BUILD
→ PUBLISH
```

---

# 四、Part 2 X：采集几乎已经可以完全代码化

这部分目前是仓库里最成熟的 collector。

`scripts/x_search.py` 已经明确写着：

> 无 LLM 依赖

它自己处理：

- 登录状态
- persistent Chrome profile
- storage state fallback
- 账号搜索
- X 高级查询
- 时间解析
- UTC → 北京时间
- 日期过滤
- 正文获取
- Status URL
- 部分失败
- 完整失败
- 0 结果与失败的区别
- 原始材料写入
- exit code

 

这里**采集本身完全不需要 AI**。

但当前有一个明显的架构问题：

### X 来源存在两个真相来源

`x_search.py` 自己硬编码了一大批：

```python
SEED_ACCOUNTS
OFFICIAL_ACCOUNTS
```



与此同时根目录还有：

```text
mining_people_broadcast_x_articles.csv
```

里面保存了更丰富的人物、职业、专长、X 地址等信息。

工作流还要求维护：

```text
data/sources_discovered.json
```

但目前它仍然是：

```json
"entries": []
```



这意味着**来源数据库和实际执行代码存在漂移风险**。

### 应修改为

```text
source_registry
        ↓
X collector
YouTube collector
Podcast collector
Web collector
```

而不是 `x_search.py` 自己保留一份账号名单。

---

# 五、X 哪部分仍需要 AI？

**不是“找帖子”，而是“理解帖子”。**

例如抓到：

> 公司完成一轮钻探，某孔见矿 25m @ 1.2% Cu

纯代码能发现：

- copper
- drill
- 25m
- 1.2%
- 公司名字
- URL
- 日期

但是不能稳定回答：

> 这是不是值得进入供需日报？

因为可能只是：

- 很早期勘探；
- 不改变当前资源量；
- 与实际供给相差十年；
- 只是推广性质；
- 是旧结果重发；
- 文章谈铜但真正重要的是黄金；
- 数字很大但没有经济意义。

这就是 AI 应该保留的地方。

---

# 六、Mining.com：目前只代码化了一半

`mining_com_search.py` 做得不错，它已经可以：

- Playwright
- anti-automation 参数
- 页面真实性检查
- DOM 抽取
- 日期匹配
- URL 过滤
- structured JSON 输出
- 明确失败状态



但是当前写死：

```python
CATEGORY_URL = "https://www.mining.com/commodity/copper/"
```

因此工作流里金和银仍需要额外搜索。

这完全可以改成：

```text
mining_com_search.py copper 2026-08-15
mining_com_search.py gold   2026-08-15
mining_com_search.py silver 2026-08-15
```

甚至：

```python
for metal in ["copper", "gold", "silver"]:
    collect_category(metal, report_date)
```

然后程序进一步自动：

```text
分类页
 ↓
候选 URL
 ↓
逐篇打开
 ↓
正文提取
 ↓
发布时间解析
 ↓
canonical URL
 ↓
原始文本缓存
```

整个过程都不需要 AI。

AI只需要拿到**已经提取完成的文章正文**。

---

# 七、Part 1 访谈/YouTube/Podcast：采集也应该代码化

目前这部分是 Agent 手动“搜”。

这是非常值得改造的部分。

可以代码化：

```text
已知 YouTube channel
→ 最近 72h 视频

已知 Podcast RSS
→ 最近 72h episode

公司 IR
→ 最近 webcast/presentation

conference_calendar
→ 当前是否位于会议窗口
→ 自动增加会议来源
```

`conference_calendar.json` 已经提供：

- 会议名称
- typical month
- metals
- search types
- target part
- before/after window



也就是说目前很多“Prompt 规则”实际上已经具有数据库雏形。

### 这里不需要 AI 的部分

发现：

```text
视频是什么时候发布的？
标题是什么？
频道是谁？
URL 是什么？
有没有字幕？
字幕文本是什么？
```

全部代码。

### AI 需要做的是

给它字幕之后判断：

> 访谈的 40 分钟里，到底哪 3 分钟出现了新的可归因供需事实？

这个是 AI。

---

# 八、普通新闻来源发现：可以大量代码化，但不能完全取消 AI

目前工作流规定优先级：

1. 官方/监管/交易所
2. 公司新闻稿
3. Reuters / Mining.com
4. 行业媒体和转载



这实际上可以建立一个来源注册系统：

```text
domain
source_name
source_tier
source_type
language
metal_focus
fetch_method
requires_browser
```

比如：

```text
codelco.com        primary   company_ir
sec.gov            primary   regulator
asx.com.au         primary   exchange
sedarplus.ca       primary   regulator
mining.com         secondary media
reuters.com        secondary media
```

然后代码可以自动赋予**来源等级**。

这比让 AI 每天重新决定“哪个站更权威”稳定得多。

---

# 九、URL 核验：80% 可以代码化

现在的 workflow 要求：

- URL 必须能打开
- 具体文章，而非首页
- 标题匹配
- 日期匹配
- 主体匹配
- 核心数字匹配



前四项基本全部能程序化。

例如：

```text
HTTP status
canonical URL
<title>
article headline
published time
author
domain
正文字符数
页面是否 login wall
```

都可以由代码完成。

### 真正需要 AI 的是最后一层

比如 JSON 写：

> 二季度铜产量同比下降 11%

网页中确实有：

```text
Q2 copper output 96kt versus 108kt...
```

程序可以通过数字查找帮助检查。

但如果文章写的是：

> production attributable to operations excluding...

而 JSON 写成：

> 集团总产量

这属于**口径语义错误**。

单纯字符串匹配无法判断。

所以应当分成：

```text
technical verification      → code
semantic evidence checking  → AI
```

---

# 十、最值得改造的地方：Evidence 模型

现在 AI 直接产生：

```json
"excerpt": "...",
"interpretation": "...",
"importance": "..."
```

我建议不要让 AI 直接从网页跳到最终日报。

中间增加：

```json
{
  "claim": "Bayan Khundii Q2 produced 11,709 oz gold",
  "evidence": "produced and sold 11,709 ounces...",
  "source_url": "...",
  "evidence_type": "actual",
  "period": "2026-Q2",
  "unit": "oz",
  "value": 11709
}
```

这样 AI 先输出**Claims + Evidence**。

然后代码检查：

```text
每个 factual claim
→ 必须有 source
→ 必须有 evidence
→ 数字必须能在 evidence 找到
→ period/unit 不得为空
```

最终才允许生成：

```text
excerpt
interpretation
importance
```

这会明显降低 hallucination 风险。

---

# 十一、`metal_tags`：可以部分代码化

例如：

```text
gold
gold production
Au
ounces of gold
silver
Ag
copper
Cu
copper concentrate
```

可以规则识别候选金属。

但是当前工作流的要求不是：

> 文中提到了什么金属

而是：

> 哪个金属具有**实质供需关联**



这就是关键区别。

例如：

> 某铜矿公司提到黄金价格上涨

代码可能给：

```text
["copper", "gold"]
```

但正确可能只是：

```text
["copper"]
```

所以推荐：

```text
规则生成 candidate_tags
       ↓
AI 确认 semantic_tags
```

---

# 十二、`primary_metal` 仍然应该 AI 判断

当前规则是：

> 按最重要的未来供需变化或催化剂，而不是标题顺序决定主金属。



这是一个典型的研究判断。

例如一个项目：

```text
8Moz gold
400Moz silver
```

但开发决策真正受银项目驱动。

按数量、单价、标题关键词，都可能选错。

所以 `primary_metal`：

**不建议完全规则化。**

可以让规则提出候选，最终 AI 选择。

---

# 十三、`supply_demand`：Hybrid

显式新闻很容易：

```text
mine shutdown → supply
production increase → supply
ETF inflow → demand
central bank purchase → demand
```

这部分可以规则化。

但例如：

> 政府批准新的铜矿 royalty regime

究竟是：

```text
supply
demand
both
```

以及方向和时间范围，需要解释政策传导。

所以：

> 简单事件规则自动分类，复杂事件 AI fallback。

---

# 十四、事实类型识别：必须保留 AI

这是整个日报最重要的 AI 功能之一。

你现在的日报实际上做得很好的一点，是不断区分：

```text
actual production
guidance
resource
reserve
PEA
DFS
historical estimate
exploration result
conceptual production
management target
analyst estimate
```

例如 8 月 14 日的日报明确说 Diablillos 的 DFS、项目产量和 2029 首产目标是**项目方案，不是实际产量**；Faraday 的历史铜资源和 15 万吨/年是概念方案，不能当当前供应。

8 月 15 日又明确区分 Bayan Khundii 已实现季度产量，与 Tereg Uul / Zuun Mod 勘探管线。

这种判断就是你这个项目真正的研究价值。

**这部分不要尝试用 regex 替代 AI。**

---

# 十五、语义去重：不能完全纯代码

URL 去重当然应该代码化：

```text
utm_source
utm_campaign
fragment
www
trailing slash
canonical URL
```

内容 hash 也可以代码化。

公司+项目+日期也可以做初筛。

但是：

> Reuters、公司新闻稿、Mining.com 和新浪分别报道同一个事故，是不是同一事件？

需要语义理解。

尤其：

> 昨天报道矿山停产，今天报道停产时间延长两周。

从实体上完全一样，但**第二条实际上是新的供需信息**。

所以应使用：

```text
Code:
exact URL duplicate
canonical duplicate
same-document hash
obvious entity/date duplicate

AI:
same event?
incremental information?
old event or genuine update?
```

---

# 十六、来源冲突：AI 仍然重要

工作流规定：

> 来源冲突时优先一手、时间更近、口径更完整。



“谁是一手来源”可以代码化。

但：

> 两个看起来都像一手来源的数字为什么不同？

可能因为：

- equity vs attributable production
- payable vs contained metal
- concentrate vs cathode
- quarterly vs YTD
- actual vs preliminary
- wet metric tonne vs dry metric tonne

这不能仅靠 URL 优先级解决。

需要 AI 做口径比较。

重大冲突最好进一步升级成人工确认。

---

# 十七、`excerpt`：AI 仍然需要，但应该受 Evidence 约束

`excerpt` 不是单纯抽取原文。

它实际上是：

> 从长文章里选择与金银铜供需最相关、同时又能被来源直接支持的事实。

这是 summarization + selection。

AI适合做。

但是不能允许自由发挥。

正确结构应该是：

```text
raw source
 ↓
evidence claims
 ↓
AI factual compression
 ↓
excerpt
```

---

# 十八、`interpretation`：明确应该 AI

这字段的本质是：

> 事实通过什么机制影响供应/需求？

例如：

```text
permit delayed
→ construction delayed
→ commissioning delayed
→ concentrate supply delayed
```

或者：

```text
recovery rate improves
→ same throughput produces more saleable metal
→ near-term physical supply increases
```

这种因果链条是研究推理。

不建议代码化。

---

# 十九、`importance`：最不应该纯代码化

目前 validator 已经检查：

- 80–300 字
- 2–4 句
- 有数字/日期/比较/里程碑
- 有“意味着/导致/风险/增加”等分析词



这很好，但必须认识到：

**它只能检查形式，不能检查研究质量。**

比如 AI 完全可以写出一段：

- 150 字；
- 3 句；
- 有数字；
- 有“意味着”；
- 实际上全是废话。

它仍然能通过 validator。

所以：

```text
importance formatting → code
importance intelligence → AI
```

这条边界非常明确。

---

# 二十、日报总 `summary`：Hybrid

现在 summary 要：

- ≤300 字
- 按金属
- 只写方向
- 不逐项罗列
- 不写检索过程



可以先由代码生成 skeleton：

```text
黄金：...
白银：...
铜：...
```

甚至从 accepted signals 得出：

```text
supply_positive
supply_negative
demand_positive
demand_negative
neutral
```

但最后如何压缩成自然且不误导的研究摘要，AI价值仍然明显。

因此建议：

> 代码生成事实框架，AI完成最终文字。

---

# 二十一、中英翻译：仍然属于 AI 能力

代码当然可以调用翻译服务。

但“调用翻译模型”本质仍是 AI，不是 deterministic code。

尤其矿业术语：

```text
contained metal
head grade
recovery
throughput
M&I resource
inferred resource
TC/RC
payability
commissioning
ramp-up
```

如果要求研究级中文，就应该保留 LLM/机器翻译模型，并使用术语表约束。

---

# 二十二、TC 是最适合进一步彻底代码化的模块

TC 目前很多步骤已经是严格算术：

```text
PRIOR = CSV latest
CHANGE = VALUE - PRIOR
```

日期唯一、单位、URL、CSV header 都已经代码验证。

当前 CSV 已经更新到 2026-08-14，并且最近来源已经稳定使用：

```text
https://hq.smm.cn/h5/copper-ore-data
```



因此完全可以开发：

```text
smm_tc_collector.py
```

自动：

```text
读取 SMM public data page
→ 找 Imported Copper Concentrate Index (Weekly)
→ assessment date
→ value
→ 与 CSV 最后一项比较
→ 计算 change
→ 幂等检查
→ append
→ parse again
```

### AI 什么时候才介入？

仅当：

```text
页面结构改变
指标名称模糊
公开页失效
必须搜索第三方转载
两个来源冲突
节假日发布日期异常
```

正常星期六：

**完全没必要调用 AI。**

这能显著降低 TC 出错概率和每日 Agent 工作量。

---

# 二十三、构建、测试、发布：全部代码化

这一层已经基本完成。

`package.json`：

```text
validate:content
test
build
```



GitHub Actions：

```text
Python compile
Python unittest
npm ci
validate
test
Next build
```



这完全不需要 AI。

甚至部署后的：

```text
/
daily/date
/archive
/historical-tc
```

都可以用 Playwright 自动 smoke test。

### UI 检查同样不需要 AI

例如：

- TC 菜单 hover 后出现
- 鼠标移动到 menu 不消失
- viewport <800 无横向 overflow
- tooltip 正确
- 页面无 console error

都是 Playwright assertion。

AI vision 最多用于额外视觉 QA，不应该作为主要正确性检查。

---

# 二十四、目前最缺的一层：Orchestrator

这是整个项目当前最大的架构缺口。

仓库有：

```text
x_search.py
mining_com_search.py
validate-content.mjs
```



但没有真正的：

```text
daily_pipeline.py
```

所以现在实际上是：

```text
Prompt
   ↓
AI Agent
 ┌────────────────────────────┐
 日期 / 搜索 / 浏览 / 判断
 写文件 / 校验 / retry
 git / deploy
 └────────────────────────────┘
```

这导致 AI 承担大量它本来不应该负责的 deterministic state management。

我建议改成：

```text
                ┌──────────────┐
                │ Scheduler     │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │ Preflight     │  ← code
                └──────┬───────┘
                       ↓
          ┌────────────┴────────────┐
          ↓             ↓           ↓
     Broadcast       X Posts       News
     Collector       Collector     Collectors
          └────────────┬────────────┘
                       ↓
                Raw Candidate DB
                       ↓
                 Normalize/Filter    ← code
                       ↓
                  AI Research
                       ↓
              Evidence verification
                code + AI
                       ↓
               Semantic Dedup AI
                       ↓
                 Report Builder      ← code
                       ↓
                 Validators          ← code
                       ↓
              Test / Build / Deploy  ← code
```

---

# 二十五、AI 最好不要再拥有文件写入权

这是我最重要的架构建议之一。

当前 `Daily_Task_Prompt.md` 要求 Agent：

> 实际完成研究、写入、校验、提交、推送和上线检查。



更稳健的模型应该是：

### AI 输入

```json
{
  "candidate_id": "...",
  "source": "...",
  "url": "...",
  "published_at": "...",
  "raw_text": "...",
  "previous_related_events": [...]
}
```

### AI 输出

严格 JSON：

```json
{
  "decision": "include",
  "primary_metal": "copper",
  "metal_tags": ["copper"],
  "supply_demand": "supply",
  "claims": [...],
  "interpretation": "...",
  "importance": "...",
  "confidence": 0.91
}
```

然后：

> **代码负责最终拼装和写入 `data/YYYY-MM-DD.json`。**

AI 不需要知道：

```text
目标文件在哪里
git 当前是什么状态
是否允许 overwrite
怎么提交
什么时候 push
```

这样可以极大减少误写文件、覆盖旧日报和状态漂移问题。

---

# 二十六、建议新增一个 staging database

现在大量 audit 信息直接被写进日报里的中文自然语言，例如最新日报中的：

> 首次 headless 采集部分失败；随后登录墙；再使用 persistent Chrome headed retry……



信息是完整的，但**机器不可查询**。

建议使用 Python 标准库 SQLite：

```text
data/pipeline.sqlite
```

或者运行期不进 Git：

```text
.runtime/pipeline.sqlite
```

例如：

```text
runs
sources
queries
fetch_attempts
candidates
documents
claims
ai_decisions
verification
dedup_decisions
```

这样你可以回答：

> 最近一个月 Mining.com 成功率多少？

> X 哪些账号连续 30 天零结果？

> 哪些来源最常产出合格信号？

> AI reject 最多的原因是什么？

> 哪种来源最终被纳入率最高？

现在这些信息虽然存在 `search_log`，但都是 prose，无法真正分析。

---

# 二十七、来源 registry 应该重构

建议把：

```text
mining_people_broadcast_x_articles.csv
data/sources_discovered.json
x_search.py SEED_ACCOUNTS
x_search.py OFFICIAL_ACCOUNTS
conference_calendar.json
```

统一成：

```text
data/source_registry.json
```

结构例如：

```json
{
  "name": "Rick Rule",
  "kind": "person",
  "priority": 2,
  "metals": ["gold", "silver", "copper"],
  "channels": {
    "x": {
      "handle": "RealRickRule"
    },
    "youtube": [],
    "website": []
  },
  "topics": ["mining", "financing"],
  "active": true,
  "last_verified": "2026-08-01"
}
```

collector 不再硬编码任何人。

---

# 二十八、Schema 也有一些历史技术债

`daily_report_schema.json` 和 TS types 仍然支持：

```text
browser_use
rss_fallback
```

而当前 workflow 已经要求成功 X 采集必须：

```text
playwright
```

validator 也强制新日报是 `playwright`。

Schema 里甚至还残留：

```text
image_source.method = ai_generated
```



但现在工作流又明确说：

> 不要生成图片或 AI 模块。

因此 schema、TypeScript type 与实际 workflow 出现了一些**历史兼容字段漂移**。

长期建议不要继续用：

```javascript
if (report.date >= "2026-08-09")
```

这样的规则版本管理。

当前 validator 中已经积累多个日期门槛：

```text
PRIMARY_METAL_REQUIRED_FROM
IMPORTANCE_VALIDATED_FROM
COLLECTION_COMPLETENESS_REQUIRED_FROM
VERIFICATION_STATUS_REQUIRED_FROM
...
```



更好的方式是给报告增加：

```json
"schema_version": 3
```

然后：

```text
v1 historical
v2 primary_metal
v3 verification/evidence
```

维护会干净很多。

---

# 二十九、`ReportAudit` 还有数据没有展示

当前 `ReportAudit` 展示：

- sources checked
- result
- dedup



但 JSON 里还有：

```text
url_verification
part2_channel
new_sources_discovered
mining_com_source_note
part2_deduped_urls
verification failures
```

目前很多没有直接展示。

如果“审计透明度”是这个站的重要定位，可以考虑把这些数据结构化并展示得更完整。

这同样完全是代码，不需要 AI。

---

# 三十、历史 HTML/CSS 不属于当前核心系统

旧：

```text
Historical_Daily_Reports/*.html
assets/report.css
assets/report-detail.css
```

仍有历史引用。

但是 Next 配置已经将历史 URL 301 到：

```text
/archive
/daily/:date
```



因此这些文件现在主要是：

> migration provenance / legacy archive

不是当前业务逻辑。

可以继续保留作为历史证据，但最好明确放入：

```text
legacy/
```

避免以后误以为它们还参与生产网站。

---

# 三十一、哪些东西“不应该试图消灭 AI”

最终真正应当长期保留 AI 的核心，我归纳为 **8 项**：

1. **非结构化内容的事实理解**  
   从长文、访谈、字幕中找真正新增的供需事实。

2. **事实类型判断**  
   actual / guidance / resource / reserve / PEA / DFS / target / speculation。

3. **供需因果判断**  
   一个事实通过什么链路影响 mine → concentrate → smelter → inventory → end demand。

4. **`primary_metal` 编辑判断**  
   多金属事件究竟由哪个金属驱动。

5. **语义去重及“是否有新增信息”**  
   同事件的新进展不能被机械去掉。

6. **来源冲突和统计口径比较**  
   判断两个数字为什么不同。

7. **`interpretation` / `importance`**  
   这是项目最有研究价值的部分。

8. **最终中文研究表达和翻译**  
   保持专业、准确、区分事实与判断。

其他大多数事情都应该逐渐从 AI Agent 手里拿走。

---

# 三十二、另外还有极少数必须保留“人”的环节

这和 AI 又不完全一样。

X 登录目前明确需要用户实际完成：

- credentials
- 2FA
- 登录确认

`setup_x_login.py` 本来就是这样设计的。

另外建议以下情况升级人工：

```text
两个一级来源给出 materially conflicting data
AI confidence 很低
涉及定义/口径改变
目标日报文件已存在但原因不明
工作区有未知用户修改
首次出现新指标/新数据体系
```

不要让 AI 自己猜。

---

# 三十三、我会如何重新划分职责

最终应当是：

| 工作 | Code | AI | Human |
|---|---:|---:|---:|
| 日期/窗口 | ✅ | | |
| 调度 | ✅ | | |
| 来源 registry | ✅ | | |
| X 抓取 | ✅ | | Login |
| Mining.com 抓取 | ✅ | | |
| YouTube/Podcast 发现 | ✅ | | |
| 网页正文提取 | ✅ | | |
| 发布时间解析 | ✅ | AI fallback | |
| URL technical verification | ✅ | | |
| 来源层级 | ✅ | AI fallback | |
| 关键词预筛 | ✅ | | |
| 金属候选识别 | ✅ | ✅ | |
| 是否值得纳入 | | ✅ | |
| actual/guidance/resource 等分类 | | ✅ | |
| supply/demand 因果 | | ✅ | |
| `primary_metal` | | ✅ | |
| 精确 URL 去重 | ✅ | | |
| 语义事件去重 | ✅初筛 | ✅ | |
| 来源冲突 | ✅整理 | ✅ | 高风险 |
| factual evidence mapping | ✅检查 | ✅提取 | |
| `excerpt` | | ✅ | |
| `interpretation` | | ✅ | |
| `importance` | 格式 QA | ✅ | |
| summary | ✅骨架 | ✅ | |
| JSON 拼装 | ✅ | | |
| Schema validation | ✅ | | |
| TC 正常更新 | ✅ | fallback | |
| Tests/build | ✅ | | |
| UI smoke tests | ✅ | | |
| Git commit/push | ✅ | | 授权边界 |
| Deployment check | ✅ | | |

---

# 三十四、改造优先级

如果只做最有价值的改造，我会按这个顺序：

### P0 — 先把 AI 从“执行器”变成“分析器”

开发：

```text
scripts/daily_pipeline.py
```

代码管理所有状态。

**这是第一优先级。**

---

### P0 — 统一 Source Registry

消灭：

```text
CSV 一份
x_search.py 一份
sources_discovered 一份
```

之间的漂移。

---

### P0 — 建立 Raw Candidate / Evidence 中间层

不要：

```text
网页 → AI → 最终日报 JSON
```

改成：

```text
网页
↓
Raw Document
↓
Candidate
↓
Claims + Evidence
↓
Research interpretation
↓
Final JSON
```

这是提升可靠性的关键。

---

### P1 — Collector 全代码化

新增：

```text
collectors/x.py
collectors/mining_com.py
collectors/youtube.py
collectors/podcast.py
collectors/company_ir.py
collectors/conference.py
collectors/tc.py
```

---

### P1 — TC 彻底自动化

正常周六几乎做到 **0 AI call**。

---

### P1 — Structured run manifest

替代大量：

```json
"part3_sources_checked": [
  "使用Python……",
  "随后……",
  "同时执行……"
]
```

变成结构化 audit。

---

### P2 — AI Research Kernel

最终 AI 接口可能只有三四个：

```text
analyze_candidate()
compare_sources()
deduplicate_events()
compose_report_summary()
```

而不是“完成整个日报”。

---

# 三十五、最理想的最终状态

每天 07:00：

```text
Code scheduler starts
        ↓
Code calculates REPORT_DATE
        ↓
Code checks workspace/state
        ↓
Collectors fetch everything
        ↓
Code removes obvious garbage
        ↓
Code normalizes documents
        ↓
AI evaluates only qualified candidates
        ↓
Code verifies evidence and schema
        ↓
AI resolves semantic duplicates
        ↓
Code assembles JSON
        ↓
AI produces final metal-level summary
        ↓
Code validates
        ↓
Tests
        ↓
Build
        ↓
Commit / deploy
        ↓
Playwright production verification
```

如果当天抓到 200 个网页：

> 不应该把 200 个都给 AI。

代码先把：

- 超日期；
- 重复 URL；
- 纯价格；
- 非目标金属；
- 无正文；
- 非原创 X；
- 已收录历史 URL；
- 明显重复新闻；

过滤掉。

可能剩 25 条。

AI 分析 25 条，最终纳入 5 条。

这才是更合理的系统。

---

## 最后的判断

现在这个项目**不是“需要 AI 才能运行的网站”**。

它本质上是：

> **一个确定性的金银铜 research data pipeline，里面有一个必须保留 AI 的研究判断环节。**

目前主要问题是这两个层次还没有彻底分开。

你现在让 AI 承担了太多：

```text
workflow engine
crawler
browser operator
state manager
file writer
research analyst
editor
QA
release engineer
```

其中真正应该长期留给 AI 的，基本只有：

> **研究分析师 + 编辑。**

其他角色都应该尽量代码化。

而且现有仓库已经有很好的基础：严格 schema、失败/零结果区分、atomic write、Playwright collector、TC parser、强 validator、测试和 CI 都说明这条路线已经走了一半。  

**如果继续演进，我会把目标定成：“80% deterministic pipeline + 20% evidence-grounded AI research kernel”。** 这会比继续扩大 Daily Prompt 更稳定、更便宜、更容易测试，也更符合这个项目强调“可核验供需信号”的定位。

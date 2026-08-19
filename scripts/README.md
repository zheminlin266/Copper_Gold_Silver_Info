# 支持的脚本

- `pipeline_contracts.py`：标准库数据类和严格校验，定义采集、分析和运行清单边界。
- `daily_pipeline.py`：安全的日期窗口预检和显式采集编排；默认不启动浏览器或外部采集。
- `report_builder.py`：唯一可以写入 `data/YYYY-MM-DD.json` 的分析结果投影器，默认拒绝覆盖。
- `setup_x_login.py`：设置 X 的 Playwright 登录会话。
- `x_search.py`：按权威工作流采集 X 原始候选。
- `mining_com_search.py`：按日期从 Mining.com 金、银、铜分类页采集候选。
- `validate-content.mjs`：校验日报内容。

## 确定性流水线

```bash
python scripts/daily_pipeline.py 2026-08-17 --dry-run
python scripts/daily_pipeline.py 2026-08-17 --collect-mining --collect-x
python scripts/report_builder.py .runtime/pipeline/2026-08-17/<run-id>/analysis.json
```

预检会读取 `data/source_registry.json`、计算北京时区窗口并创建运行清单，但不会调用 AI、浏览器或采集器。采集开关必须显式提供；采集失败会记录为失败，不能变成零结果成功。分析完成后只把完整、带证据的 bundle 交给 `report_builder.py`。

安装 Python 依赖：

```bash
python -m pip install -r scripts/requirements.txt
```

可选 X 通道不会改变基线依赖，按需安装：

```bash
python -m pip install -r scripts/requirements-optional.txt
```

运行采集脚本时使用本项目要求的 managed Python 3.13；不要改用 Python 3.14 或 browser-use 的 Python 3.12。

`x_search.py` 固定按 `web_access_xai -> twscrape -> Playwright` 顺序尝试。web-access 只读取 `--web-access-input PATH` 或 `X_WEB_ACCESS_INPUT` 指向的外部 staging JSON；Python 不调用 AI 或网络 SDK。有效 staging 已完成账户不会重复查询，失败或缺失账户才进入下一路径。未设置 `X_TWSCRAPE_ENABLED`（或设置为其他值）时 twscrape 保持启用；设置为 `0`、`false`、`no` 或 `off` 会在导入 twscrape 前将其标记为不可用，继续选择 Playwright。twscrape 只使用一个 `auth_token`/`ct0` cookie 账号，不使用密码登录。账号请求严格串行，默认每个账号间随机等待 `uniform(35.0, 50.0)` 秒；可用 `X_SAFE_DELAY_MIN_SECONDS` 和 `X_SAFE_DELAY_MAX_SECONDS` 配置范围（各为 5-300 秒），旧版 `X_SAFE_DELAY_SECONDS` 可固定覆盖。每个查询默认最多返回 20 条结果，可用 `X_MAX_RESULTS_PER_QUERY` 调整（1-500）。这些设置不保证不会触发 X 限制；不启用代理轮换、账号轮换或自动登录。

可用 `CHROME_EXECUTABLE` 覆盖 Chrome 路径；未设置或系统 Chrome 不存在时使用 Playwright Chromium。

原始采集失败必须非零退出，不能伪装成零结果。退出码 4 表示已写入审计文件的部分结果；其他非零退出均为失败。采集完整完成但没有窗口内合格候选时，可以成功返回空结果。X partial/failed 仍保留候选与 sidecar 覆盖审计，日报页面显示完成账户数/总账户数及原因；只有 Part 1 或 Part 3 失败才阻止发布。

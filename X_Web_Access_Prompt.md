# X web-access（xAI）staging 提示

使用 web-access 或 web search 时固定指定 `provider=xai`。按注册表顺序逐个账号查询，或只使用很小的账号批次；不要真实调用本地 Python SDK、AI SDK 或其他网络 SDK。Python 端只读取并严格验证 staging JSON。

## 查询边界

- `report_date` 是北京时间（Asia/Shanghai）日期。
- 只接受北京时间 `report_date 00:00:00` 至 `23:59:59` 窗口内的原帖。
- 只使用原作者帖子；搜索摘要、截图、转发内容、引用摘要不能替代原帖。
- 逐条核对原作者、handle、非空正文、x.com/twitter.com status URL 和带时区的绝对 `publish_time`。
- 账号出现登录墙、401/403/429、challenge、CAPTCHA、suspension 或账号不可用时，记录失败原因并停止新增流量，不切换账号规避限制。

## staging JSON

文件必须是一个 JSON 对象，字段只能是：

```json
{
  "provider": "xai",
  "report_date": "2026-08-19",
  "accounts_total": 2,
  "accounts_completed": 1,
  "account_results": [
    {
      "source_id": "x-example",
      "handle": "example",
      "status": "complete",
      "error": null,
      "posts": [
        {
          "author": "Example",
          "handle": "example",
          "url": "https://x.com/example/status/123",
          "text": "Original post text",
          "publish_time": "2026-08-19T10:00:00+08:00"
        }
      ]
    },
    {
      "source_id": "x-other",
      "handle": "other",
      "status": "failed",
      "error": "login wall",
      "posts": []
    }
  ]
}
```

`accounts_total` 必须等于 `data/source_registry.json` 中带 `x_handle` 的账号数。`source_id` 和 `handle` 必须唯一匹配该注册表。每个账户只能出现一次；状态只能是 `complete` 或 `failed`。失败账户必须有非空 `error`，完成账户可以有空 `posts`。帖子必须属于对应账号，正文非空，URL 必须是 status URL，时间必须带时区并落在北京时间 `report_date` 内。未知字段、未知账号、重复账户、重复帖子、日期、计数或结构错误都不要输出可用 staging。

保存后运行：

```bash
python scripts/x_search.py REPORT_DATE --headless --web-access-input PATH
```

命令会按 `web_access_xai -> twscrape -> playwright` 回退。web-access 已完成的账号不会重复查询；失败或缺失账号才交给后续路径。整个运行仍保持单账号、串行、低频和安全停止边界。

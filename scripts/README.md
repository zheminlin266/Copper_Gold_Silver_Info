# 支持的脚本

- `setup_x_login.py`：设置 X 的 Playwright 登录会话。
- `x_search.py`：按权威工作流采集 X 原始候选。
- `mining_com_search.py`：按日期从 Mining.com 铜分类页采集候选。
- `validate-content.mjs`：校验日报内容。

安装 Python 依赖：

```bash
python -m pip install -r scripts/requirements.txt
```

可用 `CHROME_EXECUTABLE` 覆盖 Chrome 路径；未设置或系统 Chrome 不存在时使用 Playwright Chromium。

原始采集失败必须非零退出；禁止把空结果或失败结果当作成功。

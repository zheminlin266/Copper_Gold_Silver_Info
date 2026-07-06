"""
X (Twitter) 登录设置脚本 v2 — 使用 Playwright 持久化 Chrome profile。

使用 Playwright 的 launch_persistent_context 直接打开 Chromium，
所有 cookies/login 状态直接写入持久化目录，无需导出/导入。

用法:
    python scripts/setup_x_login.py              # 默认超时 300 秒
    python scripts/setup_x_login.py --timeout 600  # 自定义超时
"""

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / ".browser_profile" / "chromium-data"
STORAGE_STATE_FILE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"
CHROME_EXECUTABLE = "C:/Program Files/Google/Chrome/Application/chrome.exe"


async def main():
    # 确保 stdout 实时输出（非 TTY 环境下默认缓冲）
    sys.stdout.reconfigure(line_buffering=True)

    timeout = 300
    for i, arg in enumerate(sys.argv[1:], start=1):
        if arg.startswith("--timeout="):
            timeout = int(arg.split("=", 1)[1])
        elif arg == "--timeout" and i < len(sys.argv) - 1:
            timeout = int(sys.argv[i + 1])

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  X (Twitter) 登录设置")
    print("=" * 60)
    print()
    print(f"Profile 目录: {PROFILE_DIR}")
    print(f"Auth 存储:    {STORAGE_STATE_FILE}")
    print(f"超时时间:     {timeout} 秒")
    print()
    print("即将打开 Chromium 并跳转到 X 登录页面。")
    print("请在浏览器中完成以下操作:")
    print("  1. 登录你的 X 账号")
    print("  2. 如有 2FA 验证，请完成验证")
    print("  3. 确认已成功登录到 X 首页")
    print()
    print(f"浏览器将在 {timeout} 秒后自动关闭并保存登录状态。")
    print()

    # 使用 Playwright 的 async API，支持 launch_persistent_context
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # 尝试使用用户安装的 Chrome，如果版本不匹配则回退到 Playwright 的 Chromium
        try:
            print("正在启动 Chrome (用户安装版本)...")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                executable_path=CHROME_EXECUTABLE,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                viewport={"width": 1280, "height": 900},
            )
        except Exception as e:
            print(f"用户 Chrome 启动失败 ({e})，使用 Playwright Chromium...")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                viewport={"width": 1280, "height": 900},
            )

        page = context.pages[0] if context.pages else await context.new_page()

        print("正在打开 X (Twitter) 登录页面...")
        try:
            await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=15000)
        except Exception:
            # X 可能加载很慢，忽略超时
            pass

        print()
        print("=" * 60)
        print("  Chromium 已打开，请在浏览器中完成 X 登录")
        print(f"  浏览器将在 {timeout} 秒后自动关闭并保存")
        print("=" * 60)
        print()

        # 等待超时
        await asyncio.sleep(timeout)

        # 检查当前 URL
        try:
            current_url = page.url
            print(f"当前页面: {current_url}")
        except Exception:
            pass

        # 导出 storage_state（cookies, localStorage 等）
        print("正在导出登录状态...")
        storage_state = await context.storage_state()
        STORAGE_STATE_FILE.write_text(json.dumps(storage_state, indent=2), encoding="utf-8")
        print(f"✓ 登录状态已导出到: {STORAGE_STATE_FILE}")

        await context.close()

        print()
        print("=" * 60)
        print("  ✓ X 登录设置完成！")
        print("=" * 60)
        print()
        print("后续使用 browser-use 时，通过 storage_state 参数")
        print("自动复用 X 登录状态，无需重复登录。")
        print()
        print("验证登录: python scripts/verify_x_login.py")
        print("自动化任务: python scripts/x_auto.py \"<任务描述>\"")


if __name__ == "__main__":
    asyncio.run(main())

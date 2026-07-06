"""
验证 X (Twitter) 登录状态是否持久化。

使用已保存的 Playwright profile 打开 Chromium 到 X 首页。
如果之前通过 setup_x_login.py 完成了登录，这里应该直接显示已登录状态。

用法:
    python scripts/verify_x_login.py
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / ".browser_profile" / "chromium-data"
AUTH_FILE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"


async def main():
    if not PROFILE_DIR.exists():
        print("✗ 尚未设置 X 登录，请先运行: python scripts/setup_x_login.py")
        sys.exit(1)

    print("=" * 60)
    print("  验证 X (Twitter) 登录状态")
    print("=" * 60)
    print(f"Profile: {PROFILE_DIR}")
    print(f"Auth:    {AUTH_FILE}")
    print()

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass

        url = page.url
        if "login" in url.lower():
            print("✗ 仍在登录页面 — 登录状态可能已过期")
            print("  请重新运行: python scripts/setup_x_login.py")
        else:
            print(f"✓ 已登录！当前页面: {url}")
            print("  X 登录状态有效，可以放心使用自动化功能。")

        print()
        print("浏览器将保持打开 30 秒，你可以查看确认。")
        await asyncio.sleep(30)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())

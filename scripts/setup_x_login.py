"""Set up a persistent Playwright session for X (Twitter)."""

import argparse
import asyncio
import sys
from pathlib import Path

try:
    from scripts.script_utils import (
        atomic_write_json,
        bounded_int,
        is_x_authenticated,
        resolve_chrome_executable,
    )
except ModuleNotFoundError:
    from script_utils import (  # type: ignore[no-redef]
        atomic_write_json,
        bounded_int,
        is_x_authenticated,
        resolve_chrome_executable,
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / ".browser_profile" / "chromium-data"
STORAGE_STATE_FILE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"


def parse_timeout(value: str) -> int:
    try:
        parsed = int(value)
        return bounded_int(parsed, 30, 1800, "timeout")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


async def main(timeout: int = 300) -> None:
    timeout = bounded_int(timeout, 30, 1800, "timeout")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    chrome_executable = resolve_chrome_executable()

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

    from playwright.async_api import async_playwright

    launch_options = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        "viewport": {"width": 1280, "height": 900},
    }
    if chrome_executable:
        launch_options["executable_path"] = chrome_executable

    async with async_playwright() as playwright:
        context = None
        try:
            if chrome_executable:
                try:
                    print(f"正在启动 Chrome: {chrome_executable}")
                    context = await playwright.chromium.launch_persistent_context(
                        **launch_options
                    )
                except Exception as error:
                    print(f"用户 Chrome 启动失败 ({error})，使用 Playwright Chromium...")

            if context is None:
                chromium_options = {key: value for key, value in launch_options.items() if key != "executable_path"}
                print("正在启动 Playwright Chromium...")
                context = await playwright.chromium.launch_persistent_context(
                    **chromium_options
                )

            page = context.pages[0] if context.pages else await context.new_page()
            print("正在打开 X (Twitter) 登录页面...")
            response = await page.goto(
                "https://x.com/login", wait_until="domcontentloaded", timeout=15000
            )
            if response is None:
                raise RuntimeError("X login navigation returned no HTTP response")
            if response.status >= 400:
                raise RuntimeError(f"X login navigation returned HTTP {response.status}")

            print()
            print("=" * 60)
            print("  Chromium 已打开，请在浏览器中完成 X 登录")
            print(f"  浏览器将在 {timeout} 秒后自动关闭并保存")
            print("=" * 60)
            print()

            await asyncio.sleep(timeout)
            print(f"当前页面: {page.url}")

            if not await is_x_authenticated(page):
                raise RuntimeError(
                    "X authentication was not confirmed; existing x_auth.json was preserved"
                )

            print("正在导出登录状态...")
            storage_state = await context.storage_state()
            atomic_write_json(STORAGE_STATE_FILE, storage_state)
            print(f"登录状态已导出到: {STORAGE_STATE_FILE}")
        finally:
            if context is not None:
                await context.close()

    print()
    print("=" * 60)
    print("  X 登录设置完成！")
    print("=" * 60)
    print()
    print("验证登录: python scripts/x_search.py --check-login --headless")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up the X Playwright login session")
    parser.add_argument(
        "--timeout",
        type=parse_timeout,
        default=300,
        help="等待登录的秒数（30-1800，默认 300）",
    )
    arguments = parser.parse_args()
    asyncio.run(main(arguments.timeout))

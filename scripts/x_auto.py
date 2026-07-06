"""
X (Twitter) 自动化脚本 — 使用 browser-use Agent 在 X 上执行自动化任务。

使用 storage_state 导入已保存的登录状态，无需重复登录。

要求:
    1. 先运行 setup_x_login.py 完成 X 登录（只需一次）
    2. 设置 LLM API key（OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY）

用法:
    python scripts/x_auto.py "在 X 上搜索 copper gold mining 并查看最新帖子"
    python scripts/x_auto.py --headless "查看我的首页"
"""

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_STATE_FILE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"
CHROME_EXECUTABLE = "C:/Program Files/Google/Chrome/Application/chrome.exe"


async def main():
    # 解析参数
    headless = False
    args = []
    for arg in sys.argv[1:]:
        if arg == "--headless":
            headless = True
        else:
            args.append(arg)

    if not args:
        print("用法: python scripts/x_auto.py [--headless] \"<你的任务描述>\"")
        print("示例: python scripts/x_auto.py \"在 X 上搜索 mining industry news\"")
        print("      python scripts/x_auto.py --headless \"查看 @elonmusk 最近的帖子\"")
        sys.exit(1)

    task = " ".join(args)

    if not STORAGE_STATE_FILE.exists():
        print("✗ 尚未设置 X 登录，请先运行: python scripts/setup_x_login.py")
        sys.exit(1)

    # 选择 LLM
    llm_provider = os.environ.get("BROWSER_USE_LLM", "openai")
    print(f"LLM provider: {llm_provider}")
    print(f"Headless: {headless}")
    print(f"任务: {task}")
    print()

    from browser_use import Agent, BrowserProfile
    from browser_use.llm import ChatOpenAI, ChatAnthropic, ChatGoogle

    llm_map = {
        "openai": lambda: ChatOpenAI(model="gpt-4o"),
        "anthropic": lambda: ChatAnthropic(model="claude-sonnet-4-6"),
        "google": lambda: ChatGoogle(model="gemini-2.5-pro"),
    }

    if llm_provider not in llm_map:
        print(f"✗ 不支持的 LLM provider: {llm_provider}")
        print(f"  支持的: {list(llm_map.keys())}")
        print(f"  设置 BROWSER_USE_LLM 环境变量来选择")
        sys.exit(1)

    try:
        llm = llm_map[llm_provider]()
    except Exception as e:
        print(f"✗ 初始化 LLM 失败: {e}")
        print("请确保已设置对应的 API key 环境变量")
        print("  OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY")
        sys.exit(1)

    browser_profile = BrowserProfile(
        headless=headless,
        executable_path=CHROME_EXECUTABLE,
        storage_state=str(STORAGE_STATE_FILE),
        window_size={"width": 1280, "height": 900},
        allowed_domains=["x.com", "twitter.com"],
        highlight_elements=True,
    )

    agent = Agent(
        task=task,
        llm=llm,
        browser_profile=browser_profile,
    )

    print("正在启动 Agent...")
    history = await agent.run()

    print()
    print("=" * 60)
    print("  任务完成")
    print("=" * 60)
    print()
    print(history.final_result())


if __name__ == "__main__":
    asyncio.run(main())

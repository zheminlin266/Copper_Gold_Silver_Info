"""
X (Twitter) 供需信息搜索 — 轻量级 Playwright 脚本。
从种子账号搜索窗口内的帖子，保存原始候选到 x_outputs/。

无 LLM 依赖，无 browser-use 依赖。

用法:
    python scripts/x_search.py 2026-07-13
    python scripts/x_search.py 2026-07-13 --headless
    python scripts/x_search.py 2026-07-13 --headless --overwrite

Python 环境:
    必须使用 managed Python 3.13 (唯一已安装 playwright 的运行时):
        C:/Users/Zhemin/.workbuddy/binaries/python/versions/3.13.12/python.exe
    不要使用 Python 3.14 或 browser-use 环境的 Python 3.12 — 它们没有 playwright

输出:
    x_outputs/{date}_x_raw_materials.txt
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / ".browser_profile" / "chromium-data"
STORAGE_STATE_FILE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"
CHROME_EXECUTABLE = "C:/Program Files/Google/Chrome/Application/chrome.exe"

# 种子账号 (handle → 姓名)
SEED_ACCOUNTS = [
    ("KatusaResearch", "Marin Katusa"),
    ("RealRickRule", "Rick Rule"),
    ("silverguru22", "David Morgan"),
    ("peter_krauth", "Peter Krauth"),
    ("ArcadiaEconomic", "Chris Marcus"),
    ("duediligenceguy", "Lobo Tiggre"),
    ("mercenarygeo", "Mickey Fulp"),
    ("JoeMazumdar", "Joe Mazumdar"),
    ("KaiserResearch", "John Kaiser"),
    ("mjgeiger", "Matt Geiger"),
    ("Junior_Stock", "Brian Leni"),
    ("Jamie_Keech", "Jamie Keech"),
    ("TheDailyGold", "Jordan Roy-Byrne"),
    ("Brien_Lundin", "Brien Lundin"),
    ("TaviCosta", "Otavio Costa"),
    ("RonStoeferle", "Ronnie Stoeferle"),
    ("wmiddelkoop", "Willem Middelkoop"),
    ("LawrenceLepard", "Lawrence Lepard"),
    ("soarfinancial", "Kai Hoffmann"),
    ("GerardoDelReal", "Gerardo Del Real"),
    ("TekoaDaSilva", "Tekoa Da Silva"),
    ("Frank_Giustra", "Frank Giustra"),
    ("RobMcEwenMUX", "Rob McEwen"),
    ("keith_neumeyer", "Keith Neumeyer"),
    ("NolanWatson", "Nolan Watson"),
    ("AmirAdnani", "Amir Adnani"),
    ("MichaelKonnert", "Michael Konnert"),
    ("WalterColesJr", "Walter Coles Jr"),
    ("ivanbebek", "Ivan Bebek"),
    ("JohnFeneck", "John Feneck"),
    ("JayantBhandari5", "Jayant Bhandari"),
    ("chenpicks", "Chen Lin"),
    ("SteveTodoruk", "Steve Todoruk"),
    ("ResourceMaven", "Gwen Preston"),
]

# 官方/公司账号
OFFICIAL_ACCOUNTS = [
    ("IvanhoeMines_", "Ivanhoe Mines"),
    ("FreeportMcMoRan", "Freeport-McMoRan"),
    ("NewmontCorp", "Newmont"),
    ("BarrickGold", "Barrick Gold"),
    ("TeckResources", "Teck Resources"),
    ("AntofagastaPLC", "Antofagasta"),
    ("LundinMining", "Lundin Mining"),
    ("AgnicoEagle", "Agnico Eagle"),
    ("FirstMajestic", "First Majestic Silver"),
    ("PanAmericanSlvr", "Pan American Silver"),
    ("Wheaton_PM", "Wheaton Precious Metals"),
    ("EndeavourMining", "Endeavour Mining"),
    ("SSRMining", "SSR Mining"),
    ("KinrossGold", "Kinross Gold"),
    ("SandstormGold", "Sandstorm Gold"),
    ("Fortuna_Silver", "Fortuna Mining"),
    ("GoGoldResources", "GoGold Resources"),
    ("vizslasilver", "Vizsla Silver"),
]

TZ_BEIJING = timezone(timedelta(hours=8))
SEARCH_QUERY = "(gold OR silver OR copper OR mining OR mine OR production OR supply OR demand OR permit OR smelter OR mill OR drill OR resource OR reserve)"


class XLoginRequired(RuntimeError):
    """Raised when X redirects the collector to a login or onboarding page."""


def parse_x_datetime(dt_str: str) -> datetime:
    """解析 X 的 <time datetime> 为 UTC datetime。"""
    # X 时间格式: "2026-07-13T15:30:00.000Z"
    dt_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(dt_str)


async def search_account(page, handle: str, name: str, date_str: str) -> list[dict]:
    """搜索单个账号在指定日期的帖子。"""
    next_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    query = f"from:{handle} {SEARCH_QUERY} since:{date_str} until:{next_date}"
    url = "https://x.com/search?" + urlencode({"q": query, "src": "typed_query", "f": "live"})
    
    print(f"  搜索 @{handle} ({name})...")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2500)

        if await is_login_wall(page):
            raise XLoginRequired("X redirected the search page to a login/onboarding wall")
        
        # 解析推文
        tweets = []
        articles = await page.query_selector_all('article[data-testid="tweet"]')
        
        for article in articles:
            try:
                # 提取时间
                time_el = await article.query_selector("time")
                if not time_el:
                    continue
                dt_attr = await time_el.get_attribute("datetime")
                if not dt_attr:
                    continue
                
                utc_time = parse_x_datetime(dt_attr)
                bj_time = utc_time.astimezone(TZ_BEIJING)
                
                # 只收录目标日期的帖子
                if bj_time.strftime("%Y-%m-%d") != date_str:
                    continue
                
                # 提取文本
                text_el = await article.query_selector('[data-testid="tweetText"]')
                text = await text_el.inner_text() if text_el else ""
                
                # 提取链接
                link_el = await article.query_selector('a[href*="/status/"]')
                post_url = ""
                if link_el:
                    href = await link_el.get_attribute("href")
                    post_url = f"https://x.com{href}" if href else ""
                
                tweets.append({
                    "author": name,
                    "handle": handle,
                    "utc_time": utc_time.isoformat(),
                    "bj_time": bj_time.isoformat(),
                    "text": text[:500],
                    "url": post_url,
                })
            except Exception as e:
                continue
        
        print(f"    → {len(tweets)} 条窗口内帖子")
        return tweets
        
    except XLoginRequired:
        raise
    except Exception as e:
        print(f"    ✗ 失败: {e}")
        return []


async def is_login_wall(page) -> bool:
    """Return whether the current page requires an X login."""
    url = page.url.lower()
    if "/login" in url or "/i/jf/onboarding" in url:
        return True

    body = (await page.locator("body").inner_text()).lower()
    login_markers = ("sign in to x", "log in to x", "登录 x", "注册或登录")
    return any(marker in body for marker in login_markers)


async def assert_authenticated(page) -> None:
    """Fail clearly instead of treating a login wall as zero search results."""
    await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    if await is_login_wall(page):
        raise XLoginRequired("X session is missing or expired; run scripts/setup_x_login.py")

    home_link = await page.locator('a[data-testid="AppTabBar_Home_Link"]').count()
    account_switcher = await page.locator('[data-testid="SideNav_AccountSwitcher_Button"]').count()
    if home_link == 0 and account_switcher == 0:
        raise XLoginRequired("X home page did not expose authenticated navigation")


async def open_x_context(playwright, headless: bool):
    """Use the live persistent profile first, with exported auth as a fallback."""
    if not PROFILE_DIR.exists() and not STORAGE_STATE_FILE.exists():
        raise XLoginRequired("No X profile found; run scripts/setup_x_login.py")

    launch_args = ["--disable-blink-features=AutomationControlled"]
    if PROFILE_DIR.exists():
        try:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=headless,
                executable_path=CHROME_EXECUTABLE,
                args=launch_args,
                viewport={"width": 1280, "height": 900},
            )
            print(f"登录会话: persistent profile ({PROFILE_DIR})")
            return context, None
        except Exception as error:
            print(f"persistent profile unavailable, falling back to x_auth.json: {error}")

    browser = await playwright.chromium.launch(
        headless=headless,
        executable_path=CHROME_EXECUTABLE,
        args=launch_args,
    )
    context = await browser.new_context(
        storage_state=str(STORAGE_STATE_FILE),
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    print(f"登录会话: exported state fallback ({STORAGE_STATE_FILE})")
    return context, browser


async def main(
    date_str: str,
    headless: bool = False,
    overwrite: bool = False,
    output_suffix: str = "",
):
    output_dir = PROJECT_ROOT / "x_outputs"
    output_dir.mkdir(exist_ok=True)
    if output_suffix and not re.fullmatch(r"[A-Za-z0-9_-]+", output_suffix):
        raise ValueError("output suffix may contain only letters, numbers, underscores, and hyphens")
    suffix = f"_{output_suffix}" if output_suffix else ""
    output_file = output_dir / f"{date_str}_x_raw_materials{suffix}.txt"
    if output_file.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing X raw materials: {output_file}. "
            "Move it aside or use a new report date after confirming the workflow state."
        )

    print(f"X 供需搜索 — 目标日期: {date_str}")
    print(f"种子账号: {len(SEED_ACCOUNTS)} 个人 + {len(OFFICIAL_ACCOUNTS)} 官方")
    print(f"搜索词: {SEARCH_QUERY}")
    print()

    if not PROFILE_DIR.exists() and not STORAGE_STATE_FILE.exists():
        print("✗ 未找到 X 登录状态文件!")
        print(f"  路径: {STORAGE_STATE_FILE}")
        print("  请先运行 setup_x_login.py 完成 X 登录")
        sys.exit(1)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context, browser = await open_x_context(p, headless)
        page = await context.new_page()
        await assert_authenticated(page)

        all_tweets = []
        all_accounts = SEED_ACCOUNTS + OFFICIAL_ACCOUNTS

        for batch_idx in range(0, len(all_accounts), 5):
            batch = all_accounts[batch_idx:batch_idx + 5]
            print(f"--- 批次 {batch_idx // 5 + 1} ({len(batch)} 账号) ---")
            
            for handle, name in batch:
                tweets = await search_account(page, handle, name, date_str)
                all_tweets.extend(tweets)
            
            await page.wait_for_timeout(1000)  # 批次间隔

        await context.close()
        if browser:
            await browser.close()

    # 写入原始候选文件
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"X 原始候选 — {date_str}\n")
        f.write(f"采集时间: {datetime.now(TZ_BEIJING).isoformat()}\n")
        f.write(f"采集方法: Playwright + Chrome (persistent profile with storage_state fallback)\n")
        f.write(f"搜索词: {SEARCH_QUERY}\n")
        f.write(f"账号批次: {len(SEED_ACCOUNTS)} 个人 + {len(OFFICIAL_ACCOUNTS)} 官方\n")
        f.write(f"=" * 60 + "\n\n")
        f.write(f"总计候选: {len(all_tweets)} 条\n\n")
        f.write("=" * 60 + "\n\n")

        for i, tweet in enumerate(all_tweets, 1):
            f.write(f"[{i}] @{tweet['handle']} ({tweet['author']})\n")
            f.write(f"    UTC: {tweet['utc_time']}\n")
            f.write(f"    北京: {tweet['bj_time']}\n")
            f.write(f"    文本: {tweet['text']}\n")
            f.write(f"    链接: {tweet['url']}\n")
            f.write("\n")

    print(f"\n✓ 完成: {len(all_tweets)} 条候选 → {output_file}")
    return output_file


async def check_login(headless: bool = True):
    """Check the active X profile without creating or changing report files."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context, browser = await open_x_context(p, headless)
        try:
            page = await context.new_page()
            await assert_authenticated(page)
            print("X login check passed: authenticated home navigation is available")
        finally:
            await context.close()
            if browser:
                await browser.close()


if __name__ == "__main__":
    if "--check-login" in sys.argv:
        try:
            asyncio.run(check_login(headless=True))
        except XLoginRequired as error:
            print(f"X login required: {error}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    if len(sys.argv) < 2:
        print("用法: python scripts/x_search.py <DATE> [--headless]")
        print("示例: python scripts/x_search.py 2026-07-13")
        print("      python scripts/x_search.py 2026-07-13 --headless")
        sys.exit(1)

    date = sys.argv[1]
    headless = "--headless" in sys.argv
    overwrite = "--overwrite" in sys.argv
    output_suffix = ""
    for index, argument in enumerate(sys.argv[2:], start=2):
        if argument.startswith("--output-suffix="):
            output_suffix = argument.split("=", 1)[1]
        elif argument == "--output-suffix" and index + 1 < len(sys.argv):
            output_suffix = sys.argv[index + 1]
    try:
        asyncio.run(main(date, headless, overwrite, output_suffix))
    except XLoginRequired as error:
        print(f"X login required: {error}", file=sys.stderr)
        sys.exit(2)
    except FileExistsError as error:
        print(f"X raw-material output already exists: {error}", file=sys.stderr)
        sys.exit(3)

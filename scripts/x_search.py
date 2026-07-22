"""
X (Twitter) 供需信息搜索 — 轻量级 Playwright 脚本。
从种子账号搜索窗口内的帖子，保存原始候选到 x_outputs/。

无 LLM 依赖，无 browser-use 依赖。

用法:
    python scripts/x_search.py 2026-07-13
    python scripts/x_search.py 2026-07-13 --headless

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
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


def parse_x_datetime(dt_str: str) -> datetime:
    """解析 X 的 <time datetime> 为 UTC datetime。"""
    # X 时间格式: "2026-07-13T15:30:00.000Z"
    dt_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(dt_str)


async def search_account(page, handle: str, name: str, date_str: str) -> list[dict]:
    """搜索单个账号在指定日期的帖子。"""
    query = f"from:{handle} {SEARCH_QUERY}"
    url = f"https://x.com/search?q={query.replace(' ', '%20').replace('(', '%28').replace(')', '%29')}&f=live"
    
    print(f"  搜索 @{handle} ({name})...")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1500)
        
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
        
    except Exception as e:
        print(f"    ✗ 失败: {e}")
        return []


async def main(date_str: str, headless: bool = False):
    print(f"X 供需搜索 — 目标日期: {date_str}")
    print(f"种子账号: {len(SEED_ACCOUNTS)} 个人 + {len(OFFICIAL_ACCOUNTS)} 官方")
    print(f"搜索词: {SEARCH_QUERY}")
    print()

    if not STORAGE_STATE_FILE.exists():
        print("✗ 未找到 X 登录状态文件!")
        print(f"  路径: {STORAGE_STATE_FILE}")
        print("  请先运行 setup_x_login.py 完成 X 登录")
        sys.exit(1)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            executable_path=CHROME_EXECUTABLE if CHROME_EXECUTABLE else None,
        )
        context = await browser.new_context(
            storage_state=str(STORAGE_STATE_FILE),
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        all_tweets = []
        all_accounts = SEED_ACCOUNTS + OFFICIAL_ACCOUNTS

        for batch_idx in range(0, len(all_accounts), 5):
            batch = all_accounts[batch_idx:batch_idx + 5]
            print(f"--- 批次 {batch_idx // 5 + 1} ({len(batch)} 账号) ---")
            
            for handle, name in batch:
                tweets = await search_account(page, handle, name, date_str)
                all_tweets.extend(tweets)
            
            await page.wait_for_timeout(1000)  # 批次间隔

        await browser.close()

    # 写入原始候选文件
    output_dir = PROJECT_ROOT / "x_outputs"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{date_str}_x_raw_materials.txt"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"X 原始候选 — {date_str}\n")
        f.write(f"采集时间: {datetime.now(TZ_BEIJING).isoformat()}\n")
        f.write(f"采集方法: Playwright + Chrome (storage_state)\n")
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/x_search.py <DATE> [--headless]")
        print("示例: python scripts/x_search.py 2026-07-13")
        print("      python scripts/x_search.py 2026-07-13 --headless")
        sys.exit(1)

    date = sys.argv[1]
    headless = "--headless" in sys.argv
    asyncio.run(main(date, headless))

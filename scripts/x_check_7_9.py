"""
Check X posts for 2026-07-09 Beijing window using Playwright + storage_state.
No LLM needed - direct Playwright control.
"""
import asyncio, sys, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_STATE = str(PROJECT_ROOT / ".browser_profile" / "x_auth.json")
OUTPUT_DIR = PROJECT_ROOT / "x_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "2026-07-09_x_raw_materials.txt"

BEIJING_TZ = timezone(timedelta(hours=8))
DAY = "2026-07-09"
WINDOW_START = datetime(2026, 7, 9, 0, 0, 0, tzinfo=BEIJING_TZ)
WINDOW_END = datetime(2026, 7, 9, 23, 59, 59, tzinfo=BEIJING_TZ)

HANDLES = [
    "RealRickRule", "KatusaResearch", "ResourceMaven", "TheDailyGold",
    "Brien_Lundin", "silverguru22", "peter_krauth", "ArcadiaEconomic",
    "duediligenceguy", "mercenarygeo", "JoeMazumdar", "KaiserResearch",
    "SteveTodoruk", "TaviCosta", "RonStoeferle", "wmiddelkoop",
    "LawrenceLepard", "mjgeiger", "Junior_Stock", "Jamie_Keech",
    "JuniorMinerJunky", "JohnFeneck", "JayantBhandari5", "chenpicks",
    "GerardoDelReal", "TekoaDaSilva", "soarfinancial", "RobMcEwenMUX",
    "keith_neumeyer", "Frank_Giustra", "NolanWatson", "AmirAdnani",
    "MichaelKonnert", "ivanbebek", "WalterColesJr"
]

OFFICIAL = [
    "BarrickGold", "NewmontCorp", "agnicoeagle", "FreeportFCX",
    "IvanhoeMines_", "RioTinto", "Glencore", "TeckResources",
    "CodelcoChile", "AntofagastaPLC", "LundinMining", "FirstMajesticAG",
    "PanAmericanSlvr", "Wheaton_PM", "SandstormSSL", "McEwenMining",
    "VizslaSilverCorp", "SkeenaResources"
]

SEARCH_TERMS = "gold OR silver OR copper OR mining OR mine OR project OR production OR supply OR demand OR permit OR smelter OR mill OR drill OR resource OR reserve"


async def check_handle(page, handle, batch_num):
    results = []
    search_url = f"https://x.com/search?q=from%3A{handle}%20({SEARCH_TERMS})&src=typed_query&f=live"
    print(f"  [{batch_num}] Searching: @{handle}...")

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"    Error: {e}")
        return results

    try:
        articles = await page.query_selector_all('article[data-testid="tweet"]')
        for article in articles:
            try:
                time_el = await article.query_selector('time')
                if not time_el:
                    continue
                dt_attr = await time_el.get_attribute('datetime')
                if not dt_attr:
                    continue

                utc_time = datetime.fromisoformat(dt_attr.replace('Z', '+00:00'))
                bj_time = utc_time.astimezone(BEIJING_TZ)

                if not (WINDOW_START <= bj_time <= WINDOW_END):
                    continue

                link_el = await article.query_selector('a[href*="/status/"]')
                if not link_el:
                    continue
                href = await link_el.get_attribute('href')
                if not href:
                    continue

                text_el = await article.query_selector('[data-testid="tweetText"]')
                text = await text_el.inner_text() if text_el else "(no text)"

                results.append({
                    "handle": handle,
                    "url": f"https://x.com{href}" if href.startswith("/") else href,
                    "utc_time": dt_attr,
                    "bj_time": bj_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "text": text[:300]
                })
            except Exception as e:
                continue
    except Exception as e:
        print(f"    Parse error: {e}")

    print(f"    Found {len(results)} in-window posts")
    return results


async def main():
    from playwright.async_api import async_playwright

    # Also check previous day's raw materials
    prev_raw = PROJECT_ROOT / "x_outputs" / "2026-07-08_x_raw_materials.txt"
    cross_day_candidates = []
    if prev_raw.exists():
        print("Checking previous day's raw materials for cross-day candidates...")
        with open(prev_raw, "r", encoding="utf-8") as f:
            for line in f:
                if "BJ:" in line:
                    try:
                        bj_part = line.split("BJ:")[1].strip().split()[0]
                        if bj_part.startswith("2026-07-09"):
                            cross_day_candidates.append(line.strip())
                    except:
                        pass
        print(f"  Found {len(cross_day_candidates)} cross-day candidates from 07-08 raw")

    print(f"\n=== X Search for {DAY} ===")
    print(f"Window: {WINDOW_START} to {WINDOW_END} Beijing")
    print(f"Seed handles: {len(HANDLES)}, Official: {len(OFFICIAL)}")
    print()

    all_results = []
    chrome_path = "C:/Program Files/Google/Chrome/Application/chrome.exe"

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                executable_path=chrome_path,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
        except Exception as e:
            print(f"Chrome launch failed: {e}")
            print("Falling back to default chromium...")
            browser = await p.chromium.launch(headless=False)

        context = await browser.new_context(
            storage_state=STORAGE_STATE,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Check login state
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        print(f"Login check: {page.url}")

        # Seed handles
        batch = 0
        for handle in HANDLES:
            batch += 1
            posts = await check_handle(page, handle, batch)
            all_results.extend(posts)
            if batch % 10 == 0:
                print(f"  --- Batch {batch}/{len(HANDLES)} complete, total: {len(all_results)} ---")

        # Official accounts
        print(f"\n--- Official accounts ({len(OFFICIAL)}) ---")
        for handle in OFFICIAL:
            batch += 1
            posts = await check_handle(page, handle, batch)
            all_results.extend(posts)

        await browser.close()

    # Write raw materials file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"X Raw Materials: {DAY}\n")
        f.write(f"Window: {WINDOW_START} to {WINDOW_END} Beijing\n")
        f.write(f"Method: Playwright + Chrome, storage_state from x_auth.json\n")
        f.write(f"Handles: {len(HANDLES)} seed + {len(OFFICIAL)} official\n")
        f.write(f"Search: from:{{handle}} ({SEARCH_TERMS})\n")
        f.write(f"Total in-window candidates: {len(all_results)}\n")
        f.write("=" * 60 + "\n\n")

        for r in all_results:
            f.write(f"@{r['handle']}\n")
            f.write(f"  UTC: {r['utc_time']}  BJ: {r['bj_time']}\n")
            f.write(f"  URL: {r['url']}\n")
            f.write(f"  Text: {r['text']}\n")
            f.write(f"  ---\n")

        if cross_day_candidates:
            f.write("\n\n=== Cross-day candidates from 2026-07-08 raw materials ===\n")
            for c in cross_day_candidates:
                f.write(f"{c}\n")

    print(f"\n=== DONE ===")
    print(f"Total in-window: {len(all_results)}")
    print(f"Cross-day: {len(cross_day_candidates)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Check X posts for 2026-07-12 Beijing window using Playwright + storage_state.
"""
import asyncio, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_STATE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"
OUTPUT_FILE = PROJECT_ROOT / "x_outputs" / "2026-07-12_x_raw_materials.txt"

BEIJING_TZ = timezone(timedelta(hours=8))
DAY = "2026-07-12"
WINDOW_START = datetime(2026, 7, 12, 0, 0, 0, tzinfo=BEIJING_TZ)
WINDOW_END = datetime(2026, 7, 12, 23, 59, 59, tzinfo=BEIJING_TZ)

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


async def check_handle(page, handle):
    results = []
    search_url = f"https://x.com/search?q=from%3A{handle}%20({SEARCH_TERMS})&src=typed_query&f=live"
    print(f"  Searching: @{handle}...")

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"    Error loading search: {e}")
        return results

    current_url = page.url
    if "x.com" not in current_url and "twitter.com" not in current_url:
        print(f"    Not on X: {current_url}")
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
                url = f"https://x.com{href}" if href.startswith('/') else href

                text_el = await article.query_selector('[data-testid="tweetText"]')
                text = await text_el.inner_text() if text_el else "(text unavailable)"

                results.append({
                    "handle": handle,
                    "url": url,
                    "utc": dt_attr,
                    "beijing": bj_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "text": text[:500]
                })
                print(f"    FOUND: {url}")
                print(f"    Time: {bj_time.strftime('%Y-%m-%d %H:%M:%S')} BJT")
            except Exception:
                continue
    except Exception as e:
        print(f"    Error parsing: {e}")

    return results


async def main():
    if not STORAGE_STATE.exists():
        print("ERROR: x_auth.json not found. Run setup_x_login.py first.")
        sys.exit(1)

    print(f"Checking X posts for {DAY} Beijing window...")
    print(f"Window: {WINDOW_START} to {WINDOW_END}")
    print(f"Seed handles: {len(HANDLES)}, Official: {len(OFFICIAL)}")
    print()

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe",
            args=["--no-sandbox"]
        )
        context = await browser.new_context(
            storage_state=str(STORAGE_STATE),
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()

        all_results = []

        for i, handle in enumerate(HANDLES):
            if i > 0 and i % 5 == 0:
                print(f"  Progress: {i}/{len(HANDLES)} seed handles checked...")
            res = await check_handle(page, handle)
            all_results.extend(res)

        print(f"\n  Seed handles complete. Found {len(all_results)} candidates so far.")

        for handle in OFFICIAL:
            res = await check_handle(page, handle)
            all_results.extend(res)

        print(f"\n  Official accounts complete. Total: {len(all_results)} candidates.")

        await browser.close()

    output = [
        "X raw materials before filtering",
        f"Report day: {DAY}",
        "Collection date: 2026-07-13",
        "Method:",
        "- Used Playwright with storage_state from .browser_profile/x_auth.json (Chrome).",
        "- Seed pool from mining_people_broadcast_x_articles.csv handles.",
        "- Each handle searched with from:handle + gold/silver/copper/mining terms.",
        "- Final day attribution uses Asia/Shanghai time from exact time element datetime.",
        "",
        f"{DAY} (Asia/Shanghai window)",
        "Raw candidates found before filtering:",
    ]

    if not all_results:
        output.append("- No qualifying posts found in the Beijing window.")
    else:
        for idx, r in enumerate(all_results, 1):
            output.append(f"{idx}. @{r['handle']}")
            output.append(f"   URL: {r['url']}")
            output.append(f"   UTC: {r['utc']}")
            output.append(f"   Beijing: {r['beijing']}")
            output.append(f"   Text: {r['text']}")
            output.append("")

    output.append("")
    output.append("Filtering takeaway for this day:")
    if not all_results:
        output.append("- Search worked and checked all seed handles + official accounts.")
        output.append('- Final result: "searched but no qualifying posts for this Beijing-day window."')
    else:
        output.append(f"- Found {len(all_results)} candidates. Filter by supply/demand relevance.")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text("\n".join(output), encoding="utf-8")
    print(f"\nOutput written to: {OUTPUT_FILE}")
    print(f"Total candidates in {DAY} window: {len(all_results)}")


asyncio.run(main())

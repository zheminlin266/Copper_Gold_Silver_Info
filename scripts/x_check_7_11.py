"""
Check X posts for 2026-07-11 Beijing window using Playwright + storage_state.
Saturday window - expect low activity.
"""
import asyncio, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_STATE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"
OUTPUT_FILE = PROJECT_ROOT / "x_outputs" / "2026-07-11_x_raw_materials.txt"

BEIJING_TZ = timezone(timedelta(hours=8))
WINDOW_START = datetime(2026, 7, 11, 0, 0, 0, tzinfo=BEIJING_TZ)
WINDOW_END = datetime(2026, 7, 11, 23, 59, 59, tzinfo=BEIJING_TZ)

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


async def extract_tweet_info(page, article):
    """Extract tweet time and text from an article element."""
    try:
        time_el = await article.query_selector('time')
        datetime_attr = await time_el.get_attribute('datetime') if time_el else None
        
        text_el = await article.query_selector('[data-testid="tweetText"]')
        text = await text_el.inner_text() if text_el else "(no text)"
        
        link_el = await article.query_selector('a[href*="/status/"]')
        href = await link_el.get_attribute('href') if link_el else ""
        url = f"https://x.com{href}" if href else ""
        
        return {
            "datetime_utc": datetime_attr,
            "text": text[:300],
            "url": url
        }
    except Exception as e:
        return {"datetime_utc": None, "text": f"(error: {e})", "url": ""}


async def check_handle(page, handle, all_results):
    """Search a handle for posts."""
    search_url = f"https://x.com/search?q=from%3A{handle}%20({SEARCH_TERMS})&src=typed_query&f=live"
    print(f"  @{handle}...", end=" ", flush=True)

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=12000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"LOAD_ERR:{e}")
        return

    current_url = page.url
    if "x.com" not in current_url and "twitter.com" not in current_url:
        print(f"NOT_X")
        return

    try:
        articles = await page.query_selector_all('article[data-testid="tweet"]')
    except:
        print("0")
        return

    count = 0
    for article in articles[:8]:
        info = await extract_tweet_info(page, article)
        if info["datetime_utc"]:
            try:
                t = datetime.fromisoformat(info["datetime_utc"].replace("Z", "+00:00"))
                bj = t.astimezone(BEIJING_TZ)
                if WINDOW_START <= bj <= WINDOW_END:
                    all_results.append({
                        "handle": handle,
                        "utc": info["datetime_utc"],
                        "beijing": bj.strftime("%Y-%m-%d %H:%M"),
                        "text": info["text"],
                        "url": info["url"]
                    })
                    count += 1
            except:
                pass
    print(f"{count}")


async def main():
    results = []
    
    print(f"X Search: 2026-07-11 Beijing window")
    print(f"Window: {WINDOW_START} to {WINDOW_END}")
    print(f"Seed accounts: {len(HANDLES)} | Official: {len(OFFICIAL)}")
    print()

    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe",
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            storage_state=str(STORAGE_STATE),
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Quick login check
        try:
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(2000)
            page_text = await page.inner_text("body")
            if "Log in" in page_text or "Sign in" in page_text:
                print("AUTH FAILED: Not logged in. Run setup_x_login.py first.")
                await browser.close()
                return
        except Exception as e:
            print(f"Login check error: {e}")
        
        print("=== Seed Accounts ===")
        for handle in HANDLES:
            await check_handle(page, handle, results)
        
        print(f"\n=== Official Accounts ===")
        for handle in OFFICIAL:
            await check_handle(page, handle, results)
        
        await browser.close()
    
    # Write raw materials
    bj_now = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"X Raw Materials: 2026-07-11 Beijing Window\n")
        f.write(f"Collection time: {bj_now} Beijing\n")
        f.write(f"Channel: Playwright + Chrome (storage_state)\n")
        f.write(f"Window: {WINDOW_START} to {WINDOW_END}\n")
        f.write(f"Accounts searched: {len(HANDLES)} seed + {len(OFFICIAL)} official\n")
        f.write(f"Candidates found: {len(results)}\n")
        f.write("=" * 70 + "\n\n")
        
        for i, r in enumerate(results, 1):
            f.write(f"[{i}] @{r['handle']}\n")
            f.write(f"    UTC: {r['utc']}\n")
            f.write(f"    Beijing: {r['beijing']}\n")
            f.write(f"    URL: {r['url']}\n")
            f.write(f"    Text: {r['text']}\n")
            f.write("-" * 50 + "\n")
    
    print(f"\nTotal candidates in window: {len(results)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())

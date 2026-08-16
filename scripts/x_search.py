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
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urljoin

try:
    from scripts.script_utils import (
        atomic_write_text,
        is_x_authenticated,
        parse_report_date,
        resolve_chrome_executable,
    )
except ModuleNotFoundError:
    from script_utils import (  # type: ignore[no-redef]
        atomic_write_text,
        is_x_authenticated,
        parse_report_date,
        resolve_chrome_executable,
    )

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / ".browser_profile" / "chromium-data"
STORAGE_STATE_FILE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"

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


class XPartialFailure(RuntimeError):
    """Raised after a partial audit file has been written."""


def parse_x_datetime(dt_str: str) -> datetime:
    """解析 X 的 <time datetime> 为带时区的 UTC datetime。"""
    normalized = f"{dt_str[:-1]}+00:00" if dt_str.endswith("Z") else dt_str
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("X datetime must include a timezone")
    return parsed


async def search_account(
    page, handle: str, name: str, date_str: str
) -> tuple[list[dict], str | None]:
    """搜索单个账号；返回候选和可审计的账号级错误。"""
    next_date = (parse_report_date(date_str) + timedelta(days=1)).isoformat()
    query = f"from:{handle} {SEARCH_QUERY} since:{date_str} until:{next_date}"
    url = "https://x.com/search?" + urlencode({"q": query, "src": "typed_query", "f": "live"})

    print(f"  搜索 @{handle} ({name})...")
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if response is None:
            raise RuntimeError("X search navigation returned no HTTP response")
        if response.status >= 400:
            raise RuntimeError(f"X search returned HTTP {response.status}")
        await page.wait_for_timeout(2500)

        if not await is_x_authenticated(page):
            raise XLoginRequired("X redirected the search page to a login/onboarding wall")

        tweets = []
        extraction_errors = []
        articles = await page.query_selector_all('article[data-testid="tweet"]')

        for index, article in enumerate(articles, start=1):
            try:
                time_el = await article.query_selector("time")
                if not time_el:
                    extraction_errors.append(f"tweet {index}: missing time element")
                    continue
                dt_attr = await time_el.get_attribute("datetime")
                if not dt_attr:
                    extraction_errors.append(f"tweet {index}: missing time datetime")
                    continue

                utc_time = parse_x_datetime(dt_attr)
                bj_time = utc_time.astimezone(TZ_BEIJING)
                if bj_time.strftime("%Y-%m-%d") != date_str:
                    continue

                text_el = await article.query_selector('[data-testid="tweetText"]')
                text = await text_el.inner_text() if text_el else ""
                if not text.strip():
                    extraction_errors.append(f"tweet {index}: missing or empty tweet text")
                    continue

                link_el = await article.query_selector('a[href*="/status/"]')
                href = await link_el.get_attribute("href") if link_el else None
                if not href:
                    extraction_errors.append(f"tweet {index}: missing status URL")
                    continue
                post_url = urljoin("https://x.com", href)

                tweets.append(
                    {
                        "author": name,
                        "handle": handle,
                        "utc_time": utc_time.isoformat(),
                        "bj_time": bj_time.isoformat(),
                        "text": text[:500],
                        "url": post_url,
                    }
                )
            except Exception as error:
                extraction_errors.append(f"tweet {index}: {type(error).__name__}: {error}")

        if extraction_errors:
            detail = "; ".join(extraction_errors[:3])
            if len(extraction_errors) > 3:
                detail += f"; and {len(extraction_errors) - 3} more"
            error = f"tweet extraction failed for {len(extraction_errors)} item(s): {detail}"
            print(f"    失败: {error}")
            return tweets, error

        print(f"    {len(tweets)} 条窗口内帖子")
        return tweets, None
    except XLoginRequired:
        raise
    except Exception as error:
        detail = f"{type(error).__name__}: {error}"
        print(f"    失败: {detail}")
        return [], detail


async def assert_authenticated(page) -> None:
    """Fail clearly instead of treating an unauthenticated session as zero results."""
    try:
        response = await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
    except Exception as error:
        raise XLoginRequired(f"X home navigation failed: {error}") from error
    if response is None:
        raise XLoginRequired("X home navigation returned no HTTP response")
    if response.status >= 400:
        raise XLoginRequired(f"X home navigation returned HTTP {response.status}")
    await page.wait_for_timeout(3000)
    if not await is_x_authenticated(page):
        raise XLoginRequired(
            "X session is missing or expired; run scripts/setup_x_login.py"
        )


async def _validate_context_authentication(context) -> None:
    """Validate a context before exposing it to collection callers."""
    page = await context.new_page()
    try:
        await assert_authenticated(page)
    finally:
        await page.close()


async def _close_context_quietly(context) -> None:
    try:
        await context.close()
    except Exception:
        pass


async def open_x_context(playwright, headless: bool):
    """Use an authenticated persistent profile, with exported auth as a fallback."""
    if not PROFILE_DIR.exists() and not STORAGE_STATE_FILE.exists():
        raise XLoginRequired("No X profile or x_auth.json found; run scripts/setup_x_login.py")

    chrome_executable = resolve_chrome_executable()
    launch_args = ["--disable-blink-features=AutomationControlled"]
    persistent_error = None

    if PROFILE_DIR.exists():
        persistent_options = {
            "user_data_dir": str(PROFILE_DIR),
            "headless": headless,
            "args": launch_args,
            "viewport": {"width": 1280, "height": 900},
        }
        if chrome_executable:
            persistent_options["executable_path"] = chrome_executable
        context = None
        try:
            context = await playwright.chromium.launch_persistent_context(**persistent_options)
            await _validate_context_authentication(context)
            print(f"登录会话: authenticated persistent profile ({PROFILE_DIR})")
            return context, None
        except Exception as error:
            persistent_error = error
            await _close_context_quietly(context)
            if chrome_executable:
                print(f"persistent Chrome profile unavailable or unauthenticated ({error})，尝试 Playwright Chromium...")
                chromium_options = {
                    key: value for key, value in persistent_options.items() if key != "executable_path"
                }
                context = None
                try:
                    context = await playwright.chromium.launch_persistent_context(**chromium_options)
                    await _validate_context_authentication(context)
                    print(f"登录会话: authenticated persistent profile ({PROFILE_DIR})")
                    return context, None
                except Exception as chromium_error:
                    persistent_error = chromium_error
                    await _close_context_quietly(context)
            else:
                print(f"persistent profile unavailable or unauthenticated: {error}")

    if not STORAGE_STATE_FILE.exists():
        raise XLoginRequired(
            "X persistent profile could not be opened and x_auth.json is missing; "
            "run scripts/setup_x_login.py"
        ) from persistent_error

    browser_options = {"headless": headless, "args": launch_args}
    if chrome_executable:
        browser_options["executable_path"] = chrome_executable
    try:
        browser = await playwright.chromium.launch(**browser_options)
    except Exception as error:
        if chrome_executable:
            print(f"Chrome auth fallback unavailable ({error})，使用 Playwright Chromium...")
            browser = await playwright.chromium.launch(
                **{key: value for key, value in browser_options.items() if key != "executable_path"}
            )
        else:
            raise

    try:
        context = await browser.new_context(
            storage_state=str(STORAGE_STATE_FILE),
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
    except Exception as error:
        await browser.close()
        raise XLoginRequired(f"x_auth.json could not be loaded: {error}") from error
    print(f"登录会话: exported state fallback ({STORAGE_STATE_FILE})")
    return context, browser


async def main(
    date_str: str,
    headless: bool = False,
    overwrite: bool = False,
    output_suffix: str = "",
):
    report_date = parse_report_date(date_str).isoformat()
    if output_suffix and not re.fullmatch(r"[A-Za-z0-9_-]+", output_suffix):
        raise ValueError("output suffix may contain only letters, numbers, underscores, and hyphens")

    output_dir = PROJECT_ROOT / "x_outputs"
    output_dir.mkdir(exist_ok=True)
    suffix = f"_{output_suffix}" if output_suffix else ""
    output_file = output_dir / f"{report_date}_x_raw_materials{suffix}.txt"
    if output_file.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing X raw materials: {output_file}. "
            "Move it aside or use a new report date after confirming the workflow state."
        )

    print(f"X 供需搜索 — 目标日期: {report_date}")
    print(f"种子账号: {len(SEED_ACCOUNTS)} 个人 + {len(OFFICIAL_ACCOUNTS)} 官方")
    print(f"搜索词: {SEARCH_QUERY}")
    print()

    from playwright.async_api import async_playwright

    all_tweets = []
    failed_accounts: list[tuple[str, str, str]] = []
    all_accounts = SEED_ACCOUNTS + OFFICIAL_ACCOUNTS

    async with async_playwright() as playwright:
        context, browser = await open_x_context(playwright, headless)
        try:
            page = await context.new_page()
            await assert_authenticated(page)

            for batch_idx in range(0, len(all_accounts), 5):
                batch = all_accounts[batch_idx : batch_idx + 5]
                print(f"--- 批次 {batch_idx // 5 + 1} ({len(batch)} 账号) ---")

                for handle, name in batch:
                    tweets, error = await search_account(page, handle, name, report_date)
                    all_tweets.extend(tweets)
                    if error:
                        failed_accounts.append((handle, name, error))

                await page.wait_for_timeout(1000)
        finally:
            await context.close()
            if browser:
                await browser.close()

    status = "partial" if failed_accounts else "complete"
    output = [
        f"X 原始候选 — {report_date}\n",
        f"采集时间: {datetime.now(TZ_BEIJING).isoformat()}\n",
        "采集方法: Playwright + Chrome (persistent profile with storage_state fallback)\n",
        f"搜索词: {SEARCH_QUERY}\n",
        f"账号批次: {len(SEED_ACCOUNTS)} 个人 + {len(OFFICIAL_ACCOUNTS)} 官方\n",
        f"采集状态: {status}\n",
        f"失败账号数: {len(failed_accounts)}\n",
    ]
    if failed_accounts:
        output.append("失败账号:\n")
        for handle, name, error in failed_accounts:
            output.append(f"  @{handle} ({name}): {error}\n")
    else:
        output.append("失败账号: 无\n")
    output.extend(
        [
            "=" * 60 + "\n\n",
            f"总计候选: {len(all_tweets)} 条\n\n",
            "=" * 60 + "\n\n",
        ]
    )

    for index, tweet in enumerate(all_tweets, 1):
        output.extend(
            [
                f"[{index}] @{tweet['handle']} ({tweet['author']})\n",
                f"    UTC: {tweet['utc_time']}\n",
                f"    北京: {tweet['bj_time']}\n",
                f"    文本: {tweet['text']}\n",
                f"    链接: {tweet['url']}\n",
                "\n",
            ]
        )

    atomic_write_text(output_file, "".join(output), overwrite=overwrite)
    if failed_accounts:
        print(f"\n部分完成: {len(all_tweets)} 条候选，{len(failed_accounts)} 个账号失败 -> {output_file}")
        raise XPartialFailure(
            f"{len(failed_accounts)} account(s) failed; audit output written to {output_file}"
        )

    print(f"\n完成: {len(all_tweets)} 条候选 -> {output_file}")
    return output_file


async def check_login(headless: bool = True):
    """Check the active X profile without creating or changing report files."""
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        context, browser = await open_x_context(playwright, headless)
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
    except XPartialFailure as error:
        print(f"X raw-material collection partial: {error}", file=sys.stderr)
        sys.exit(4)

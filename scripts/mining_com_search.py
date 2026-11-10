"""Collect report-date candidates from Mining.com metal category pages.

This intentionally uses the category page DOM as the primary discovery path.
It does not use sitemap, RSS, or archive services.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urljoin, urlsplit, urlunsplit

try:
    from scripts.script_utils import atomic_write_json, chromium_launch_options, parse_report_date
except ModuleNotFoundError:
    from script_utils import atomic_write_json, chromium_launch_options, parse_report_date  # type: ignore[no-redef]


METALS = ("gold", "silver", "copper")
CATEGORY_URL = "https://www.mining.com/commodity/copper/"
COLLECTOR = "mining_com_search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Windows runners may expose a GBK console.  The collector emits article titles
# from the live page, so force UTF-8 output instead of failing after extraction.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def category_url(metal: str) -> str:
    """Return a category URL only for the supported metal slugs."""
    normalized = metal.casefold() if isinstance(metal, str) else ""
    if normalized not in METALS:
        raise ValueError(f"metal must be one of: {', '.join(METALS)}")
    return f"https://www.mining.com/commodity/{normalized}/"


# English month names are hard-coded so matching does not depend on locale.
_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")
_MONTH_NUMBERS = {name: index for index, name in enumerate(_MONTHS, 1)}
_MONTH_NUMBERS.update({name[:3]: index for index, name in enumerate(_MONTHS, 1)})
_MONTH_NUMBERS["sept"] = 9
# Mining.com uses "November 5, 2026" in the main list and "November 05, 2026"
# in sidebar and "more news" blocks; abbreviated months are accepted as well.
_HUMAN_DATE = re.compile(r"\b([A-Za-z]{3,9})\.? (\d{1,2}), (\d{4})\b")


def human_dates(text: str) -> list[date]:
    """Return every English "Month D, YYYY" date in text, padded or not."""
    found = []
    for month, day, year in _HUMAN_DATE.findall(text):
        number = _MONTH_NUMBERS.get(month.casefold())
        if number is None:
            continue
        try:
            found.append(date(int(year), number, int(day)))
        except ValueError:
            continue
    return found


def matches_report_date(text: str, date_str: str) -> bool:
    normalized = " ".join(text.split())
    if date_str in normalized:
        return True
    return date.fromisoformat(date_str) in human_dates(normalized)


def needs_next_page(body_text: str, metal: str, date_str: str) -> bool:
    """True when the main category list ends without reaching an older date.

    The main list is the text before the "Load more <Metal> news" link; if its
    oldest date is still on or after the report date, report-date articles may
    continue on page 2.
    """
    marker = body_text.casefold().find(f"load more {metal} news")
    if marker < 0:
        return False
    dates = human_dates(" ".join(body_text[:marker].split()))
    return bool(dates) and min(dates) >= date.fromisoformat(date_str)


async def collect(date_str: str, metal: str = "copper", *, output_dir: Path | None = None) -> dict:
    date_str = parse_report_date(date_str).isoformat()
    metal = metal.casefold() if isinstance(metal, str) else ""
    url = category_url(metal)
    result = {
        "status": "failed",
        "extraction_status": "failed",
        "collector": COLLECTOR,
        "metal": metal,
        "url": url,
        "report_date": date_str,
        "access_status": "unverified",
        "captured_at": None,
        "article_count": 0,
        "articles": [],
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=False)
    stage = "launch"
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            launch_options = chromium_launch_options(args=(
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", "--disable-dev-shm-usage",
            ))
            browser = await playwright.chromium.launch(**launch_options)
            try:
                context = await browser.new_context(
                    user_agent=USER_AGENT, locale="en-US",
                    viewport={"width": 1920, "height": 1080},
                )
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
                page = await context.new_page()
                stage = "navigation"
                await _read_category(page, result, date_str, metal, output_dir)
            finally:
                await browser.close()
    except Exception as error:
        result.update(status="failed", extraction_status="failed", articles=[], article_count=0,
                      failure_stage=stage, error=f"{type(error).__name__}: {error}")
    finally:
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        if output_dir is not None:
            result["evidence_dir"] = str(output_dir)
            result["evidence_sha256"] = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in output_dir.iterdir() if path.is_file()
            }
            atomic_write_json(output_dir / "result.json", result, overwrite=False)
    return result


async def _read_category(page, result: dict, date_str: str, metal: str, output_dir: Path | None) -> None:
    url = result["url"]
    response = await page.goto(
        url, wait_until="domcontentloaded", timeout=45000
    )
    result["captured_at"] = datetime.now(timezone.utc).isoformat()
    final = urlsplit(page.url)
    # Redirect query strings can contain challenge or login tokens. They are
    # unnecessary for category identity and must not enter logs or evidence.
    result["final_url"] = urlunsplit((final.scheme, final.hostname or "", final.path, "", ""))
    if output_dir is not None:
        try:
            await page.screenshot(path=str(output_dir / "page.png"), full_page=True, timeout=10000)
        except Exception as error:
            result["screenshot_error"] = f"{type(error).__name__}: {error}"
    if response is None:
        result["error"] = "Mining.com category navigation returned no HTTP response"
        return
    result["http_status"] = response.status
    if response.status >= 400:
        result.update(access_status="blocked", failure_stage="access",
                      error=f"Mining.com category returned HTTP {response.status}; no automatic retry")
        return

    if (final.scheme != "https" or final.hostname != "www.mining.com"
            or final.path.rstrip("/") != urlsplit(url).path.rstrip("/")):
        result.update(access_status="blocked", failure_stage="access",
                      error="Mining.com category redirected away from the requested category; no automatic retry")
        return

    result["page_title"] = await page.title()
    if any(marker in result["page_title"].casefold() for marker in
           ("just a moment", "access denied", "verify you are human", "attention required")):
        result.update(access_status="blocked", failure_stage="access", error="Mining.com category shows an access challenge; no automatic retry")
        return
    await page.wait_for_timeout(3000)
    body_text = await page.locator("body").inner_text()
    result["captured_at"] = datetime.now(timezone.utc).isoformat()
    result["body_chars"] = len(body_text)
    if output_dir is not None:
        (output_dir / "page.txt").write_text(body_text, encoding="utf-8")
    if any(marker in body_text[:1000].casefold() for marker in (
        "checking your browser", "verify you are human", "enable javascript and cookies to continue",
        "you have been blocked", "please log in to continue", "sign in to continue",
    )):
        result.update(access_status="blocked", failure_stage="access",
                      error="Mining.com category shows an access gate; no automatic retry")
        return
    authenticity_errors = []
    if metal not in result["page_title"].casefold():
        authenticity_errors.append(
            f"page title does not contain '{metal}'"
        )
    if len(body_text) < 500:
        authenticity_errors.append(
            f"page body text is too short ({len(body_text)} characters; need at least 500)"
        )
    if authenticity_errors:
        result["error"] = "Mining.com category authenticity check failed: " + "; ".join(authenticity_errors)
        result["failure_stage"] = "authenticity"
        return

    seen: set[str] = set()
    articles = _extract_articles(await _link_candidates(page), url, date_str, seen)
    result["pages_read"] = 1
    if needs_next_page(body_text, metal, date_str):
        page2_url = url + "page/2/"
        result["pagination_complete"] = False
        try:
            error = await _read_next_page(page, page2_url, metal, output_dir)
            if error:
                result["pagination_error"] = error
            else:
                articles += _extract_articles(await _link_candidates(page), url, date_str, seen)
                result["pages_read"] = 2
                result["pagination_complete"] = True
        except Exception as error:
            result["pagination_error"] = f"{type(error).__name__}: {error}"

    result["articles"] = articles
    result["article_count"] = len(articles)
    result["status"] = "ok"
    result["access_status"] = "public"
    result["extraction_status"] = (
        "success_empty" if not articles else "success"
    )


async def _read_next_page(page, url: str, metal: str, output_dir: Path | None) -> str | None:
    """Open a category page 2 with the same gates; return an error or None."""
    response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    final = urlsplit(page.url)
    if response is None or response.status >= 400:
        return f"page 2 returned HTTP {getattr(response, 'status', None)}"
    if (final.scheme != "https" or final.hostname != "www.mining.com"
            or final.path.rstrip("/") != urlsplit(url).path.rstrip("/")):
        return "page 2 redirected away from the requested category page"
    title = (await page.title()).casefold()
    if metal not in title or any(marker in title for marker in
                                 ("just a moment", "access denied", "verify you are human")):
        return "page 2 title failed the authenticity check"
    await page.wait_for_timeout(3000)
    body_text = await page.locator("body").inner_text()
    if output_dir is not None:
        (output_dir / "page-2.txt").write_text(body_text, encoding="utf-8")
    if len(body_text) < 500 or any(marker in body_text[:1000].casefold() for marker in (
        "checking your browser", "verify you are human", "you have been blocked",
    )):
        return "page 2 shows an access gate or is too short"
    return None


async def _link_candidates(page) -> list[dict]:
    return await page.locator("a[href]").evaluate_all(
        """links => links.map(link => ({
            href: link.href,
            text: (link.innerText || link.textContent || '').trim(),
            context: [
                link.parentElement,
                link.parentElement?.parentElement,
                link.parentElement?.parentElement?.parentElement,
                link.parentElement?.parentElement?.parentElement?.parentElement
            ].filter(Boolean).map(node => node.innerText || node.textContent || '')
        }))"""
    )


def _extract_articles(candidates: list[dict], url: str, date_str: str, seen: set[str]) -> list[dict]:
    articles: list[dict] = []
    for candidate in candidates:
        href = urljoin(url, candidate.get("href", ""))
        title = " ".join(candidate.get("text", "").split())
        context_text = " ".join(
            " ".join(candidate.get("context", [])).split()
        )
        if title.lower().startswith("load more") or "/page/" in href:
            continue
        if not href.startswith("https://www.mining.com/"):
            continue
        if href.rstrip("/") == url.rstrip("/") or href in seen:
            continue
        if not title or not matches_report_date(context_text, date_str):
            continue
        if "/" not in href.removeprefix("https://www.mining.com/"):
            continue
        seen.add(href)
        articles.append({
            "title": title,
            "url": href,
            "date_match_text": context_text[:500],
        })
    return articles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_date", help="Report date in YYYY-MM-DD")
    parser.add_argument("--metal", choices=METALS, default="copper")
    parser.add_argument("--output-dir", type=Path, help="New directory for category evidence; never overwritten")
    args = parser.parse_args()
    try:
        report_date = parse_report_date(args.report_date).isoformat()
    except ValueError as error:
        parser.error(str(error))
    output_dir = args.output_dir or (Path(__file__).resolve().parents[1] / ".runtime" / "mining" / report_date /
                                     f"{args.metal}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}")
    try:
        result = asyncio.run(collect(report_date, args.metal, output_dir=output_dir))
    except OSError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Collect report-date candidates from Mining.com metal category pages.

This intentionally uses the category page DOM as the primary discovery path.
It does not use sitemap, RSS, or archive services.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from urllib.parse import urljoin

try:
    from scripts.script_utils import parse_report_date, resolve_chrome_executable
except ModuleNotFoundError:
    from script_utils import parse_report_date, resolve_chrome_executable  # type: ignore[no-redef]


METALS = ("gold", "silver", "copper")
CATEGORY_URL = "https://www.mining.com/commodity/copper/"
COLLECTOR = "mining_com_search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def category_url(metal: str) -> str:
    """Return a category URL only for the supported metal slugs."""
    normalized = metal.casefold() if isinstance(metal, str) else ""
    if normalized not in METALS:
        raise ValueError(f"metal must be one of: {', '.join(METALS)}")
    return f"https://www.mining.com/commodity/{normalized}/"


def matches_report_date(text: str, date_str: str) -> bool:
    normalized = " ".join(text.split())
    if date_str in normalized:
        return True
    # Windows Python's strftime does not support %-d; compare a portable form.
    date = datetime.strptime(date_str, "%Y-%m-%d")
    for marker in (f"{date.strftime('%B')} {date.day}, {date.year}",
                   f"{date.strftime('%b')} {date.day}, {date.year}"):
        if marker in normalized:
            return True
    return False


async def collect(date_str: str, metal: str = "copper") -> dict:
    date_str = parse_report_date(date_str).isoformat()
    metal = metal.casefold() if isinstance(metal, str) else ""
    url = category_url(metal)
    from playwright.async_api import async_playwright

    result = {
        "status": "failed",
        "extraction_status": "failed",
        "collector": COLLECTOR,
        "metal": metal,
        "url": url,
        "report_date": date_str,
        "article_count": 0,
        "articles": [],
    }
    async with async_playwright() as playwright:
        launch_options = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        chrome_executable = resolve_chrome_executable()
        if chrome_executable:
            launch_options["executable_path"] = chrome_executable
        browser = await playwright.chromium.launch(**launch_options)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1920, "height": 1080},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        try:
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=45000
            )
            await page.wait_for_timeout(3000)
            if response is None:
                result["error"] = "Mining.com category navigation returned no HTTP response"
                return result
            result["http_status"] = response.status
            if response.status >= 400:
                result["error"] = f"Mining.com category returned HTTP {response.status}"
                return result

            result["page_title"] = await page.title()
            body_text = await page.locator("body").inner_text()
            result["body_chars"] = len(body_text)
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
                return result

            candidates = await page.locator("a[href]").evaluate_all(
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
            seen: set[str] = set()
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

            result["articles"] = articles
            result["article_count"] = len(articles)
            result["status"] = "ok"
            result["extraction_status"] = (
                "success_empty" if not articles else "success"
            )
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        finally:
            await context.close()
            await browser.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_date", help="Report date in YYYY-MM-DD")
    parser.add_argument("--metal", choices=METALS, default="copper")
    args = parser.parse_args()
    try:
        report_date = parse_report_date(args.report_date).isoformat()
    except ValueError as error:
        parser.error(str(error))
    result = asyncio.run(collect(report_date, args.metal))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

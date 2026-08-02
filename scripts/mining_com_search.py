"""Collect report-date candidates from Mining.com's copper category page.

This intentionally uses the category page DOM as the primary discovery path.
It does not use sitemap, RSS, or archive services.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from urllib.parse import urljoin

from playwright.async_api import async_playwright


CATEGORY_URL = "https://www.mining.com/commodity/copper/"
CHROME_EXECUTABLE = "C:/Program Files/Google/Chrome/Application/chrome.exe"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


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


async def collect(date_str: str) -> dict:
    result = {
        "status": "failed",
        "url": CATEGORY_URL,
        "report_date": date_str,
        "article_count": 0,
        "articles": [],
    }
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            executable_path=CHROME_EXECUTABLE,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
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
                CATEGORY_URL, wait_until="domcontentloaded", timeout=45000
            )
            await page.wait_for_timeout(3000)
            result["http_status"] = response.status if response else None
            result["page_title"] = await page.title()
            result["body_chars"] = len(await page.locator("body").inner_text())

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
                href = urljoin(CATEGORY_URL, candidate.get("href", ""))
                title = " ".join(candidate.get("text", "").split())
                context_text = " ".join(
                    " ".join(candidate.get("context", [])).split()
                )
                if title.lower().startswith("load more") or "/page/" in href:
                    continue
                if not href.startswith("https://www.mining.com/"):
                    continue
                if href.rstrip("/") == CATEGORY_URL.rstrip("/") or href in seen:
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
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        finally:
            await context.close()
            await browser.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_date", help="Report date in YYYY-MM-DD")
    args = parser.parse_args()
    try:
        datetime.strptime(args.report_date, "%Y-%m-%d")
    except ValueError as error:
        parser.error(str(error))
    result = asyncio.run(collect(args.report_date))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

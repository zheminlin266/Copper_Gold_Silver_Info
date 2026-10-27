"""Collect report-date candidates from Mining.com metal category pages.

This intentionally uses the category page DOM as the primary discovery path.
It does not use sitemap, RSS, or archive services.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
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
    result["access_status"] = "public"
    result["extraction_status"] = (
        "success_empty" if not articles else "success"
    )


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

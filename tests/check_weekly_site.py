"""Browser acceptance of the seeded weekly report, legacy archive, and TC chart."""

import argparse
import csv
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def check_tc_navigation(page):
    tc = page.get_by_role("button", name="TC", exact=True)
    inventory = page.get_by_role("button", name="库存", exact=True)
    panel = page.locator("#tc-menu-panel")
    for fraction in (0.06, 0.5, 0.94):
        page.mouse.move(0, 150)
        tc.hover()
        expect(tc).to_have_attribute("aria-expanded", "true")
        page.wait_for_function('getComputedStyle(document.querySelector("#tc-menu-panel")).opacity === "1"')
        box = panel.bounding_box()
        header = page.locator(".site-header").bounding_box()
        assert abs(box["y"] - header["y"] - header["height"]) <= 2
        page.mouse.move(box["x"] + fraction * box["width"], box["y"] + 25, steps=15)
        page.wait_for_timeout(350)
        expect(tc).to_have_attribute("aria-expanded", "true")
        inventory.hover()
        expect(inventory).to_have_attribute("aria-expanded", "true")
        expect(tc).to_have_attribute("aria-expanded", "false")
    tc.focus()
    if tc.get_attribute("aria-expanded") == "false":
        page.keyboard.press("Enter")
    expect(tc).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Tab")
    expect(panel.locator("a").first).to_be_focused()
    expect(panel.locator("a").first).to_have_attribute("href", "https://www.metal.com/copper/201910240001")
    expect(panel.locator("a").last).to_have_attribute("href", "/historical-tc")
    expect(page.locator("#inventory-menu-panel a").first).to_have_attribute(
        "href", "https://sc.macromicro.me/charts/40914/tong-ku-cun-jia-ge",
    )
    page.keyboard.press("Escape")
    expect(tc).to_have_attribute("aria-expanded", "false")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--executable-path", required=True)
    parser.add_argument("--week-start", default="2026-11-09")
    args = parser.parse_args()
    base = urlsplit(args.base_url)
    local = base.scheme == "http" and base.hostname == "127.0.0.1"
    preview = base.scheme == "https" and base.hostname and base.hostname.endswith(".vercel.app")
    production = base.scheme == "https" and base.netloc == "metals.zhemin.ltd"
    if (not (local or preview or production) or base.path not in ("", "/") or base.username or base.password
            or base.query or base.fragment):
        parser.error("Expected the local, Preview, or production origin")
    origin = f"{base.scheme}://{base.netloc}"
    oidc = os.environ.get("VERCEL_OIDC_TOKEN", "") if preview else ""
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root / f"data/weekly/{args.week_start}.json").read_text(encoding="utf-8"))
    with (root / "data/smm_copper_concentrate_index_2026.csv").open(encoding="utf-8-sig", newline="") as stream:
        tc = list(csv.DictReader(stream))[-1]
    weekly_path = f"/weekly/{report['week_start']}"
    daily_path = "/daily/2026-11-09"
    source_links = {
        source["url"]
        for item in (*report["copper_events"], *report["gold_briefs"])
        for source in item["sources"]
    }
    errors = []
    exceptions = set()

    def route_request(route):
        target = urlsplit(route.request.url)
        if preview and (target.hostname == "vercel.live" or target.hostname == "feedback.vercel.com"):
            exceptions.add("Preview feedback toolbar")
            route.abort()
        elif oidc and (target.scheme, target.netloc) == (base.scheme, base.netloc):
            headers = {**route.request.headers, "x-vercel-trusted-oidc-idp-token": oidc}
            route.fulfill(response=route.fetch(headers=headers, max_redirects=0))
        else:
            route.continue_()

    def response_failed(response):
        if response.status >= 400 and response.url.startswith(origin + "/"):
            if local and response.url == origin + "/_vercel/insights/script.js" and response.status == 404:
                exceptions.add("Local platform-only Vercel analytics 404")
            else:
                errors.append(f"HTTP {response.status} for {urlsplit(response.url).path}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.executable_path)
        try:
            for width in (1440, 800, 390):
                context = browser.new_context(viewport={"width": width, "height": 960})
                if preview:
                    context.route("**/*", route_request)
                page = context.new_page()

                def console(message):
                    if message.type != "error":
                        return
                    location = message.location["url"]
                    if local and (location.endswith("/_vercel/insights/script.js") or
                                  "[Vercel Web Analytics]" in message.text):
                        exceptions.add("Local platform-only Vercel analytics 404")
                    elif preview and ("vercel.live" in location or "feedback.vercel.com" in location):
                        exceptions.add("Preview feedback toolbar")
                    else:
                        errors.append(message.text)

                page.on("response", response_failed)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", console)
                page.on("requestfailed", lambda request: errors.append(
                    f"Request failed for {urlsplit(request.url).path}: {request.failure}"
                ) if request.url.startswith(origin + "/") and request.failure != "net::ERR_ABORTED" else None)

                def open_page(path):
                    response = page.goto(origin + path, wait_until="networkidle")
                    assert response and response.ok, f"{path}: {response.status if response else 'no response'}"
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (path, width)
                    expect(page.locator("nextjs-portal")).to_have_count(0)

                def weekly_ok():
                    expect(page.locator(".weekly-report")).to_have_attribute("data-week-start", report["week_start"])
                    assert page.locator("main h2").all_text_contents() == ["铜矿重要事实", "综合供给影响", "黄金简讯"]
                    expect(page.locator("#copper-events article")).to_have_count(len(report["copper_events"]))
                    expect(page.locator("#gold-briefs article")).to_have_count(len(report["gold_briefs"]))
                    assert source_links <= set(page.locator("main a[href]").evaluate_all("(links) => links.map(a => a.getAttribute('href'))"))
                    expect(page.get_by_role("heading", name="白银", exact=True)).to_have_count(0)

                open_page("/")
                weekly_ok()
                page.get_by_role("link", name="综合供给影响", exact=True).click()
                assert page.url.endswith("#supply-analysis")
                page.get_by_role("link", name="本期链接", exact=True).click()
                page.wait_for_url(origin + weekly_path)
                weekly_ok()

                open_page("/archive")
                expect(page.locator(f"#weekly-archive a[href='{weekly_path}']")).to_be_visible()
                search = page.get_by_role("searchbox", name="搜索日报")
                search.fill("2026-11-09")
                page.get_by_role("combobox", name="金属").select_option("copper")
                expect(page.locator("#daily-archive .archive-item")).to_have_count(1)
                expect(page.locator(f".archive-list a[href='{daily_path}']")).to_be_visible()
                open_page(daily_path)
                daily_nav = page.get_by_role("navigation", name="日报内导航")
                expect(daily_nav.get_by_role("link", name="白银")).to_be_visible()
                daily_nav.evaluate("(nav) => window.scrollTo({ top: scrollY + nav.getBoundingClientRect().bottom + 80, behavior: 'instant' })")
                assert daily_nav.evaluate("(nav) => nav.getBoundingClientRect().bottom < 0")

                open_page("/historical-tc")
                check_tc_navigation(page)
                expect(page.get_by_text(tc["assessment_date"], exact=True).first).to_be_visible()
                expect(page.get_by_text(f"{float(tc['value_usd_per_dmt']):.2f} USD/dmt", exact=True).first).to_be_visible()
                plot = page.locator(".tc-chart__svg")
                plot.scroll_into_view_if_needed()
                plot.hover(position={"x": min(160, width // 3), "y": 100})
                expect(page.locator(".tc-chart__tooltip")).to_be_visible()
                assert not errors, errors
                print(f"PASS {width}px: weekly sections and sources, archive filtering, legacy route, TC menu and tooltip")
                context.close()
        finally:
            browser.close()
    if exceptions:
        print("Environment exceptions: " + ", ".join(sorted(exceptions)))


if __name__ == "__main__":
    main()

"""Opt-in real-browser regression against a running LOCAL production build only.

python tests/check_nav_menu.py --base-url http://127.0.0.1:3000 \
    --executable-path "C:/Program Files/Google/Chrome/Application/chrome.exe"
No existing browser profile, external navigation or persistent browser data.
"""
import argparse
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--executable-path", help="Installed Chrome; otherwise Playwright's bundled Chromium")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
        parser.error("--base-url must be a loopback HTTP origin")
    origin = f"{url.scheme}://{url.netloc}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.executable_path)
        try:
            context = browser.new_context()
            context.route("**/*", lambda r: r.continue_() if r.request.url.startswith(origin + "/") else r.abort())
            page = context.new_page()
            for width in (1440, 800, 390):
                page.set_viewport_size({"width": width, "height": 960})
                page.goto(origin + "/historical-tc", wait_until="networkidle")
                tc = page.get_by_role("button", name="TC", exact=True)
                inventory = page.get_by_role("button", name="库存", exact=True)
                panel = page.locator("#tc-menu-panel")
                # Left edge, center and right edge of the panel must all be reachable.
                for offset in (16, 143, 270):
                    page.mouse.move(0, 150)
                    tc.hover()
                    expect(tc).to_have_attribute("aria-expanded", "true")
                    page.wait_for_function('getComputedStyle(document.querySelector("#tc-menu-panel")).opacity === "1"')
                    box = panel.bounding_box()
                    header = page.locator(".site-header").bounding_box()
                    assert abs(box["y"] - header["y"] - header["height"]) <= 2
                    page.mouse.move(box["x"] + offset, box["y"] + 25, steps=15)
                    page.wait_for_timeout(350)  # Must outlast the 280 ms close timer.
                    expect(tc).to_have_attribute("aria-expanded", "true")
                    expect(panel.locator("a")).to_have_count(2)
                    # The corridor must not trap intentional sibling switching.
                    inventory.hover()
                    expect(inventory).to_have_attribute("aria-expanded", "true")
                    expect(tc).to_have_attribute("aria-expanded", "false")
                tc.focus()
                expect(tc).to_have_attribute("aria-expanded", "true")
                page.keyboard.press("Tab")
                expect(panel.locator("a").first).to_be_focused()
                page.keyboard.press("Escape")
                expect(tc).to_have_attribute("aria-expanded", "false")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                print(f"PASS {width}px: diagonal edges, sibling switching, alignment, keyboard, width")
        finally:
            browser.close()


if __name__ == "__main__":
    main()

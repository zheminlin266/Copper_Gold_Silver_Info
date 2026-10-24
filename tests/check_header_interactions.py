"""Browser regression check: python tests/check_header_interactions.py URL --channel chrome.

Uses the Playwright dependency in scripts/requirements.txt and a running site.
"""

import argparse

from playwright.sync_api import expect, sync_playwright


def assert_menu(page, name, opened):
    menu = page.locator(f".{name}-menu")
    expect(menu.locator("button")).to_have_attribute("aria-expanded", str(opened).lower())
    if opened:
        expect(menu.locator(".nav-menu__panel")).to_be_visible()
    else:
        expect(menu.locator(".nav-menu__panel")).to_be_hidden()


def check_touch(browser, base_url, width):
    context = browser.new_context(viewport={"width": width, "height": 844},
                                  is_mobile=True, has_touch=True)
    try:
        page = context.new_page()
        for name in ("inventory", "tc"):
            page.goto(base_url, wait_until="networkidle")
            trigger = page.locator(f".{name}-menu button")
            # No focus or warm-up click: the first physical tap must open it.
            trigger.tap()
            assert_menu(page, name, True)
            trigger.tap()
            assert_menu(page, name, False)
            trigger.tap()
            assert_menu(page, name, True)

            other = "tc" if name == "inventory" else "inventory"
            page.locator(f".{other}-menu button").tap()
            assert_menu(page, name, False)
            assert_menu(page, other, True)
            page.touchscreen.tap(10, 400)
            assert_menu(page, other, False)
            page.locator(f".{other}-menu button").tap()
            assert_menu(page, other, True)

        page.locator(".tc-menu button").tap()
        assert_menu(page, "tc", True)
        page.get_by_role("link", name="Historical TC", exact=False).tap()
        expect(page).to_have_url(base_url.rstrip("/") + "/historical-tc")
        print(f"PASS touch {width}px: first tap, toggle, switch, outside close, submenu link")
    finally:
        context.close()


def check_desktop(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = context.new_page()
        page.goto(base_url, wait_until="networkidle")
        for name in ("inventory", "tc"):
            page.locator(f".{name}-menu button").hover()
            assert_menu(page, name, True)
            page.locator(f".{name}-menu .nav-menu__panel a").first.hover()
            page.wait_for_timeout(350)  # Exceed the delayed mouse-leave close timer.
            assert_menu(page, name, True)
            page.mouse.move(10, 400)
            assert_menu(page, name, False)

        # Start keyboard navigation from the document, without programmatic focus.
        page.reload(wait_until="networkidle")
        for _ in range(4):
            page.keyboard.press("Tab")
        expect(page.locator(".inventory-menu button")).to_be_focused()
        assert_menu(page, "inventory", False)
        page.keyboard.press("Enter")
        assert_menu(page, "inventory", True)
        page.keyboard.press("Escape")
        assert_menu(page, "inventory", False)
        page.keyboard.press("Space")
        assert_menu(page, "inventory", True)
        page.keyboard.press("Tab")
        expect(page.locator(".inventory-menu__panel a").first).to_be_focused()
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        expect(page.locator(".tc-menu button")).to_be_focused()
        assert_menu(page, "inventory", False)
        page.keyboard.press("Enter")
        assert_menu(page, "tc", True)
        page.keyboard.press("Escape")
        assert_menu(page, "tc", False)
        print("PASS desktop: hover, submenu traversal, leave, Tab, Enter, Space, Escape")
    finally:
        context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--browser", choices=("chromium", "webkit"), default="chromium")
    parser.add_argument("--channel", help="Installed browser channel, e.g. chrome")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        options = {"headless": True}
        if args.channel:
            options["channel"] = args.channel
        browser = getattr(playwright, args.browser).launch(**options)
        try:
            for width in (375, 390, 768):
                check_touch(browser, args.base_url, width)
            check_desktop(browser, args.base_url)
        finally:
            browser.close()

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from scripts.mining_com_search import category_url, collect, matches_report_date


class MiningComSearchTests(unittest.TestCase):
    def test_category_url_is_limited_to_supported_metals(self):
        self.assertEqual(category_url("gold"), "https://www.mining.com/commodity/gold/")
        self.assertEqual(category_url("SILVER"), "https://www.mining.com/commodity/silver/")
        with self.assertRaises(ValueError):
            category_url("gold?redirect=elsewhere")

    def test_date_matching_handles_iso_and_human_dates(self):
        self.assertTrue(matches_report_date("Published 2026-07-14", "2026-07-14"))
        self.assertTrue(matches_report_date("July 14, 2026", "2026-07-14"))
        self.assertTrue(matches_report_date("Jul 14, 2026", "2026-07-14"))
        self.assertFalse(matches_report_date("July 13, 2026", "2026-07-14"))


class MiningCaptureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        options = patch("scripts.mining_com_search.chromium_launch_options", return_value={"headless": True})
        options.start()
        self.addCleanup(options.stop)

    def browser(self, *, status=200, title="Copper Archives", body="Copper news " * 70):
        page = SimpleNamespace(
            url=category_url("copper"), goto=AsyncMock(return_value=SimpleNamespace(status=status)),
            title=AsyncMock(return_value=title), wait_for_timeout=AsyncMock(), screenshot=AsyncMock(),
        )
        text = SimpleNamespace(inner_text=AsyncMock(return_value=body))
        links = SimpleNamespace(evaluate_all=AsyncMock(return_value=[]))
        page.locator = Mock(side_effect=lambda selector: text if selector == "body" else links)
        async def screenshot(**kwargs):
            Path(kwargs["path"]).write_bytes(b"test image")
        page.screenshot.side_effect = screenshot
        context = SimpleNamespace(add_init_script=AsyncMock(), new_page=AsyncMock(return_value=page))
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=SimpleNamespace(chromium=SimpleNamespace(launch=launch)))
        manager.__aexit__ = AsyncMock(return_value=False)
        return manager, page, launch, browser

    async def test_blocked_page_saves_evidence_without_extracting_or_retrying(self):
        manager, page, _, browser = self.browser(status=403)
        with tempfile.TemporaryDirectory() as directory, \
                patch("playwright.async_api.async_playwright", return_value=manager):
            output = Path(directory) / "capture"
            result = await collect("2026-10-26", output_dir=output)
            saved = json.loads((output / "result.json").read_text())
            self.assertEqual(saved, result)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["access_status"], "blocked")
            self.assertEqual(result["http_status"], 403)
            self.assertEqual(result["articles"], [])
            self.assertEqual(result["evidence_sha256"]["page.png"], hashlib.sha256(b"test image").hexdigest())
            page.goto.assert_awaited_once()
            page.locator.assert_not_called()
            browser.close.assert_awaited_once()

    async def test_http_200_challenge_is_not_successful_zero_results(self):
        manager, page, _, _ = self.browser(title="Just a moment...")
        with patch("playwright.async_api.async_playwright", return_value=manager):
            result = await collect("2026-10-26")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["access_status"], "blocked")
        page.locator.assert_not_called()

    async def test_redirect_or_visible_login_gate_cannot_be_complete_empty(self):
        for redirected in (True, False):
            manager, page, _, _ = self.browser(body="Sign in to continue " + "Copper news " * 70)
            if redirected:
                page.url = "https://www.mining.com/login/"
            with self.subTest(redirected=redirected), \
                    patch("playwright.async_api.async_playwright", return_value=manager):
                result = await collect("2026-10-26")
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["access_status"], "blocked")
                self.assertEqual(result["articles"], [])

    async def test_launch_failure_is_a_persisted_structured_failure(self):
        manager, _, launch, _ = self.browser()
        launch.side_effect = RuntimeError("browser executable unavailable")
        with tempfile.TemporaryDirectory() as directory, \
                patch("playwright.async_api.async_playwright", return_value=manager):
            output = Path(directory) / "capture"
            result = await collect("2026-10-26", output_dir=output)
            self.assertEqual(result["failure_stage"], "launch")
            self.assertEqual(json.loads((output / "result.json").read_text())["status"], "failed")
            self.assertNotIn("http_status", result)

    async def test_only_an_authentic_empty_category_can_succeed(self):
        for body, status in (("too short", "failed"), ("Copper news " * 70, "ok")):
            manager, _, _, _ = self.browser(body=body)
            with self.subTest(body_length=len(body)), \
                    patch("playwright.async_api.async_playwright", return_value=manager):
                result = await collect("2026-10-26")
                self.assertEqual(result["status"], status)
                self.assertEqual(result["article_count"], 0)

    async def test_existing_capture_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            output.mkdir()
            (output / "result.json").write_text("original")
            with self.assertRaises(FileExistsError):
                await collect("2026-10-26", output_dir=output)
            self.assertEqual((output / "result.json").read_text(), "original")

    async def test_redirect_tokens_do_not_enter_saved_results(self):
        manager, page, _, _ = self.browser(status=403)
        page.url += "?challenge_token=private-value#fragment"
        with patch("playwright.async_api.async_playwright", return_value=manager):
            result = await collect("2026-10-26")
        self.assertEqual(result["final_url"], category_url("copper"))
        self.assertNotIn("private-value", json.dumps(result))


if __name__ == "__main__":
    unittest.main()

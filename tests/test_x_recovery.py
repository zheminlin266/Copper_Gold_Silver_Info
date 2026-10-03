"""Offline crash/recovery contracts. No real browser, cookies, or X traffic."""
import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

from scripts import x_search as x

DATE = "2026-07-14"
ACCOUNTS = [
    {"source_id": "x-one", "x_handle": "one", "display_name": "One"},
    {"source_id": "x-two", "x_handle": "two", "display_name": "Two"},
]
TWEET = {"source_id": "x-one", "handle": "one", "author": "One",
         "text": "Copper supply", "url": "https://x.com/one/status/1",
         "utc_time": "2026-07-14T10:00:00+00:00", "bj_time": "2026-07-14T18:00:00+08:00"}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.patches = [mock.patch.object(x, "PROJECT_ROOT", self.root),
                        mock.patch.object(x, "load_registry", return_value=ACCOUNTS),
                        mock.patch.object(x, "get_x_accounts", return_value=ACCOUNTS)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def interrupted(self, suffix=""):
        async def first_then_kill(_date, accounts, *, per_account_callback, **kwargs):
            per_account_callback(accounts[0], [TWEET], None)
            raise asyncio.CancelledError("simulated kill before account two finished")
        with mock.patch.object(x, "collect_playwright", side_effect=first_then_kill):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(x.main(DATE, output_suffix=suffix))
        return x.checkpoint_path(DATE, suffix)

    def test_process_exit_without_finally_preserves_completed_account(self):
        code = '''
import asyncio, os, sys
from pathlib import Path
from scripts import x_search as x
x.PROJECT_ROOT = Path(sys.argv[1])
accounts = [{"source_id": "x-one", "x_handle": "one", "display_name": "One"},
            {"source_id": "x-two", "x_handle": "two", "display_name": "Two"}]
x.load_registry = lambda: accounts
x.get_x_accounts = lambda registry: accounts
async def runner(date, accounts, *, per_account_callback, **kwargs):
    per_account_callback(accounts[0], [], None)
    os._exit(99)
x.collect_playwright = runner
asyncio.run(x.main("2026-07-14"))
'''
        process = subprocess.run([sys.executable, "-c", code, str(self.root)],
                                 cwd=Path(x.__file__).resolve().parent.parent,
                                 capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 99, process.stderr.decode("utf-8", errors="replace"))
        saved = json.loads(x.checkpoint_path(DATE).read_text(encoding="utf-8"))
        self.assertEqual(saved["completed_accounts"], ["x-one"])
        self.assertEqual(saved["completed_channels"], {"x-one": "playwright"})

    def test_failed_account_callback_is_durable(self):
        async def failed_then_kill(_date, accounts, *, per_account_callback, **kwargs):
            per_account_callback(accounts[0], [TWEET], "ordinary extraction error")
            raise asyncio.CancelledError()
        with mock.patch.object(x, "collect_playwright", side_effect=failed_then_kill):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(x.main(DATE))
        saved = json.loads(x.checkpoint_path(DATE).read_text(encoding="utf-8"))
        self.assertEqual(saved["completed_accounts"], [])
        self.assertEqual(saved["failed_accounts"], [["x-one", "one", "One", "ordinary extraction error"]])
        self.assertEqual(saved["tweets"], [TWEET])

    def test_first_account_is_durable_before_interrupt(self):
        path = self.interrupted()
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["completed_accounts"], ["x-one"])
        self.assertEqual(saved["tweets"], [TWEET])
        self.assertEqual(saved["attempted_channels"], ["playwright"])
        self.assertFalse((self.root / "x_outputs" / f"{DATE}_x_raw_materials.txt").exists())

    def test_fresh_refuses_checkpoint_before_traffic_even_overwrite(self):
        self.interrupted()
        with mock.patch.object(x, "run_ordered_channels") as runners:
            with self.assertRaises(FileExistsError):
                asyncio.run(x.main(DATE, overwrite=True))
            runners.assert_not_called()

    def test_recovery_uses_saved_counts_and_no_runner_or_import(self):
        self.interrupted("manual")
        with mock.patch.object(x, "run_ordered_channels") as runners, mock.patch.object(x.importlib, "import_module") as imports:
            with self.assertRaises(x.XPartialFailure):
                asyncio.run(x.main(DATE, output_suffix="manual", recover_checkpoint=True))
            runners.assert_not_called()
            imports.assert_not_called()
        raw = self.root / "x_outputs" / f"{DATE}_x_raw_materials_manual.txt"
        sidecar = json.loads(raw.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(sidecar["metadata"]["raw_sha256"], hashlib.sha256(raw.read_bytes()).hexdigest())
        self.assertEqual(sidecar["accounts_completed"], 1)
        self.assertEqual(sidecar["accounts_failed"], 1)
        self.assertEqual(sidecar["channel_completed_accounts"], {"playwright": 1})
        self.assertIn("in-flight/unvisited", sidecar["errors"][0]["error"])
        self.assertTrue(any("in-flight/unvisited" in error for error in sidecar["metadata"]["channel_errors"]))
        before = raw.read_bytes()
        with self.assertRaises(x.XPartialFailure):
            asyncio.run(x.main(DATE, output_suffix="manual", recover_checkpoint=True))
        self.assertEqual(raw.read_bytes(), before)
        # Exact interrupted raw/sidecar pair can be completed without touching raw.
        raw.with_suffix(".json").unlink()
        with self.assertRaises(x.XPartialFailure):
            asyncio.run(x.main(DATE, output_suffix="manual", recover_checkpoint=True))
        self.assertEqual(raw.read_bytes(), before)
        # Even newline-only byte changes must not pass checkpoint/hash binding.
        raw.write_bytes(before.replace(b"\n", b"\r\n"))
        with self.assertRaises(FileExistsError):
            asyncio.run(x.main(DATE, output_suffix="manual", recover_checkpoint=True))
        raw.write_text("unrelated valid raw", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            asyncio.run(x.main(DATE, output_suffix="manual", recover_checkpoint=True))
        self.assertEqual(raw.read_text(encoding="utf-8"), "unrelated valid raw")

    def test_timeout_is_whole_chain_and_cannot_start_second_channel(self):
        async def slow(_date, accounts, *, per_account_callback, **kwargs):
            per_account_callback(accounts[0], [], None)  # Explicit zero-tweet completion.
            await asyncio.sleep(60)
        with mock.patch.object(x, "COLLECTION_TIMEOUT_SECONDS", .01), mock.patch.object(x, "collect_playwright", side_effect=slow), mock.patch.object(x, "collect_twscrape") as fallback:
            with self.assertRaises(x.XPartialFailure):
                asyncio.run(x.main(DATE))
            fallback.assert_not_called()
        saved = json.loads(x.checkpoint_path(DATE).read_text(encoding="utf-8"))
        self.assertEqual(saved["completed_accounts"], ["x-one"])
        self.assertEqual(saved["attempted_channels"], ["playwright"])
        self.assertIn("deadline", saved["channel_errors"][0])

    def test_checkpoint_without_channel_attempt_cannot_claim_failed_coverage(self):
        path = self.interrupted()
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(tweets=[], completed_accounts=[], completed_channels={}, channel_completed_accounts={}, attempted_channels=[])
        path.write_text(json.dumps(data), encoding="utf-8")
        with mock.patch.object(x, "run_ordered_channels") as runners:
            with self.assertRaisesRegex(x.XCheckpointError, "no channel attempt"):
                asyncio.run(x.main(DATE, recover_checkpoint=True))
            runners.assert_not_called()
        self.assertFalse((self.root / "x_outputs" / f"{DATE}_x_raw_materials.json").exists())

    def test_backend_rejects_posts_by_another_author(self):
        tweet = {"username": "two", "id": "1", "text": "Copper", "date": TWEET["utc_time"]}
        with self.assertRaisesRegex(x.XNormalizationUnavailable, "unexpected author"):
            x.normalize_twscrape_tweet(tweet, ACCOUNTS[0], DATE)

    def test_registry_change_or_corrupt_checkpoint_fails_closed(self):
        path = self.interrupted()
        valid = json.loads(path.read_text(encoding="utf-8"))
        for mutate in (lambda d: d["accounts"][0].update(x_handle="different"),
                       lambda d: d.update(report_date="2026-07-15"),
                       lambda d: d.update(query="different"),
                       lambda d: d.update(completed_accounts=["invented"]),
                       lambda d: d.update(channel_completed_accounts={"playwright": 2}),
                       lambda d: d.update(completed_channels={"x-one": "twscrape"}),
                       lambda d: d["tweets"][0].update(url="https://x.com/two/status/1")):
            data = json.loads(json.dumps(valid))
            mutate(data)
            path.write_text(json.dumps(data), encoding="utf-8")
            with mock.patch.object(x, "run_ordered_channels") as runners:
                with self.assertRaises(x.XCheckpointError):
                    asyncio.run(x.main(DATE, recover_checkpoint=True))
                runners.assert_not_called()

    def test_auth_stop_and_cleanup_failure_never_launch_fallback_browser(self):
        class Context:
            async def new_page(self):
                return SimpleNamespace(close=mock.AsyncMock(side_effect=RuntimeError("page cleanup")))
            async def close(self):
                raise RuntimeError("context cleanup")
        chromium = SimpleNamespace(launch_persistent_context=mock.AsyncMock(return_value=Context()),
                                   launch=mock.AsyncMock())
        profile = self.root / "profile"
        profile.mkdir()
        state = self.root / "state.json"
        state.write_text("{}", encoding="utf-8")
        for safety in (x.XLoginRequired("expired login"), x.XSafetyStop("HTTP 429")):
            chromium.launch_persistent_context.reset_mock()
            with mock.patch.object(x, "PROFILE_DIR", profile), mock.patch.object(x, "STORAGE_STATE_FILE", state), mock.patch.object(x, "resolve_chrome_executable", return_value="chrome"), mock.patch.object(x, "assert_authenticated", side_effect=safety):
                with self.assertRaises(type(safety)):
                    asyncio.run(x.open_x_context(SimpleNamespace(chromium=chromium), True))
            self.assertEqual(chromium.launch_persistent_context.await_count, 1)
            chromium.launch.assert_not_called()

    def test_later_normalization_failure_keeps_earlier_completed_account(self):
        class Pool:
            async def get_all(self):
                return []
            async def add_account_cookies(self, *args):
                return None
        class API:
            def __init__(self, database, raise_when_no_account=False, wait_timeout=0):
                self.pool = Pool()
                self.queries = 0
            async def search(self, query, limit=20):
                self.queries += 1
                if self.queries == 1:
                    return [{"username": "one", "id": "1", "text": "Copper", "date": TWEET["utc_time"]}]
                return [{"username": "two", "id": "2", "text": "Copper", "date": "not absolute"}]
        with mock.patch.object(x.importlib, "import_module", return_value=SimpleNamespace(API=API)), mock.patch.object(x, "TWSCRAPE_DB", self.root / "db"), mock.patch.object(x, "_cookie_pair_from_storage", return_value={"auth_token": "a", "ct0": "c"}):
            with self.assertRaises(x.XSafetyStop) as stopped:
                asyncio.run(x.collect_twscrape(DATE, ACCOUNTS, sleep=lambda _: None))
        self.assertEqual(stopped.exception.completed_accounts, ["x-one"])
        self.assertEqual(len(stopped.exception.tweets), 1)
        self.assertEqual(stopped.exception.tweets[0]["source_id"], "x-one")

    def test_normal_cleanup_failure_stops_before_fallback(self):
        class Context:
            async def new_page(self):
                return object()
            async def close(self):
                raise RuntimeError("cleanup")
        class Manager:
            async def __aenter__(self):
                return object()
            async def __aexit__(self, *args):
                return None
        module = ModuleType("playwright.async_api")
        module.async_playwright = Manager
        with mock.patch.dict("sys.modules", {"playwright": ModuleType("playwright"), "playwright.async_api": module}), mock.patch.object(x, "open_x_context", return_value=(Context(), None)), mock.patch.object(x, "assert_authenticated", return_value=None), mock.patch.object(x, "search_account", side_effect=[([TWEET], None), ([], "ordinary timeout")]), mock.patch.object(x, "collect_twscrape") as fallback:
            result, _ = asyncio.run(x.run_ordered_channels(DATE, ACCOUNTS, sleep=lambda _: None))
            self.assertEqual(result.completed_accounts, ["x-one"])
            self.assertEqual(result.tweets, [TWEET])
            self.assertEqual(result.status, "partial")
            fallback.assert_not_called()

    def test_authenticated_cleanup_failure_retains_completed_and_stops(self):
        class Context:
            async def new_page(self):
                return object()
            async def close(self):
                raise RuntimeError("cleanup")
        class Manager:
            async def __aenter__(self):
                return object()
            async def __aexit__(self, *args):
                raise RuntimeError("driver cleanup")
        module = ModuleType("playwright.async_api")
        module.async_playwright = Manager
        with mock.patch.dict("sys.modules", {"playwright": ModuleType("playwright"), "playwright.async_api": module}), mock.patch.object(x, "open_x_context", return_value=(Context(), None)), mock.patch.object(x, "assert_authenticated", return_value=None), mock.patch.object(x, "search_account", side_effect=[([TWEET], None), x.XLoginRequired("expired")]), mock.patch.object(x, "collect_twscrape") as fallback:
            result, _ = asyncio.run(x.run_ordered_channels(DATE, ACCOUNTS, sleep=lambda _: None))
            self.assertEqual(result.completed_accounts, ["x-one"])
            self.assertEqual(result.tweets, [TWEET])
            self.assertEqual(result.status, "partial")
            fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()

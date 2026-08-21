import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

from scripts import x_search


ACCOUNT = {
    "source_id": "x-example",
    "x_handle": "example",
    "display_name": "Example",
}


class XChannelTests(unittest.TestCase):
    def test_playwright_complete_empty_result_does_not_call_twscrape(self):
        calls = []

        async def empty(report_date, accounts, *, sleep=None, headless=False):
            calls.append((x_search.CHANNEL_PLAYWRIGHT, report_date, sleep, headless, [item["source_id"] for item in accounts]))
            return x_search.ChannelResult(
                x_search.CHANNEL_PLAYWRIGHT,
                completed_accounts=["x-example"],
                status="complete",
            )

        async def should_not_run(*args, **kwargs):
            self.fail("twscrape ran after a valid Playwright zero-result completion")

        result, metadata = asyncio.run(
            x_search.run_ordered_channels(
                "2026-07-14",
                [ACCOUNT],
                headless=True,
                runners=[
                    (x_search.CHANNEL_PLAYWRIGHT, empty),
                    (x_search.CHANNEL_TWSCRAPE, should_not_run),
                ],
            )
        )

        self.assertEqual(result.status, "complete")
        self.assertEqual(metadata["selected_channel"], x_search.CHANNEL_PLAYWRIGHT)
        self.assertEqual([item[0] for item in calls], [x_search.CHANNEL_PLAYWRIGHT])
        self.assertTrue(calls[0][3])

    def test_invalid_complete_mapping_falls_back_to_next_channel(self):
        calls = []
        second = {"source_id": "x-two", "x_handle": "two", "display_name": "Two"}

        async def invalid(_date, accounts, **_kwargs):
            calls.append((x_search.CHANNEL_PLAYWRIGHT, [item["source_id"] for item in accounts]))
            return x_search.ChannelResult(x_search.CHANNEL_PLAYWRIGHT, status="complete")

        async def fallback(_date, accounts, **_kwargs):
            calls.append((x_search.CHANNEL_TWSCRAPE, [item["source_id"] for item in accounts]))
            return x_search.ChannelResult(
                x_search.CHANNEL_TWSCRAPE,
                completed_accounts=[item["source_id"] for item in accounts],
                status="complete",
            )

        result, metadata = asyncio.run(x_search.run_ordered_channels(
            "2026-08-19",
            [ACCOUNT, second],
            runners=[(x_search.CHANNEL_PLAYWRIGHT, invalid), (x_search.CHANNEL_TWSCRAPE, fallback)],
        ))
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.completed_accounts, ["x-example", "x-two"])
        self.assertEqual(calls, [
            (x_search.CHANNEL_PLAYWRIGHT, ["x-example", "x-two"]),
            (x_search.CHANNEL_TWSCRAPE, ["x-example", "x-two"]),
        ])
        self.assertEqual(metadata["selected_channel"], x_search.CHANNEL_TWSCRAPE)
        self.assertTrue(metadata["unavailable_channels"])

    def test_playwright_safety_error_types_do_not_call_twscrape(self):
        class UnauthorizedError(Exception):
            pass

        class StatusError(Exception):
            status_code = 429

        for error in (UnauthorizedError("access denied"), StatusError("retry later")):
            with self.subTest(error=type(error).__name__):
                calls = []

                async def blocked(*_args, **_kwargs):
                    calls.append(x_search.CHANNEL_PLAYWRIGHT)
                    raise error

                async def fallback(*_args, **_kwargs):
                    calls.append(x_search.CHANNEL_TWSCRAPE)
                    self.fail("twscrape ran after a Playwright safety error")

                result, _metadata = asyncio.run(x_search.run_ordered_channels(
                    "2026-07-14",
                    [ACCOUNT],
                    runners=[(x_search.CHANNEL_PLAYWRIGHT, blocked), (x_search.CHANNEL_TWSCRAPE, fallback)],
                ))
                self.assertEqual(result.status, "failed")
                self.assertEqual(calls, [x_search.CHANNEL_PLAYWRIGHT])

        self.assertFalse(x_search.is_x_safety_error(TimeoutError("ordinary timeout")))

    def test_playwright_failures_send_only_remaining_accounts_to_twscrape_and_dedupe(self):
        calls = []
        second = {"source_id": "x-two", "x_handle": "two", "display_name": "Two"}
        first_tweet = {"source_id": "x-example", "author": "Example", "handle": "example", "text": "one", "url": "https://x.com/example/status/1"}

        async def playwright(_date, accounts, **_kwargs):
            calls.append((x_search.CHANNEL_PLAYWRIGHT, [item["source_id"] for item in accounts]))
            return x_search.ChannelResult(
                x_search.CHANNEL_PLAYWRIGHT,
                completed_accounts=["x-example"],
                failed_accounts=[("x-two", "two", "Two", "ordinary timeout")],
                tweets=[first_tweet],
                status="partial",
            )

        async def twscrape(_date, accounts, **_kwargs):
            calls.append((x_search.CHANNEL_TWSCRAPE, [item["source_id"] for item in accounts]))
            return x_search.ChannelResult(
                x_search.CHANNEL_TWSCRAPE,
                completed_accounts=["x-two"],
                tweets=[first_tweet, {"source_id": "x-two", "author": "Two", "handle": "two", "text": "two", "url": "https://x.com/two/status/2"}],
            )

        result, metadata = asyncio.run(x_search.run_ordered_channels(
            "2026-08-19", [ACCOUNT, second],
            runners=[(x_search.CHANNEL_PLAYWRIGHT, playwright), (x_search.CHANNEL_TWSCRAPE, twscrape)],
        ))
        self.assertEqual(result.status, "complete")
        self.assertEqual(calls, [(x_search.CHANNEL_PLAYWRIGHT, ["x-example", "x-two"]), (x_search.CHANNEL_TWSCRAPE, ["x-two"])])
        self.assertEqual([tweet["url"] for tweet in result.tweets], [first_tweet["url"], "https://x.com/two/status/2"])
        self.assertEqual(metadata["selected_channel"], "playwright+twscrape")

    def test_playwright_safety_stop_does_not_try_twscrape(self):
        calls = []

        async def blocked(*args, **kwargs):
            calls.append(x_search.CHANNEL_PLAYWRIGHT)
            raise x_search.XSafetyStop("HTTP 429 rate limit")

        async def fallback(*args, **kwargs):
            calls.append(x_search.CHANNEL_TWSCRAPE)
            self.fail("twscrape ran after a Playwright safety stop")

        result, metadata = asyncio.run(x_search.run_ordered_channels(
            "2026-07-14", [ACCOUNT],
            runners=[(x_search.CHANNEL_PLAYWRIGHT, blocked), (x_search.CHANNEL_TWSCRAPE, fallback)],
        ))
        self.assertEqual(result.status, "failed")
        self.assertIsNone(metadata["selected_channel"])
        self.assertEqual(calls, [x_search.CHANNEL_PLAYWRIGHT])

    def test_twscrape_curl_backend_is_unavailable_before_import(self):
        with mock.patch.object(x_search.importlib, "import_module") as import_module:
            with mock.patch.dict(os.environ, {"TWS_HTTP_BACKEND": "curl"}, clear=False):
                with self.assertRaisesRegex(x_search.ChannelUnavailable, "TWS_HTTP_BACKEND=curl"):
                    asyncio.run(x_search.collect_twscrape("2026-07-14", [ACCOUNT]))
        import_module.assert_not_called()

    def test_disabled_twscrape_is_unavailable_before_import(self):
        with mock.patch.object(x_search.importlib, "import_module") as import_module:
            for value in ("0", "false", "no", "off"):
                with self.subTest(value=value), mock.patch.dict(
                    os.environ, {"X_TWSCRAPE_ENABLED": value}, clear=False
                ):
                    with self.assertRaisesRegex(x_search.ChannelUnavailable, "X_TWSCRAPE_ENABLED"):
                        asyncio.run(x_search.collect_twscrape("2026-07-14", [ACCOUNT]))
        import_module.assert_not_called()

    def test_missing_twscrape_module_is_unavailable(self):
        with mock.patch.object(
            x_search.importlib,
            "import_module",
            side_effect=ModuleNotFoundError("optional module"),
        ):
            with self.assertRaises(x_search.ChannelUnavailable):
                asyncio.run(x_search.collect_twscrape("2026-07-14", [ACCOUNT]))

    def test_safety_stop_does_not_try_next_channel(self):
        calls = []

        async def blocked(report_date, accounts, *, sleep=None):
            calls.append("blocked")
            raise x_search.XSafetyStop("HTTP 429 rate limit")

        async def fallback(*args, **kwargs):
            calls.append("fallback")
            return x_search.ChannelResult(x_search.CHANNEL_PLAYWRIGHT)

        result, metadata = asyncio.run(
            x_search.run_ordered_channels(
                "2026-07-14",
                [ACCOUNT],
                runners=[
                    (x_search.CHANNEL_TWSCRAPE, blocked),
                    (x_search.CHANNEL_PLAYWRIGHT, fallback),
                ],
            )
        )
        self.assertEqual(result.status, "failed")
        self.assertIsNone(metadata["selected_channel"])
        self.assertEqual(calls, ["blocked"])

    def test_default_safe_delay_config_is_uniform_25_to_30(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = x_search.parse_safe_delay_config()

        self.assertEqual(config.min_seconds, 25.0)
        self.assertEqual(config.max_seconds, 30.0)
        self.assertIsNone(config.fixed_seconds)
        self.assertEqual(config.metadata, {
            "safe_delay_mode": "uniform",
            "safe_delay_min_seconds": 25.0,
            "safe_delay_max_seconds": 30.0,
        })
        self.assertEqual(x_search.max_results_per_query(), 20)

    def test_twscrape_uses_one_cookie_account_sequentially(self):
        calls = []
        sleeps = []
        random_calls = []
        selected_delays = iter((26.25, 28.75))

        class Pool:
            async def get_all(self):
                return []

            async def add_account_cookies(self, username, cookie_header):
                calls.append(("account", username, cookie_header))

        class API:
            def __init__(self, database, raise_when_no_account=False, wait_timeout=0):
                self.pool = Pool()

            async def search(self, query, limit=20):
                calls.append(("search", query, limit))
                return []

        def random_uniform(minimum, maximum):
            random_calls.append((minimum, maximum))
            return next(selected_delays)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            x_search.importlib, "import_module", return_value=SimpleNamespace(API=API)
        ), mock.patch.object(x_search, "TWSCRAPE_DB", Path(directory) / "twscrape.db"), mock.patch.object(
            x_search, "_cookie_pair_from_storage", return_value={"auth_token": "a", "ct0": "c"}
        ), mock.patch.dict(os.environ, {}, clear=True):
            result = asyncio.run(
                x_search.collect_twscrape(
                    "2026-07-14",
                    [ACCOUNT, {**ACCOUNT, "source_id": "x-two", "x_handle": "two"},
                     {**ACCOUNT, "source_id": "x-three", "x_handle": "three"}],
                    sleep=lambda seconds: sleeps.append(seconds),
                    random_uniform=random_uniform,
                )
            )

        self.assertEqual(result.status, "complete")
        self.assertEqual(calls[0], ("account", "x_authorized_account", "auth_token=a; ct0=c"))
        self.assertEqual([item[0] for item in calls[1:]], ["search", "search", "search"])
        self.assertEqual(random_calls, [(25.0, 30.0), (25.0, 30.0)])
        self.assertEqual(sleeps, [26.25, 28.75])
        self.assertEqual(result.metadata["max_results_per_query"], 20)
        self.assertEqual(result.metadata["safe_delay_mode"], "uniform")
        self.assertEqual(result.metadata["safe_delay_min_seconds"], 25.0)
        self.assertEqual(result.metadata["safe_delay_max_seconds"], 30.0)

    def test_twscrape_dedicated_db_fails_closed_on_extra_account(self):
        calls = []

        class Pool:
            async def get_all(self):
                return [SimpleNamespace(username="other", proxy=None)]

            async def add_account_cookies(self, *args):
                calls.append("add")

        class API:
            def __init__(self, database, raise_when_no_account=False, wait_timeout=0):
                self.pool = Pool()

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            x_search.importlib, "import_module", return_value=SimpleNamespace(API=API)
        ), mock.patch.object(x_search, "TWSCRAPE_DB", Path(directory) / "twscrape.db"), mock.patch.object(
            x_search, "_cookie_pair_from_storage", return_value={"auth_token": "a", "ct0": "c"}
        ):
            with self.assertRaisesRegex(x_search.ChannelUnavailable, "extra account"):
                asyncio.run(x_search.collect_twscrape("2026-07-14", [ACCOUNT]))

        self.assertEqual(calls, [])

    def test_transient_after_first_query_stops_before_fallback_and_preserves_tweets(self):
        calls = []
        first_tweet = SimpleNamespace(
            user=SimpleNamespace(username="example", displayname="Example"),
            id="1",
            rawContent="Copper project update",
            date="2026-07-14T10:00:00+00:00",
        )

        class Pool:
            async def get_all(self):
                return []

            async def add_account_cookies(self, username, cookie_header):
                return None

        class API:
            def __init__(self, database, raise_when_no_account=False, wait_timeout=0):
                self.pool = Pool()

            async def search(self, query, limit=20):
                calls.append(query)
                if len(calls) == 1:
                    return [first_tweet]
                raise RuntimeError("upstream timeout")

        async def fallback(*args, **kwargs):
            self.fail("fallback ran after a query transient")

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            x_search.importlib, "import_module", return_value=SimpleNamespace(API=API)
        ), mock.patch.object(x_search, "TWSCRAPE_DB", Path(directory) / "twscrape.db"), mock.patch.object(
            x_search, "_cookie_pair_from_storage", return_value={"auth_token": "a", "ct0": "c"}
        ):
            result, metadata = asyncio.run(
                x_search.run_ordered_channels(
                    "2026-07-14",
                    [ACCOUNT, {**ACCOUNT, "source_id": "x-two", "x_handle": "two"}],
                    runners=[
                        (x_search.CHANNEL_TWSCRAPE, x_search.collect_twscrape),
                        (x_search.CHANNEL_PLAYWRIGHT, fallback),
                    ],
                    sleep=lambda _seconds: None,
                )
            )

        self.assertEqual(result.status, "partial")
        self.assertEqual(metadata["selected_channel"], x_search.CHANNEL_TWSCRAPE)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result.tweets), 1)
        self.assertEqual(result.tweets[0]["id"], "1")

    def test_twscrape_no_account_error_is_a_safety_stop(self):
        class NoAccountError(Exception):
            pass

        class Pool:
            async def get_all(self):
                return []

            async def add_account_cookies(self, username, cookie_header):
                return None

        class API:
            def __init__(self, database, raise_when_no_account=False, wait_timeout=0):
                self.pool = Pool()

            async def search(self, query, limit=20):
                raise NoAccountError("No account available after rate limit")

        async def fallback(*args, **kwargs):
            self.fail("safety stop incorrectly fell back")

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            x_search.importlib, "import_module", return_value=SimpleNamespace(API=API)
        ), mock.patch.object(x_search, "TWSCRAPE_DB", Path(directory) / "twscrape.db"), mock.patch.object(
            x_search, "_cookie_pair_from_storage", return_value={"auth_token": "a", "ct0": "c"}
        ):
            result, metadata = asyncio.run(
                x_search.run_ordered_channels(
                    "2026-07-14",
                    [ACCOUNT],
                    runners=[
                        (x_search.CHANNEL_TWSCRAPE, x_search.collect_twscrape),
                        (x_search.CHANNEL_PLAYWRIGHT, fallback),
                    ],
                )
            )

        self.assertEqual(result.status, "failed")
        self.assertIsNone(metadata["selected_channel"])
        self.assertIn("No account available", result.error or "")

    def test_safe_delay_validation_and_injected_selection(self):
        with mock.patch.dict(
            os.environ,
            {"X_SAFE_DELAY_MIN_SECONDS": "7", "X_SAFE_DELAY_MAX_SECONDS": "12"},
            clear=True,
        ):
            self.assertEqual(
                x_search.parse_safe_delay_config(),
                x_search.SafeDelayConfig(7.0, 12.0),
            )
        with mock.patch.dict(os.environ, {"X_SAFE_DELAY_SECONDS": "15"}, clear=True):
            fixed_config = x_search.parse_safe_delay_config()
        self.assertEqual(fixed_config, x_search.SafeDelayConfig(25.0, 30.0, 15.0))
        self.assertEqual(fixed_config.metadata, {
            "safe_delay_mode": "fixed",
            "safe_delay_min_seconds": 25.0,
            "safe_delay_max_seconds": 30.0,
            "safe_delay_fixed_seconds": 15.0,
        })
        self.assertEqual(
            x_search.select_safe_delay_seconds(
                x_search.SafeDelayConfig(7.0, 12.0), lambda minimum, maximum: 9.5
            ),
            9.5,
        )
        self.assertEqual(
            x_search.select_safe_delay_seconds(
                x_search.SafeDelayConfig(25.0, 30.0, 15.0),
                lambda *_: self.fail("fixed override called random_uniform"),
            ),
            15.0,
        )
        for minimum, maximum in (("4", "10"), ("5", "301"), ("nan", "10"), ("5", "inf"), ("bad", "10")):
            with self.subTest(minimum=minimum, maximum=maximum):
                with self.assertRaises(ValueError):
                    x_search.parse_safe_delay_config(minimum, maximum)
        with self.assertRaisesRegex(ValueError, "less than or equal"):
            x_search.parse_safe_delay_config("10", "5")

        sleeps = []
        random_calls = []
        selected_delays = iter((26.0, 29.0))

        def random_uniform(minimum, maximum):
            random_calls.append((minimum, maximum))
            return next(selected_delays)

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        config = x_search.parse_safe_delay_config()
        for index in range(3):
            asyncio.run(x_search.pace_between_accounts(index, 3, config, fake_sleep, random_uniform))
        self.assertEqual(random_calls, [(25.0, 30.0), (25.0, 30.0)])
        self.assertEqual(sleeps, [26.0, 29.0])

    def test_playwright_uses_injected_delays_without_network(self):
        calls = []
        sleeps = []
        random_calls = []
        selected_delays = iter((25.5, 28.5))

        class Context:
            async def new_page(self):
                return object()

            async def close(self):
                return None

        class AsyncPlaywright:
            async def __aenter__(self):
                return SimpleNamespace()

            async def __aexit__(self, exc_type, exc, traceback):
                return None

        async def fake_open_x_context(_playwright, headless):
            self.assertTrue(headless)
            return Context(), None

        async def fake_assert_authenticated(_page):
            return None

        async def fake_search_account(_page, handle, name, date, source_id, max_results):
            calls.append((handle, max_results))
            return [], None

        def random_uniform(minimum, maximum):
            random_calls.append((minimum, maximum))
            return next(selected_delays)

        async_api = ModuleType("playwright.async_api")
        async_api.async_playwright = lambda: AsyncPlaywright()
        playwright = ModuleType("playwright")
        accounts = [
            ACCOUNT,
            {**ACCOUNT, "source_id": "x-two", "x_handle": "two"},
            {**ACCOUNT, "source_id": "x-three", "x_handle": "three"},
        ]
        with mock.patch.dict(
            sys.modules, {"playwright": playwright, "playwright.async_api": async_api}
        ), mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            x_search, "open_x_context", side_effect=fake_open_x_context
        ), mock.patch.object(x_search, "assert_authenticated", side_effect=fake_assert_authenticated), mock.patch.object(
            x_search, "search_account", side_effect=fake_search_account
        ):
            result = asyncio.run(
                x_search.collect_playwright(
                    "2026-07-14",
                    accounts,
                    headless=True,
                    sleep=lambda seconds: sleeps.append(seconds),
                    random_uniform=random_uniform,
                )
            )

        self.assertEqual(result.status, "complete")
        self.assertEqual(calls, [("example", 20), ("two", 20), ("three", 20)])
        self.assertEqual(random_calls, [(25.0, 30.0), (25.0, 30.0)])
        self.assertEqual(sleeps, [25.5, 28.5])
        self.assertEqual(result.metadata["safe_delay_mode"], "uniform")
        self.assertEqual(result.metadata["safe_delay_min_seconds"], 25.0)
        self.assertEqual(result.metadata["safe_delay_max_seconds"], 30.0)


if __name__ == "__main__":
    unittest.main()

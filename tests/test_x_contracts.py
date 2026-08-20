import unittest

from scripts.x_search import (
    build_sidecar,
    candidate_id,
    normalize_x_candidate,
    sidecar_path,
)


class XContractTests(unittest.TestCase):
    def test_sidecar_accepts_only_current_channel_audit_values(self):
        sidecar = build_sidecar(
            "2026-08-20",
            [],
            [],
            status="complete",
            attempted_channels=["playwright", "twscrape"],
            selected_channel="playwright+twscrape",
            accounts_total=2,
            accounts_completed=2,
            channel_completed_accounts={"playwright": 1, "twscrape": 1},
        )
        self.assertEqual(sidecar["attempted_channels"], ["playwright", "twscrape"])
        self.assertEqual(sidecar["selected_channel"], "playwright+twscrape")
        with self.assertRaises(ValueError):
            build_sidecar("2026-08-20", [], [], attempted_channels=["web_access_xai"])
        with self.assertRaises(ValueError):
            build_sidecar("2026-08-20", [], [], attempted_channels=["playwright"], selected_channel="web_access_xai")

    def test_sidecar_rejects_status_and_selected_count_conflicts(self):
        failed = [("x-failed", "failed", "Failed", "blocked")]
        with self.assertRaisesRegex(ValueError, "complete status"):
            build_sidecar(
                "2026-08-20", [], failed,
                status="complete", accounts_total=2, accounts_completed=1,
                attempted_channels=["playwright"], selected_channel="playwright",
                channel_completed_accounts={"playwright": 1},
            )
        with self.assertRaisesRegex(ValueError, "partial status"):
            build_sidecar(
                "2026-08-20", [], failed * 2,
                status="partial", accounts_total=2, accounts_completed=0,
                attempted_channels=["playwright"], selected_channel=None,
                channel_completed_accounts={},
            )
        with self.assertRaisesRegex(ValueError, "selected_channel"):
            build_sidecar(
                "2026-08-20", [], failed,
                status="partial", accounts_total=2, accounts_completed=1,
                attempted_channels=["playwright", "twscrape"], selected_channel="playwright+twscrape",
                channel_completed_accounts={"playwright": 1},
            )

    def test_candidate_normalization_keeps_full_text_and_stable_id(self):
        tweet = {
            "source_id": "x-example",
            "author": "Example",
            "handle": "Example",
            "utc_time": "2026-07-14T10:00:00+00:00",
            "text": "long text " * 100,
            "url": "https://x.com/Example/status/1",
        }
        candidate = normalize_x_candidate(tweet, "2026-07-14")
        self.assertEqual(candidate["candidate_id"], candidate_id("x-example", tweet["url"]))
        self.assertEqual(candidate["text"], tweet["text"])
        self.assertEqual(candidate["collector"], "x_search")
        self.assertEqual(candidate["status"], "ok")

    def test_sidecar_name_follows_raw_output_suffix(self):
        self.assertEqual(
            sidecar_path("x_outputs/2026-07-14_x_raw_materials_retry.txt").name,
            "2026-07-14_x_raw_materials_retry.json",
        )

    def test_partial_sidecar_preserves_source_errors(self):
        sidecar = build_sidecar(
            "2026-07-14",
            [],
            [("x-example", "Example", "Example", "timeout")],
            status="partial",
            accounts_total=2,
            accounts_completed=1,
            channel_completed_accounts={"playwright": 1},
            attempted_channels=["playwright"],
            selected_channel="playwright",
        )
        self.assertEqual(sidecar["status"], "partial")
        self.assertEqual(sidecar["errors"][0]["source_id"], "x-example")


if __name__ == "__main__":
    unittest.main()

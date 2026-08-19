import unittest

from scripts.x_search import (
    ChannelUnavailable,
    build_sidecar,
    candidate_id,
    normalize_x_candidate,
    sidecar_path,
    validate_web_access_staging,
)


class XContractTests(unittest.TestCase):
    def setUp(self):
        self.accounts = [
            {"source_id": "x-example", "x_handle": "example", "display_name": "Example"},
            {"source_id": "x-other", "x_handle": "other", "display_name": "Other"},
        ]

    def test_web_access_staging_requires_strict_account_and_post_contract(self):
        staging = {
            "provider": "xai",
            "report_date": "2026-08-19",
            "accounts_total": 2,
            "accounts_completed": 1,
            "account_results": [
                {"source_id": "x-example", "handle": "example", "status": "complete", "error": None, "posts": [{
                    "author": "Example", "handle": "example", "url": "https://x.com/example/status/1",
                    "text": "Copper supply update", "publish_time": "2026-08-19T10:00:00+08:00",
                }]},
                {"source_id": "x-other", "handle": "other", "status": "failed", "error": "login wall", "posts": []},
            ],
        }
        normalized = validate_web_access_staging(staging, "2026-08-19", self.accounts)
        self.assertEqual(normalized["accounts_completed"], 1)
        for bad in (
            {**staging, "provider": "other"},
            {**staging, "accounts_completed": 2},
            {**staging, "account_results": [{**staging["account_results"][0], "handle": "other"}]},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ChannelUnavailable):
                    validate_web_access_staging(bad, "2026-08-19", self.accounts)

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
        )
        self.assertEqual(sidecar["status"], "partial")
        self.assertEqual(sidecar["errors"][0]["source_id"], "x-example")


if __name__ == "__main__":
    unittest.main()

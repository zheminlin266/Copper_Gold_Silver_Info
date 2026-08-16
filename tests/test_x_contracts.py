import unittest

from scripts.x_search import build_sidecar, candidate_id, normalize_x_candidate, sidecar_path


class XContractTests(unittest.TestCase):
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

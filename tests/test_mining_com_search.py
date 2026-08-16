import unittest

from scripts.mining_com_search import category_url, matches_report_date


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


if __name__ == "__main__":
    unittest.main()

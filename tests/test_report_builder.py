import tempfile
import unittest
from pathlib import Path

from scripts.report_builder import ReportBuilderError, project_report, write_report


class ReportBuilderTests(unittest.TestCase):
    def bundle(self):
        return {
            "report_date": "2024-02-29",
            "summary": "铜供给端出现新的项目进展。",
            "candidates": [{
                "id": "c-1",
                "document_id": "d-1",
                "source_url": "https://example.com/news/1",
                "title": "Project update",
                "text": "raw source text",
                "published_at": "2024-02-29T08:00:00+08:00",
                "kind": "news",
                "source": "Example",
            }],
            "decisions": [{
                "candidate_id": "c-1",
                "decision": "accept",
                "kind": "news",
                "metal": "copper",
                "direction": "supply",
                "confidence": 0.9,
                "verification_status": "verified",
                "source": "Example",
                "title": "Project update",
                "excerpt": "The company announced a supply-side project update.",
                "language": "en",
                "claims": [{
                    "claim": "The project advanced.",
                    "evidence": "The source states the project advanced.",
                    "source_url": "https://example.com/news/1",
                    "evidence_type": "company release",
                    "period": "2024",
                    "unit": "status",
                    "value": "advanced",
                }],
            }],
            "search_log": {
                "part1_searched": True,
                "part1_sources_checked": ["broadcast registry"],
                "part1_result": "completed; no accepted broadcasts",
                "part2_searched": True,
                "part2_channel": "playwright",
                "part2_sources_checked": ["X registry"],
                "part2_result": "completed; no accepted X posts",
                "part3_searched": True,
                "part3_sources_checked": ["Example"],
                "part3_result": "completed; one candidate analyzed",
                "url_verification": {"checked": 1, "passed": 1, "failed": 0, "failures": []},
            },
            "dedup_log": {},
        }

    def test_safe_projection_has_schema_version_windows_and_news_shape(self):
        report = project_report(self.bundle(), report_time="2024-03-01T07:00:00+08:00")
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["windows"]["part1"]["start"], "2024-02-27T00:00:00+08:00")
        self.assertEqual(report["part3_news"][0]["primary_metal"], "copper")
        self.assertEqual(report["part3_news"][0]["claims"][0]["value"], "advanced")

    def test_invalid_analysis_is_rejected(self):
        bundle = self.bundle()
        bundle["decisions"][0]["confidence"] = float("nan")
        with self.assertRaises(ReportBuilderError):
            project_report(bundle)
        bundle = self.bundle()
        bundle["decisions"][0]["candidate_id"] = "missing"
        with self.assertRaises(ReportBuilderError):
            project_report(bundle)

    def test_current_report_requires_complete_collection_audit(self):
        bundle = self.bundle()
        bundle["report_date"] = "2026-08-17"
        bundle["candidates"][0]["published_at"] = "2026-08-17"
        report = project_report(bundle, report_time="2026-08-18T07:00:00+08:00")
        self.assertEqual(report["schema_version"], 3)
        bundle["search_log"]["part2_channel"] = "failed"
        with self.assertRaises(ReportBuilderError):
            project_report(bundle, report_time="2026-08-18T07:00:00+08:00")

    def test_twscrape_channel_is_publishable(self):
        bundle = self.bundle()
        bundle["report_date"] = "2026-08-17"
        bundle["candidates"][0]["published_at"] = "2026-08-17"
        bundle["search_log"]["part2_channel"] = "twscrape"
        report = project_report(bundle, report_time="2026-08-18T07:00:00+08:00")
        self.assertEqual(report["search_log"]["part2_channel"], "twscrape")

    def test_explicit_rejection_is_not_published(self):
        bundle = self.bundle()
        bundle["decisions"][0] = {
            "candidate_id": "c-1",
            "decision": "reject",
            "reason": "not a material supply-demand signal",
        }
        bundle["search_log"]["url_verification"] = {
            "checked": 0,
            "passed": 0,
            "failed": 0,
            "failures": [],
        }
        report = project_report(bundle, report_time="2024-03-01T07:00:00+08:00")
        self.assertEqual(report["part3_news"], [])

    def test_final_writer_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = write_report(self.bundle(), directory, report_time="2024-03-01T07:00:00+08:00")
            self.assertEqual(target, Path(directory) / "2024-02-29.json")
            with self.assertRaises(FileExistsError):
                write_report(self.bundle(), directory, report_time="2024-03-01T07:00:00+08:00")


if __name__ == "__main__":
    unittest.main()

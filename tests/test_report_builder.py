import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.report_builder import ReportBuilderError, build_report, project_report, validate_report, write_report


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

    def test_partial_and_failed_x_coverage_are_publishable_with_audit(self):
        for status, completed, failed in (("partial", 1, 1), ("failed", 0, 2)):
            with self.subTest(status=status):
                bundle = self.bundle()
                bundle["report_date"] = "2026-08-19"
                bundle["candidates"][0]["published_at"] = "2026-08-19"
                bundle["search_log"].update({
                    "part2_searched": False,
                    "part2_channel": "twscrape",
                    "part2_result": f"X {completed}/2; {status} reason",
                    "part2_coverage": {
                        "status": status,
                        "accounts_total": 2,
                        "accounts_completed": completed,
                        "accounts_failed": failed,
                        "attempted_channels": ["web_access_xai", "twscrape"],
                        "selected_channel": "web_access_xai" if status == "partial" else None,
                        "channel_errors": ["account unavailable"],
                        "notes": "preserved candidates",
                    },
                })
                report = build_report(bundle, report_time="2026-08-20T07:00:00+08:00")
                self.assertEqual(report["search_log"]["part2_coverage"]["status"], status)

    def test_new_x_report_requires_consistent_coverage(self):
        bundle = self.bundle()
        bundle["report_date"] = "2026-08-19"
        bundle["candidates"][0]["published_at"] = "2026-08-19"
        with self.assertRaises(ReportBuilderError):
            project_report(bundle, report_time="2026-08-20T07:00:00+08:00")
        bundle["search_log"]["part2_coverage"] = {
            "status": "complete", "accounts_total": 2, "accounts_completed": 1, "accounts_failed": 0,
            "attempted_channels": ["web_access_xai"], "selected_channel": "web_access_xai",
            "channel_errors": [], "notes": "bad count",
        }
        with self.assertRaises(ReportBuilderError):
            project_report(bundle, report_time="2026-08-20T07:00:00+08:00")

    def test_current_x_coverage_rejects_old_channel_and_accepts_new_order(self):
        bundle = self.bundle()
        bundle["report_date"] = "2026-08-20"
        bundle["candidates"][0]["published_at"] = "2026-08-20"
        bundle["search_log"].update({
            "part2_searched": False,
            "part2_channel": "twscrape",
            "part2_result": "X 2/3; one account failed",
            "part2_coverage": {
                "status": "partial",
                "accounts_total": 3,
                "accounts_completed": 2,
                "accounts_failed": 1,
                "attempted_channels": ["playwright", "twscrape"],
                "selected_channel": "playwright+twscrape",
                "channel_errors": ["one account failed"],
                "notes": "preserved candidates",
            },
        })
        self.assertEqual(project_report(bundle, report_time="2026-08-21T07:00:00+08:00")["search_log"]["part2_coverage"]["selected_channel"], "playwright+twscrape")
        bundle["search_log"]["part2_result"] = "X 1/2; one account failed"
        bundle["search_log"]["part2_coverage"].update({
            "accounts_total": 2,
            "accounts_completed": 1,
            "accounts_failed": 1,
        })
        with self.assertRaisesRegex(ReportBuilderError, "more channels than completed accounts"):
            project_report(bundle, report_time="2026-08-21T07:00:00+08:00")
        bundle["search_log"]["part2_coverage"]["attempted_channels"] = ["web_access_xai"]
        bundle["search_log"]["part2_coverage"]["selected_channel"] = "web_access_xai"
        with self.assertRaisesRegex(ReportBuilderError, "ordered channel prefix"):
            project_report(bundle, report_time="2026-08-21T07:00:00+08:00")

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

    def current_bundle(self):
        bundle = self.bundle()
        bundle["report_date"] = "2026-08-17"
        bundle["candidates"][0]["published_at"] = "2026-08-17"
        return bundle

    def test_conflicting_decision_and_accepted_are_rejected(self):
        for decision, accepted in (("accept", False), ("accepted", False), ("reject", True), ("rejected", True)):
            with self.subTest(decision=decision):
                bundle = self.bundle()
                bundle["decisions"][0].update(decision=decision, accepted=accepted)
                with self.assertRaisesRegex(ReportBuilderError, "disagree"):
                    project_report(bundle)

    def test_semantic_failures_never_create_or_replace_final_report(self):
        mutations = (
            ("window", lambda b: b["candidates"][0].update(published_at="2026-08-16"), "outside its validation window"),
            ("duplicate metals", lambda b: b["decisions"][0].update(metal_tags=["copper", "copper"]), "duplicates"),
            ("importance", lambda b: b["decisions"][0].update(importance="too short"), "80-300"),
            ("schema field", lambda b: b["decisions"][0].update(companies="not an array"), "must be array"),
        )
        for name, mutate, message in mutations:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                bundle = self.current_bundle()
                mutate(bundle)
                target = Path(directory) / "2026-08-17.json"
                with self.assertRaisesRegex(ReportBuilderError, message):
                    write_report(bundle, directory)
                self.assertFalse(target.exists())
                self.assertEqual(list(Path(directory).iterdir()), [])
                target.write_bytes(b"original report bytes")
                with self.assertRaisesRegex(ReportBuilderError, message):
                    write_report(bundle, directory, overwrite=True)
                self.assertEqual(target.read_bytes(), b"original report bytes")
                self.assertEqual(list(Path(directory).iterdir()), [target])
                with self.assertRaisesRegex(ReportBuilderError, message):
                    build_report(bundle)

    def test_title_source_only_unverified_news_and_x(self):
        for kind in ("news", "x"):
            with self.subTest(kind=kind):
                bundle = self.current_bundle()
                decision = bundle["decisions"][0]
                decision.update(kind=kind, verification_status="unverified", verification_note="Source inaccessible")
                decision.pop("claims")
                decision.pop("excerpt")
                if kind == "x":
                    decision.update(author="Example", handle="@example")
                bundle["search_log"]["url_verification"] = {
                    "checked": 1, "passed": 0, "failed": 1,
                    "failures": [{"url": bundle["candidates"][0]["source_url"], "reason": "Source inaccessible"}],
                }
                report = build_report(bundle)
                card = report["part3_news" if kind == "news" else "part2_x_posts"][0]
                self.assertNotIn("excerpt", card)
                self.assertNotIn("claims", card)
                with tempfile.TemporaryDirectory() as directory:
                    self.assertTrue(write_report(bundle, directory).exists())
                decision["importance"] = "unsupported short judgment"
                with self.assertRaisesRegex(ReportBuilderError, "80-300"):
                    build_report(bundle)
                decision.pop("importance")
                decision["detail"] = "unsupported factual field"
                with self.assertRaisesRegex(ReportBuilderError, "unsupported"):
                    build_report(bundle)

    def test_broadcast_retains_schema_required_summary_without_inventing_claims(self):
        bundle = self.current_bundle()
        decision = bundle["decisions"][0]
        decision.update(kind="broadcast", verification_status="unverified", verification_note="Source inaccessible", source_type="podcast", summary="Source title and availability note")
        decision.pop("claims")
        decision.pop("excerpt")
        bundle["search_log"]["url_verification"] = {
            "checked": 1, "passed": 0, "failed": 1,
            "failures": [{"url": bundle["candidates"][0]["source_url"], "reason": "Source inaccessible"}],
        }
        self.assertNotIn("claims", build_report(bundle)["part1_broadcasts"][0])
        decision["guest"] = "invalid legacy guest string"
        with self.assertRaisesRegex(ReportBuilderError, "must be object"):
            build_report(bundle)
        decision.pop("guest")
        decision.pop("summary")
        with self.assertRaisesRegex(ReportBuilderError, "summary must be non-empty"):
            build_report(bundle)

    def test_verified_cards_still_require_claims_and_facts(self):
        for field in ("claims", "excerpt"):
            bundle = self.current_bundle()
            bundle["decisions"][0].pop(field)
            with self.assertRaises(ReportBuilderError):
                build_report(bundle)

    def test_coverage_rejects_empty_attempts_and_zero_accounts(self):
        for zero_accounts in (False, True):
            bundle = self.current_bundle()
            bundle["report_date"] = "2026-08-20"
            bundle["candidates"][0]["published_at"] = "2026-08-20"
            bundle["search_log"]["part2_coverage"] = {
                "status": "complete", "accounts_total": 0 if zero_accounts else 1,
                "accounts_completed": 0 if zero_accounts else 1, "accounts_failed": 0,
                "attempted_channels": ["playwright"] if zero_accounts else [],
                "selected_channel": None if zero_accounts else "playwright", "channel_errors": [], "notes": "audit",
            }
            with self.assertRaisesRegex(ReportBuilderError, "positive|ordered channel prefix"):
                project_report(bundle)

    def test_node_validation_fails_closed_and_cleans_node_options(self):
        report = project_report(self.bundle())
        for error in (FileNotFoundError("node missing"), subprocess.TimeoutExpired("node", 30)):
            with patch("scripts.report_builder.subprocess.run", side_effect=error):
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(ReportBuilderError, "could not complete"):
                        write_report(self.bundle(), directory)
                    self.assertEqual(list(Path(directory).iterdir()), [])
        with patch.dict(os.environ, {"NODE_OPTIONS": "--require=untrusted"}):
            # A real subprocess proves injected Node startup options are not used.
            validate_report(report)
        with patch("scripts.report_builder.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            validate_report(report)
            self.assertEqual(run.call_args.kwargs["timeout"], 30)
            self.assertNotIn("NODE_OPTIONS", run.call_args.kwargs["env"])
            self.assertEqual(run.call_args.args[0][-2:], ["--stdin", "2024-02-29.json"])
        report["date"] = "../unsafe"
        with self.assertRaises(ReportBuilderError), patch("scripts.report_builder.subprocess.run") as run:
            validate_report(report)
        run.assert_not_called()

    def test_cli_validate_only_and_errors(self):
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.pop("NODE_OPTIONS", None)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            command = [sys.executable, "-B", str(root / "scripts/report_builder.py"), "-", "--validate-only", "--data-dir", str(output)]
            valid = subprocess.run(command, input=json.dumps(self.current_bundle()), text=True, capture_output=True, env=env)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertFalse(output.exists())
            invalid = self.current_bundle()
            invalid["candidates"][0]["published_at"] = "2026-08-16"
            for payload, message in ((json.dumps(invalid), "outside its validation window"), ("{", "unable to read"), ("[]", "must be an object")):
                result = subprocess.run(command, input=payload, text=True, capture_output=True, env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(output.exists())
            invalid_date = self.current_bundle()
            invalid_date["report_date"] = "2026-02-30"
            result = subprocess.run(command, input=json.dumps(invalid_date), text=True, capture_output=True, env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            missing = subprocess.run([sys.executable, "-B", str(root / "scripts/report_builder.py"), str(Path(directory) / "missing.json")], text=True, capture_output=True, env=env)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("unable to read", missing.stderr)
            self.assertNotIn("Traceback", missing.stderr)

    def test_final_writer_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = write_report(self.bundle(), directory, report_time="2024-03-01T07:00:00+08:00")
            self.assertEqual(target, Path(directory) / "2024-02-29.json")
            original = target.read_bytes()
            for overwrite in (False, True):
                with self.subTest(overwrite=overwrite), self.assertRaises(FileExistsError):
                    write_report(self.bundle(), directory, overwrite=overwrite, report_time="2024-03-01T08:00:00+08:00")
                self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

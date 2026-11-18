"""Offline Grok handoff and omission guards; no real sources or X are queried."""

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import date
from unittest.mock import patch
from pathlib import Path

from scripts.grok_research import ROOT, discovery_template, prepare_collection
from scripts.report_builder import ReportBuilderError, build_report, calculate_windows, project_report, validate_report

PUBLISHED_FIXTURE_DATE = "2026-11-17"
PUBLISHED_FIXTURE_SHA256 = "fb7883345206842e96aba7b634f6a5c3d44e46d92ac061f92bbcfa55c683642d"


def _published_report_name(path: Path) -> str | None:
    """Return a daily-report filename when path is exactly data/YYYY-MM-DD.json."""
    try:
        relative = Path(path).relative_to(ROOT / "data")
    except ValueError:
        return None
    if len(relative.parts) != 1 or not relative.name.endswith(".json"):
        return None
    try:
        date.fromisoformat(relative.name[:-5])
    except ValueError:
        return None
    return relative.name


class GrokResearchTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".runtime").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="grok-test-", dir=ROOT / ".runtime")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        # prepare_collection refuses when data/<date>.json exists. Point that
        # existence check at an empty directory so a published report cannot
        # collide with the offline fixture. The production check itself stays
        # in place and still fails when this isolated directory contains the date.
        self.isolated_data = self.folder / "isolated-data"
        self.isolated_data.mkdir()
        original_exists = Path.exists

        def exists(path, *args, **kwargs):
            name = _published_report_name(path)
            if name is not None:
                return original_exists(self.isolated_data / name, *args, **kwargs)
            return original_exists(path, *args, **kwargs)

        patcher = patch.object(Path, "exists", exists)
        patcher.start()
        self.addCleanup(patcher.stop)

    def discovery(self):
        manifest = discovery_template(PUBLISHED_FIXTURE_DATE)
        for source in manifest["sources"]:
            source.update(status="complete", entry_urls=["https://example.com/offline-list"],
                          termination="end_of_window", note="Offline fixture: list boundary precedes the report window")
        manifest["x_attempted_channels"] = ["grok_x"]
        for number, account in enumerate(manifest["x_accounts"]):
            account.update(user_id=manifest["x_registry"][number]["user_id"] or str(number + 1),
                           resolved_handle=account["handle"], identity_verified=True,
                           pagination_complete=True, status="complete", channel="grok_x",
                           note="Offline fixture: identity checked and pagination exhausted, zero posts")
        manifest["candidates"] = [{
            "source_id": "newsfile", "source_url": "https://example.com/offline-release",
            "kind": "news", "title": "Offline copper production fixture", "published_at": "2026-11-17T09:00:00+08:00",
            "source": "Offline issuer", "source_channel": "web", "language": "en",
        }]
        next(s for s in manifest["sources"] if s["source_id"] == "newsfile")["discovered_count"] = 1
        return manifest

    def prepare(self, manifest=None):
        manifest = manifest or self.discovery()
        source = self.folder / "collection.json"
        source.write_text(json.dumps(manifest), encoding="utf-8")
        bundle = json.loads(prepare_collection(source).read_text(encoding="utf-8"))
        self.assertEqual(bundle["summary"], "")  # A forgotten draft summary must not publish.
        bundle["summary"] = "离线测试样本，不发布。"
        return bundle

    def accepted_bundle(self, manifest=None):
        bundle = self.prepare(manifest)
        capture = self.folder / "body.json"
        raw = json.dumps({"source_url": bundle["candidates"][0]["source_url"],
                          "text": "Quarterly copper production increased to 100 tonnes.",
                          "captured_at": "2026-11-18T07:15:00+08:00", "access_status": "public"}).encode()
        capture.write_bytes(raw)
        cid = bundle["candidates"][0]["id"]
        bundle["summary"] = "铜矿季度产量增加，供给改善。"
        bundle["decisions"] = [{
            "candidate_id": cid, "decision": "accept", "kind": "news", "metal": "copper", "direction": "supply",
            "confidence": 0.9, "verification_status": "verified", "excerpt": "季度铜产量增至100吨。",
            "evidence_documents": [{"artifact_path": capture.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}],
            "claims": [{"claim": "产量增至100吨", "evidence": "100 tonnes", "source_url": bundle["candidates"][0]["source_url"],
                        "evidence_type": "issuer_release", "period": "quarter", "unit": "tonnes", "value": 100}],
        }]
        bundle["search_log"]["url_verification"] = {"checked": 1, "passed": 1, "failed": 0, "failures": []}
        return bundle

    def test_native_grok_handoff_accepts_body_captured_after_discovery_freeze(self):
        bundle = self.accepted_bundle()
        report = build_report(bundle)
        self.assertEqual(report["part3_news"][0]["claims"][0]["value"], 100)
        self.assertEqual(report["search_log"]["part2_channel"], "grok_x")
        self.assertEqual(report["search_log"]["research_audit"]["candidates"][0]["signal_url"], bundle["candidates"][0]["source_url"])
        self.assertNotIn("evidence_documents", bundle["candidates"][0])
        self.assertIn("evidence_documents", bundle["decisions"][0])

    def test_missing_or_changed_frozen_candidates_and_hash_are_blocked(self):
        bundle = self.accepted_bundle()
        for change in ("omit", "change", "hash", "missing"):
            broken = copy.deepcopy(bundle)
            if change == "omit":
                broken["candidates"] = []
                broken["decisions"] = []
            elif change == "change":
                broken["candidates"][0]["title"] = "Changed after freezing"
            elif change == "hash":
                broken["collection_manifest"]["sha256"] = "0" * 64
            else:
                del broken["collection_manifest"]
            with self.subTest(change=change), self.assertRaisesRegex(ReportBuilderError, "collection_manifest"):
                project_report(broken)

    def test_pending_and_technical_failure_cannot_be_editorial_rejections(self):
        bundle = self.prepare()
        with self.assertRaisesRegex(ReportBuilderError, "pending_verification"):
            project_report(bundle)
        cid = bundle["candidates"][0]["id"]
        for code in ("fetch_timeout", "no_supply_demand"):
            bundle["decisions"] = [{"candidate_id": cid, "decision": "reject", "reason_code": code, "reason": "Body fetch timed out"}]
            with self.subTest(code=code), self.assertRaisesRegex(ReportBuilderError, "editorial|captured source body"):
                project_report(bundle)
        bundle["decisions"][0].update(reason_code="non_target_metal", reason="Listing explicitly concerns lithium only")
        self.assertEqual(build_report(bundle)["part3_news"], [])

    def test_required_source_discovery_count_and_unchecked_source_block_prepare(self):
        for change in ("required", "count", "unchecked"):
            manifest = self.discovery()
            source = next(s for s in manifest["sources"] if s["source_id"] == "asx")
            if change == "required":
                source["status"] = "partial"
            elif change == "count":
                source["discovered_count"] = 3
            else:
                source = next(s for s in manifest["sources"] if s["source_id"] == "business-wire")
                source["status"] = "pending"
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "incomplete|count|not been checked"):
                self.prepare(manifest)

    def test_source_counts_and_publication_decisions_are_rechecked_by_node(self):
        report = build_report(self.accepted_bundle())
        for change in ("required", "count", "decision", "pagination", "missing_optional"):
            broken = copy.deepcopy(report)
            audit = broken["search_log"]["research_audit"]
            source = next(s for s in audit["sources"] if s["source_id"] == "asx")
            if change == "required":
                source.update(status="partial", termination="error")
            elif change == "count":
                source["discovered_count"] = 1
            elif change == "decision":
                audit["candidates"] = []
            elif change == "pagination":
                source["termination"] = "error"
            else:
                audit["sources"] = [s for s in audit["sources"] if s["source_id"] != "business-wire"]
            with self.subTest(change=change), self.assertRaisesRegex(ReportBuilderError, "research audit"):
                validate_report(broken)

    def test_x_identity_pagination_and_real_channel_are_enforced(self):
        report = build_report(self.accepted_bundle())
        for change in ("identity", "pagination", "placeholder", "missing_account"):
            broken = copy.deepcopy(report)
            account = broken["search_log"]["research_audit"]["x_accounts"][0]
            if change == "identity":
                account["resolved_handle"] = "different_person"
            elif change == "pagination":
                account["pagination_complete"] = False
            elif change == "placeholder":
                broken["search_log"]["part2_channel"] = "playwright"
            else:
                broken["search_log"]["research_audit"]["x_accounts"].pop()
            with self.subTest(change=change), self.assertRaisesRegex(ReportBuilderError, "research audit"):
                validate_report(broken)

    def test_failed_native_x_and_optional_source_failure_can_publish_honest_audit(self):
        manifest = self.discovery()
        manifest["x_attempted_channels"] = []
        for account in manifest["x_accounts"]:
            account.update(status="failed", identity_verified=False, pagination_complete=False,
                           channel=None, user_id="", resolved_handle="", note="Offline fixture: native tool unavailable")
        source = next(s for s in manifest["sources"] if s["source_id"] == "business-wire")
        source.update(status="failed", termination="error", note="Offline fixture: newsroom inaccessible")
        report = build_report(self.accepted_bundle(manifest))
        self.assertFalse(report["search_log"]["part2_searched"])
        self.assertEqual(report["search_log"]["part2_coverage"]["status"], "failed")
        self.assertIsNone(report["search_log"]["part2_coverage"]["selected_channel"])

    def test_prepare_is_exclusive_and_existing_reports_are_not_recollected(self):
        self.prepare()
        with self.assertRaises(FileExistsError):
            prepare_collection(self.folder / "collection.json")
        manifest = self.discovery()
        manifest["report_date"] = "2026-11-16"
        (self.isolated_data / "2026-11-16.json").write_bytes(b"{}")
        (self.folder / "existing.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare_collection(self.folder / "existing.json")

    def test_fixture_prepare_stays_isolated_when_published_report_exists(self):
        published = ROOT / "data" / f"{PUBLISHED_FIXTURE_DATE}.json"
        self.assertTrue(published.is_file())
        before = published.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), PUBLISHED_FIXTURE_SHA256)
        bundle = self.prepare()
        self.assertEqual(bundle["report_date"], PUBLISHED_FIXTURE_DATE)
        self.assertFalse((self.isolated_data / published.name).is_file())
        (self.isolated_data / published.name).write_bytes(before)
        blocked = self.folder / "published-date.json"
        blocked.write_text(json.dumps(self.discovery()), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare_collection(blocked)
        self.assertEqual(published.read_bytes(), before)
        self.assertEqual(hashlib.sha256(published.read_bytes()).hexdigest(), PUBLISHED_FIXTURE_SHA256)

    def test_interrupted_prepare_recovers_only_the_missing_analysis_file(self):
        from scripts.grok_research import _atomic_write_json
        def fail_analysis(path, data):
            if path.name == "analysis.json":
                raise OSError("Offline fixture: interrupted before analysis write")
            return _atomic_write_json(path, data)
        with patch("scripts.grok_research._atomic_write_json", side_effect=fail_analysis):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.prepare()
        frozen = (self.folder / "collection.frozen.json").read_bytes()
        self.assertFalse((self.folder / "analysis.json").exists())
        prepare_collection(self.folder / "collection.json")
        self.assertEqual((self.folder / "collection.frozen.json").read_bytes(), frozen)
        self.assertTrue((self.folder / "analysis.json").exists())

    def test_nonempty_native_x_posts_and_confirmed_browser_fallback(self):
        manifest = self.discovery()
        account = manifest["x_accounts"][0]
        manifest["x_attempted_channels"] = ["grok_x", "playwright"]
        account["channel"] = "playwright"
        url = f"https://x.com/{account['handle']}/status/123"
        manifest["candidates"].append({
            "kind": "x", "source_id": "assigned-by-prepare", "handle": account["handle"], "author": "Offline fixture author",
            "source_url": url, "title": "Offline production post", "published_at": "2026-11-17T10:00:00+08:00",
            "text": "Mine production rose to 10 ounces.",
        })
        bundle = self.accepted_bundle(manifest)
        candidate = bundle["candidates"][1]
        bundle["decisions"].append({
            "candidate_id": candidate["id"], "decision": "accept", "kind": "x", "metal": "gold", "direction": "supply",
            "confidence": 0.9, "verification_status": "verified", "excerpt": "测试矿山产量增至10盎司。",
            "claims": [{"claim": "测试产量", "evidence": "10 ounces", "source_url": url,
                        "evidence_type": "original_post", "period": "quarter", "unit": "ounces", "value": 10}],
        })
        bundle["search_log"]["url_verification"].update(checked=2, passed=2)
        report = build_report(bundle)
        self.assertEqual(report["search_log"]["part2_coverage"]["selected_channel"], "grok_x+playwright")
        self.assertEqual(report["part2_x_posts"][0]["source_channel"], "playwright")
        report["part2_x_posts"][0]["source_channel"] = "grok_x"
        with self.assertRaisesRegex(ReportBuilderError, "actual account channel"):
            validate_report(report)

    def test_november_16_known_27_additions_survive_offline_handoff_and_reconcile(self):
        fixture = json.loads((ROOT / "tests/fixtures/2026-11-16-known-additions.json").read_text(encoding="utf-8"))
        manifest = self.discovery()
        manifest["candidates"] = []
        for item in fixture:
            candidate = {key: value for key, value in item.items() if key != "primary_metal"}
            candidate.update(source="Offline replay fixture", language="en")
            if candidate["kind"] == "broadcast":
                candidate["source_type"] = "podcast"
            manifest["candidates"].append(candidate)
        for source in manifest["sources"]:
            source["discovered_count"] = sum(c["source_id"] == source["source_id"] for c in manifest["candidates"])
        # Historical replay is entirely offline; it does not claim that an X
        # account or source was queried by this test, and writes no daily report.
        manifest["x_attempted_channels"] = ["playwright"]
        for account in manifest["x_accounts"]:
            account.update(status="failed", channel=None, identity_verified=False, pagination_complete=False,
                           note="Offline historical fixture: no X collection performed")
        bundle = self.prepare(manifest)
        frozen = json.loads((self.folder / "collection.frozen.json").read_text(encoding="utf-8"))
        frozen.update(report_date="2026-11-16", windows=calculate_windows("2026-11-16"))
        raw = json.dumps(frozen, ensure_ascii=False).encode("utf-8")
        replay = self.folder / "historical-replay.json"
        replay.write_bytes(raw)
        bundle.update(report_date="2026-11-16", summary="离线回放样本，仅验证候选对账，不发布。",
                      collection_manifest={"artifact_path": replay.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()})
        bundle["search_log"]["url_verification"] = {
            "checked": 27, "passed": 0, "failed": 27,
            "failures": [{"url": c["source_url"], "reason": "Offline accounting fixture"} for c in bundle["candidates"]],
        }
        bundle["decisions"] = []
        for candidate, item in zip(bundle["candidates"], fixture):
            decision = {"candidate_id": candidate["id"], "decision": "accept", "kind": candidate["kind"],
                        "metal": item["primary_metal"], "direction": "supply", "confidence": 0,
                        "verification_status": "unverified", "verification_note": "Offline accounting fixture; no new source access"}
            if candidate["kind"] == "broadcast":
                decision.update(publish_date=candidate["published_at"][:10], summary=candidate["title"])
            bundle["decisions"].append(decision)
        report = build_report(bundle)
        self.assertEqual((len(report["part1_broadcasts"]), len(report["part2_x_posts"]), len(report["part3_news"])), (1, 0, 26))
        self.assertEqual(len(report["search_log"]["research_audit"]["candidates"]), 27)
        bundle["candidates"].pop()
        bundle["decisions"].pop()
        with self.assertRaisesRegex(ReportBuilderError, "frozen collection_manifest"):
            project_report(bundle)


if __name__ == "__main__":
    unittest.main()

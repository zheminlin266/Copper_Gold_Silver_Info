import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.daily_pipeline import PipelineError, calculate_windows, run_pipeline
from scripts.runtime_support import AlreadyRunning, exclusive_lock
from scripts.source_registry import get_x_accounts, load_registry


class DailyPipelineTests(unittest.TestCase):
    def test_windows_are_exact_beijing_calendar_boundaries(self):
        windows = calculate_windows("2024-02-29")
        self.assertEqual(windows["part1"], {
            "start": "2024-02-27T00:00:00+08:00",
            "end": "2024-02-29T23:59:59+08:00",
        })
        self.assertEqual(windows["part2"], windows["part3"])

    def test_mining_candidates_dedupe_cross_category_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            shutil.copy(Path("data/source_registry.json"), root / "data/source_registry.json")
            payload = {
                "status": "ok",
                "extraction_status": "success",
                "articles": [{
                    "url": "https://example.com/mining-article",
                    "title": "Shared mining article",
                    "date_match_text": "February 29, 2024",
                }],
            }
            with mock.patch(
                "scripts.daily_pipeline._run_process",
                return_value=(0, json.dumps(payload), "", None),
            ):
                manifest = run_pipeline("2024-02-29", collect_mining=True, project_root=root)
            candidates = json.loads(
                (root / ".runtime" / "pipeline" / "2024-02-29" / next(
                    (item.name for item in (root / ".runtime" / "pipeline" / "2024-02-29").iterdir())
                ) / "candidates.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(len(candidates), 1)

    def test_x_collection_uses_current_channel_order_and_preserves_partial_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "x_outputs").mkdir()
            shutil.copy(Path("data/source_registry.json"), root / "data/source_registry.json")
            sidecar = {
                "collector": "x_search", "report_date": "2024-02-29", "status": "partial",
                "accounts_total": 53, "accounts_completed": 2, "accounts_failed": 51,
                "attempted_channels": ["playwright", "twscrape"], "channel_completed_accounts": {"playwright": 1, "twscrape": 1}, "selected_channel": "playwright+twscrape",
                "metadata": {"channel_errors": []}, "unavailable_channels": [],
                "candidates": [], "errors": [
                    {"source_id": account["source_id"], "handle": account["x_handle"], "author": account["display_name"], "error": "failed"}
                    for account in get_x_accounts(load_registry())[:51]
                ],
            }
            captured = {}
            def fake_process(command, **kwargs):
                captured["command"] = command
                (root / "x_outputs" / "2024-02-29_x_raw_materials.txt").write_text("audit", encoding="utf-8")
                (root / "x_outputs" / "2024-02-29_x_raw_materials.json").write_text(json.dumps(sidecar), encoding="utf-8")
                return 4, "stdout", "stderr", None
            with mock.patch("scripts.daily_pipeline._run_process", side_effect=fake_process):
                manifest = run_pipeline("2024-02-29", collect_x=True, project_root=root)
            self.assertNotIn("web-access", " ".join(captured["command"]))
            self.assertEqual(manifest["status"], "partial")
            collector = manifest["collectors"][0]
            self.assertEqual(collector["metadata"]["part2_coverage"]["accounts_completed"], 2)

    def test_x_sidecar_rejects_status_and_selected_count_conflicts(self):
        accounts = get_x_accounts(load_registry())
        base = {
            "collector": "x_search", "report_date": "2024-02-29", "status": "partial",
            "accounts_total": 53, "accounts_completed": 1, "accounts_failed": 52,
            "attempted_channels": ["playwright", "twscrape"],
            "channel_completed_accounts": {"playwright": 1}, "selected_channel": "playwright",
            "metadata": {"channel_errors": []}, "unavailable_channels": [],
            "candidates": [], "errors": [
                {"source_id": account["source_id"], "handle": account["x_handle"], "author": account["display_name"], "error": "failed"}
                for account in accounts[:52]
            ],
        }

        def run_invalid(sidecar):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data").mkdir()
                (root / "x_outputs").mkdir()
                shutil.copy(Path("data/source_registry.json"), root / "data" / "source_registry.json")

                def fake_process(_command, **_kwargs):
                    (root / "x_outputs" / "2024-02-29_x_raw_materials.txt").write_text("audit", encoding="utf-8")
                    (root / "x_outputs" / "2024-02-29_x_raw_materials.json").write_text(json.dumps(sidecar), encoding="utf-8")
                    return 4, "stdout", "stderr", None

                with mock.patch("scripts.daily_pipeline._run_process", side_effect=fake_process):
                    return run_pipeline("2024-02-29", collect_x=True, project_root=root)

        status_conflict = dict(base, status="complete")
        self.assertEqual(run_invalid(status_conflict)["status"], "failed")
        selected_conflict = dict(base, selected_channel="playwright+twscrape")
        self.assertEqual(run_invalid(selected_conflict)["status"], "failed")

    def test_nonzero_or_malformed_mining_is_a_durable_failure(self):
        for payload, returncode in (({"status": "ok", "extraction_status": "success_empty", "articles": []}, 7),
                                    ({"status": "ok", "extraction_status": "success", "articles": [None]}, 0)):
            with self.subTest(returncode=returncode), tempfile.TemporaryDirectory() as directory:
                root = self.prepare_root(directory)
                with mock.patch("scripts.daily_pipeline._run_process", return_value=(returncode, json.dumps(payload), "", None)):
                    manifest = run_pipeline("2024-02-29", collect_mining=True, project_root=root)
                self.assertEqual(manifest["status"], "failed")
                self.assertTrue(manifest["completed_at"])
                self.assertTrue(manifest["collectors"][0]["errors"])
                self.assertTrue((Path(manifest["run_dir"]) / "mining_com_search.result.json").exists())

    @staticmethod
    def prepare_root(directory):
        root = Path(directory)
        (root / "data").mkdir()
        (root / "x_outputs").mkdir()
        shutil.copy(Path("data/source_registry.json"), root / "data/source_registry.json")
        return root

    @staticmethod
    def complete_sidecar():
        total = len(get_x_accounts(load_registry()))
        return {"collector": "x_search", "report_date": "2024-02-29", "status": "complete",
                "accounts_total": total, "accounts_completed": total, "accounts_failed": 0,
                "attempted_channels": ["playwright"], "selected_channel": "playwright",
                "channel_completed_accounts": {"playwright": total},
                "metadata": {"channel_errors": []}, "unavailable_channels": [], "candidates": [], "errors": []}

    def test_existing_x_requires_explicit_offline_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare_root(directory)
            raw = root / "x_outputs/2024-02-29_x_raw_materials.txt"
            sidecar = raw.with_suffix(".json")
            raw.write_text("audit", encoding="utf-8")
            sidecar.write_text(json.dumps(self.complete_sidecar()), encoding="utf-8")
            with mock.patch("scripts.daily_pipeline._run_process", side_effect=AssertionError("X ran")) as process:
                rejected = run_pipeline("2024-02-29", collect_x=True, project_root=root)
                imported = run_pipeline("2024-02-29", import_x=True, project_root=root)
            process.assert_not_called()
            self.assertEqual(rejected["status"], "failed")
            self.assertEqual(imported["status"], "complete")
            self.assertEqual(raw.read_text(), "audit")

    def test_invalid_sidecar_cannot_leak_candidates_or_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare_root(directory)
            payload = self.complete_sidecar()
            payload["candidates"] = [{"candidate_id": "x-test", "source_id": "not-registered", "author": "someone",
                                      "handle": "someone", "text": "fact", "url": "https://x.com/someone/status/1",
                                      "publish_time": "2024-02-29T12:00:00+08:00", "collector": "x_search",
                                      "status": "ok", "report_date": "2024-02-29"}]
            (root / "x_outputs/2024-02-29_x_raw_materials.txt").write_text("audit")
            (root / "x_outputs/2024-02-29_x_raw_materials.json").write_text(json.dumps(payload))
            manifest = run_pipeline("2024-02-29", import_x=True, project_root=root)
            collector = manifest["collectors"][0]
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(collector["candidates"], [])
            self.assertEqual(collector["metadata"], {})

    def test_mining_stage_survives_x_exception_and_reuses_without_traffic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare_root(directory)
            payload = {"status": "ok", "extraction_status": "success", "articles": [
                {"url": "https://example.com/article", "title": "mine", "date_match_text": "February 29, 2024"}]}
            with mock.patch("scripts.daily_pipeline._run_process", return_value=(0, json.dumps(payload), "", None)), \
                 mock.patch("scripts.daily_pipeline._collect_x", side_effect=RuntimeError("injected X failure")):
                first = run_pipeline("2024-02-29", collect_mining=True, collect_x=True, project_root=root)
            self.assertEqual(first["status"], "failed")
            self.assertEqual(len(first["candidate_ids"]), 1)
            saved = json.loads((Path(first["run_dir"]) / "candidates.json").read_text())
            self.assertEqual(len(saved), 1)
            with mock.patch("scripts.daily_pipeline._run_process", side_effect=AssertionError("collector reran")):
                resumed = run_pipeline("2024-02-29", reuse_mining=first["run_dir"], project_root=root)
            self.assertEqual(resumed["status"], "complete")
            self.assertEqual(resumed["candidate_ids"], first["candidate_ids"])
            path = Path(first["run_dir"]) / "mining_com_search.result.json"
            record = json.loads(path.read_text())
            record["report_date"] = "2024-02-28"
            path.write_text(json.dumps(record))
            rejected = run_pipeline("2024-02-29", reuse_mining=first["run_dir"], project_root=root)
            self.assertEqual(rejected["status"], "failed")

    def test_interruption_persists_failed_manifest_without_next_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare_root(directory)
            with mock.patch("scripts.daily_pipeline._collect_mining", side_effect=KeyboardInterrupt), \
                 mock.patch("scripts.daily_pipeline._collect_x") as collect_x:
                with self.assertRaises(KeyboardInterrupt):
                    run_pipeline("2024-02-29", collect_mining=True, collect_x=True, project_root=root)
                collect_x.assert_not_called()
            path = next((root / ".runtime/pipeline/2024-02-29").glob("*/manifest.json"))
            manifest = json.loads(path.read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertIsNotNone(manifest["completed_at"])

    def test_duplicate_collector_lock_and_x_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare_root(directory)
            with exclusive_lock(root / ".runtime/locks/pipeline-2024-02-29-x_search.lock"):
                with self.assertRaises(AlreadyRunning):
                    run_pipeline("2024-02-29", collect_x=True, project_root=root)
            with mock.patch("scripts.daily_pipeline._run_process", return_value=(124, "", "", "timeout")) as process:
                manifest = run_pipeline("2024-02-29", collect_x=True, project_root=root)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(process.call_args.kwargs["timeout"], 3600)
            self.assertEqual(manifest["status"], "failed")

    def test_removed_x_web_access_option_fails_explicitly(self):
        from scripts import daily_pipeline

        with self.assertRaises(SystemExit):
            daily_pipeline.main(["2024-02-29", "--x-web-access-input", "staging.json"])

    def test_preflight_creates_manifest_without_running_collectors_and_refuses_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            shutil.copy(Path("data/source_registry.json"), root / "data/source_registry.json")
            with mock.patch("scripts.daily_pipeline.run_logged_process", side_effect=AssertionError("collector ran")):
                manifest = run_pipeline("2024-02-29", dry_run=True, collect_x=True, project_root=root)
            self.assertEqual(manifest["status"], "preflight")
            run_dirs = list((root / ".runtime" / "pipeline" / "2024-02-29").iterdir())
            self.assertEqual(len(run_dirs), 1)
            self.assertTrue((run_dirs[0] / "manifest.json").exists())
            self.assertTrue((run_dirs[0] / "candidates.json").exists())
            (root / "data" / "2024-02-29.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(PipelineError):
                run_pipeline("2024-02-29", dry_run=True, project_root=root)


if __name__ == "__main__":
    unittest.main()

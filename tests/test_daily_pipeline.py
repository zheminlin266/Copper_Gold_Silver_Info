import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.daily_pipeline import PipelineError, calculate_windows, run_pipeline


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

    def test_preflight_creates_manifest_without_running_collectors_and_refuses_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            shutil.copy(Path("data/source_registry.json"), root / "data/source_registry.json")
            with mock.patch("scripts.daily_pipeline.subprocess.run", side_effect=AssertionError("collector ran")):
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

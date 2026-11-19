from datetime import date, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import run_scheduled_weekly as weekly
from scripts.weekly_tc import tc_rows, update_tc


WEEK = date(2026, 11, 9)
TC_BASE = (
    "assessment_date,value_usd_per_dmt,change_usd_per_dmt,source_url,source_note\n"
    "2026-11-06,-247.35,0.33,https://www.metal.com/copper/201910240001,SMM baseline\n"
)
POINT = {
    "assessment_date": "2026-11-13",
    "value_usd_per_dmt": "-241.75",
    "source_url": "https://www.metal.com/copper/201910240001",
    "source_note": "SMM verified observation",
}


class ScheduledWeeklyTest(unittest.TestCase):
    def test_state_write_retries_a_windows_file_sharing_conflict(self):
        conflict = PermissionError("Status file in use")
        conflict.winerror = 5
        with patch.object(weekly, "atomic_write_json", side_effect=[conflict, None]) as write, \
                patch.object(weekly, "sleep") as sleep:
            weekly.write_state(Path("state.json"), {"status": "running"})
        self.assertEqual(write.call_count, 2)
        sleep.assert_called_once_with(0.25)

    def test_window_for_monday_start_catchup_and_year_boundary(self):
        for now, expected in [
            ("2026-11-15T23:59:59+00:00", "2026-11-02"),
            ("2026-11-16T00:00:00+00:00", "2026-11-09"),
            ("2026-11-17T17:00:00+08:00", "2026-11-09"),
            ("2027-01-04T08:00:00+08:00", "2026-12-28"),
        ]:
            self.assertEqual(str(weekly.week_for_run(datetime.fromisoformat(now))), expected)

    def test_append_only_tc_is_idempotent_and_uses_actual_assessment_date(self):
        point = {**POINT, "assessment_date": "2026-11-12"}
        text, status = update_tc(TC_BASE, point, WEEK)
        self.assertEqual(status, "updated")
        self.assertTrue(text.startswith(TC_BASE))
        self.assertEqual(tc_rows(text)[-1]["assessment_date"], "2026-11-12")
        self.assertEqual(tc_rows(text)[-1]["change_usd_per_dmt"], "5.60")
        self.assertEqual(update_tc(text, point, WEEK), (text, "existing"))
        self.assertEqual(update_tc(TC_BASE, None, WEEK), (TC_BASE, "unavailable"))
        with self.assertRaisesRegex(ValueError, "conflicts"):
            update_tc(text, {**point, "value_usd_per_dmt": "-242.00"}, WEEK)
        with self.assertRaisesRegex(ValueError, "outside"):
            update_tc(TC_BASE, POINT, date(2026, 11, 16))

    def test_prepare_retry_preserves_timestamp_and_does_not_duplicate_tc(self):
        report = json.loads((weekly.ROOT / "data/weekly/2026-11-09.json").read_text(encoding="utf-8"))
        draft = {"report": report, "tc": POINT, "tc_note": "SMM checked"}
        with TemporaryDirectory() as temp:
            root = Path(temp)
            tc_path = root / weekly.TC_PATH
            tc_path.parent.mkdir()
            tc_path.write_text(TC_BASE, encoding="utf-8")
            target_dir = root / "data/weekly"
            target_dir.mkdir()
            target = target_dir / "2026-11-09.json"
            first_run = root / "first"
            second_run = root / "second"
            first_run.mkdir()
            second_run.mkdir()
            with patch.object(weekly, "ROOT", root):
                first, status = weekly.prepare_report(draft, target, WEEK, lambda _: None, first_run)
                self.assertEqual(status, "updated")
                second, status = weekly.prepare_report(draft, target, WEEK, lambda _: None, second_run)
                self.assertEqual(status, "existing")
            self.assertEqual(first, second)
            self.assertEqual(len(tc_rows(tc_path.read_text(encoding="utf-8"))), 2)


if __name__ == "__main__":
    unittest.main()

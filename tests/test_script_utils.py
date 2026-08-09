import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scripts.script_utils import (
    atomic_write_text,
    bounded_int,
    parse_report_date,
    resolve_chrome_executable,
)


class ScriptUtilsTests(unittest.TestCase):
    def test_parse_report_date_is_strict_and_real(self):
        self.assertEqual(parse_report_date("2024-02-29"), date(2024, 2, 29))
        for value in ("2023-02-29", "2024-2-09", "2024-02-9", "D:/reports/2024-02-29"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_report_date(value)

    def test_bounded_int_requires_an_integer_inclusive_range(self):
        self.assertEqual(bounded_int(3, 1, 3, "timeout"), 3)
        for value in (0, 4, True, "2"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    bounded_int(value, 1, 3, "timeout")

    def test_chrome_resolution_without_environment_does_not_depend_on_local_chrome(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(Path, "is_file", return_value=False):
                self.assertIsNone(resolve_chrome_executable())

    def test_chrome_resolution_rejects_a_missing_configured_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing-chrome")
            with mock.patch.dict(os.environ, {"CHROME_EXECUTABLE": missing}, clear=True):
                with self.assertRaises(FileNotFoundError):
                    resolve_chrome_executable()

    def test_atomic_text_refuses_overwrite_by_default_and_can_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.txt"
            atomic_write_text(target, "first")
            self.assertEqual(target.read_text(encoding="utf-8"), "first")
            with self.assertRaises(FileExistsError):
                atomic_write_text(target, "second")
            atomic_write_text(target, "second", overwrite=True)
            self.assertEqual(target.read_text(encoding="utf-8"), "second")
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

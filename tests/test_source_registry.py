import tempfile
import unittest
from pathlib import Path

from scripts.source_registry import (
    SourceRegistryError,
    get_x_accounts,
    load_registry,
    validate_registry,
)


class SourceRegistryTests(unittest.TestCase):
    def test_authoritative_registry_has_valid_unique_x_sources(self):
        registry = load_registry()
        accounts = get_x_accounts(registry)
        handles = {entry["x_handle"].casefold() for entry in accounts}
        self.assertEqual(len(accounts), len(handles))
        self.assertTrue(accounts)
        self.assertTrue(all(entry["source_id"] for entry in accounts))

    def test_source_without_x_handle_keeps_channel_but_is_not_collected(self):
        registry = validate_registry({"version": 1, "sources": [
            {"source_id": "paused", "display_name": "Paused", "category": "person",
             "channel": "https://x.com/Paused", "x_user_id": "42"},
            {"source_id": "active", "display_name": "Active", "category": "person",
             "x_handle": "Active"},
        ]})
        self.assertEqual([entry["source_id"] for entry in get_x_accounts(registry)], ["active"])
        self.assertEqual(registry[0]["channel"], "https://x.com/Paused")
        self.assertEqual(registry[0]["x_user_id"], "42")

    def test_duplicate_handles_merge_case_insensitively(self):
        entries = validate_registry(
            {
                "version": 1,
                "sources": [
                    {
                        "source_id": "first",
                        "display_name": "First",
                        "category": "person",
                        "notes": "primary",
                        "x_handle": "Example",
                    },
                    {
                        "source_id": "second",
                        "display_name": "Second",
                        "category": "person",
                        "notes": "additional",
                        "channel": "https://x.com/example",
                        "x_handle": "example",
                        "x_user_id": "42",
                    },
                ],
            }
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source_id"], "first")
        self.assertEqual(entries[0]["x_user_id"], "42")
        self.assertIn("additional", entries[0]["notes"])

    def test_malformed_entries_fail_clearly(self):
        with self.assertRaisesRegex(SourceRegistryError, "x_handle"):
            validate_registry(
                {"version": 1, "sources": [{"source_id": "bad", "display_name": "Bad", "category": "x", "x_handle": "bad handle"}]}
            )

    def test_invalid_json_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(SourceRegistryError, "not valid JSON"):
                load_registry(path)


if __name__ == "__main__":
    unittest.main()

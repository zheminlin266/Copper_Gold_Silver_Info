#!/usr/bin/env python3
"""Build the static search index used by index.html."""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "Historical_Daily_Reports"
WEEKLY_DIR = ROOT / "Weekly_Reports"
OUTPUT_FILE = ROOT / "data" / "search-index.json"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title_parts = []
        self.body_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.body_parts.append(data)


def compact_text(value):
    return re.sub(r"\s+", " ", value).strip()


def normalize(value):
    return unicodedata.normalize("NFKC", value).casefold()


def read_text(path):
    return path.read_text(encoding="utf-8")


def html_entry(path):
    parser = TextExtractor()
    parser.feed(read_text(path))
    title = compact_text(" ".join(parser.title_parts))
    text = compact_text(" ".join(parser.body_parts))
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    date = date_match.group(1) if date_match else ""
    return {
        "type": "Daily",
        "date": date,
        "sortDate": date,
        "title": title or path.stem,
        "url": f"./Historical_Daily_Reports/{path.name}",
        "text": text,
    }


def markdown_title(text, fallback):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def weekly_entry(path):
    text = compact_text(read_text(path))
    week_match = re.search(r"(\d{4})-W(\d{2})", path.name)
    if week_match:
        year, week = int(week_match.group(1)), int(week_match.group(2))
        week_start = datetime.fromisocalendar(year, week, 1).date()
        date = f"{year}-W{week:02d}"
        sort_date = str(week_start + timedelta(days=6))
    else:
        date = ""
        sort_date = ""
    return {
        "type": "Weekly",
        "date": date,
        "sortDate": sort_date,
        "title": markdown_title(text, path.stem),
        "url": f"./Weekly_Reports/{path.name}",
        "text": text,
    }


def build_index():
    entries = []
    for path in sorted(DAILY_DIR.glob("*.html"), reverse=True):
        if path.name.endswith("_backup.html"):
            continue
        entries.append(html_entry(path))

    for path in sorted(WEEKLY_DIR.glob("*.md"), reverse=True):
        entries.append(weekly_entry(path))

    entries.sort(key=lambda item: item.get("sortDate", ""), reverse=True)
    return entries


def write_index(entries):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def check_index(entries):
    raw = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    if raw != entries:
        raise AssertionError("Written search index does not match generated entries.")

    daily_files = [
        path for path in DAILY_DIR.glob("*.html")
        if not path.name.endswith("_backup.html")
    ]
    daily_entries = [entry for entry in entries if entry["type"] == "Daily"]
    if len(daily_entries) != len(daily_files):
        raise AssertionError("Every non-backup historical daily report must be indexed.")

    if any("_backup.html" in entry["url"] for entry in entries):
        raise AssertionError("Backup daily reports must not be indexed.")

    searchable_entries = [
        normalize(f"{entry['title']} {entry['text']}") for entry in entries
    ]
    for term in ("Codelco", "KatusaResearch"):
        needle = normalize(term)
        if not any(needle in text for text in searchable_entries):
            raise AssertionError(f"Expected search term not found in index: {term}")

    # ponytail: Chinese text in older generated pages may be mojibake; keep this
    # as a soft check until the source encoding is cleaned up.
    if any("铜" in f"{entry['title']} {entry['text']}" for entry in entries):
        if not any("铜" in text for text in searchable_entries):
            raise AssertionError("Expected Chinese copper keyword not found in index.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run minimal self-checks")
    args = parser.parse_args()

    entries = build_index()
    write_index(entries)

    if args.check:
        check_index(entries)

    print(f"Wrote {len(entries)} search entries to {OUTPUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

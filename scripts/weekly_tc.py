"""Apply one verified SMM weekly TC observation without rewriting history."""

import csv
from datetime import date, timedelta
from decimal import Decimal
import io
import re
from urllib.parse import urlsplit

from scripts.script_utils import parse_report_date

HEADERS = ("assessment_date", "value_usd_per_dmt", "change_usd_per_dmt", "source_url", "source_note")
TC_FIELDS = {"assessment_date", "value_usd_per_dmt", "source_url", "source_note"}


def tc_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if tuple(reader.fieldnames or ()) != HEADERS:
        raise ValueError("Unexpected TC CSV schema")
    rows = list(reader)
    if not rows:
        raise ValueError("TC CSV needs an existing baseline")
    return rows


def update_tc(text: str, observation: dict | None, week_start: date) -> tuple[str, str]:
    rows = tc_rows(text)
    week_end = week_start + timedelta(days=6)
    existing = [row for row in rows if week_start <= parse_report_date(row["assessment_date"]) <= week_end]
    if observation is None:
        return text, "existing" if existing else "unavailable"
    if not isinstance(observation, dict) or observation.keys() != TC_FIELDS:
        raise ValueError("TC requires a date, value, URL and source note")
    assessment = parse_report_date(observation["assessment_date"])
    value_text = observation["value_usd_per_dmt"]
    if not week_start <= assessment <= week_end:
        raise ValueError("TC assessment falls outside the report week")
    if not isinstance(value_text, str) or not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", value_text):
        raise ValueError("TC must be a decimal string with at most two places")
    url = urlsplit(observation["source_url"])
    note = observation["source_note"]
    if (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password
            or not isinstance(note, str) or not note.strip()):
        raise ValueError("TC requires a public source URL and a nonempty source note")
    value = Decimal(value_text)
    if existing:
        if len(existing) != 1 or existing[0]["assessment_date"] != str(assessment) or (
            Decimal(existing[0]["value_usd_per_dmt"]) != value
        ):
            raise ValueError("TC observation conflicts with an existing assessment for this week")
        return text, "existing"
    previous = rows[-1]
    if assessment <= parse_report_date(previous["assessment_date"]):
        raise ValueError("TC assessments must be appended chronologically")
    change = value - Decimal(previous["value_usd_per_dmt"])
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(
        (str(assessment), f"{value:.2f}", f"{change:.2f}", observation["source_url"],
         f"{note.strip()} Prior CSV value {previous['value_usd_per_dmt']} USD/dmt."),
    )
    separator = "" if text.endswith("\n") else "\n"
    return text + separator + buffer.getvalue(), "updated"

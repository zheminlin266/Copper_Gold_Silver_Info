"""Read-only freshness/business-status check. No collection, scheduling or network calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEIJING = timezone(timedelta(hours=8))
TC_PATH = "data/smm_copper_concentrate_index_2026.csv"


def aware_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(BEIJING)


def check_health(root: Path, now: datetime, grace_minutes: int = 240) -> dict:
    """Describe the latest scheduled cycle, never infer that absent state means no AI ran."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if type(grace_minutes) is not int or not 1 <= grace_minutes <= 1440:
        raise ValueError("grace_minutes must be an integer from 1 to 1440")
    now = now.astimezone(BEIJING)
    run_date = now.date() if now.hour >= 7 else now.date() - timedelta(days=1)
    report_date = str(run_date - timedelta(days=1))
    deadline = datetime.combine(run_date, time(7), BEIJING) + timedelta(minutes=grace_minutes)
    result = {"checked_at": now.isoformat(), "run_date": str(run_date), "report_date": report_date,
              "deadline": deadline.isoformat(), "scope": "local saved verification evidence; not a live production or Chrome authorization check"}

    def finish(status: str, reason: str, alert: bool = True) -> dict:
        return {**result, "status": status, "alert": alert, "reason": reason}

    target = root / "data" / f"{report_date}.json"
    state_path = root / ".runtime" / "scheduled" / f"{report_date}.state.json"
    try:
        state = None
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or state.get("report_date") != report_date:
                raise ValueError("saved state date/shape is invalid")
            if state.get("status") not in {"running", "failed", "success"}:
                raise ValueError("saved state status is invalid")
            if state["status"] == "failed":
                return finish("failed", str(state.get("error") or "saved verification failed"))
        if not target.exists():
            if state and state["status"] == "success":
                return finish("missing_report", "Saved success exists but the expected report is missing")
            if now < deadline:
                return finish("pending", "Expected report not yet present; completion grace has not elapsed; AI start is unknown", False)
            return finish("missing_report", "Completion deadline passed without the expected report; do not automatically recollect")
        report_bytes = target.read_bytes()
        report = json.loads(report_bytes)
        if not isinstance(report, dict) or report.get("date") != report_date:
            raise ValueError("report date/shape does not match the expected cycle")
        if not state:
            return finish("verification_required", "Report exists without saved business verification; AI start is unknown")
        if state["status"] == "running":
            return finish("overdue" if now >= deadline else "pending", "Saved run has no terminal verification result; liveness is not inferred", now >= deadline)
        stages = state.get("stages")
        required = ("report", "validate:content", "typecheck", "python-tests", "npm-test", "build", "publication")
        if not isinstance(stages, dict) or any(not isinstance(stages.get(key), dict) or stages[key].get("status") != "success" for key in required):
            return finish("verification_required", "Saved success lacks successful business stages")
        completed = aware_time(state.get("completed_at", ""))
        if completed > now or completed < datetime.combine(run_date, time.min, BEIJING):
            raise ValueError("saved completion time is outside the expected cycle")
        if not re.fullmatch(r"[0-9a-f]{40}", str(state.get("verified_main_sha", ""))):
            return finish("verification_required", "Saved success lacks a verified main SHA")
        expected = {"verified_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
                    "verified_tc_sha256": hashlib.sha256((root / TC_PATH).read_bytes()).hexdigest()}
        if any(state.get(key) != digest for key, digest in expected.items()):
            return finish("verification_required", "Report/TC has changed or legacy state has no content hashes; reverify existing artifacts only")
        return finish("verified", "Expected report matches saved successful CI/production verification; no live recheck performed", False)
    except (OSError, ValueError, TypeError) as error:
        return finish("invalid_evidence", str(error))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", type=aware_time, help="Explicit timezone-aware check time for offline replay")
    parser.add_argument("--grace-minutes", type=int, default=240, help="Completion grace after Beijing 07:00 (default 240)")
    args = parser.parse_args(argv)
    try:
        result = check_health(ROOT, args.now or datetime.now(BEIJING), args.grace_minutes)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["alert"] else 0


if __name__ == "__main__":
    sys.exit(main())

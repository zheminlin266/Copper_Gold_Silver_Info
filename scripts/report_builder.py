"""Validate an analysis bundle and atomically create one daily report.

This is intentionally the only module that writes ``data/YYYY-MM-DD.json``.
It accepts analysis output, never performs collection, and never calls an AI or
browser service.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.pipeline_contracts import (
        ContractError,
        DIRECTIONS,
        KINDS,
        METALS,
        EvidenceClaim,
        validate_confidence,
        validate_date,
        validate_date_or_datetime,
        validate_datetime,
        validate_direction,
        validate_metal,
        validate_url,
    )
except ModuleNotFoundError:
    from pipeline_contracts import (  # type: ignore[no-redef]
        ContractError,
        DIRECTIONS,
        KINDS,
        METALS,
        EvidenceClaim,
        validate_confidence,
        validate_date,
        validate_date_or_datetime,
        validate_datetime,
        validate_direction,
        validate_metal,
        validate_url,
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
TZ_BEIJING = timezone(timedelta(hours=8))
SOURCE_TYPES = frozenset({
    "podcast", "webcast", "youtube", "conference_interview", "panel", "keynote",
    "company_presentation",
})
LANGUAGES = frozenset({"en", "zh"})
PART2_CHANNELS = frozenset({"browser_use", "rss_fallback", "web_access_xai", "twscrape", "playwright", "failed"})
LEGACY_PART2_CHANNEL_ORDER = ("web_access_xai", "twscrape", "playwright")
CURRENT_PART2_CHANNEL_ORDER = ("playwright", "twscrape")
LEGACY_PART2_SELECTED_CHANNELS = frozenset({
    "web_access_xai", "twscrape", "playwright",
    "web_access_xai+twscrape", "web_access_xai+playwright", "twscrape+playwright",
    "web_access_xai+twscrape+playwright",
})
CURRENT_PART2_SELECTED_CHANNELS = frozenset({"playwright", "twscrape", "playwright+twscrape"})
PART2_COVERAGE_REQUIRED_FROM = "2026-08-19"
CURRENT_PART2_ORDER_FROM = "2026-08-20"
PART3_CHANNELS = frozenset({"web", "playwright"})


class ReportBuilderError(ContractError):
    """Raised when an analysis bundle cannot produce a safe report."""


def calculate_windows(report_date: str) -> dict[str, dict[str, str]]:
    """Return the three inclusive Beijing calendar-day windows."""
    report = date.fromisoformat(validate_date(report_date, "report_date"))

    def iso(day: date, end: bool) -> str:
        return datetime.combine(day, time(23, 59, 59) if end else time.min, TZ_BEIJING).isoformat()

    return {
        "part1": {"start": iso(report - timedelta(days=2), False), "end": iso(report, True)},
        "part2": {"start": iso(report, False), "end": iso(report, True)},
        "part3": {"start": iso(report, False), "end": iso(report, True)},
    }


def _is_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReportBuilderError(f"{name} must be an object")
    return value


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportBuilderError(f"{field_name} must be non-empty")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name)


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ReportBuilderError(f"{name} has unsupported field(s): {', '.join(sorted(unknown))}")


CANDIDATE_FIELDS = {
    "id", "candidate_id", "document_id", "source_url", "url", "title", "text", "raw_text",
    "published_at", "publish_time", "publish_date", "collector", "kind", "source", "author",
    "handle", "metal", "metal_tags", "direction", "supply_demand", "language", "source_type",
    "source_channel", "excerpt", "summary", "detail", "interpretation", "importance", "claims",
    "guest", "companies", "projects", "verification_status", "verification_note",
    "mining_com_source_note", "duplicate_of", "raw",
}
DECISION_FIELDS = {
    "candidate_id", "accepted", "decision", "kind", "metal", "primary_metal", "metal_tags",
    "direction", "supply_demand", "confidence", "reason", "claims", "title", "summary", "detail",
    "excerpt", "interpretation", "importance", "author", "handle", "source", "url", "source_url",
    "publish_date", "publish_time", "language", "source_type", "source_channel", "guest", "companies",
    "projects", "verification_status", "verification_note", "mining_com_source_note", "duplicate_of",
}
SEARCH_LOG_FIELDS = {
    "part1_searched", "part1_sources_checked", "part1_result", "part2_searched", "part2_channel",
    "part2_sources_checked", "part2_result", "part2_coverage", "part3_searched", "part3_sources_checked", "part3_result",
    "mining_com_source_note", "image_source", "new_sources_discovered", "url_verification",
}
DEDUP_LOG_FIELDS = {"part1_deduped_urls", "part2_deduped_urls", "part3_deduped_events", "notes"}
BUNDLE_FIELDS = {"report_date", "summary", "candidates", "decisions", "search_log", "dedup_log"}


def _record_id(record: Mapping[str, Any], name: str) -> str:
    value = record.get("id")
    alternate = record.get("candidate_id")
    if value is None:
        value = alternate
    elif alternate is not None and value != alternate:
        raise ReportBuilderError(f"{name} has conflicting id and candidate_id")
    return _nonempty(value, f"{name}.id")


def _candidate_url(candidate: Mapping[str, Any]) -> str:
    value = candidate.get("source_url", candidate.get("url"))
    return validate_url(value, "candidate.source_url")


def _candidate_date(candidate: Mapping[str, Any]) -> str | None:
    value = candidate.get("published_at")
    if value is None:
        value = candidate.get("publish_time", candidate.get("publish_date"))
    return validate_date_or_datetime(value, "candidate.published_at") if value is not None else None


def _field(decision: Mapping[str, Any], candidate: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in decision and decision[name] is not None:
            return decision[name]
        if name in candidate and candidate[name] is not None:
            return candidate[name]
    return default


def _copy_optional(output: dict[str, Any], decision: Mapping[str, Any], candidate: Mapping[str, Any], key: str, *aliases: str) -> None:
    value = _field(decision, candidate, key, *aliases)
    if value is not None:
        output[key] = value


def _validate_claims(value: Any, candidate_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ReportBuilderError(f"decision {candidate_id} must include at least one evidence claim")
    claims = []
    for index, claim in enumerate(value):
        try:
            parsed = claim if isinstance(claim, EvidenceClaim) else EvidenceClaim.from_dict(claim)
        except (ContractError, TypeError) as error:
            raise ReportBuilderError(f"invalid evidence claim for {candidate_id}[{index}]: {error}") from error
        claims.append(parsed.to_dict())
    return claims


def _validate_part2_coverage(value: Any, report_date: str | None = None) -> dict[str, Any]:
    coverage = dict(_is_mapping(value, "search_log.part2_coverage"))
    allowed = {"status", "accounts_total", "accounts_completed", "accounts_failed", "attempted_channels", "selected_channel", "channel_errors", "notes"}
    _reject_unknown(coverage, allowed, "search_log.part2_coverage")
    if not allowed.issubset(coverage):
        raise ReportBuilderError("search_log.part2_coverage is missing required audit fields")
    if coverage.get("status") not in {"complete", "partial", "failed"}:
        raise ReportBuilderError("search_log.part2_coverage.status is unsupported")
    for field in ("accounts_total", "accounts_completed", "accounts_failed"):
        if type(coverage.get(field)) is not int or coverage[field] < 0:
            raise ReportBuilderError(f"search_log.part2_coverage.{field} must be a non-negative integer")
    if coverage["accounts_completed"] + coverage["accounts_failed"] != coverage["accounts_total"]:
        raise ReportBuilderError("search_log.part2_coverage counts must sum to accounts_total")
    if coverage["status"] == "complete" and coverage["accounts_completed"] != coverage["accounts_total"]:
        raise ReportBuilderError("complete Part 2 coverage must complete every account")
    if coverage["status"] != "complete" and coverage["accounts_completed"] == coverage["accounts_total"]:
        raise ReportBuilderError("non-complete Part 2 coverage cannot complete every account")
    channel_order = CURRENT_PART2_CHANNEL_ORDER if report_date and report_date >= CURRENT_PART2_ORDER_FROM else LEGACY_PART2_CHANNEL_ORDER
    selected_channels = CURRENT_PART2_SELECTED_CHANNELS if report_date and report_date >= CURRENT_PART2_ORDER_FROM else LEGACY_PART2_SELECTED_CHANNELS
    attempted = coverage.get("attempted_channels")
    if not isinstance(attempted, list) or attempted != list(channel_order[:len(attempted)]):
        raise ReportBuilderError("search_log.part2_coverage.attempted_channels must be an ordered channel prefix")
    selected = coverage.get("selected_channel")
    if selected not in selected_channels and selected is not None:
        raise ReportBuilderError("search_log.part2_coverage.selected_channel is unsupported")
    if selected is not None:
        selected_parts = selected.split("+")
        if any(part not in attempted for part in selected_parts) or selected_parts != sorted(selected_parts, key=channel_order.index):
            raise ReportBuilderError("search_log.part2_coverage.selected_channel conflicts with attempted_channels")
    for field in ("channel_errors", "notes"):
        if not isinstance(coverage[field], (str, list)):
            raise ReportBuilderError(f"search_log.part2_coverage.{field} must be text or a list")
    if not isinstance(coverage["channel_errors"], list) or any(not isinstance(item, str) or not item.strip() for item in coverage["channel_errors"]):
        raise ReportBuilderError("search_log.part2_coverage.channel_errors must be a list of text")
    if isinstance(coverage["notes"], list) and any(not isinstance(item, str) or not item.strip() for item in coverage["notes"]):
        raise ReportBuilderError("search_log.part2_coverage.notes must contain text")
    return coverage


def _validate_search_log(value: Any, report_date: str | None = None) -> dict[str, Any]:
    """Validate the publish-time audit contract, not just its JSON shape."""
    data = dict(_is_mapping(value, "search_log"))
    _reject_unknown(data, SEARCH_LOG_FIELDS, "search_log")
    for part in ("part1", "part3"):
        searched = f"{part}_searched"
        sources = f"{part}_sources_checked"
        result = f"{part}_result"
        if data.get(searched) is not True:
            raise ReportBuilderError(f"search_log.{searched} must be true; Part {part[-1]} failed collection cannot be published")
        checked_sources = data.get(sources)
        if not isinstance(checked_sources, list) or any(not isinstance(item, str) or not item.strip() for item in checked_sources):
            raise ReportBuilderError(f"search_log.{sources} must be a list of non-empty strings")
        if not isinstance(data.get(result), str) or not data[result].strip():
            raise ReportBuilderError(f"search_log.{result} must be a non-empty string")
    coverage = data.get("part2_coverage")
    if coverage is not None:
        coverage = _validate_part2_coverage(coverage, report_date)
        data["part2_coverage"] = coverage
        if data.get("part2_searched") is not (coverage["status"] == "complete"):
            raise ReportBuilderError("search_log.part2_searched conflicts with Part 2 coverage status")
        if coverage["status"] == "complete":
            if not isinstance(data.get("part2_sources_checked"), list) or not data["part2_sources_checked"]:
                raise ReportBuilderError("complete Part 2 requires part2_sources_checked")
            if not isinstance(data.get("part2_result"), str) or not data["part2_result"].strip():
                raise ReportBuilderError("complete Part 2 requires part2_result")
        elif not isinstance(data.get("part2_result"), str) or not data["part2_result"].strip():
            raise ReportBuilderError("partial or failed Part 2 requires a non-empty audit result")
        else:
            match = re.search(r"(?<!\d)(\d+)/(\d+)(?!\d)", data["part2_result"])
            if not match:
                raise ReportBuilderError("partial or failed Part 2 result must include completed n/N")
            if (int(match.group(1)), int(match.group(2))) != (coverage["accounts_completed"], coverage["accounts_total"]):
                raise ReportBuilderError("partial or failed Part 2 n/N conflicts with coverage counts")
    else:
        if data.get("part2_searched") is not True:
            raise ReportBuilderError("legacy Part 2 requires part2_searched=true")
        if data.get("part2_channel") not in {"twscrape", "playwright", "browser_use", "rss_fallback"}:
            raise ReportBuilderError("search_log.part2_channel is unsupported")
        if report_date and report_date >= CURRENT_PART2_ORDER_FROM and data.get("part2_channel") == "web_access_xai":
            raise ReportBuilderError("new Part 2 reports cannot use web_access_xai")
        if not isinstance(data.get("part2_result"), str) or not data["part2_result"].strip():
            raise ReportBuilderError("search_log.part2_result must be a non-empty string")
    if data.get("part2_channel") is not None and data["part2_channel"] not in PART2_CHANNELS:
        raise ReportBuilderError("search_log.part2_channel is unsupported")
    if report_date and report_date >= CURRENT_PART2_ORDER_FROM and data.get("part2_channel") == "web_access_xai":
        raise ReportBuilderError("new Part 2 reports cannot use web_access_xai")
    verification = data.get("url_verification")
    if not isinstance(verification, Mapping):
        raise ReportBuilderError("search_log.url_verification is required")
    for field in ("checked", "passed", "failed"):
        value = verification.get(field)
        if type(value) is not int or value < 0:
            raise ReportBuilderError(f"search_log.url_verification.{field} must be a non-negative integer")
    if verification["checked"] != verification["passed"] + verification["failed"]:
        raise ReportBuilderError("search_log.url_verification.checked must equal passed + failed")
    failures = verification.get("failures", [])
    if not isinstance(failures, list):
        raise ReportBuilderError("search_log.url_verification.failures must be a list")
    if verification["failed"] > 0 and not failures:
        raise ReportBuilderError("search_log.url_verification.failures must be non-empty when failed > 0")
    return data


def _validate_verification_coverage(search_log: Mapping[str, Any], signals: list[Mapping[str, Any]]) -> None:
    verification = search_log["url_verification"]
    verified = [item for item in signals if item.get("verification_status") == "verified"]
    unverified = [item for item in signals if item.get("verification_status") == "unverified"]
    if verification["passed"] < len(verified):
        raise ReportBuilderError("url_verification.passed must cover verified signals")
    if verification["failed"] < len(unverified):
        raise ReportBuilderError("url_verification.failed must cover unverified signals")
    failed_urls = {
        failure.get("url")
        for failure in verification.get("failures", [])
        if isinstance(failure, Mapping) and isinstance(failure.get("url"), str)
    }
    for item in unverified:
        if item.get("url") not in failed_urls:
            raise ReportBuilderError(
                f"url_verification.failures must list unverified URL {item.get('url')}"
            )


def _validate_dedup_log(value: Any) -> dict[str, Any]:
    data = dict(_is_mapping(value, "dedup_log"))
    _reject_unknown(data, DEDUP_LOG_FIELDS, "dedup_log")
    data.setdefault("part1_deduped_urls", [])
    data.setdefault("part3_deduped_events", [])
    for key in ("part1_deduped_urls", "part2_deduped_urls", "part3_deduped_events"):
        if key in data and not isinstance(data[key], list):
            raise ReportBuilderError(f"dedup_log.{key} must be a list")
    return data


def _validate_candidate(data: Any, index: int) -> dict[str, Any]:
    candidate = dict(_is_mapping(data, f"candidates[{index}]"))
    _reject_unknown(candidate, CANDIDATE_FIELDS, f"candidates[{index}]")
    candidate["id"] = _record_id(candidate, f"candidates[{index}]")
    candidate["document_id"] = _nonempty(candidate.get("document_id"), f"candidates[{index}].document_id")
    candidate["source_url"] = _candidate_url(candidate)
    candidate["title"] = _nonempty(candidate.get("title"), f"candidates[{index}].title")
    _candidate_date(candidate)
    if candidate.get("kind") is not None and candidate["kind"] not in KINDS:
        raise ReportBuilderError(f"candidates[{index}].kind is unsupported")
    if candidate.get("metal") is not None:
        validate_metal(candidate["metal"], f"candidates[{index}].metal")
    if candidate.get("direction") is not None:
        validate_direction(candidate["direction"], f"candidates[{index}].direction")
    return candidate


def _validate_decision(data: Any, index: int) -> dict[str, Any]:
    decision = dict(_is_mapping(data, f"decisions[{index}]"))
    _reject_unknown(decision, DECISION_FIELDS, f"decisions[{index}]")
    candidate_id = _nonempty(decision.get("candidate_id"), f"decisions[{index}].candidate_id")
    decision["candidate_id"] = candidate_id
    raw_decision = decision.get("decision")
    accepted = decision.get("accepted")
    if raw_decision is not None:
        if raw_decision not in {"accept", "accepted", "reject", "rejected"}:
            raise ReportBuilderError(f"decisions[{index}].decision is unsupported")
        is_accept = raw_decision in {"accept", "accepted"}
    elif type(accepted) is bool:
        is_accept = accepted
    else:
        raise ReportBuilderError(f"decisions[{index}] must include decision or accepted")
    if accepted is not None and type(accepted) is not bool:
        raise ReportBuilderError(f"decisions[{index}].accepted must be boolean")
    if not is_accept:
        reason = _nonempty(decision.get("reason"), f"decisions[{index}].reason")
        decision["decision"] = "reject"
        decision["accepted"] = False
        decision["reason"] = reason
        return decision
    decision["decision"] = "accept"
    decision["accepted"] = True
    kind = decision.get("kind")
    if kind not in KINDS:
        raise ReportBuilderError(f"decisions[{index}].kind is unsupported or missing")
    metal = decision.get("metal", decision.get("primary_metal"))
    decision["metal"] = validate_metal(metal, f"decisions[{index}].metal")
    direction = decision.get("direction", decision.get("supply_demand"))
    decision["direction"] = validate_direction(direction, f"decisions[{index}].direction")
    if "confidence" not in decision:
        raise ReportBuilderError(f"decisions[{index}].confidence is required")
    decision["confidence"] = validate_confidence(decision["confidence"], f"decisions[{index}].confidence")
    decision["claims"] = _validate_claims(decision.get("claims"), candidate_id)
    return decision


def _base_signal(decision: Mapping[str, Any], candidate: Mapping[str, Any], index: int) -> dict[str, Any]:
    kind = decision["kind"]
    url = validate_url(_field(decision, candidate, "url", "source_url"), f"decisions[{index}].url")
    metal = decision["metal"]
    tags = decision.get("metal_tags", candidate.get("metal_tags", [metal]))
    if not isinstance(tags, list) or not tags:
        raise ReportBuilderError(f"decisions[{index}].metal_tags must be a non-empty list")
    normalized_tags = []
    for tag in tags:
        normalized_tags.append(validate_metal(tag, f"decisions[{index}].metal_tags"))
    if metal not in normalized_tags:
        raise ReportBuilderError(f"decisions[{index}].metal must appear in metal_tags")
    published = _field(decision, candidate, "publish_date", "publish_time", "published_at")
    if published is None:
        raise ReportBuilderError(f"decisions[{index}] is missing publish date/time")
    published = validate_date_or_datetime(published, f"decisions[{index}].publish_time")
    result = {
        "url": url,
        "metal_tags": normalized_tags,
        "primary_metal": metal,
        "supply_demand": decision["direction"],
        "claims": decision["claims"],
    }
    if kind == "broadcast":
        if len(published) != 10:
            raise ReportBuilderError(f"decisions[{index}] broadcast publish_date must be a date")
        result["publish_date"] = validate_date(published, f"decisions[{index}].publish_date")
    else:
        result["publish_time"] = published
    return result


def _project_signal(decision: Mapping[str, Any], candidate: Mapping[str, Any], index: int) -> dict[str, Any]:
    result = _base_signal(decision, candidate, index)
    kind = decision["kind"]
    if kind == "broadcast":
        result["title"] = _nonempty(_field(decision, candidate, "title"), f"decisions[{index}].title")
        result["source_type"] = _field(decision, candidate, "source_type")
        if result["source_type"] not in SOURCE_TYPES:
            raise ReportBuilderError(f"decisions[{index}].source_type is unsupported or missing")
        result["summary"] = _nonempty(_field(decision, candidate, "summary"), f"decisions[{index}].summary")
        for key in ("detail", "importance", "verification_status", "verification_note", "guest", "companies", "projects"):
            _copy_optional(result, decision, candidate, key)
    elif kind == "x":
        result["author"] = _nonempty(_field(decision, candidate, "author"), f"decisions[{index}].author")
        result["handle"] = _nonempty(_field(decision, candidate, "handle"), f"decisions[{index}].handle")
        body = _field(decision, candidate, "excerpt", "interpretation")
        if body is None:
            raise ReportBuilderError(f"decisions[{index}] needs a non-empty excerpt or interpretation")
        result["excerpt"] = _nonempty(body, f"decisions[{index}].excerpt")
        for key in ("interpretation", "importance", "verification_status", "verification_note", "source_channel"):
            _copy_optional(result, decision, candidate, key)
        if result.get("source_channel") is not None and result["source_channel"] not in PART2_CHANNELS - {"failed"}:
            raise ReportBuilderError(f"decisions[{index}].source_channel is unsupported")
    else:
        result["source"] = _nonempty(_field(decision, candidate, "source"), f"decisions[{index}].source")
        result["title"] = _nonempty(_field(decision, candidate, "title"), f"decisions[{index}].title")
        body = _field(decision, candidate, "excerpt", "interpretation")
        if body is None:
            raise ReportBuilderError(f"decisions[{index}] needs a non-empty excerpt or interpretation")
        result["excerpt"] = _nonempty(body, f"decisions[{index}].excerpt")
        language = _field(decision, candidate, "language")
        if language not in LANGUAGES:
            raise ReportBuilderError(f"decisions[{index}].language is unsupported or missing")
        result["language"] = language
        for key in ("interpretation", "importance", "verification_status", "verification_note", "duplicate_of", "companies", "projects", "mining_com_source_note", "source_channel"):
            _copy_optional(result, decision, candidate, key)
        if result.get("source_channel") is not None and result["source_channel"] not in PART3_CHANNELS:
            raise ReportBuilderError(f"decisions[{index}].source_channel is unsupported")
    verification_status = result.get("verification_status")
    if verification_status not in {"verified", "unverified"}:
        raise ReportBuilderError(
            f"decisions[{index}].verification_status must be explicitly verified or unverified"
        )
    if verification_status == "unverified":
        result["verification_note"] = _nonempty(
            result.get("verification_note"), f"decisions[{index}].verification_note"
        )
    return result


def project_report(bundle: Mapping[str, Any], *, report_time: str | None = None) -> dict[str, Any]:
    """Validate and project a bundle into the published report schema."""
    data = dict(_is_mapping(bundle, "analysis bundle"))
    _reject_unknown(data, BUNDLE_FIELDS, "analysis bundle")
    report_date = validate_date(data.get("report_date"), "report_date")
    summary = _nonempty(data.get("summary"), "summary")
    if len(summary) > 300:
        raise ReportBuilderError("summary must be at most 300 characters")
    raw_candidates = data.get("candidates")
    raw_decisions = data.get("decisions")
    if not isinstance(raw_candidates, list) or not isinstance(raw_decisions, list):
        raise ReportBuilderError("candidates and decisions must be lists")
    try:
        candidates = [_validate_candidate(item, index) for index, item in enumerate(raw_candidates)]
        decisions = [_validate_decision(item, index) for index, item in enumerate(raw_decisions)]
    except ReportBuilderError:
        raise
    except ContractError as error:
        raise ReportBuilderError(str(error)) from error
    candidate_map: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if candidate["id"] in candidate_map:
            raise ReportBuilderError(f"duplicate candidate id: {candidate['id']}")
        candidate_map[candidate["id"]] = candidate
    decision_ids = [item["candidate_id"] for item in decisions]
    if len(set(decision_ids)) != len(decision_ids):
        raise ReportBuilderError("duplicate decision candidate_id")
    if set(decision_ids) != set(candidate_map):
        missing = sorted(set(candidate_map) - set(decision_ids))
        extra = sorted(set(decision_ids) - set(candidate_map))
        detail = []
        if missing:
            detail.append("missing decisions for " + ", ".join(missing))
        if extra:
            detail.append("unknown candidates " + ", ".join(extra))
        raise ReportBuilderError("analysis records would be silently dropped: " + "; ".join(detail))
    accepted = [
        (index, decision, candidate_map[decision["candidate_id"]])
        for index, decision in enumerate(decisions)
        if decision["accepted"]
    ]
    projected = [
        _project_signal(decision, candidate, index)
        for index, decision, candidate in accepted
    ]
    projected_by_kind = {
        kind: [
            item
            for item, (_, decision, _) in zip(projected, accepted)
            if decision["kind"] == kind
        ]
        for kind in KINDS
    }
    search_log = _validate_search_log(data.get("search_log"), report_date)
    if report_date >= PART2_COVERAGE_REQUIRED_FROM and "part2_coverage" not in search_log:
        raise ReportBuilderError(
            f"search_log.part2_coverage is required for reports from {PART2_COVERAGE_REQUIRED_FROM}"
        )
    if report_date >= CURRENT_PART2_ORDER_FROM and any(
        item.get("source_channel") == "web_access_xai" for item in projected_by_kind["x"]
    ):
        raise ReportBuilderError("new Part 2 reports cannot use web_access_xai source_channel")
    _validate_verification_coverage(search_log, projected)
    output = {
        "schema_version": 3,
        "date": report_date,
        "report_time": validate_datetime(report_time or datetime.now(TZ_BEIJING).replace(microsecond=0).isoformat(), "report_time"),
        "summary": summary,
        "windows": calculate_windows(report_date),
        "part1_broadcasts": projected_by_kind["broadcast"],
        "part2_x_posts": projected_by_kind["x"],
        "part3_news": projected_by_kind["news"],
        "search_log": search_log,
        "dedup_log": _validate_dedup_log(data.get("dedup_log")),
    }
    return output


def _atomic_write_json(path: Path, data: Mapping[str, Any], *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing report: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
            temporary = None
            return
        # A hard-link publish is atomic and cannot replace an existing target.
        os.link(temporary, path)
        temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def build_report(bundle: Mapping[str, Any], *, report_time: str | None = None) -> dict[str, Any]:
    """Public name for the pure validation/projection step."""
    return project_report(bundle, report_time=report_time)


def write_report(bundle: Mapping[str, Any], data_dir: str | Path = DEFAULT_DATA_DIR, *, overwrite: bool = False, report_time: str | None = None) -> Path:
    """Validate, project, and atomically write one report without overwriting."""
    report = build_report(bundle, report_time=report_time)
    target = Path(data_dir) / f"{report['date']}.json"
    _atomic_write_json(target, report, overwrite=overwrite)
    return target


def load_bundle(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8") if str(path) != "-" else __import__("sys").stdin.read()
        value = json.loads(text)
    except (OSError, json.JSONDecodeError) as error:
        raise ReportBuilderError(f"unable to read analysis bundle: {error}") from error
    return _is_mapping(value, "analysis bundle")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build one deterministic daily report from an analysis bundle")
    parser.add_argument("bundle", help="analysis bundle JSON path, or - for stdin")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--overwrite", action="store_true", help="explicitly allow replacing the final report")
    args = parser.parse_args(argv)
    try:
        target = write_report(load_bundle(args.bundle), args.data_dir, overwrite=args.overwrite)
    except (ReportBuilderError, FileExistsError) as error:
        parser.error(str(error))
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Freeze Grok discovery inputs and project a compact, persistent research audit.

The Node content validator owns the final semantic checks. This module binds the
analysis input to the frozen collection, so omitted records cannot disappear
between collection and analysis. It never calls a model or a network service.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
POLICIES = json.loads((ROOT / "data/research_policy.json").read_text(encoding="utf-8"))["policies"]
GROK_REPORT_DATE = POLICIES[0]["effective_from"]
GROK_CHANNELS = ("grok_x", "playwright", "twscrape")
REJECTION_CODES = frozenset({"non_target_metal", "no_supply_demand", "no_new_facts", "not_interview", "promotion_only", "duplicate", "out_of_window"})


def research_policy(report_date: str, version: int | None = None) -> dict[str, Any]:
    if report_date > GROK_REPORT_DATE:
        raise ValueError("Grok research is archived; use the Codex workflow for this date")
    policies = [p for p in POLICIES if p["version"] == version] if version is not None else [
        p for p in POLICIES if p["effective_from"] <= report_date
    ]
    if not policies:
        raise ValueError("No applicable research policy; use an explicit version for an offline historical replay")
    return policies[-1]


def load_artifact(reference: Any) -> tuple[dict[str, Any], str]:
    """Read one size-limited, hash-bound JSON artifact inside the allowed roots."""
    if not isinstance(reference, dict) or set(reference) != {"artifact_path", "sha256"}:
        raise ValueError("collection_manifest requires artifact_path and sha256")
    relative = Path(reference["artifact_path"])
    if relative.is_absolute() or relative.drive or not relative.parts or relative.parts[0] not in {".runtime", "x_outputs"} or ".." in relative.parts:
        raise ValueError("collection_manifest must stay beneath .runtime or x_outputs")
    target = ROOT / relative
    for parent in (target, *target.parents):
        if parent == ROOT:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("collection_manifest symlinks/junctions are forbidden")
    if not target.resolve(strict=True).is_relative_to(ROOT.resolve()):
        raise ValueError("collection_manifest escapes repository")
    with target.open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) > 8 * 1024 * 1024 or reference["sha256"] != digest:
        raise ValueError("collection_manifest size or sha256 mismatch")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("collection_manifest must contain an object")
    return data, digest


def project_research_audit(bundle: dict[str, Any], projected: list[dict[str, Any]], content_checked: set[str]) -> dict[str, Any] | None:
    reference = bundle.get("collection_manifest")
    if reference is None:
        if bundle["report_date"] == GROK_REPORT_DATE:
            raise ValueError("collection_manifest is required for Grok reports")
        return None
    manifest, digest = load_artifact(reference)
    if type(manifest.get("version")) is not int or manifest["version"] != 1 or manifest.get("report_date") != bundle["report_date"]:
        raise ValueError("collection_manifest version or report_date mismatch")
    if type(manifest.get("policy_version")) is not int:
        raise ValueError("collection_manifest policy_version must be an integer")
    try:
        from scripts.source_registry import get_x_accounts
    except ModuleNotFoundError:
        from source_registry import get_x_accounts
    expected_registry = [{"handle": a["x_handle"], "user_id": a.get("x_user_id", "")} for a in get_x_accounts()]
    if manifest.get("x_registry") != expected_registry:
        raise ValueError("frozen X registry differs from the actual source registry")
    policy = research_policy(bundle["report_date"], manifest.get("policy_version"))
    applicable = [p for p in POLICIES if p["effective_from"] <= bundle["report_date"]]
    if applicable and policy["version"] != applicable[-1]["version"]:
        raise ValueError("collection_manifest must use the applicable research policy")
    originals = manifest.get("candidates")
    # Equality includes captured text, identifiers, timestamps and source metadata.
    if not isinstance(originals, list) or originals != bundle["candidates"]:
        raise ValueError("analysis candidates differ from frozen collection_manifest")
    if not isinstance(manifest.get("sources"), list) or not isinstance(manifest.get("x_accounts"), list):
        raise ValueError("collection_manifest needs sources and x_accounts")
    if bundle["search_log"].get("part2_coverage") != coverage_from_manifest(manifest):
        raise ValueError("Part 2 coverage differs from frozen account/channel results")
    decisions = {d["candidate_id"]: d for d in bundle["decisions"]}
    accepted_urls = {d["candidate_id"]: item["url"] for d, item in zip(
        [d for d in bundle["decisions"] if d["decision"] == "accept"], projected
    )}
    rows = []
    for candidate in originals:
        decision = decisions[candidate["id"]]
        action = decision["decision"]
        code = decision.get("reason_code", "")
        if action == "reject" and code not in REJECTION_CODES:
            raise ValueError("Grok rejection requires an editorial reason_code; access failures remain pending_verification")
        if action == "pending_verification":
            raise ValueError(f"pending_verification cannot be published: {candidate['id']}; finish verification or accept a source-only card")
        row = {key: candidate[key] for key in ("id", "source_id", "source_url", "kind", "title")}
        row["published_at"] = candidate.get("published_at")
        row["content_checked"] = candidate["id"] in content_checked
        if candidate["kind"] == "x":
            row["handle"] = candidate["handle"]
        row.update(decision=action, reason_code=code, reason=decision.get("reason", ""),
                   signal_url=accepted_urls.get(candidate["id"]))
        rows.append(row)
    return {
        "version": 1, "policy_version": policy["version"], "manifest_sha256": digest,
        "sources": manifest["sources"], "candidates": rows,
        "x_registry": manifest["x_registry"], "x_accounts": manifest["x_accounts"],
    }


def coverage_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    accounts = manifest["x_accounts"]
    completed = [a for a in accounts if a["status"] == "complete"]
    channels = [c for c in GROK_CHANNELS if any(a.get("channel") == c for a in completed)]
    total = len(accounts)
    return {
        "status": "complete" if len(completed) == total else "partial" if completed else "failed",
        "accounts_total": total, "accounts_completed": len(completed), "accounts_failed": total - len(completed),
        "attempted_channels": manifest["x_attempted_channels"],
        "selected_channel": "+".join(channels) or None,
        "channel_errors": [f"@{a['handle']}: {a['note']}" for a in accounts if a["status"] != "complete"],
        "notes": "根据逐账号身份、分页及候选审计生成；失败账号不计为成功零帖。",
    }

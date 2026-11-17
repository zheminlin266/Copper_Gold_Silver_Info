"""Grok's offline handoff: init discovery, then freeze it into an analysis bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from scripts.research_audit import ROOT, research_policy, coverage_from_manifest
    from scripts.report_builder import calculate_windows, _atomic_write_json
    from scripts.source_registry import get_x_accounts
except ModuleNotFoundError:
    from research_audit import ROOT, research_policy, coverage_from_manifest
    from report_builder import calculate_windows, _atomic_write_json
    from source_registry import get_x_accounts


def discovery_template(report_date: str) -> dict:
    windows = calculate_windows(report_date)
    policy = research_policy(report_date)
    registry = [{"handle": a["x_handle"], "user_id": a.get("x_user_id", "")} for a in get_x_accounts()]
    return {
        "version": 1, "policy_version": policy["version"], "report_date": report_date, "windows": windows,
        "sources": [{"source_id": s["source_id"], "kind": s["kind"], "status": "pending",
                     "entry_urls": [], "termination": "pending", "note": "",
                     "discovered_count": 0, "candidate_ids": []} for s in policy["sources"]],
        "candidates": [], "x_registry": registry, "x_attempted_channels": [],
        "x_accounts": [{"handle": a["handle"], "user_id": "", "resolved_handle": "",
                        "identity_verified": False, "pagination_complete": False,
                        "status": "pending", "channel": None, "note": "", "candidate_ids": []} for a in registry],
    }


def prepare_collection(collection_path: Path) -> Path:
    collection_path = collection_path.resolve(strict=True)
    if not collection_path.is_relative_to((ROOT / ".runtime").resolve()):
        raise ValueError("collection input must stay under the repository .runtime directory")
    manifest = json.loads(collection_path.read_text(encoding="utf-8"))
    report_date = manifest["report_date"]
    if (ROOT / f"data/{report_date}.json").exists():
        raise ValueError("report already exists; verify/resume publication without recollecting or overwriting")
    if manifest.get("windows") != calculate_windows(report_date):
        raise ValueError("collection windows do not match the frozen report date")
    sources = {s["source_id"]: s for s in manifest["sources"]}
    for source in manifest["sources"]:
        source["candidate_ids"] = []
    accounts = {a["handle"].casefold(): a for a in manifest["x_accounts"]}
    for account in manifest["x_accounts"]:
        account["candidate_ids"] = []
    seen = set()
    for candidate in manifest["candidates"]:
        if candidate["kind"] == "x":
            candidate["handle"] = candidate["handle"].lstrip("@")
            candidate["source_id"] = "x-" + candidate["handle"].casefold()
        url = candidate["source_url"]
        identity = f"{candidate['source_id']}\n{url}"
        cid = "grok-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        if cid in seen:
            raise ValueError(f"duplicate discovery URL within one source: {url}")
        seen.add(cid)
        candidate["id"] = cid
        candidate["document_id"] = "doc-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        candidate.setdefault("collector", "grok_bot")
        if candidate["kind"] == "x":
            account = accounts[candidate["handle"].lstrip("@").casefold()]
            candidate["source_channel"] = account["channel"]
            account["candidate_ids"].append(cid)
        else:
            sources[candidate["source_id"]]["candidate_ids"].append(cid)
    policy = research_policy(report_date, manifest["policy_version"])
    for expected in policy["sources"]:
        source = sources.get(expected["source_id"])
        if not source or source["status"] not in {"complete", "partial", "failed"}:
            raise ValueError(f"source has not been checked: {expected['source_id']}")
        if expected["required"] and source["status"] != "complete":
            raise ValueError(f"required source incomplete: {expected['source_id']}")
    for source in manifest["sources"]:
        if source["discovered_count"] != len(source["candidate_ids"]):
            raise ValueError(f"discovery count differs from candidates: {source['source_id']}")
    if any(a["status"] not in {"complete", "partial", "failed"} for a in manifest["x_accounts"]):
        raise ValueError("every X registry account needs an explicit terminal coverage status")
    coverage = coverage_from_manifest(manifest)
    log = {
        "part2_searched": coverage["status"] == "complete", "part2_channel": (coverage["selected_channel"] or "failed").split("+")[-1],
        "part2_coverage": coverage, "part2_sources_checked": ["Per-account Grok discovery audit"],
        "part2_result": f"X 完成 {coverage['accounts_completed']}/{coverage['accounts_total']}；状态 {coverage['status']}；身份、分页与失败原因见逐账号审计。",
        "url_verification": {"checked": 0, "passed": 0, "failed": 0, "failures": []},
    }
    for part, kind in (("part1", "broadcast"), ("part3", "news")):
        required = [s for s in policy["sources"] if s["kind"] == kind and s["required"]]
        log[f"{part}_searched"] = all(sources.get(s["source_id"], {}).get("status") == "complete" for s in required)
        log[f"{part}_sources_checked"] = [f"{s['source_id']}: {s['status']}; {s['note']}" for s in manifest["sources"] if s["kind"] == kind]
        log[f"{part}_result"] = "来源覆盖见结构化审计；完成表示所有必查来源的发现均已结束，可选来源降级单独保留。"
    frozen = collection_path.with_name("collection.frozen.json")
    analysis = collection_path.with_name("analysis.json")
    if analysis.exists():
        raise FileExistsError("analysis already exists; resume it instead of replacing evidence")
    if frozen.exists():
        if json.loads(frozen.read_text(encoding="utf-8")) != manifest:
            raise FileExistsError("frozen collection conflicts with discovery; preserve both and reconcile explicitly")
    else:
        _atomic_write_json(frozen, manifest)
    raw = frozen.read_bytes()
    reference = {"artifact_path": frozen.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}
    bundle = {
        "report_date": report_date, "summary": "", "collection_manifest": reference,
        "candidates": manifest["candidates"],
        "decisions": [{"candidate_id": c["id"], "decision": "pending_verification", "reason": "Awaiting source verification and editorial review"} for c in manifest["candidates"]],
        "search_log": log, "dedup_log": {},
    }
    _atomic_write_json(analysis, bundle)
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a date-frozen discovery checklist; never calls external tools")
    init.add_argument("report_date", nargs="?", help="YYYY-MM-DD; defaults to yesterday in Asia/Shanghai")
    prepare = commands.add_parser("prepare", help="Freeze discovery and create the analysis bundle; no collection or publication")
    prepare.add_argument("collection", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            now = datetime.now(timezone(timedelta(hours=8)))
            report_date = args.report_date or (now.date() - timedelta(days=1)).isoformat()
            if (ROOT / f"data/{report_date}.json").exists():
                raise ValueError("report already exists; verify/resume publication without recollecting")
            target = ROOT / ".runtime/grok" / report_date / "collection.json"
            _atomic_write_json(target, discovery_template(report_date))
        else:
            target = prepare_collection(args.collection)
        print(target.relative_to(ROOT).as_posix())
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Grok handoff failed: {error}\n")


if __name__ == "__main__":
    main()

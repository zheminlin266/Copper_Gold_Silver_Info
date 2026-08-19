"""Safe deterministic orchestration for the daily collectors.

The default mode is preflight only. Collection is opt-in and this module never
writes a published report; ``report_builder.py`` owns that boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import urldefrag, urlsplit
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from scripts.pipeline_contracts import Candidate, CollectorResult, ContractError, RunManifest, validate_datetime, validate_url
    from scripts.script_utils import parse_report_date
    from scripts.source_registry import get_x_accounts, load_registry
except ModuleNotFoundError:
    from pipeline_contracts import Candidate, CollectorResult, ContractError, RunManifest, validate_datetime, validate_url  # type: ignore[no-redef]
    from script_utils import parse_report_date  # type: ignore[no-redef]
    from source_registry import get_x_accounts, load_registry  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = PROJECT_ROOT / ".runtime" / "pipeline"
TZ_BEIJING = timezone(timedelta(hours=8))
METALS = ("gold", "silver", "copper")


class PipelineError(RuntimeError):
    """Raised when preflight or collection cannot be completed safely."""


def calculate_windows(report_date: str) -> dict[str, dict[str, str]]:
    """Return inclusive exact Beijing windows for a report date."""
    parsed = parse_report_date(report_date)

    def iso(day: date, end: bool) -> str:
        return datetime.combine(day, time(23, 59, 59) if end else time.min, TZ_BEIJING).isoformat()

    return {
        "part1": {"start": iso(parsed - timedelta(days=2), False), "end": iso(parsed, True)},
        "part2": {"start": iso(parsed, False), "end": iso(parsed, True)},
        "part3": {"start": iso(parsed, False), "end": iso(parsed, True)},
    }


def _atomic_json(path: Path, data: Any, *, overwrite: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _candidate_from_mining(article: Mapping[str, Any], report_date: str, metal: str) -> Candidate:
    url = article.get("url")
    title = article.get("title")
    raw_text = article.get("date_match_text", "")
    if not isinstance(url, str) or not isinstance(title, str) or not isinstance(raw_text, str):
        raise ContractError("Mining article must contain string url, title, and date_match_text")
    document_id = _stable_id("doc", "mining_com_search", url)
    return Candidate(
        id=_stable_id("candidate", "mining_com_search", metal, url),
        document_id=document_id,
        source_url=url,
        title=title,
        text=raw_text,
        published_at=report_date,
        collector="mining_com_search",
        kind="news",
        source="Mining.com",
        metal=metal,
        raw=dict(article),
    )


def _candidate_from_x(item: Mapping[str, Any], report_date: str) -> Candidate:
    required = ("candidate_id", "source_id", "author", "handle", "text", "url", "publish_time", "collector", "status", "report_date")
    if any(not isinstance(item.get(field), str) or not item[field].strip() for field in required):
        raise ContractError("X sidecar candidate is missing a required non-empty field")
    if item["collector"] != "x_search" or item["status"] != "ok" or item["report_date"] != report_date:
        raise ContractError("X sidecar candidate metadata is invalid")
    source_url = validate_url(item["url"], "X candidate.url")
    parsed_url = urlsplit(source_url)
    if (parsed_url.hostname or "").casefold() not in {"x.com", "twitter.com"} or re.fullmatch(r"/[^/\s]+/status/\d+/?", parsed_url.path or "") is None:
        raise ContractError("X candidate.url must be an x.com/twitter.com status URL")
    published_at = validate_datetime(item["publish_time"], "X candidate.publish_time")
    if datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(TZ_BEIJING).strftime("%Y-%m-%d") != report_date:
        raise ContractError("X candidate.publish_time does not match report_date")
    title = item.get("title") or f"{item['author']} ({item['handle']})"
    return Candidate(
        id=item["candidate_id"],
        document_id=_stable_id("doc", "x_search", source_url),
        source_url=source_url,
        title=title,
        text=item["text"],
        published_at=published_at,
        collector="x_search",
        kind="x",
        author=item["author"],
        handle=item["handle"],
        raw=dict(item),
    )


def _write_process_artifacts(run_dir: Path, stem: str, stdout: str, stderr: str) -> tuple[str, str]:
    stdout_path = run_dir / f"{stem}.stdout.txt"
    stderr_path = run_dir / f"{stem}.stderr.txt"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return str(stdout_path.relative_to(run_dir)), str(stderr_path.relative_to(run_dir))


def _run_process(command: list[str], *, cwd: Path) -> tuple[int, str, str, str | None]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr, None
    except OSError as error:
        return 127, "", "", f"{type(error).__name__}: {error}"


def _collect_mining(report_date: str, run_dir: Path, project_root: Path) -> CollectorResult:
    all_candidates: list[Candidate] = []
    seen_source_urls: set[str] = set()
    errors: list[str] = []
    artifacts: list[str] = []
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    exit_codes: list[int] = []
    for metal in METALS:
        stem = f"mining_{metal}"
        command = [sys.executable, str(project_root / "scripts" / "mining_com_search.py"), report_date, "--metal", metal]
        returncode, stdout, stderr, process_error = _run_process(command, cwd=project_root)
        stdout_artifact, stderr_artifact = _write_process_artifacts(run_dir, stem, stdout, stderr)
        artifacts.extend((stdout_artifact, stderr_artifact))
        stdout_parts.append(f"[{metal}]\\n{stdout}")
        stderr_parts.append(f"[{metal}]\\n{stderr}")
        exit_codes.append(returncode)
        if process_error:
            errors.append(f"{metal}: {process_error}")
            continue
        try:
            result = json.loads(stdout)
            if not isinstance(result, Mapping):
                raise ValueError("collector output is not an object")
            if result.get("status") != "ok" or result.get("extraction_status") not in {"success", "success_empty"}:
                raise ValueError(str(result.get("error") or "collector did not report a complete success"))
            articles = result.get("articles")
            if not isinstance(articles, list):
                raise ValueError("collector articles is not a list")
            for article in articles:
                candidate = _candidate_from_mining(article, report_date, metal)
                source_key = urldefrag(candidate.source_url)[0].rstrip("/")
                if source_key in seen_source_urls:
                    continue
                seen_source_urls.add(source_key)
                all_candidates.append(candidate)
        except (json.JSONDecodeError, ValueError, TypeError, ContractError) as error:
            errors.append(f"{metal}: invalid or failed collector result: {error}")
    status = "complete" if not errors and all(code == 0 for code in exit_codes) else "failed"
    return CollectorResult(
        collector="mining_com_search",
        status=status,
        candidates=tuple(all_candidates),
        errors=tuple(errors),
        exit_code=0 if status == "complete" else next((code for code in exit_codes if code), 1),
        stdout="".join(stdout_parts),
        stderr="".join(stderr_parts),
        artifacts=tuple(artifacts),
    )


def _collect_x(
    report_date: str,
    run_dir: Path,
    project_root: Path,
    web_access_input: str | Path | None = None,
) -> CollectorResult:
    output_path = project_root / "x_outputs" / f"{report_date}_x_raw_materials.txt"
    sidecar_path = output_path.with_suffix(".json")
    existed_before = output_path.exists() or sidecar_path.exists()
    command = [sys.executable, str(project_root / "scripts" / "x_search.py"), report_date, "--headless"]
    if web_access_input:
        command.extend(["--web-access-input", str(web_access_input)])
    returncode, stdout, stderr, process_error = _run_process(command, cwd=project_root)
    stdout_artifact, stderr_artifact = _write_process_artifacts(run_dir, "x_search", stdout, stderr)
    errors: list[str] = []
    candidates: list[Candidate] = []
    artifacts: list[str] = []
    status = "complete"
    if process_error:
        errors.append(process_error)
        status = "failed"
    elif returncode != 0:
        status = "partial" if returncode == 4 else "failed"
        errors.append(f"x_search exited with status {returncode}")
    # A pre-existing raw/sidecar pair must never be mistaken for this run's output.
    sidecar_metadata: dict[str, Any] = {}
    if not existed_before and output_path.exists() and sidecar_path.exists():
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            raw_candidates = sidecar.get("candidates") if isinstance(sidecar, Mapping) else None
            sidecar_status = sidecar.get("status") if isinstance(sidecar, Mapping) else None
            if not isinstance(sidecar, Mapping) or sidecar.get("collector") != "x_search":
                raise ValueError("X sidecar collector is invalid")
            if sidecar.get("report_date") != report_date:
                raise ValueError("X sidecar report_date does not match")
            if not isinstance(raw_candidates, list):
                raise ValueError("X sidecar candidates is not a list")
            if sidecar_status not in {"complete", "partial", "failed"}:
                raise ValueError("X sidecar status is not complete, partial, or failed")
            expected_accounts = get_x_accounts(load_registry(project_root / "data" / "source_registry.json"))
            expected_account_ids = {account["source_id"] for account in expected_accounts}
            expected_accounts_total = len(expected_accounts)
            for field in ("accounts_total", "accounts_completed", "accounts_failed"):
                if type(sidecar.get(field)) is not int or sidecar[field] < 0:
                    raise ValueError(f"X sidecar {field} is invalid")
            if sidecar["accounts_total"] != expected_accounts_total:
                raise ValueError("X sidecar accounts_total does not match source registry")
            if sidecar["accounts_completed"] + sidecar["accounts_failed"] != sidecar["accounts_total"]:
                raise ValueError("X sidecar account counts are inconsistent")
            sidecar_errors = sidecar.get("errors")
            if not isinstance(sidecar_errors, list) or len(sidecar_errors) != sidecar["accounts_failed"]:
                raise ValueError("X sidecar errors do not match failed account count")
            error_ids: set[str] = set()
            for error in sidecar_errors:
                if not isinstance(error, Mapping) or any(not isinstance(error.get(field), str) or not error[field].strip() for field in ("source_id", "handle", "author", "error")):
                    raise ValueError("X sidecar error entry is invalid")
                if error["source_id"] not in expected_account_ids or error["source_id"] in error_ids:
                    raise ValueError("X sidecar error account mapping is invalid")
                error_ids.add(error["source_id"])
            attempted_channels = sidecar.get("attempted_channels")
            channel_order = ["web_access_xai", "twscrape", "playwright"]
            if not isinstance(attempted_channels, list) or not attempted_channels or attempted_channels != channel_order[:len(attempted_channels)]:
                raise ValueError("X sidecar attempted_channels must be an ordered channel prefix")
            channel_completed_accounts = sidecar.get("channel_completed_accounts")
            if not isinstance(channel_completed_accounts, Mapping):
                raise ValueError("X sidecar channel_completed_accounts is invalid")
            if any(channel not in attempted_channels or type(count) is not int or count < 0 for channel, count in channel_completed_accounts.items()):
                raise ValueError("X sidecar channel_completed_accounts is invalid")
            if sum(channel_completed_accounts.values()) != sidecar["accounts_completed"]:
                raise ValueError("X sidecar channel completion counts do not match accounts_completed")
            selected_channel = sidecar.get("selected_channel")
            valid_selected = {None, *channel_order, "web_access_xai+twscrape", "web_access_xai+playwright", "twscrape+playwright", "web_access_xai+twscrape+playwright"}
            if selected_channel not in valid_selected:
                raise ValueError("X sidecar selected_channel is invalid")
            if selected_channel is not None:
                selected_parts = selected_channel.split("+")
                attempted_indexes = [attempted_channels.index(part) if part in attempted_channels else -1 for part in selected_parts]
                if any(index < 0 for index in attempted_indexes) or any(current <= previous for previous, current in zip(attempted_indexes, attempted_indexes[1:])):
                    raise ValueError("X sidecar selected_channel conflicts with attempted_channels")
            sidecar_metadata_raw = sidecar.get("metadata")
            if not isinstance(sidecar_metadata_raw, Mapping) or not isinstance(sidecar_metadata_raw.get("channel_errors", []), list):
                raise ValueError("X sidecar metadata is invalid")
            unavailable_channels = sidecar.get("unavailable_channels")
            if not isinstance(unavailable_channels, list) or any(
                not isinstance(item, Mapping)
                or item.get("channel") not in attempted_channels
                or not isinstance(item.get("error"), str)
                or not item["error"].strip()
                for item in unavailable_channels
            ):
                raise ValueError("X sidecar unavailable_channels is invalid")
            candidates = [_candidate_from_x(item, report_date) for item in raw_candidates]
            if any(item.get("source_id") not in expected_account_ids for item in raw_candidates):
                raise ValueError("X sidecar candidate account mapping is invalid")
            sidecar_metadata = {"part2_coverage": {
                "status": sidecar_status,
                "accounts_total": sidecar["accounts_total"],
                "accounts_completed": sidecar["accounts_completed"],
                "accounts_failed": sidecar["accounts_failed"],
                "attempted_channels": attempted_channels,
                "selected_channel": selected_channel,
                "channel_errors": sidecar_metadata_raw.get("channel_errors", []),
                "notes": [
                    f"{item.get('channel')}: {item.get('error')}"
                    for item in sidecar.get("unavailable_channels", [])
                    if isinstance(item, Mapping) and item.get("channel") and item.get("error")
                ],
            }}
            if returncode == 0 and sidecar_status != "complete":
                status = "failed"
                errors.append(f"X sidecar reported {sidecar_status} after exit 0")
            elif returncode == 4 and sidecar_status != "partial":
                status = "failed"
                errors.append(f"X sidecar reported {sidecar_status} after exit 4")
            elif returncode != 4 and returncode != 0 and sidecar_status != "failed":
                status = "failed"
            elif returncode == 0:
                status = "complete"
            elif sidecar_status in {"partial", "failed"}:
                status = sidecar_status
            artifacts.append(str(sidecar_path.relative_to(project_root)))
        except (OSError, json.JSONDecodeError, ValueError, TypeError, ContractError) as error:
            status = "failed"
            errors.append(f"invalid X sidecar: {error}")
    else:
        status = "failed"
        errors.append("X collector did not produce a new raw/structured sidecar")
    return CollectorResult(
        collector="x_search",
        status=status,
        candidates=tuple(candidates),
        errors=tuple(errors),
        exit_code=returncode,
        stdout=stdout,
        stderr=stderr,
        artifacts=tuple([stdout_artifact, stderr_artifact, *artifacts]),
        metadata=sidecar_metadata,
    )


def run_pipeline(
    report_date: str,
    *,
    dry_run: bool = False,
    collect_mining: bool = False,
    collect_x: bool = False,
    x_web_access_input: str | Path | None = None,
    project_root: str | Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Run preflight and optional collectors, returning the manifest dictionary."""
    parsed_date = parse_report_date(report_date).isoformat()
    root = Path(project_root).resolve()
    final_path = root / "data" / f"{parsed_date}.json"
    if final_path.exists():
        raise PipelineError(f"Refusing to run because final report already exists: {final_path}")
    registry_path = root / "data" / "source_registry.json"
    try:
        registry = load_registry(registry_path)
    except Exception as error:
        raise PipelineError(str(error)) from error
    started_at = datetime.now(TZ_BEIJING).replace(microsecond=0).isoformat()
    run_id = f"{parsed_date}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}"
    run_dir = root / ".runtime" / "pipeline" / parsed_date / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    windows = calculate_windows(parsed_date)
    planned = []
    if collect_mining:
        planned.append("mining_com_search")
    if collect_x:
        planned.append("x_search")
    manifest = RunManifest(
        run_id=run_id,
        started_at=started_at,
        report_date=parsed_date,
        run_dir=str(run_dir),
        windows=windows,
        status="preflight" if dry_run or not planned else "preflight",
        registry_source_ids=tuple(entry["source_id"] for entry in registry),
        collectors=tuple({"collector": name, "status": "planned"} for name in planned),
    )
    _atomic_json(run_dir / "manifest.json", manifest.to_dict())
    results: list[CollectorResult] = []
    if not dry_run:
        if collect_mining:
            results.append(_collect_mining(parsed_date, run_dir, root))
        if collect_x:
            results.append(_collect_x(parsed_date, run_dir, root, x_web_access_input))
    candidates = [candidate for result in results for candidate in result.candidates]
    candidate_ids = [candidate.id for candidate in candidates]
    document_ids = [candidate.document_id for candidate in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise PipelineError("collectors returned duplicate candidate IDs")
    _atomic_json(run_dir / "candidates.json", [candidate.to_dict() for candidate in candidates])
    if dry_run or not planned:
        overall_status = "preflight"
    elif any(result.status == "failed" for result in results):
        overall_status = "failed"
    elif any(result.status == "partial" for result in results):
        overall_status = "partial"
    else:
        overall_status = "complete"
    completed_at = datetime.now(TZ_BEIJING).replace(microsecond=0).isoformat()
    final_manifest = RunManifest(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        report_date=parsed_date,
        run_dir=str(run_dir),
        windows=windows,
        status=overall_status,
        document_ids=tuple(document_ids),
        candidate_ids=tuple(candidate_ids),
        decision_ids=(),
        collectors=tuple(result.to_dict() for result in results) if results else manifest.collectors,
        registry_source_ids=tuple(entry["source_id"] for entry in registry),
    )
    _atomic_json(run_dir / "manifest.json", final_manifest.to_dict())
    return final_manifest.to_dict()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run deterministic daily-pipeline preflight or explicit collectors")
    parser.add_argument("report_date", help="Report date in YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="preflight only; do not invoke collectors")
    parser.add_argument("--collect-mining", action="store_true")
    parser.add_argument("--collect-x", action="store_true")
    parser.add_argument("--x-web-access-input", help="external xAI web-access staging JSON")
    args = parser.parse_args(argv)
    try:
        manifest = run_pipeline(
            args.report_date,
            dry_run=args.dry_run,
            collect_mining=args.collect_mining,
            collect_x=args.collect_x,
            x_web_access_input=args.x_web_access_input,
        )
    except (PipelineError, ContractError, ValueError, FileExistsError) as error:
        parser.error(str(error))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if manifest["status"] == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

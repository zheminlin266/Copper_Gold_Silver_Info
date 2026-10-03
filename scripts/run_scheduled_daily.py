"""Run a frozen-date daily job once; verify existing reports without recollecting."""

from __future__ import annotations

import argparse
import base64
import csv
import html
from html.parser import HTMLParser
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
from datetime import date, datetime, timedelta, timezone

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.script_utils import atomic_write_json
from scripts.runtime_support import AlreadyRunning, exclusive_lock, run_logged_process

ROOT = Path(__file__).resolve().parents[1]
BEIJING = timezone(timedelta(hours=8))
REPOSITORY = "zheminlin266/Copper_Gold_Silver_Info"
SITE = "https://metals.zhemin.ltd"
TC_PATH = "data/smm_copper_concentrate_index_2026.csv"

# Socket timeouts alone do not stop a slow-drip body. Run the whole request in
# the existing supervised process tree, with an absolute remaining-time budget.
FETCH_PAGE_CODE = """
import json, sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
request = Request(sys.argv[1], headers={
    "User-Agent": "DailyReportVerifier/2.0", "Cache-Control": "no-cache"})
try:
    with urlopen(request, timeout=float(sys.argv[2])) as response:
        body = response.read(8 * 1024 * 1024 + 1)
        result = ({"oversized": True} if len(body) > 8 * 1024 * 1024
                  else {"status": response.status, "text": body.decode("utf-8")})
except HTTPError as error:
    result = {"status": error.code}
except (URLError, TimeoutError) as error:
    result = {"error": str(error)}
print(json.dumps(result))
"""


class Pending(RuntimeError):
    """Publication may converge within the bounded polling window."""


class TerminalPublicationError(RuntimeError):
    """Retrying cannot fix authentication or a completed failed CI run."""


def require_report(path: Path, report_date: str) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("date") != report_date:
        raise ValueError("Target report date does not match filename")
    audit = report.get("search_log", {})
    if audit.get("part1_searched") is not True or audit.get("part3_searched") is not True:
        raise ValueError("Part 1/3 collection is incomplete")
    if audit.get("part2_coverage", {}).get("status") not in {"complete", "partial", "failed"}:
        raise ValueError("Missing Part 2 coverage audit")
    return report


def require_workflow(runs: list[dict]) -> None:
    # Compatibility helper: the publication caller filters exact SHA/main/push first.
    if not runs:
        raise ValueError("No GitHub validation run for the report commit")
    newest = max(runs, key=lambda run: run["createdAt"])
    if newest.get("status") != "completed" or newest.get("conclusion") != "success":
        raise ValueError("Latest GitHub validation run did not complete successfully")


def workflow_ready(runs: list[dict], sha: str) -> None:
    matching = [run for run in runs if run.get("head_sha") == sha
                and run.get("head_branch") == "main" and run.get("event") == "push"]
    if not matching:
        raise Pending(f"No exact main/push validation run visible yet for {sha}")
    newest = max(matching, key=lambda run: (run.get("run_number", 0), run.get("run_attempt", 1)))
    if newest.get("status") != "completed":
        raise Pending(f"Validation is {newest.get('status')} for {sha}")
    if newest.get("conclusion") != "success":
        raise TerminalPublicationError(f"Validation failed for {sha}: {newest.get('conclusion')}")


def require_page(content: str, markers: list[str], route: str) -> None:
    decoded = html.unescape(content)
    for marker in markers:
        if marker not in decoded:
            raise ValueError(f"Production {route} is missing {marker!r}")


class Page(HTMLParser):
    def __init__(self, content: str):
        super().__init__(convert_charrefs=True)
        self.links: set[str] = set()
        self.text: list[str] = []
        self.hidden = 0
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "a":
            self.links.update(value for key, value in attrs if key == "href" and value)

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def tc_markers(csv_text: str) -> list[str]:
    rows = list(csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff"))))
    if not rows:
        raise ValueError("TC CSV has no data rows")
    latest = max(rows, key=lambda row: date.fromisoformat(row["assessment_date"].strip()))
    value = float(latest["value_usd_per_dmt"])
    if not math.isfinite(value):
        raise ValueError("TC value must be finite")
    return [latest["assessment_date"].strip(), f"{value:.2f} USD/dmt"]


def verify_pages(report: dict, csv_text: str, fetch) -> None:
    report_date = report["date"]
    daily = f"/daily/{report_date}"
    signals = [item["url"] for part in ("part1_broadcasts", "part2_x_posts", "part3_news")
               for item in report.get(part, [])]
    for route in ("/", daily, "/archive", "/historical-tc"):
        page = Page(fetch(route))
        text = " ".join(" ".join(page.text).split())
        required_links = {"/", "/archive", "/historical-tc",
                          "https://sc.macromicro.me/charts/40914/tong-ku-cun-jia-ge",
                          "https://www.metal.com/copper/201910240001"}
        if route in {"/", "/archive"}:
            required_links.add(daily)
        if route == daily:
            required_links.update(signals)
        missing = required_links - page.links
        if missing:
            raise Pending(f"Production {route} missing links: {sorted(missing)}")
        try:
            if route in {"/", daily, "/archive"}:
                require_page(text, [report_date], route)
            if route == "/":
                require_page(text, ["Historical TC", "SMM Copper Concentrate Index"], route)
            if route == "/historical-tc":
                require_page(text, ["Historical TC", "SMM Copper Concentrate Index", *tc_markers(csv_text)], route)
        except ValueError as error:
            raise Pending(str(error)) from error


def execute(arguments: list[str], log, *, capture: bool = False, timeout: float = 1800,
            heartbeat=None, env=None) -> str:
    executable = shutil.which(arguments[0], path=env.get("PATH", "") if env is not None else None)
    if not executable:
        raise FileNotFoundError(f"Required executable not found: {arguments[0]}")
    log.write("\nCOMMAND " + json.dumps(arguments, ensure_ascii=False) + "\n")
    log.flush()
    # New per-command files; no legacy logs are overwritten. The shared runner streams them.
    stamp = f"{time.time_ns()}-{os.getpid()}"
    prefix = Path(log.name).parent / stamp
    stdout_path = prefix.with_suffix(".stdout.log")
    stderr_path = prefix.with_suffix(".stderr.log")
    result = run_logged_process([executable, *arguments[1:]], cwd=ROOT,
                               stdout_path=stdout_path, stderr_path=stderr_path,
                               timeout=timeout, env=env, heartbeat=heartbeat)
    if result.timed_out:
        raise TimeoutError(f"{arguments[0]} exceeded {timeout:.1f}s (child tree cleaned up)")
    if result.returncode:
        details = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        if arguments[0] == "gh" and any(token in details.lower() for token in
                ("rate limit", "secondary rate", "http 429")):
            raise Pending(f"GitHub API throttled: {details}")
        if arguments[0] == "gh" and any(token in details.lower() for token in
                ("http 401", "http 403", "authentication", "gh auth login", "bad credentials")):
            raise TerminalPublicationError(f"GitHub authentication/permission failure: {details}")
        if arguments[0] == "gh":
            if any(token in details.lower() for token in
                   ("http 429", "http 500", "http 502", "http 503", "http 504", "timeout",
                    "connection", "could not resolve", "tls handshake", "http 404")):
                raise Pending(f"Transient GitHub API failure: {details}")
        raise RuntimeError(f"{arguments[0]} exited with code {result.returncode}: {details}")
    return stdout_path.read_text(encoding="utf-8").strip() if capture else ""


def fetch_page(url: str, log, *, timeout: float, heartbeat=None, env=None) -> str:
    response = json.loads(execute(
        [sys.executable, "-B", "-c", FETCH_PAGE_CODE, url, str(min(45, timeout))],
        log, capture=True, timeout=timeout, heartbeat=heartbeat, env=env))
    if response.get("oversized"):
        raise TerminalPublicationError("Production page exceeded the 8 MiB verification limit")
    if "error" in response:
        raise Pending(f"Production network error: {response['error']}")
    status = response.get("status")
    if status in {401, 403}:
        raise TerminalPublicationError(f"Production authentication failure: HTTP {status}")
    if status in {404, 408, 429} or isinstance(status, int) and status >= 500:
        raise Pending(f"Production temporarily unavailable: HTTP {status}")
    if status != 200 or not isinstance(response.get("text"), str):
        raise TerminalPublicationError(f"Unexpected production response: HTTP {status}")
    return response["text"]


def verify_publication(report_date: str, log, *, poll_timeout=1800, poll_interval=15,
                       command_timeout=120, heartbeat=None, env=None) -> str:
    report = require_report(ROOT / f"data/{report_date}.json", report_date)
    local_csv = (ROOT / TC_PATH).read_text(encoding="utf-8-sig")
    deadline = time.monotonic() + poll_timeout

    def remaining():
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise TimeoutError("Publication deadline expired; rerun --resume once CI/production is ready")
        return min(command_timeout, budget)

    def api(endpoint):
        return json.loads(execute(["gh", "api", f"repos/{REPOSITORY}/{endpoint}"], log,
                                  capture=True, timeout=remaining(), heartbeat=heartbeat, env=env))

    def remote_file(path, sha):
        try:
            data = api(f"contents/{path}?ref={sha}")
        except Pending as error:
            if "http 404" in str(error).lower():
                raise TerminalPublicationError(
                    f"{path} is not published on remote main. Publish via the authorized daily workflow, then --resume; wrapper never pushes or recollects."
                ) from error
            raise
        return base64.b64decode(data["content"], validate=False).decode("utf-8-sig")

    def fetch(route):
        return fetch_page(f"{SITE}{route}?scheduled_check={sha}", log,
                          timeout=remaining(), heartbeat=heartbeat, env=env)

    attempt = 0
    while True:
        remaining()
        try:
            sha = api("commits/main")["sha"]
            if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
                raise ValueError("GitHub returned invalid main SHA")
            remote = json.loads(remote_file(f"data/{report_date}.json", sha))
            if remote != report:
                raise TerminalPublicationError("Local report is not on remote main. Publish through the authorized daily workflow, then --resume; wrapper never pushes or recollects.")
            if normalize_csv(remote_file(TC_PATH, sha)) != normalize_csv(local_csv):
                raise TerminalPublicationError("Local TC CSV differs from remote main; publish/reconcile it then --resume")
            runs = api(f"actions/workflows/validate.yml/runs?head_sha={sha}&branch=main&event=push&per_page=100")
            workflow_ready(runs["workflow_runs"], sha)
            # Actions success is not evidence that Vercel is ready. Poll actual route content.
            verify_pages(report, local_csv, fetch)
            if api("commits/main")["sha"] != sha:
                raise Pending("Remote main moved during verification; rebinding checks")
            log.write(f"Verified remote main {sha}, exact push CI and production content (not deployment SHA attestation)\n")
            log.flush()
            return sha
        except (Pending, TimeoutError) as error:
            attempt += 1
            log.write(f"Publication pending ({attempt}): {error}\n")
            log.flush()
            if heartbeat:
                heartbeat({"publication_attempt": attempt, "pending": str(error)})
            # Backoff is capped and every API/process/request uses the remaining budget.
            time.sleep(min(poll_interval * min(2 ** min(attempt - 1, 3), 8), remaining()))


def normalize_csv(text: str) -> str:
    return text.lstrip("\ufeff").replace("\r\n", "\n").strip()


def load_previous_state(path: Path, report_date: str) -> dict | None:
    if not path.exists():
        return None
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(previous, dict):
            raise ValueError("state must be a JSON object")
        if previous.get("report_date") != report_date:
            raise ValueError("saved report_date does not match state filename/target")
        if previous.get("status") not in ("running", "failed", "success"):
            raise ValueError("invalid saved status")
        stages = previous.get("stages", {})
        if not isinstance(stages, dict) or any(not isinstance(entry, dict) for entry in stages.values()):
            raise ValueError("stages must contain JSON objects")
        if "ai_started" in previous and type(previous["ai_started"]) is not bool:
            raise ValueError("ai_started must be a boolean")
        # Legacy state lacks durable start evidence: uncertainty must survive later verify runs.
        previous["ai_started"] = previous.get("ai_started", True) or (
            "ai" in stages and stages["ai"].get("status") != "skipped"
        )
        return previous
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot safely load saved state {path}; preserved unchanged: {error}") from error


def positive_seconds(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0 or parsed > 86400:
        raise argparse.ArgumentTypeError("must be finite, > 0 and <= 86400 seconds")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Never invoke AI, collect, or write a report")
    parser.add_argument("--resume", action="store_true", help="Reuse an existing report; automatic AI recovery is not supported")
    parser.add_argument("--report-date", type=date.fromisoformat, help="Only with --verify-only or --resume")
    parser.add_argument("--model", help="Optional explicit installed opencode model; no default model override")
    parser.add_argument("--ai-timeout", type=positive_seconds, default=10800, help="AI whole-run seconds (minimum 3600)")
    parser.add_argument("--command-timeout", type=positive_seconds, default=1800)
    parser.add_argument("--poll-timeout", type=positive_seconds, default=1800)
    parser.add_argument("--poll-interval", type=positive_seconds, default=15)
    args = parser.parse_args(argv)
    if args.report_date and not (args.verify_only or args.resume):
        parser.error("--report-date requires --verify-only or --resume")
    if args.ai_timeout < 3600:
        parser.error("--ai-timeout must be >= 3600 (X collection budget)")
    now = datetime.now(BEIJING)  # Freeze once, including across midnight and all recovery/checks.
    report_date = str(args.report_date or (now.date() - timedelta(days=1)))
    directory = ROOT / ".runtime" / "scheduled"
    directory.mkdir(parents=True, exist_ok=True)
    lock = ROOT / ".runtime" / "locks" / "scheduled-daily.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    state_path = directory / f"{report_date}.state.json"
    try:
        with exclusive_lock(lock):
            previous = load_previous_state(state_path, report_date)
            name = now.strftime("%Y%m%dT%H%M%S%f") + f"-{os.getpid()}"
            run_dir = directory / "runs" / name
            run_dir.mkdir(parents=True)
            state = {"run_date": str(now.date()), "report_date": report_date,
                     "started_at": now.isoformat(), "status": "running", "stages": {},
                     "verify_only": args.verify_only, "resume": args.resume,
                     "ai_started": previous["ai_started"] if previous is not None else False,
                     "run_log": str(run_dir / "wrapper.log"), "previous_status": previous and previous.get("status")}

            def persist():
                atomic_write_json(state_path, state)

            def heartbeat(info):
                state["heartbeat"] = {"at": datetime.now(BEIJING).isoformat(), **info}
                persist()

            env = os.environ.copy()
            env.pop("NODE_OPTIONS", None)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PATH"] = os.pathsep.join([
                str(Path.home() / "AppData/Roaming/npm"), r"C:\Program Files\nodejs",
                r"C:\Program Files\Git\cmd", r"C:\Program Files\GitHub CLI", env.get("PATH", "")])
            persist()
            with (run_dir / "wrapper.log").open("a", encoding="utf-8") as log:
                def stage(label, action):
                    entry = state["stages"][label] = {"status": "running", "started_at": datetime.now(BEIJING).isoformat()}
                    if label == "ai":
                        # Persist with the stage transition BEFORE invocation. A crash after this
                        # point needs offline recovery even if the child had not yet spawned.
                        state["ai_started"] = True
                    persist()
                    try:
                        result = action()
                        entry["status"] = "success"
                        return result
                    except BaseException as error:
                        entry.update(status="failed", error=str(error) or type(error).__name__)
                        raise
                    finally:
                        entry["completed_at"] = datetime.now(BEIJING).isoformat()
                        persist()

                try:
                    target = ROOT / f"data/{report_date}.json"
                    if target.exists():
                        state["stages"]["ai"] = {"status": "skipped", "started_at": now.isoformat(),
                                                  "completed_at": datetime.now(BEIJING).isoformat(),
                                                  "reason": "Target report exists; no collection or AI"}
                        persist()
                    elif args.verify_only or args.resume or state["ai_started"]:
                        raise RuntimeError("Target report unavailable; refusing automatic AI retry/collection. Recover artifacts offline and supply the completed report via the authorized workflow, then --resume. --resume currently requires a report; --verify-only never creates one.")
                    else:
                        prompt = (
                            f"RUN_DATE={now.date()}, REPORT_DATE={report_date}, Asia/Shanghai. "
                            "Read Daily_Report_Workflow.md first and attached Daily_Task_Prompt.md fully. "
                            "Execute the authorized daily workflow, including first publication. Preserve and exclude "
                            "unrelated working-tree changes. Freeze these dates if crossing midnight. Do not edit "
                            "the scheduler entry script. On a blocker report failure explicitly."
                        )
                        command = ["opencode.cmd", "run", "--auto"]
                        if args.model:
                            command.extend(["--model", args.model])
                        command.extend(["--file", str(ROOT / "Daily_Task_Prompt.md"), prompt])
                        stage("ai", lambda: execute(command, log, timeout=args.ai_timeout, heartbeat=heartbeat, env=env))
                    stage("report", lambda: require_report(target, report_date))
                    checks = [
                        ("validate:content", ["npm.cmd", "run", "validate:content"]),
                        ("typecheck", ["npm.cmd", "run", "typecheck"]),
                        ("python-tests", [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]),
                        ("npm-test", ["npm.cmd", "test"]),
                        ("build", ["npm.cmd", "run", "build"]),
                    ]
                    for label, command in checks:
                        stage(label, lambda command=command: execute(command, log, timeout=args.command_timeout, heartbeat=heartbeat, env=env))
                    state["verified_main_sha"] = stage("publication", lambda: verify_publication(
                        report_date, log, poll_timeout=args.poll_timeout, poll_interval=args.poll_interval,
                        command_timeout=min(120, args.command_timeout), heartbeat=heartbeat, env=env))
                    state["production_evidence"] = "route content only; deployment SHA not attested"
                    state["status"] = "success"
                    result = 0
                except BaseException as error:
                    state.update(status="failed", error=str(error) or type(error).__name__)
                    log.write(f"\nFAILED: {state['error']}\n")
                    result = 1
                finally:
                    state["completed_at"] = datetime.now(BEIJING).isoformat()
                    persist()
            print(f"{state['status']}: {state_path}")
            return result
    except AlreadyRunning:
        print("Another scheduled wrapper is running (global lock); no AI or checks started", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"Scheduled wrapper failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Collect, publish and verify one completed Beijing report week."""

from __future__ import annotations

import argparse
import base64
from datetime import date, datetime, time, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from time import monotonic, sleep

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_scheduled_daily import (
    BEIJING, ROOT, REPOSITORY, SITE, TC_PATH, Page, Pending, TerminalPublicationError,
    codex_command, execute, fetch_page, normalize_csv, positive_seconds, scheduled_environment,
    tc_markers, workflow_ready,
)
from scripts.runtime_support import AlreadyRunning, exclusive_lock
from scripts.script_utils import atomic_write_json, atomic_write_text
from scripts.weekly_tc import tc_rows, update_tc

WEEKLY_DATA = Path("data/weekly")
WEEKLY_PROMPT = "Weekly_Task_Prompt.md"


def write_state(path: Path, state: dict) -> None:
    for attempt in range(4):
        try:
            atomic_write_json(path, state)
            return
        except PermissionError as error:
            # A Windows reader can briefly block replacement of the status file.
            if getattr(error, "winerror", None) not in (5, 32) or attempt == 3:
                raise
            sleep(0.25 * (attempt + 1))


def week_for_run(now: datetime) -> date:
    local = now.astimezone(BEIJING)
    monday = local.date() - timedelta(days=local.weekday())
    if local < datetime.combine(monday, time(8), BEIJING):
        monday -= timedelta(days=7)
    return monday - timedelta(days=7)


def require_clean_scope(git, allowed: set[str]) -> None:
    changes = set(git("diff", "--name-only").splitlines())
    changes.update(git("diff", "--cached", "--name-only").splitlines())
    changes.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    if unexpected := changes - allowed:
        raise ValueError(f"Unexpected working-tree changes: {sorted(unexpected)}")


def sync_checkout(git, report_path: str) -> str:
    if git("rev-parse", "--abbrev-ref", "HEAD") != "HEAD":
        raise ValueError("Weekly publication requires the dedicated detached checkout")
    if git("config", "--get", "remote.origin.url") not in (
        f"https://github.com/{REPOSITORY}", f"https://github.com/{REPOSITORY}.git",
    ):
        raise ValueError("The checkout has an unexpected origin")
    allowed = {report_path, TC_PATH}
    require_clean_scope(git, allowed)
    git("fetch", "origin", "refs/heads/main:refs/remotes/origin/main")
    base = git("rev-parse", "origin/main")
    ahead = int(git("rev-list", "--count", "origin/main..HEAD"))
    if ahead:
        changed = set(git("diff", "--name-only", "origin/main", "HEAD").splitlines())
        if ahead != 1 or git("rev-parse", "HEAD^") != base or report_path not in changed or changed - allowed:
            raise ValueError("Unexpected or diverged local commit. Inspect the pending weekly publication.")
        require_clean_scope(git, set())
    else:
        git("merge", "--ff-only", "origin/main")
    return base


def verify_pages(report: dict, latest: str, legacy_date: str, tc_text: str, fetch) -> None:
    weekly = f"/weekly/{report['week_start']}"
    daily = f"/daily/{legacy_date}"
    sections = ["铜矿重要事实", "综合供给影响", "黄金简讯"]
    sources = {
        source["url"]
        for fact in (*report["copper_events"], *report["gold_briefs"])
        for source in fact["sources"]
    }
    checks = [
        ("/", [latest, *sections], {f"/weekly/{latest}", "/archive"}),
        (weekly, [report["week_start"], report["week_end"], *sections], sources),
        ("/archive", ["历期周报", "历史日报"], {weekly, daily}),
        (daily, ["矿业供需信号"], {"/archive"}),
        ("/historical-tc", ["Historical TC", *tc_markers(tc_text)], set()),
    ]
    for route, markers, links in checks:
        page = Page(fetch(route))
        rendered = " ".join(" ".join(page.text).split())
        missing = [marker for marker in markers if marker not in rendered]
        if missing or links - page.links:
            raise Pending(f"Production {route} is missing text {missing} or links {sorted(links - page.links)}")


def verify_publication(report: dict, log, *, heartbeat, env, poll_timeout: float) -> str:
    deadline = monotonic() + poll_timeout
    local_tc = (ROOT / TC_PATH).read_text(encoding="utf-8-sig")
    report_path = f"{WEEKLY_DATA.as_posix()}/{report['week_start']}.json"
    latest = max(path.stem for path in (ROOT / WEEKLY_DATA).glob("????-??-??.json"))
    legacy = max(path.stem for path in (ROOT / "data").glob("????-??-??.json"))
    def remaining() -> float:
        budget = deadline - monotonic()
        if budget <= 0:
            raise TimeoutError("Weekly publication verification expired. Resume verification of the same week.")
        return min(budget, 120)

    def api(endpoint):
        return json.loads(execute(
            ["gh", "api", f"repos/{REPOSITORY}/{endpoint}"], log,
            capture=True, heartbeat=heartbeat, timeout=remaining(), env=env,
        ))

    while True:
        remaining()
        try:
            sha = api("commits/main")["sha"]
            if not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise ValueError("GitHub returned an invalid main SHA")
            remote = api(f"contents/{report_path}?ref={sha}")
            if json.loads(base64.b64decode(remote["content"])) != report:
                raise TerminalPublicationError("Remote main does not contain this weekly report")
            tc = api(f"contents/{TC_PATH}?ref={sha}")
            if normalize_csv(base64.b64decode(tc["content"]).decode("utf-8-sig")) != normalize_csv(local_tc):
                raise TerminalPublicationError("Remote TC CSV differs from the checked-out TC CSV")
            runs = api(f"actions/workflows/validate.yml/runs?head_sha={sha}&branch=main&event=push")
            workflow_ready(runs["workflow_runs"], sha)
            verify_pages(
                report, latest, legacy, local_tc,
                lambda route: fetch_page(
                    f"{SITE}{route}?weekly_check={sha}", log, timeout=remaining(), heartbeat=heartbeat, env=env,
                ),
            )
            if api("commits/main")["sha"] != sha:
                raise Pending("Remote main advanced during verification")
            return sha
        except (Pending, TimeoutError) as error:
            log.write(f"Publication pending: {error}\n")
            log.flush()
            heartbeat({"pending": str(error)})
            sleep(min(15, remaining()))


def prepare_report(draft: dict, target: Path, week_start: date, command, run_dir: Path) -> tuple[dict, str]:
    if not isinstance(draft, dict) or draft.keys() != {"report", "tc", "tc_note"}:
        raise ValueError("The research draft must contain report, tc and tc_note")
    if not isinstance(draft["tc_note"], str) or not draft["tc_note"].strip():
        raise ValueError("The TC outcome requires a note")
    if not isinstance(draft["report"], dict):
        raise ValueError("The research draft report must be an object")
    report = {**draft["report"], "generated_at": datetime.now(BEIJING).isoformat(timespec="seconds")}
    staged = run_dir / target.name
    atomic_write_json(staged, report, overwrite=False)
    command(["node", "scripts/validate-content.mjs", "--weekly", str(staged)])
    tc_path = ROOT / TC_PATH
    original_tc = tc_path.read_bytes().decode("utf-8")
    tc, status = update_tc(original_tc, draft["tc"], week_start)
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if {**existing, "generated_at": report["generated_at"]} != report:
            raise ValueError("The existing weekly report differs from its draft")
        report = existing
    else:
        atomic_write_json(target, report, overwrite=False)
    if status == "updated":
        atomic_write_text(tc_path, tc, overwrite=True)
    return report, status


def publish(git, command, base: str, report_path: str, week: date, tc_observation) -> None:
    tc_path = ROOT / TC_PATH
    original = git("show", f"{base}:{TC_PATH}")
    expected, status = update_tc(original, tc_observation, week)
    if tc_rows(tc_path.read_text(encoding="utf-8-sig")) != tc_rows(expected):
        raise ValueError("The TC CSV differs from the authorized single-row append")
    paths = [report_path]
    if status == "updated":
        paths.append(TC_PATH)
    require_clean_scope(git, set(paths))
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    npm = "npm.cmd" if os.name == "nt" else "npm"
    command([npm, "run", "typecheck"])
    command([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])
    command([npm, "test"])
    command([npm, "run", "build"])  # prebuild validates all content.
    require_clean_scope(git, set(paths))
    if any((ROOT / name).read_bytes() != expected for name, expected in inputs.items()):
        raise ValueError("A weekly publication input changed during validation")
    if git("rev-parse", "HEAD") == base:
        git("add", "--", *paths)
        if set(git("diff", "--cached", "--name-only").splitlines()) != set(paths):
            raise ValueError("Staged files differ from the weekly publication scope")
        git("commit", "-m", f"Add {week} copper supply weekly report")
    if set(git("diff", "--name-only", base, "HEAD").splitlines()) != set(paths):
        raise ValueError("The weekly commit contains unexpected files")
    require_clean_scope(git, set())
    git("push", "origin", "HEAD:refs/heads/main")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="Show the frozen collection window")
    modes.add_argument("--verify-only", action="store_true", help="Check a published week without collecting or pushing")
    parser.add_argument("--week-start", type=date.fromisoformat, help="Monday of a completed report week")
    parser.add_argument("--codex-sandbox", choices=("workspace-write", "danger-full-access"), default="workspace-write")
    parser.add_argument("--poll-timeout", type=positive_seconds, default=1800)
    args = parser.parse_args(argv)
    now = datetime.now(BEIJING)
    week = args.week_start or week_for_run(now)
    week_end = week + timedelta(days=6)
    if week.weekday() != 0 or week_end >= now.date():
        parser.error("week-start must be a Monday of a completed Beijing report week")
    report_path = (WEEKLY_DATA / f"{week}.json").as_posix()
    window = {"week_start": str(week), "week_end": str(week_end), "timezone": "Asia/Shanghai"}
    if args.dry_run:
        print(json.dumps({**window, "target": report_path}))
        return 0

    lock = ROOT / ".runtime/locks/scheduled-weekly.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    target = ROOT / report_path
    week_dir = ROOT / ".runtime/weekly" / str(week)
    try:
        with exclusive_lock(lock):
            run_dir = week_dir / f"{now:%Y%m%dT%H%M%S%f}-{os.getpid()}"
            run_dir.mkdir(parents=True)
            state_file = week_dir / "state.json"
            state = {**window, "status": "running", "started_at": now.isoformat(), "run_dir": str(run_dir)}

            def heartbeat(info):
                state["heartbeat"] = {"at": datetime.now(BEIJING).isoformat(), **info}
                write_state(state_file, state)

            heartbeat({})
            env = scheduled_environment()
            with (run_dir / "wrapper.log").open("w", encoding="utf-8") as log:
                def command(arguments, timeout=1800):
                    return execute(arguments, log, capture=True, timeout=timeout, heartbeat=heartbeat, env=env)

                def git(*arguments):
                    return command(["git", *arguments])

                try:
                    if not args.verify_only:
                        base = sync_checkout(git, report_path)
                        if not git("ls-tree", "--name-only", base, "--", report_path):
                            draft_path = week_dir / "draft.json"
                            if not draft_path.is_file():
                                require_clean_scope(git, set())
                                if target.exists():
                                    raise ValueError("An existing weekly report has no matching saved draft")
                                snapshot = run_dir / WEEKLY_PROMPT
                                snapshot.write_bytes((ROOT / WEEKLY_PROMPT).read_bytes())
                                state["prompt_sha256"] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
                                # A partially written draft remains in the attempt directory after failure.
                                attempt = run_dir / "draft.json"
                                prompt = (
                                    f"Use Beijing week {week} through {week_end}. Read {snapshot} as UTF-8. "
                                    f"Write only the researched JSON draft to {attempt}. Do not publish."
                                )
                                ai_command = codex_command(prompt, run_dir, sandbox_mode=args.codex_sandbox)
                                if "--add-dir" in ai_command:
                                    git_access = ai_command.index("--add-dir")
                                    del ai_command[git_access:git_access + 2]  # The child only needs the draft directory.
                                command(ai_command, timeout=10800)
                                require_clean_scope(git, set())
                                atomic_write_json(draft_path, json.loads(attempt.read_text(encoding="utf-8-sig")),
                                                  overwrite=False)
                            draft = json.loads(draft_path.read_text(encoding="utf-8"))
                            _, state["tc_status"] = prepare_report(draft, target, week, command, run_dir)
                            state["tc_note"] = draft["tc_note"]
                            heartbeat({})
                            publish(git, command, base, report_path, week, draft["tc"])
                    command(["node", "scripts/validate-content.mjs", "--weekly", str(target)])
                    report = json.loads(target.read_text(encoding="utf-8"))
                    state["tc_status"] = state.get("tc_status", update_tc(
                        (ROOT / TC_PATH).read_text(encoding="utf-8-sig"), None, week,
                    )[1])
                    report_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                    tc_hash = hashlib.sha256((ROOT / TC_PATH).read_bytes()).hexdigest()
                    sha = verify_publication(report, log, heartbeat=heartbeat, env=env, poll_timeout=args.poll_timeout)
                    if (report_hash != hashlib.sha256(target.read_bytes()).hexdigest()
                            or tc_hash != hashlib.sha256((ROOT / TC_PATH).read_bytes()).hexdigest()):
                        raise ValueError("Report or TC data changed during verification")
                    state.update(status="success", verified_main_sha=sha, report_sha256=report_hash, tc_sha256=tc_hash)
                    print(json.dumps(state, ensure_ascii=False))
                    return 0
                except Exception as error:
                    state.update(status="failed", error=str(error))
                    print(str(error), file=sys.stderr)
                    return 1
                finally:
                    state["finished_at"] = datetime.now(BEIJING).isoformat()
                    write_state(state_file, state)
    except (AlreadyRunning, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

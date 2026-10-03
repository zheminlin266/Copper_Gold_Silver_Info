"""Wrapper checks: no AI, X or external network; HTTP regressions use localhost."""
import base64
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
from threading import Event, Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_scheduled_daily as daily

DATE = "2026-09-29"
SHA = "a" * 40
CSV = ("assessment_date,value_usd_per_dmt,change_usd_per_dmt,source_url,source_note\n"
       "2026-09-28,-42.3,0,https://example.com,older\n"
       "2026-09-29,-40.5,1.8,https://example.com,latest\n")
REPORT = {"date": DATE, "search_log": {"part1_searched": True, "part3_searched": True,
          "part2_coverage": {"status": "partial"}}, "part1_broadcasts": [],
          "part2_x_posts": [], "part3_news": [{"url": "https://example.com/?a=1&b=2"}]}


def run(status="completed", conclusion="success", sha=SHA):
    return {"head_sha": sha, "head_branch": "main", "event": "push", "run_number": 1,
            "status": status, "conclusion": conclusion}


def pages(route):
    links = ["/", "/archive", "/historical-tc", f"/daily/{DATE}",
             "https://example.com/?a=1&amp;b=2", "https://sc.macromicro.me/charts/40914/tong-ku-cun-jia-ge",
             "https://www.metal.com/copper/201910240001"]
    return ("".join(f'<a href="{link}">link</a>' for link in links)
            + f"<p>{DATE} Historical TC SMM Copper Concentrate Index -40.50 USD/dmt</p>")


class ScheduledDailyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        (self.root / daily.TC_PATH).write_text(CSV, encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.object(daily, "ROOT", self.root).start()

    def report(self):
        path = self.root / f"data/{DATE}.json"
        path.write_text(json.dumps(REPORT), encoding="utf-8")
        return path

    def state(self):
        return json.loads((self.root / f".runtime/scheduled/{DATE}.state.json").read_text())

    def main_mocks(self):
        execute = patch.object(daily, "execute", return_value="").start()
        publication = patch.object(daily, "verify_publication", return_value=SHA).start()
        patch("builtins.print").start()
        return execute, publication

    def test_process_success_without_report_is_not_success(self):
        with self.assertRaises(FileNotFoundError):
            daily.require_report(self.root / "missing.json", DATE)
        path = self.report()
        self.assertEqual(daily.require_report(path, DATE), REPORT)
        with self.assertRaises(ValueError):
            daily.require_report(path, "2026-09-28")
        bad = json.loads(json.dumps(REPORT))
        bad["search_log"]["part3_searched"] = False
        path.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):
            daily.require_report(path, DATE)

    def test_latest_workflow_must_pass(self):
        old = {"createdAt": "2026-09-29", "status": "completed", "conclusion": "success"}
        daily.require_workflow([old])
        for runs in ([], [old, {"createdAt": "2026-09-30", "status": "in_progress"}]):
            with self.assertRaises(ValueError):
                daily.require_workflow(runs)

    def test_http_success_with_stale_page_is_not_success(self):
        daily.require_page('href="https://example.com/?a=1&amp;b=2"',
                           ["https://example.com/?a=1&b=2"], "/daily")
        with self.assertRaises(ValueError):
            daily.require_page("2026-09-28", [DATE], "/")

    def test_existing_report_never_ai_and_checks_rerun(self):
        self.report()
        execute, publication = self.main_mocks()
        for args in (["--resume", "--report-date", DATE], ["--verify-only", "--report-date", DATE]):
            self.assertEqual(daily.main(args), 0)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertFalse(any("opencode" in command[0] for command in commands))
        self.assertEqual(len(commands), 10)
        with patch.object(daily, "datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 30, tzinfo=daily.BEIJING)
            self.assertEqual(daily.main([]), 0)
        self.assertFalse(any("opencode" in call.args[0][0] for call in execute.call_args_list))
        self.assertIn([daily.sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], commands)
        self.assertEqual(publication.call_count, 3)
        self.assertEqual(self.state()["status"], "success")
        self.assertEqual(self.state()["verified_main_sha"], SHA)
        self.assertEqual(self.state()["verified_report_sha256"], hashlib.sha256((self.root / f"data/{DATE}.json").read_bytes()).hexdigest())
        self.assertEqual(self.state()["verified_tc_sha256"], hashlib.sha256((self.root / daily.TC_PATH).read_bytes()).hexdigest())

    def test_inputs_changed_during_verification_cannot_be_success(self):
        for relative in (f"data/{DATE}.json", daily.TC_PATH):
            with self.subTest(path=relative):
                self.report()
                execute, publication = self.main_mocks()
                target = self.root / relative
                def change(*args, **kwargs):
                    target.write_bytes(target.read_bytes() + b"\n")
                    return SHA
                publication.side_effect = change
                self.assertEqual(daily.main(["--verify-only", "--report-date", DATE]), 1)
                self.assertEqual(self.state()["status"], "failed")
                self.assertIn("changed during verification", self.state()["error"])
                self.assertNotIn("verified_report_sha256", self.state())

    def test_date_boundary_is_frozen_and_optional_model(self):
        execute, publication = self.main_mocks()
        # 16:01 UTC is the next BJT calendar day: report should still be Sept 29.
        frozen = datetime(2026, 9, 29, 16, 1, tzinfo=timezone.utc).astimezone(daily.BEIJING)
        clock = patch.object(daily, "datetime").start()
        clock.now.side_effect = [frozen] + [datetime(2026, 10, 1, tzinfo=daily.BEIJING)] * 50
        def command(args, log, **kwargs):
            if args[0] == "opencode.cmd":
                self.report()
                self.assertEqual(kwargs["timeout"], 10800)
                self.assertIn("RUN_DATE=2026-09-30, REPORT_DATE=2026-09-29", args[-1])
                self.assertIn("--model", args)
        execute.side_effect = command
        self.assertEqual(daily.main(["--model", "installed/model"]), 0)
        self.assertEqual(self.state()["run_date"], "2026-09-30")
        self.assertEqual(publication.call_args.args[0], DATE)

    def test_interrupted_state_refuses_ai_relaunch(self):
        directory = self.root / ".runtime/scheduled"
        directory.mkdir(parents=True)
        (directory / f"{DATE}.state.json").write_text(json.dumps({
            "report_date": DATE, "status": "running", "stages": {"ai": {"status": "running"}}
        }))
        execute, publication = self.main_mocks()
        with patch.object(daily, "datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 30, tzinfo=daily.BEIJING)
            self.assertEqual(daily.main([]), 1)
        self.assertEqual(daily.main(["--resume", "--report-date", DATE]), 1)
        execute.assert_not_called()
        publication.assert_not_called()
        self.assertIn("refusing automatic AI", self.state()["error"])

    def test_verify_only_missing_report_does_not_create_it(self):
        execute, _ = self.main_mocks()
        self.assertEqual(daily.main(["--verify-only", "--report-date", DATE]), 1)
        self.assertFalse((self.root / f"data/{DATE}.json").exists())
        execute.assert_not_called()

    def test_verify_failure_and_pre_ai_crash_allow_first_start(self):
        execute, _ = self.main_mocks()
        self.assertEqual(daily.main(["--verify-only", "--report-date", DATE]), 1)
        self.assertFalse(self.state()["ai_started"])
        path = self.root / f".runtime/scheduled/{DATE}.state.json"
        cases = [self.state(), {"report_date": DATE, "status": "running",
                               "ai_started": False, "stages": {}}]
        for index, previous in enumerate(cases):
            with self.subTest(previous=previous):
                path.write_text(json.dumps(previous))
                def command(args, log, **kwargs):
                    if args[0] == "opencode.cmd":
                        saved = self.state()
                        self.assertTrue(saved["ai_started"])
                        self.assertEqual(saved["stages"]["ai"]["status"], "running")
                        self.report()
                execute.side_effect = command
                with patch.object(daily, "datetime") as clock:
                    clock.now.return_value = datetime(2026, 9, 30, hour=index, tzinfo=daily.BEIJING)
                    self.assertEqual(daily.main([]), 0)
                self.assertTrue(self.state()["ai_started"])
                (self.root / f"data/{DATE}.json").unlink()

    def test_ai_started_and_legacy_uncertainty_survive_verify(self):
        execute, _ = self.main_mocks()
        path = self.root / f".runtime/scheduled/{DATE}.state.json"
        path.parent.mkdir(parents=True)
        cases = [
            {"ai_started": True, "stages": {}},
            {"stages": {}},  # Legacy running state: start cannot be disproven.
            {"ai_started": False, "stages": {"ai": {"status": "running"}}},
        ]
        for index, extra in enumerate(cases):
            with self.subTest(extra=extra):
                path.write_text(json.dumps({"report_date": DATE, "status": "running", **extra}))
                self.assertEqual(daily.main(["--verify-only", "--report-date", DATE]), 1)
                self.assertTrue(self.state()["ai_started"])
                with patch.object(daily, "datetime") as clock:
                    clock.now.return_value = datetime(2026, 9, 30, hour=index, tzinfo=daily.BEIJING)
                    self.assertEqual(daily.main([]), 1)
                self.assertIn("refusing automatic AI", self.state()["error"])
                self.assertTrue(self.state()["ai_started"])
        execute.assert_not_called()

    def test_corrupt_saved_state_preserved_and_fails_closed(self):
        execute, publication = self.main_mocks()
        path = self.root / f".runtime/scheduled/{DATE}.state.json"
        path.parent.mkdir(parents=True)
        cases = ["{broken", "null", "[]", '"text"',
                 json.dumps({"report_date": "2026-09-28", "status": "running"}),
                 json.dumps({"report_date": DATE, "status": [], "stages": {}}),
                 json.dumps({"report_date": DATE, "status": "running", "stages": []}),
                 json.dumps({"report_date": DATE, "status": "running", "ai_started": "false"})]
        for content in cases:
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                with patch.object(daily, "datetime") as clock, patch("builtins.print") as printing:
                    clock.now.return_value = datetime(2026, 9, 30, tzinfo=daily.BEIJING)
                    self.assertEqual(daily.main([]), 1)
                    self.assertIn("preserved unchanged", printing.call_args.args[0])
                self.assertEqual(path.read_text(encoding="utf-8"), content)
        execute.assert_not_called()
        publication.assert_not_called()

    def test_duplicate_wrapper_lock_and_failed_stage_persist(self):
        self.report()
        execute, publication = self.main_mocks()
        @contextmanager
        def locked(path):
            self.assertEqual(path, self.root / ".runtime/locks/scheduled-daily.lock")
            raise daily.AlreadyRunning("busy")
            yield
        with patch.object(daily, "exclusive_lock", locked):
            self.assertEqual(daily.main(["--verify-only", "--report-date", DATE]), 2)
        execute.assert_not_called()
        execute.side_effect = RuntimeError("check failed")
        self.assertEqual(daily.main(["--verify-only", "--report-date", DATE]), 1)
        state = self.state()
        self.assertEqual(state["stages"]["validate:content"]["status"], "failed")
        self.assertIn("completed_at", state["stages"]["validate:content"])
        self.assertEqual(state["error"], "check failed")
        publication.assert_not_called()
        self.assertTrue((self.root / ".runtime/locks/scheduled-daily.lock").exists())

    def test_heartbeat_is_persisted(self):
        self.report()
        execute, _ = self.main_mocks()
        execute.side_effect = lambda *args, **kwargs: kwargs["heartbeat"]({"pid": 123, "elapsed_seconds": 15})
        self.assertEqual(daily.main(["--verify-only", "--report-date", DATE]), 0)
        self.assertEqual(self.state()["heartbeat"]["pid"], 123)

    def publication_api(self, sequences=None):
        sequences = iter(sequences or [[run()]])
        def execute(command, log, **kwargs):
            self.assertGreater(kwargs["timeout"], 0)
            endpoint = command[-1]
            if endpoint.endswith("commits/main"):
                return json.dumps({"sha": SHA})
            if "actions/workflows" in endpoint:
                self.assertIn(f"head_sha={SHA}&branch=main&event=push", endpoint)
                return json.dumps({"workflow_runs": next(sequences, [run()])})
            text = json.dumps(REPORT) if f"{DATE}.json" in endpoint else CSV
            self.assertIn(f"?ref={SHA}", endpoint)
            return json.dumps({"content": base64.b64encode(text.encode()).decode()})
        return execute

    def publication(self, api=None, page=None, timeout=30):
        self.report()
        with patch.object(daily, "execute", side_effect=api or self.publication_api()), \
             patch.object(daily, "fetch_page", side_effect=lambda url, *args, **kwargs: (page or pages)(url)), \
             patch.object(daily.time, "sleep"):
            return daily.verify_publication(DATE, io.StringIO(), poll_timeout=timeout, poll_interval=.01)

    def test_ci_pending_wrong_sha_then_success(self):
        self.assertEqual(self.publication(self.publication_api([[], [run(sha="b" * 40)],
                         [run(status="queued")], [run(status="in_progress")], [run()]])), SHA)

    def test_terminal_ci_failure(self):
        with self.assertRaises(daily.TerminalPublicationError):
            self.publication(self.publication_api([[run(conclusion="failure")]]))
        with self.assertRaises(daily.Pending):
            daily.workflow_ready([dict(run(), event="pull_request")], SHA)

    def test_stale_production_then_ready_and_tc_markers(self):
        contents = iter(["old report", pages("/")])
        def fetch_page(route):
            return next(contents, pages(route))
        self.assertEqual(self.publication(page=fetch_page), SHA)
        self.assertEqual(daily.tc_markers(CSV), [DATE, "-40.50 USD/dmt"])
        for content in (pages("/").replace("-40.50", "-42.30"),
                        pages("/").replace("USD/dmt", "USD/lb")):
            with self.assertRaises(daily.Pending):
                daily.verify_pages(REPORT, CSV, lambda route: content)
        # Dates/URLs embedded only in scripts cannot substitute for visible content/links.
        with self.assertRaises(daily.Pending):
            daily.verify_pages(REPORT, CSV, lambda route: '<script>' + pages(route) + '</script>')

    def test_transient_api_error_vs_auth(self):
        real = self.publication_api()
        calls = 0
        def transient(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise daily.Pending("HTTP 503")
            return real(*args, **kwargs)
        self.assertEqual(self.publication(api=transient), SHA)
        with self.assertRaises(daily.TerminalPublicationError):
            self.publication(api=lambda *args, **kwargs: (_ for _ in ()).throw(daily.TerminalPublicationError("HTTP 401")))

    def test_http_transient_vs_auth(self):
        self.report()
        with patch.object(daily, "execute", side_effect=self.publication_api()), \
             patch.object(daily, "fetch_page", side_effect=[daily.Pending("temporary"), *[pages("/")] * 4]), \
             patch.object(daily.time, "sleep"):
            self.assertEqual(daily.verify_publication(DATE, io.StringIO()), SHA)
        for response, expected in [
            ({"error": "temporary"}, daily.Pending),
            ({"status": 503}, daily.Pending), ({"status": 429}, daily.Pending),
            ({"status": 403}, daily.TerminalPublicationError),
            ({"oversized": True}, daily.TerminalPublicationError),
        ]:
            with self.subTest(response=response), patch.object(daily, "execute", return_value=json.dumps(response)) as command:
                with self.assertRaises(expected):
                    daily.fetch_page(daily.SITE, io.StringIO(), timeout=.25)
                self.assertEqual(command.call_args.kwargs["timeout"], .25)
                self.assertEqual(command.call_args.args[0][-1], "0.25")

    def test_real_http_slow_drip_respects_publication_deadline(self):
        self.report()
        stop = Event()
        requested = Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = pages("/").encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body) if self.path == "/ok" else 1000000))
                self.end_headers()
                try:
                    if self.path == "/ok":
                        self.wfile.write(body)
                        return
                    requested.set()
                    while not stop.wait(.01):
                        self.wfile.write(b"drip")
                        self.wfile.flush()
                except OSError:
                    pass  # The supervised reader must disconnect on deadline.
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        site = f"http://127.0.0.1:{server.server_port}"
        real_execute = daily.execute
        api = self.publication_api()
        def dispatch(command, *args, **kwargs):
            return (api if command[0] == "gh" else real_execute)(command, *args, **kwargs)
        try:
            with (self.root / "http.log").open("w", encoding="utf-8") as log:
                self.assertEqual(daily.fetch_page(site + "/ok", log, timeout=5), pages("/"))
                with patch.object(daily, "SITE", site), patch.object(daily, "execute", side_effect=dispatch):
                    start = time.monotonic()
                    with self.assertRaises(TimeoutError):
                        daily.verify_publication(DATE, log, poll_timeout=1, poll_interval=.01)
                    self.assertLess(time.monotonic() - start, 4)
                    self.assertTrue(requested.is_set(), "Test must reach the slow-drip body")
        finally:
            stop.set()
            server.shutdown()
            thread.join(2)
            server.server_close()

    def test_bounded_timeout_and_flag_validation(self):
        self.report()
        with patch.object(daily, "execute", side_effect=daily.Pending("not yet")), \
             patch.object(daily.time, "monotonic", side_effect=[0, 0, 0, 2]), \
             patch.object(daily.time, "sleep") as sleeping:
            with self.assertRaises(TimeoutError):
                daily.verify_publication(DATE, io.StringIO(), poll_timeout=1)
            sleeping.assert_not_called()
        for value in ("nan", "inf", "0", "-1", "86401"):
            with self.assertRaises(daily.argparse.ArgumentTypeError):
                daily.positive_seconds(value)
        with patch("sys.stderr", io.StringIO()):
            for args in (["--report-date", DATE], ["--ai-timeout", "3599"], ["--poll-interval", "nan"]):
                with self.assertRaises(SystemExit):
                    daily.main(args)

    def test_execute_discovers_tools_using_child_environment_path(self):
        env = {"PATH": "scheduler-tools"}
        with (self.root / "wrapper.log").open("a") as log, \
             patch.object(daily.shutil, "which", return_value="resolved-tool") as which, \
             patch.object(daily, "run_logged_process", return_value=SimpleNamespace(returncode=0, timed_out=False)) as runner:
            daily.execute(["npm.cmd", "test"], log, env=env)
            which.assert_called_once_with("npm.cmd", path="scheduler-tools")
            self.assertIs(runner.call_args.kwargs["env"], env)
            daily.execute(["npm.cmd", "test"], log)
            which.assert_called_with("npm.cmd", path=None)

    def test_remote_csv_bom_crlf_equivalence(self):
        real = self.publication_api()
        def equivalent(command, *args, **kwargs):
            if daily.TC_PATH in command[-1]:
                text = "\ufeff" + CSV.replace("\n", "\r\n")
                return json.dumps({"content": base64.b64encode(text.encode()).decode()})
            return real(command, *args, **kwargs)
        self.assertEqual(self.publication(api=equivalent), SHA)
        self.assertEqual(daily.normalize_csv("\ufeff" + CSV.replace("\n", "\r\n")),
                         daily.normalize_csv(CSV))
        def changed(command, *args, **kwargs):
            if daily.TC_PATH in command[-1]:
                text = CSV.replace("-40.5", "-39.5")
                return json.dumps({"content": base64.b64encode(text.encode()).decode()})
            return real(command, *args, **kwargs)
        with self.assertRaisesRegex(daily.TerminalPublicationError, "TC CSV differs"):
            self.publication(api=changed)

    def test_process_runner_timeout_and_auth_classification(self):
        with (self.root / "wrapper.log").open("a") as log, \
             patch.object(daily.shutil, "which", return_value="executable"), \
             patch.object(daily, "run_logged_process") as runner:
            runner.return_value = SimpleNamespace(returncode=1, timed_out=True)
            with self.assertRaises(TimeoutError):
                daily.execute(["opencode.cmd", "run"], log, timeout=3600)
            def fail(command, **kwargs):
                kwargs["stderr_path"].write_text("HTTP 401 bad credentials")
                return SimpleNamespace(returncode=1, timed_out=False)
            runner.side_effect = fail
            with self.assertRaises(daily.TerminalPublicationError):
                daily.execute(["gh", "api"], log)
            for message in ("HTTP 503 unavailable", "HTTP 403 API rate limit exceeded"):
                def transient(command, **kwargs):
                    kwargs["stderr_path"].write_text(message)
                    return SimpleNamespace(returncode=1, timed_out=False)
                runner.side_effect = transient
                with self.assertRaises(daily.Pending):
                    daily.execute(["gh", "api"], log)

    def test_unpublished_report_fails_without_push(self):
        real = self.publication_api()
        def mismatch(command, *args, **kwargs):
            if f"{DATE}.json" in command[-1]:
                return json.dumps({"content": base64.b64encode(b'{"date":"old"}').decode()})
            return real(command, *args, **kwargs)
        with self.assertRaisesRegex(daily.TerminalPublicationError, "wrapper never pushes"):
            self.publication(api=mismatch)
        def missing(command, *args, **kwargs):
            if f"{DATE}.json" in command[-1]:
                raise daily.Pending("Transient GitHub API failure: HTTP 404")
            return real(command, *args, **kwargs)
        with self.assertRaisesRegex(daily.TerminalPublicationError, "not published"):
            self.publication(api=missing)


if __name__ == "__main__":
    unittest.main()

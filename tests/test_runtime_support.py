import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from scripts.runtime_support import AlreadyRunning, exclusive_lock, run_logged_process
from scripts.script_utils import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parents[1]


def process_alive(pid):
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        status = Path(f"/proc/{pid}/stat")
        return not status.exists() or status.read_text().split()[2] != "Z"
    except ProcessLookupError:
        return False


class RuntimeSupportTests(unittest.TestCase):
    def test_lock_is_nonblocking_and_leftover_file_is_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "run.lock"
            with exclusive_lock(lock):
                with self.assertRaises(AlreadyRunning):
                    with exclusive_lock(lock):
                        self.fail("duplicate lock acquired")
                code = (
                    "from scripts.runtime_support import exclusive_lock,AlreadyRunning\n"
                    f"try:\n with exclusive_lock({str(lock)!r}): pass\n"
                    "except AlreadyRunning: raise SystemExit(23)\n"
                )
                result = run_logged_process(
                    [sys.executable, "-B", "-c", code], cwd=ROOT,
                    stdout_path=Path(directory) / "out", stderr_path=Path(directory) / "err", timeout=10,
                )
                self.assertEqual(result.returncode, 23)
            self.assertTrue(lock.exists())
            with exclusive_lock(lock):
                pass

    def test_timeout_keeps_output_and_releases_child_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "child.lock"
            code = (
                "import time\nfrom scripts.runtime_support import exclusive_lock\n"
                f"with exclusive_lock({str(lock)!r}):\n"
                " print('committed progress',flush=True)\n time.sleep(30)\n"
            )
            beats = []
            result = run_logged_process(
                [sys.executable, "-B", "-c", code], cwd=ROOT,
                stdout_path=root / "out", stderr_path=root / "err", timeout=1,
                heartbeat=beats.append,
            )
            self.assertTrue(result.timed_out)
            self.assertEqual(result.returncode, 124)
            self.assertIn("committed progress", (root / "out").read_text())
            self.assertGreaterEqual(len(beats), 1)
            with exclusive_lock(lock):
                pass

    def test_success_also_cleans_up_background_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pidfile = root / "pid"
            code = (
                "import subprocess,sys; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                f"Path({str(pidfile)!r}).write_text(str(p.pid))"
            )
            result = run_logged_process(
                [sys.executable, "-B", "-c", code], cwd=ROOT,
                stdout_path=root / "out", stderr_path=root / "err", timeout=10,
            )
            self.assertEqual(result.returncode, 0)
            pid = int(pidfile.read_text())
            deadline = time.monotonic() + 3
            while process_alive(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(process_alive(pid))

    @unittest.skipUnless(os.name == "nt", "Windows kill-on-close job guarantee")
    def test_killing_supervisor_kills_child_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pidfile = root / "pid"
            child_code = (
                "import os,time; from pathlib import Path; "
                f"Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
            )
            supervisor_code = (
                "import sys; from scripts.runtime_support import run_logged_process; "
                f"run_logged_process([sys.executable,'-B','-c',{child_code!r}],"
                f"cwd={str(ROOT)!r},stdout_path={str(root / 'out')!r},"
                f"stderr_path={str(root / 'err')!r},timeout=30)"
            )
            supervisor = subprocess.Popen([sys.executable, "-B", "-c", supervisor_code], cwd=ROOT)
            pid = None
            try:
                deadline = time.monotonic() + 8
                while not pidfile.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pidfile.exists(), "child did not start")
                pid = int(pidfile.read_text())
                supervisor.kill()
                supervisor.wait(timeout=5)
                deadline = time.monotonic() + 5
                while process_alive(pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(process_alive(pid))
            finally:
                if supervisor.poll() is None:
                    supervisor.kill()
                    supervisor.wait(timeout=5)
                if pid and process_alive(pid):
                    os.kill(pid, signal.SIGTERM)

    def test_exclusive_atomic_publication_does_not_replace_racing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "raw.txt"
            original_link = os.link
            def competitor(source, destination):
                Path(destination).write_text("other run", encoding="utf-8")
                return original_link(source, destination)
            with mock.patch("scripts.script_utils.os.link", side_effect=competitor):
                with self.assertRaises(FileExistsError):
                    atomic_write_text(target, "this run")
            self.assertEqual(target.read_text(), "other run")
            with self.assertRaises(FileExistsError):
                atomic_write_json(target, {}, overwrite=False)
            self.assertEqual(target.read_text(), "other run")
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])

    def test_invalid_deadline_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            for timeout in (0, -1, float("inf"), float("nan")):
                with self.subTest(timeout=timeout), mock.patch("subprocess.Popen") as launch:
                    with self.assertRaises(ValueError):
                        run_logged_process(["unused"], cwd=ROOT, stdout_path=Path(directory) / "out",
                                           stderr_path=Path(directory) / "err", timeout=timeout)
                    launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

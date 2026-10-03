"""Crash-released locks and bounded, streamed subprocesses for unattended runs.

No retries live here. Callers decide whether an operation is safe to repeat.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Callable, Iterator, Mapping, Sequence


class AlreadyRunning(RuntimeError):
    """Another process holds the requested lock."""


@contextmanager
def exclusive_lock(path: str | Path) -> Iterator[None]:
    """Acquire a nonblocking OS lock, released even on process death.

    The file stays in place: unlinking a lock file allows two different inodes
    to be locked concurrently. A leftover file is not evidence of a live run.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+b") as stream:
        if target.stat().st_size == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise AlreadyRunning(f"Another run holds {target}") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    timed_out: bool = False


class _WindowsJob:
    """Native kill-on-close job; descendants cannot outlive their supervisor."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class Limits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
            ]

        self.ctypes = ctypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process: subprocess.Popen) -> None:
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def terminate(self) -> None:
        if not self.kernel.TerminateJobObject(self.handle, 124):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        # Confirm all descendants exited before the caller releases its lock.
        accounting = (self.ctypes.c_ubyte * 48)()
        until = time.monotonic() + 10
        while True:
            if not self.kernel.QueryInformationJobObject(self.handle, 1, accounting, 48, None):
                raise self.ctypes.WinError(self.ctypes.get_last_error())
            active = int.from_bytes(bytes(accounting)[40:44], "little")
            if active == 0:
                return
            if time.monotonic() >= until:
                raise RuntimeError("Could not confirm child process tree termination")
            time.sleep(0.05)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


# No user command executes until the parent has attached the launcher to its
# Windows job. This closes the spawn/assign race, including on parent hard kill.
_WINDOWS_LAUNCHER = (
    "import subprocess,sys; "
    "ready=sys.stdin.buffer.read(1); "
    "sys.exit(subprocess.call(sys.argv[1:],stdin=subprocess.DEVNULL) if ready==b'G' else 125)"
)


def run_logged_process(
    command: Sequence[str], *, cwd: str | Path, stdout_path: str | Path,
    stderr_path: str | Path, timeout: float, env: Mapping[str, str] | None = None,
    heartbeat: Callable[[dict], None] | None = None,
) -> ProcessResult:
    """Stream child output to disk and enforce a wall-clock deadline.

    Windows uses a job object, POSIX a process group. Both clean up descendants
    on exit/exception/timeout; the Windows job also survives supervisor hard
    termination safely. POSIX SIGKILL requires the child-level lock/checkpoint
    guards on the next invocation. Never retry a timed-out command here.
    """
    if not command or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("command must be nonempty and timeout finite and positive")
    paths = [Path(stdout_path), Path(stderr_path)]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    child_env = dict(os.environ if env is None else env)
    child_env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    started = time.monotonic()
    job = _WindowsJob() if os.name == "nt" else None
    process = None
    timed_out = False
    try:
        with paths[0].open("wb") as stdout, paths[1].open("wb") as stderr:
            arguments = list(command)
            if job is not None:
                arguments = [sys.executable, "-u", "-c", _WINDOWS_LAUNCHER, *arguments]
            process = subprocess.Popen(
                arguments, cwd=cwd, env=child_env, stdout=stdout, stderr=stderr,
                stdin=subprocess.PIPE if job is not None else subprocess.DEVNULL,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            if job is not None:
                job.assign(process)
                process.stdin.write(b"G")
                process.stdin.close()
            while True:
                elapsed = time.monotonic() - started
                if heartbeat is not None:
                    heartbeat({"pid": process.pid, "elapsed_seconds": round(elapsed, 3)})
                remaining = timeout - elapsed
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    process.wait(timeout=min(15, remaining))
                    break
                except subprocess.TimeoutExpired:
                    pass
            return ProcessResult(124 if timed_out else process.returncode, timed_out)
    finally:
        try:
            if process is not None:
                if job is not None:
                    # If assignment failed, the unarmed launcher is still waiting.
                    if process.stdin is not None and not process.stdin.closed:
                        process.stdin.close()
                    job.terminate()
                    if process.poll() is None:
                        process.kill()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait(timeout=10)
        finally:
            if job is not None:
                job.close()

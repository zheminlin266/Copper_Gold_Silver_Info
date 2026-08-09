"""Small standard-library helpers shared by supported collection scripts."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable, TextIO

_REPORT_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_DEFAULT_CHROME_EXECUTABLE = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")


def parse_report_date(value: object) -> date:
    """Parse a real, zero-padded YYYY-MM-DD report date."""
    if not isinstance(value, str) or _REPORT_DATE_PATTERN.fullmatch(value) is None:
        raise ValueError("report date must be a real YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("report date must be a real YYYY-MM-DD date") from error


def bounded_int(value: object, minimum: int, maximum: int, label: str) -> int:
    """Return an integer when it is within the inclusive bounds."""
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    if minimum > maximum:
        raise ValueError(f"{label} has invalid bounds")
    if value < minimum or value > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


def resolve_chrome_executable() -> str | None:
    """Resolve an explicit Chrome executable, or let Playwright use Chromium."""
    if "CHROME_EXECUTABLE" in os.environ:
        configured = Path(os.environ["CHROME_EXECUTABLE"]).expanduser()
        if not configured.is_file():
            raise FileNotFoundError(
                "CHROME_EXECUTABLE is set but does not point to an existing file: "
                f"{configured}"
            )
        return str(configured)

    if _DEFAULT_CHROME_EXECUTABLE.is_file():
        return str(_DEFAULT_CHROME_EXECUTABLE)
    return None


async def is_x_authenticated(page: Any) -> bool:
    """Return true only when X exposes authenticated navigation controls."""
    try:
        url = (page.url or "").lower()
        if "/login" in url or "/onboarding" in url:
            return False
        home_link = await page.locator('a[data-testid="AppTabBar_Home_Link"]').count()
        account_switcher = await page.locator(
            '[data-testid="SideNav_AccountSwitcher_Button"]'
        ).count()
        return home_link > 0 or account_switcher > 0
    except Exception:
        return False


def _atomic_write(path: Path, writer: Callable[[TextIO], None], *, secure: bool = False) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            if secure:
                try:
                    os.chmod(temporary_path, 0o600)
                except OSError:
                    pass
            writer(temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass


def atomic_write_json(path: str | os.PathLike[str], data: Any) -> None:
    """Write JSON through a same-directory, fsynced temporary file."""
    target = Path(path)
    _atomic_write(
        target,
        lambda stream: (json.dump(data, stream, ensure_ascii=False, indent=2), stream.write("\n")),
        secure=True,
    )


def atomic_write_text(
    path: str | os.PathLike[str], text: str, overwrite: bool = False
) -> None:
    """Write UTF-8 text atomically, refusing an existing target by default."""
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {target}")
    _atomic_write(target, lambda stream: stream.write(text))

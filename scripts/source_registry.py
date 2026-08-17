"""Load and validate the authoritative source registry.

The registry is deliberately JSON plus standard-library Python so collectors do
not each carry their own source lists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "source_registry.json"
_HANDLE_PATTERN = re.compile(r"[A-Za-z0-9_]+\Z")


class SourceRegistryError(ValueError):
    """Raised when the source registry cannot be loaded or is malformed."""


def _required_text(entry: dict[str, Any], key: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SourceRegistryError(
            f"source entry {index} field '{key}' must be a non-empty string"
        )
    return value.strip()


def _normalise_entry(entry: dict[str, Any], index: int) -> dict[str, Any]:
    source_id = _required_text(entry, "source_id", index)
    display_name = _required_text(entry, "display_name", index)
    category = _required_text(entry, "category", index)
    notes = entry.get("notes", "")
    if not isinstance(notes, str):
        raise SourceRegistryError(f"source entry {index} field 'notes' must be a string")

    normalised = {
        "source_id": source_id,
        "display_name": display_name,
        "category": category,
        "notes": notes.strip(),
    }
    for key in ("channel", "x_user_id"):
        value = entry.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise SourceRegistryError(
                    f"source entry {index} field '{key}' must be a string when present"
                )
            normalised[key] = value.strip()

    handle = entry.get("x_handle")
    if handle is not None:
        if not isinstance(handle, str) or not handle.strip():
            raise SourceRegistryError(
                f"source entry {index} field 'x_handle' must be a non-empty string"
            )
        handle = handle.strip().lstrip("@")
        if not _HANDLE_PATTERN.fullmatch(handle):
            raise SourceRegistryError(
                f"source entry {index} field 'x_handle' is not a valid X handle: {handle!r}"
            )
        normalised["x_handle"] = handle

    unknown = set(entry) - {
        "source_id", "display_name", "category", "notes", "channel", "x_handle", "x_user_id"
    }
    if unknown:
        raise SourceRegistryError(
            f"source entry {index} has unsupported field(s): {', '.join(sorted(unknown))}"
        )
    return normalised


def _merge_duplicate_handles(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first handle record and fill missing metadata from later records."""
    merged: list[dict[str, Any]] = []
    by_handle: dict[str, dict[str, Any]] = {}
    for entry in entries:
        handle = entry.get("x_handle")
        if not handle:
            merged.append(entry)
            continue
        key = handle.casefold()
        existing = by_handle.get(key)
        if existing is None:
            by_handle[key] = entry
            merged.append(entry)
            continue
        for field in ("channel", "x_user_id"):
            if not existing.get(field) and entry.get(field):
                existing[field] = entry[field]
        if entry.get("notes") and entry["notes"] not in existing["notes"]:
            existing["notes"] = "; ".join(
                value for value in (existing.get("notes", ""), entry["notes"]) if value
            )
    return merged


def validate_registry(data: Any) -> list[dict[str, Any]]:
    """Validate registry JSON and return normalised, case-insensitively deduped entries."""
    if not isinstance(data, dict):
        raise SourceRegistryError("registry root must be a JSON object")
    if data.get("version") != 1:
        raise SourceRegistryError("registry field 'version' must be 1")
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise SourceRegistryError("registry field 'sources' must be a list")

    entries = []
    source_ids: set[str] = set()
    for index, entry in enumerate(sources, start=1):
        if not isinstance(entry, dict):
            raise SourceRegistryError(f"source entry {index} must be a JSON object")
        normalised = _normalise_entry(entry, index)
        source_id = normalised["source_id"]
        if source_id in source_ids:
            raise SourceRegistryError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)
        entries.append(normalised)

    entries = _merge_duplicate_handles(entries)
    return entries


def load_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> list[dict[str, Any]]:
    """Load the authoritative registry from *path* with clear errors."""
    registry_path = Path(path)
    try:
        with registry_path.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError as error:
        raise SourceRegistryError(f"source registry not found: {registry_path}") from error
    except json.JSONDecodeError as error:
        raise SourceRegistryError(
            f"source registry is not valid JSON ({registry_path}): {error.msg}"
        ) from error
    return validate_registry(data)


def get_x_accounts(registry: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return X-enabled source records in registry order."""
    entries = load_registry() if registry is None else registry
    return [dict(entry) for entry in entries if entry.get("x_handle")]


def get_x_handles(registry: list[dict[str, Any]] | None = None) -> list[str]:
    """Return deduplicated X handles in registry order."""
    return [entry["x_handle"] for entry in get_x_accounts(registry)]


def source_by_handle(handle: str, registry: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Find one X source by handle, case-insensitively."""
    if not isinstance(handle, str) or not handle.strip():
        raise SourceRegistryError("X handle must be a non-empty string")
    key = handle.strip().lstrip("@").casefold()
    for entry in get_x_accounts(registry):
        if entry["x_handle"].casefold() == key:
            return entry
    raise SourceRegistryError(f"X handle is not in the source registry: @{handle}")


__all__ = [
    "DEFAULT_REGISTRY_PATH",
    "SourceRegistryError",
    "get_x_accounts",
    "get_x_handles",
    "load_registry",
    "source_by_handle",
    "validate_registry",
]

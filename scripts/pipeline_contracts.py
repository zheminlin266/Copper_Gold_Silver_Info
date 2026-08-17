"""Strict, dependency-free contracts shared by the deterministic pipeline."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Mapping
from urllib.parse import urlsplit

METALS = frozenset({"gold", "silver", "copper"})
DIRECTIONS = frozenset({"supply", "demand", "both"})
DECISIONS = frozenset({"accept", "accepted", "reject", "rejected"})
KINDS = frozenset({"broadcast", "x", "news"})
COLLECTOR_STATUSES = frozenset({"preflight", "complete", "partial", "failed"})
SCHEMA_VERSION = 3


class ContractError(ValueError):
    """Raised when a pipeline record violates its contract."""


def _text(value: Any, field_name: str, *, required: bool = True) -> str | None:
    if not isinstance(value, str):
        if required:
            raise ContractError(f"{field_name} must be a non-empty string")
        return None
    if required and not value.strip():
        raise ContractError(f"{field_name} must be a non-empty string")
    return value if value else None


def require_id(value: Any, field_name: str = "id") -> str:
    result = _text(value, field_name)
    assert result is not None
    return result


def validate_url(value: Any, field_name: str = "url") -> str:
    result = _text(value, field_name)
    assert result is not None
    parsed = urlsplit(result)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ContractError(f"{field_name} must be an absolute http(s) URL")
    return result


def validate_date(value: Any, field_name: str = "date") -> str:
    result = _text(value, field_name)
    assert result is not None
    if len(result) != 10:
        raise ContractError(f"{field_name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(result)
    except ValueError as error:
        raise ContractError(f"{field_name} must be a real YYYY-MM-DD date") from error
    if parsed.isoformat() != result:
        raise ContractError(f"{field_name} must be zero-padded YYYY-MM-DD")
    return result


def validate_datetime(value: Any, field_name: str = "datetime") -> str:
    result = _text(value, field_name)
    assert result is not None
    normalized = result[:-1] + "+00:00" if result.endswith("Z") else result
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ContractError(f"{field_name} must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field_name} must include a timezone")
    return result


def validate_date_or_datetime(value: Any, field_name: str) -> str:
    if isinstance(value, str) and len(value) == 10:
        return validate_date(value, field_name)
    return validate_datetime(value, field_name)


def validate_metal(value: Any, field_name: str = "metal") -> str:
    result = _text(value, field_name)
    assert result is not None
    if result not in METALS:
        raise ContractError(f"{field_name} must be one of: {', '.join(sorted(METALS))}")
    return result


def validate_direction(value: Any, field_name: str = "direction") -> str:
    result = _text(value, field_name)
    assert result is not None
    if result not in DIRECTIONS:
        raise ContractError(f"{field_name} must be one of: {', '.join(sorted(DIRECTIONS))}")
    return result


def validate_decision(value: Any, field_name: str = "decision") -> str:
    result = _text(value, field_name)
    assert result is not None
    if result not in DECISIONS:
        raise ContractError(f"{field_name} is unsupported: {result!r}")
    return result


def validate_confidence(value: Any, field_name: str = "confidence") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ContractError(f"{field_name} must be a finite number")
    if result < 0 or result > 1:
        raise ContractError(f"{field_name} must be between 0 and 1")
    return result


def _json_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], record_name: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ContractError(
            f"{record_name} has unsupported field(s): {', '.join(sorted(unknown))}"
        )


@dataclass(frozen=True)
class RawDocument:
    id: str
    source_url: str
    title: str
    text: str
    published_at: str | None = None

    def __post_init__(self) -> None:
        require_id(self.id)
        validate_url(self.source_url, "source_url")
        _text(self.title, "title")
        if not isinstance(self.text, str):
            raise ContractError("text must be a string")
        if self.published_at is not None:
            validate_date_or_datetime(self.published_at, "published_at")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawDocument":
        if not isinstance(data, Mapping):
            raise ContractError("RawDocument must be an object")
        _reject_unknown(data, {"id", "source_url", "title", "text", "published_at"}, "RawDocument")
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Candidate:
    id: str
    document_id: str
    source_url: str
    title: str
    published_at: str | None = None
    text: str = ""
    collector: str = ""
    kind: str | None = None
    source: str | None = None
    author: str | None = None
    handle: str | None = None
    metal: str | None = None
    direction: str | None = None
    raw: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        require_id(self.id)
        require_id(self.document_id, "document_id")
        validate_url(self.source_url, "source_url")
        _text(self.title, "title")
        if not isinstance(self.text, str):
            raise ContractError("text must be a string")
        if self.published_at is not None:
            validate_date_or_datetime(self.published_at, "published_at")
        _text(self.collector, "collector")
        if self.kind is not None and self.kind not in KINDS:
            raise ContractError(f"kind is unsupported: {self.kind!r}")
        if self.metal is not None:
            validate_metal(self.metal)
        if self.direction is not None:
            validate_direction(self.direction)
        for field_name, value in (("source", self.source), ("author", self.author), ("handle", self.handle)):
            if value is not None:
                _text(value, field_name)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Candidate":
        if not isinstance(data, Mapping):
            raise ContractError("Candidate must be an object")
        allowed = {
            "id", "document_id", "source_url", "title", "text", "raw_text", "published_at",
            "collector", "kind", "source", "author", "handle", "metal", "direction", "raw",
        }
        _reject_unknown(data, allowed, "Candidate")
        values = dict(data)
        if "raw_text" in values:
            if "text" in values and values["text"] != values["raw_text"]:
                raise ContractError("Candidate text and raw_text disagree")
            values.setdefault("text", values.pop("raw_text"))
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class EvidenceClaim:
    claim: str
    evidence: str
    source_url: str
    evidence_type: str
    period: str
    unit: str
    value: str | int | float | None

    def __post_init__(self) -> None:
        for field_name in ("claim", "evidence", "evidence_type", "period", "unit"):
            _text(getattr(self, field_name), field_name)
        validate_url(self.source_url, "source_url")
        if isinstance(self.value, bool) or not isinstance(self.value, (str, int, float, type(None))):
            raise ContractError("value must be a string, number, or null")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ContractError("value must be finite")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceClaim":
        if not isinstance(data, Mapping):
            raise ContractError("EvidenceClaim must be an object")
        _reject_unknown(
            data,
            {"claim", "evidence", "source_url", "evidence_type", "period", "unit", "value"},
            "EvidenceClaim",
        )
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisDecision:
    candidate_id: str
    accepted: bool | None = None
    reason: str = ""
    claims: tuple[EvidenceClaim, ...] = ()
    decision: str | None = None
    kind: str | None = None
    metal: str | None = None
    direction: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        require_id(self.candidate_id, "candidate_id")
        if self.accepted is not None and type(self.accepted) is not bool:
            raise ContractError("accepted must be a boolean")
        normalized_decision = self.decision
        if normalized_decision is not None:
            normalized_decision = validate_decision(normalized_decision)
            object.__setattr__(self, "decision", normalized_decision)
        if self.accepted is None and normalized_decision is None:
            raise ContractError("analysis decision must include accepted or decision")
        if self.accepted is not None and normalized_decision is not None:
            expected = normalized_decision in {"accept", "accepted"}
            if self.accepted != expected:
                raise ContractError("accepted and decision disagree")
        if self.kind is not None and self.kind not in KINDS:
            raise ContractError(f"kind is unsupported: {self.kind!r}")
        if self.metal is not None:
            validate_metal(self.metal)
        if self.direction is not None:
            validate_direction(self.direction)
        if self.confidence is not None:
            validate_confidence(self.confidence)
        _text(self.reason, "reason", required=False)
        claims = tuple(
            claim if isinstance(claim, EvidenceClaim) else EvidenceClaim.from_dict(claim)
            for claim in self.claims
        )
        object.__setattr__(self, "claims", claims)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AnalysisDecision":
        if not isinstance(data, Mapping):
            raise ContractError("AnalysisDecision must be an object")
        _reject_unknown(
            data,
            {"candidate_id", "accepted", "decision", "kind", "metal", "direction", "confidence", "reason", "claims"},
            "AnalysisDecision",
        )
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class CollectorResult:
    collector: str
    status: str
    candidates: tuple[Candidate, ...] = ()
    errors: tuple[str, ...] = ()
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    artifacts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.collector, "collector")
        if self.status not in COLLECTOR_STATUSES:
            raise ContractError(f"collector status is unsupported: {self.status!r}")
        if self.status in {"failed", "partial"} and not self.errors:
            raise ContractError(f"collector status {self.status!r} requires at least one error")
        if self.status == "complete" and self.exit_code not in (None, 0):
            raise ContractError("complete collector status requires exit_code 0 or null")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ContractError("exit_code must be an integer or null")
        for value, name in ((self.stdout, "stdout"), (self.stderr, "stderr")):
            if not isinstance(value, str):
                raise ContractError(f"{name} must be a string")
        candidates = tuple(
            candidate if isinstance(candidate, Candidate) else Candidate.from_dict(candidate)
            for candidate in self.candidates
        )
        object.__setattr__(self, "candidates", candidates)
        errors = tuple(self.errors)
        if any(not isinstance(error, str) or not error.strip() for error in errors):
            raise ContractError("collector errors must be non-empty strings")
        object.__setattr__(self, "errors", errors)
        artifacts = tuple(self.artifacts)
        if any(not isinstance(path, str) or not path.strip() for path in artifacts):
            raise ContractError("collector artifacts must be non-empty strings")
        object.__setattr__(self, "artifacts", artifacts)

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    schema_version: int = SCHEMA_VERSION
    started_at: str = ""
    completed_at: str | None = None
    document_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    report_date: str | None = None
    run_dir: str | None = None
    windows: Mapping[str, Any] = field(default_factory=dict)
    status: str = "preflight"
    collectors: tuple[Mapping[str, Any], ...] = ()
    registry_source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_id(self.run_id, "run_id")
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"schema_version must be {SCHEMA_VERSION}")
        validate_datetime(self.started_at, "started_at")
        if self.completed_at is not None:
            validate_datetime(self.completed_at, "completed_at")
        if self.report_date is not None:
            validate_date(self.report_date, "report_date")
        if self.run_dir is not None:
            _text(self.run_dir, "run_dir")
        if self.status not in COLLECTOR_STATUSES:
            raise ContractError(f"manifest status is unsupported: {self.status!r}")
        for name, values in (("document_ids", self.document_ids), ("candidate_ids", self.candidate_ids), ("decision_ids", self.decision_ids), ("registry_source_ids", self.registry_source_ids)):
            normalized = tuple(require_id(value, name[:-1] + "_id") for value in values)
            if len(set(normalized)) != len(normalized):
                raise ContractError(f"{name} must not contain duplicate IDs")
            object.__setattr__(self, name, normalized)
        if not isinstance(self.windows, Mapping):
            raise ContractError("windows must be an object")
        collectors = tuple(self.collectors)
        if any(not isinstance(item, Mapping) for item in collectors):
            raise ContractError("collectors must be objects")
        object.__setattr__(self, "collectors", collectors)

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


def contract_from_json(text: str, contract_type: type[Any]) -> Any:
    """Decode one JSON object into a named contract type."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid JSON: {error.msg}") from error
    if not isinstance(data, Mapping) or not hasattr(contract_type, "from_dict"):
        raise ContractError("contract JSON must be an object")
    return contract_type.from_dict(data)


__all__ = [
    "AnalysisDecision", "Candidate", "COLLECTOR_STATUSES", "ContractError",
    "DECISIONS", "DIRECTIONS", "EvidenceClaim", "KINDS", "METALS",
    "RawDocument", "RunManifest", "SCHEMA_VERSION", "CollectorResult",
    "contract_from_json", "require_id", "validate_confidence", "validate_date",
    "validate_date_or_datetime", "validate_datetime", "validate_direction",
    "validate_decision", "validate_metal", "validate_url",
]

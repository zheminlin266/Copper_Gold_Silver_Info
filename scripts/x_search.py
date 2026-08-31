"""
X (Twitter) 供需信息搜索 — 有序多通道采集器。
按 Playwright、twscrape 顺序获取窗口内帖子，保存原始候选到 x_outputs/。

无 LLM 依赖，不调用 browser-use API；可选通道按需安装。

用法:
    C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/x_search.py 2026-07-13
    C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/x_search.py 2026-07-13 --headless
    C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe scripts/x_search.py 2026-07-13 --headless --overwrite

Python 环境:
    必须使用日报固定 Python 运行时（Playwright + twscrape）:
        C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe
    该解释器同时提供 Playwright 1.62.0 与 twscrape 0.20.1。
    不要使用 `python`、`py` 或 `.workbuddy` Python；daily_pipeline.py 会以当前
    `sys.executable` 启动子采集器

输出:
    x_outputs/{date}_x_raw_materials.txt
"""

import asyncio
import hashlib
import importlib
import inspect
import json
import math
import os
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

try:
    from scripts.script_utils import (
        atomic_write_json,
        atomic_write_text,
        is_x_authenticated,
        parse_report_date,
        resolve_chrome_executable,
    )
except ModuleNotFoundError:
    from script_utils import (  # type: ignore[no-redef]
        atomic_write_json,
        atomic_write_text,
        is_x_authenticated,
        parse_report_date,
        resolve_chrome_executable,
    )

try:
    from scripts.source_registry import get_x_accounts, load_registry
except ModuleNotFoundError:
    from source_registry import get_x_accounts, load_registry  # type: ignore[no-redef]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / ".browser_profile" / "chromium-data"
STORAGE_STATE_FILE = PROJECT_ROOT / ".browser_profile" / "x_auth.json"
TWSCRAPE_DB = PROJECT_ROOT / ".browser_profile" / "twscrape.db"

TZ_BEIJING = timezone(timedelta(hours=8))
SEARCH_QUERY = "(gold OR silver OR copper OR mining OR mine OR production OR supply OR demand OR permit OR smelter OR mill OR drill OR resource OR reserve)"
CHANNEL_TWSCRAPE = "twscrape"
CHANNEL_PLAYWRIGHT = "playwright"
X_CHANNEL_ORDER = (CHANNEL_PLAYWRIGHT, CHANNEL_TWSCRAPE)
DEFAULT_SAFE_DELAY_MIN_SECONDS = 25.0
DEFAULT_SAFE_DELAY_MAX_SECONDS = 30.0
DEFAULT_MAX_RESULTS_PER_QUERY = 20
_UNSET = object()


class XLoginRequired(RuntimeError):
    """Raised when X redirects the collector to a login or onboarding page."""


class XPartialFailure(RuntimeError):
    """Raised after a partial audit file has been written."""


class XCollectionFailure(RuntimeError):
    """Raised after a failed audit file has been written."""


class ChannelUnavailable(RuntimeError):
    """A channel cannot be used safely; the ordered fallback may continue."""


class ChannelTransient(RuntimeError):
    """An ordinary pre-collection transient error; the fallback may continue."""


class XSafetyStop(RuntimeError):
    """An X safety event that must stop the run without another fallback."""

    def __init__(
        self,
        message: str,
        *,
        tweets: list[dict] | None = None,
        failed_accounts: list[tuple[str, str, str, str]] | None = None,
        completed_accounts: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.tweets = tweets or []
        self.failed_accounts = failed_accounts or []
        self.completed_accounts = completed_accounts or []


class XNormalizationUnavailable(ChannelUnavailable):
    """A channel returned data that cannot satisfy the existing candidate contract."""


@dataclass
class ChannelResult:
    channel: str
    tweets: list[dict] = field(default_factory=list)
    failed_accounts: list[tuple[str, str, str, str]] = field(default_factory=list)
    status: str = "complete"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    completed_accounts: list[str] = field(default_factory=list)


def candidate_id(source_id: str, url: str) -> str:
    """Return a stable ID for one source post."""
    digest = hashlib.sha256(f"{source_id}|{url}".encode("utf-8")).hexdigest()
    return f"x-{digest[:24]}"


@dataclass(frozen=True)
class SafeDelayConfig:
    """Validated inter-account pacing settings."""

    min_seconds: float
    max_seconds: float
    fixed_seconds: float | None = None

    @property
    def metadata(self) -> dict[str, float | str]:
        data: dict[str, float | str] = {
            "safe_delay_mode": "fixed" if self.fixed_seconds is not None else "uniform",
            "safe_delay_min_seconds": self.min_seconds,
            "safe_delay_max_seconds": self.max_seconds,
        }
        if self.fixed_seconds is not None:
            data["safe_delay_fixed_seconds"] = self.fixed_seconds
        return data


def _parse_safe_delay_value(value: object, variable_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{variable_name} must be a number between 5 and 300") from error
    if not math.isfinite(parsed) or not 5 <= parsed <= 300:
        raise ValueError(f"{variable_name} must be between 5 and 300")
    return parsed


def parse_safe_delay_seconds(value: object | None = None) -> float | None:
    """Parse the optional fixed emergency override, or return None when unset."""
    raw = os.environ.get("X_SAFE_DELAY_SECONDS") if value is None else value
    if raw is None or raw == "":
        return None
    return _parse_safe_delay_value(raw, "X_SAFE_DELAY_SECONDS")


def parse_safe_delay_config(
    min_value: object | None = None,
    max_value: object | None = None,
    fixed_value: object = _UNSET,
) -> SafeDelayConfig:
    """Read fixed override or a validated uniform delay range from the environment."""
    if fixed_value is _UNSET:
        fixed_value = os.environ.get("X_SAFE_DELAY_SECONDS")
    if fixed_value is not None and fixed_value != "":
        fixed = _parse_safe_delay_value(fixed_value, "X_SAFE_DELAY_SECONDS")
        return SafeDelayConfig(
            min_seconds=DEFAULT_SAFE_DELAY_MIN_SECONDS,
            max_seconds=DEFAULT_SAFE_DELAY_MAX_SECONDS,
            fixed_seconds=fixed,
        )

    raw_min = os.environ.get("X_SAFE_DELAY_MIN_SECONDS") if min_value is None else min_value
    raw_max = os.environ.get("X_SAFE_DELAY_MAX_SECONDS") if max_value is None else max_value
    minimum = (
        DEFAULT_SAFE_DELAY_MIN_SECONDS
        if raw_min is None or raw_min == ""
        else _parse_safe_delay_value(raw_min, "X_SAFE_DELAY_MIN_SECONDS")
    )
    maximum = (
        DEFAULT_SAFE_DELAY_MAX_SECONDS
        if raw_max is None or raw_max == ""
        else _parse_safe_delay_value(raw_max, "X_SAFE_DELAY_MAX_SECONDS")
    )
    if minimum > maximum:
        raise ValueError("X_SAFE_DELAY_MIN_SECONDS must be less than or equal to X_SAFE_DELAY_MAX_SECONDS")
    return SafeDelayConfig(minimum, maximum)


# Alias with a name that makes the non-fixed case explicit for callers/tests.
parse_safe_delay_range = parse_safe_delay_config


def select_safe_delay_seconds(
    config: SafeDelayConfig | float,
    random_uniform: Callable[[float, float], float] | None = None,
) -> float:
    """Select one gap delay; random selection occurs each time this is called."""
    if isinstance(config, (int, float)):
        return float(config)
    if config.fixed_seconds is not None:
        return config.fixed_seconds
    return (random_uniform or random.uniform)(config.min_seconds, config.max_seconds)


def max_results_per_query(value: object | None = None) -> int:
    """Read a bounded per-query result limit."""
    raw = os.environ.get("X_MAX_RESULTS_PER_QUERY") if value is None else value
    if raw is None or raw == "":
        return DEFAULT_MAX_RESULTS_PER_QUERY
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as error:
        raise ValueError("X_MAX_RESULTS_PER_QUERY must be an integer between 1 and 500") from error
    if parsed < 1 or parsed > 500:
        raise ValueError("X_MAX_RESULTS_PER_QUERY must be between 1 and 500")
    return parsed


def build_search_query(handle: str, report_date: str) -> str:
    next_date = (parse_report_date(report_date) + timedelta(days=1)).isoformat()
    return f"from:{handle} {SEARCH_QUERY} since:{report_date} until:{next_date}"


def _normalise_post_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").casefold()
    if host == "twitter.com":
        host = "x.com"
    return urlunsplit(("https", host, parsed.path.rstrip("/"), "", ""))


def _is_status_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https"}
        and (parsed.hostname or "").casefold() in {"x.com", "twitter.com"}
        and re.fullmatch(r"/[^/\s]+/status/\d+/?", parsed.path or "") is not None
    )


async def pace_between_accounts(
    index: int,
    total: int,
    delay_config: SafeDelayConfig | float,
    sleep: Callable[[float], Any] | None = None,
    random_uniform: Callable[[float, float], float] | None = None,
) -> None:
    """Sleep only between sequential accounts; select a fresh gap delay each time."""
    if index > 0 and index < total:
        delay_seconds = select_safe_delay_seconds(delay_config, random_uniform)
        await _maybe_await((sleep or asyncio.sleep)(delay_seconds))


def _text_for_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}".casefold()


def _status_code(value: Any) -> int | None:
    if isinstance(value, dict):
        for name in ("status_code", "status"):
            candidate = value.get(name)
            if isinstance(candidate, int) and not isinstance(candidate, bool):
                return candidate
            if isinstance(candidate, str) and candidate.strip().isdigit():
                return int(candidate.strip())
        return None
    for name in ("status_code", "status"):
        candidate = getattr(value, name, None)
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, str) and candidate.strip().isdigit():
            return int(candidate.strip())
    return None


def is_x_safety_error(error: BaseException) -> bool:
    """Classify stop conditions without retrying or probing another channel."""
    for value in (error, getattr(error, "response", None)):
        if _status_code(value) in {401, 403, 429}:
            return True
    text = _text_for_error(error)
    return any(
        marker in text
        for marker in (
            "401",
            "403",
            "429",
            "http 401",
            "http 403",
            "http 429",
            "status 401",
            "status 403",
            "status 429",
            "unauthorized",
            "forbidden",
            "toomanyrequests",
            "rate limit",
            "ratelimit",
            "challenge",
            "login wall",
            "login required",
            "requires login",
            "authentication required",
            "account lock",
            "account_locked",
            "locked account",
            "suspended",
            "suspension",
            "captcha",
            "authorization required",
            "no account available",
            "all accounts unavailable",
            "account exhausted",
            "accounts exhausted",
            "account exhaustion",
        )
    )


def is_twscrape_safety_error(error: BaseException) -> bool:
    """Treat account exhaustion as a hard stop, never as a fallback trigger."""
    names = {cls.__name__.casefold() for cls in type(error).__mro__}
    text = _text_for_error(error)
    return (
        "noaccounterror" in names
        or "no account available" in text
        or "all accounts unavailable" in text
        or "all accounts are unavailable" in text
        or "account exhausted" in text
        or "accounts exhausted" in text
        or "account exhaustion" in text
        or is_x_safety_error(error)
    )


def _get_value(item: Any, *names: str) -> Any:
    for name in names:
        if isinstance(item, dict) and name in item:
            return item[name]
        value = getattr(item, name, None)
        if value is not None:
            return value
    return None


def _absolute_datetime(value: Any, channel: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = parse_x_datetime(value.strip())
        except ValueError as error:
            raise XNormalizationUnavailable(
                f"{channel} returned a non-absolute tweet timestamp"
            ) from error
    else:
        raise XNormalizationUnavailable(
            f"{channel} returned no absolute tweet timestamp; time_ago cannot satisfy the contract"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise XNormalizationUnavailable(f"{channel} returned a naive tweet timestamp")
    return parsed.astimezone(timezone.utc)


def normalize_backend_tweet(
    tweet: Any,
    account: dict[str, str],
    report_date: str,
    *,
    channel: str,
) -> dict | None:
    """Normalize twscrape objects without inventing timestamps or text."""
    user = _get_value(tweet, "user")
    handle = _get_value(user, "username") or _get_value(tweet, "username", "handle")
    author = _get_value(user, "displayname", "display_name", "name") or account["display_name"]
    tweet_id = _get_value(tweet, "id", "tweet_id")
    text = _get_value(tweet, "rawContent", "raw_content", "text", "content")
    timestamp = _get_value(tweet, "date", "created_at", "published_at", "timestamp")
    if not isinstance(handle, str) or not handle.strip():
        raise XNormalizationUnavailable(f"{channel} returned a tweet without a username")
    if tweet_id is None:
        raise XNormalizationUnavailable(f"{channel} returned a tweet without an id")
    if not isinstance(text, str) or not text.strip():
        raise XNormalizationUnavailable(f"{channel} returned a tweet without text")
    utc_time = _absolute_datetime(timestamp, channel)
    bj_time = utc_time.astimezone(TZ_BEIJING)
    if bj_time.strftime("%Y-%m-%d") != report_date:
        return None
    clean_handle = handle.strip().lstrip("@")
    return {
        "source_id": account["source_id"],
        "author": str(author).strip() or account["display_name"],
        "handle": clean_handle,
        "id": str(tweet_id),
        "utc_time": utc_time.isoformat(),
        "bj_time": bj_time.isoformat(),
        "text": text,
        "url": f"https://x.com/{clean_handle}/status/{tweet_id}",
    }


def normalize_twscrape_tweet(tweet: Any, account: dict[str, str], report_date: str) -> dict | None:
    return normalize_backend_tweet(tweet, account, report_date, channel=CHANNEL_TWSCRAPE)




async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _collect_items(value: Any) -> list[Any]:
    value = await _maybe_await(value)
    if hasattr(value, "__aiter__"):
        items = []
        async for item in value:
            items.append(item)
        return items
    if isinstance(value, (str, bytes)):
        raise ChannelUnavailable("X backend returned a non-iterable result")
    try:
        return list(value)
    except TypeError as error:
        raise ChannelUnavailable("X backend returned an unsupported result type") from error


def _call_with_supported_kwargs(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Pass only advertised kwargs so fake and future optional APIs fail closed."""
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_var_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )
    supported = kwargs if accepts_var_kwargs else {
        key: value for key, value in kwargs.items() if key in parameters
    }
    missing = [key for key in kwargs if key not in supported]
    if missing:
        raise ChannelUnavailable(
            f"optional X backend does not expose required setting(s): {', '.join(missing)}"
        )
    return function(*args, **supported)


def normalize_x_candidate(
    tweet: dict, report_date: str, *, status: str = "ok", errors: list[str] | None = None
) -> dict:
    """Normalize a collected tweet for the structured sidecar without truncation."""
    source_id = str(tweet.get("source_id") or f"x-{str(tweet['handle']).casefold()}")
    url = str(tweet["url"])
    candidate = {
        "candidate_id": candidate_id(source_id, url),
        "source_id": source_id,
        "author": tweet["author"],
        "handle": tweet["handle"],
        "publish_time": tweet.get("utc_time") or tweet.get("bj_time") or tweet.get("published_at"),
        "text": tweet["text"],
        "url": url,
        "collector": "x_search",
        "report_date": report_date,
        "status": status,
    }
    if tweet.get("published_at_precision"):
        candidate["published_at_precision"] = tweet["published_at_precision"]
    if errors:
        candidate["errors"] = list(errors)
    return candidate


def sidecar_path(output_file: str | Path) -> Path:
    """Return the JSON sidecar path matching the raw-material filename."""
    return Path(output_file).with_suffix(".json")


def build_sidecar(
    report_date: str,
    tweets: list[dict],
    failed_accounts: list[tuple[str, str, str, str]],
    *,
    status: str | None = None,
    selected_channel: str | None = None,
    attempted_channels: list[str] | None = None,
    unavailable_channels: list[dict[str, str]] | None = None,
    metadata: dict[str, Any] | None = None,
    accounts_total: int | None = None,
    accounts_completed: int | None = None,
    channel_completed_accounts: dict[str, int] | None = None,
) -> dict:
    """Build deterministic structured output while retaining account audit errors."""
    channel_order = list(X_CHANNEL_ORDER)
    attempted = list(attempted_channels or [])
    if attempted != channel_order[:len(attempted)]:
        raise ValueError("attempted_channels must be a Playwright -> twscrape prefix")
    inferred_ids = {item.get("source_id") for item in tweets if item.get("source_id")}
    inferred_ids.update(item[0] for item in failed_accounts)
    total = len(inferred_ids) if accounts_total is None else accounts_total
    completed = max(0, total - len(failed_accounts)) if accounts_completed is None else accounts_completed
    failed = len(failed_accounts)
    if any(type(value) is not int or value < 0 for value in (total, completed, failed)):
        raise ValueError("account counts must be non-negative integers")
    if completed + failed != total:
        raise ValueError("account counts must sum to accounts_total")
    resolved_status = status or ("failed" if failed and completed == 0 else "partial" if failed else "complete")
    if resolved_status not in {"complete", "partial", "failed"}:
        raise ValueError("status must be complete, partial, or failed")
    if resolved_status == "complete" and (completed != total or failed != 0):
        raise ValueError("complete status requires all accounts completed and no failures")
    if resolved_status == "partial" and (completed < 1 or failed < 1):
        raise ValueError("partial status requires at least one completed and one failed account")
    if resolved_status == "failed" and (completed != 0 or failed != total):
        raise ValueError("failed status requires zero completed and all accounts failed")
    channel_completed = dict(channel_completed_accounts or {})
    if any(
        channel not in attempted or type(count) is not int or count < 0
        for channel, count in channel_completed.items()
    ):
        raise ValueError("channel_completed_accounts is invalid")
    if sum(channel_completed.values()) != completed:
        raise ValueError("channel completion counts do not match accounts_completed")
    expected_selected = "+".join(
        channel for channel in channel_order if channel in attempted and channel_completed.get(channel, 0) > 0
    ) or None
    if selected_channel != expected_selected:
        raise ValueError("selected_channel does not match channel completion counts")
    sidecar = {
        "collector": "x_search",
        "report_date": report_date,
        "status": resolved_status,
        "selected_channel": selected_channel,
        "attempted_channels": list(attempted_channels or []),
        "unavailable_channels": list(unavailable_channels or []),
        "accounts_total": total,
        "accounts_completed": completed,
        "accounts_failed": failed,
        "channel_completed_accounts": channel_completed,
        "candidates": [normalize_x_candidate(tweet, report_date) for tweet in tweets],
        "errors": [
            {"source_id": source_id, "handle": handle, "author": name, "error": error}
            for source_id, handle, name, error in failed_accounts
        ],
    }
    if metadata:
        sidecar["metadata"] = dict(metadata)
    return sidecar


def _cookie_pair_from_storage() -> dict[str, str]:
    """Read only auth_token/ct0 from the existing state or explicit cookie env."""
    raw_cookie = os.environ.get("X_TWSCRAPE_COOKIE")
    if raw_cookie:
        pairs = {}
        for part in raw_cookie.split(";"):
            if "=" in part:
                name, value = part.strip().split("=", 1)
                if name in {"auth_token", "ct0"} and value:
                    pairs[name] = value
        if set(pairs) == {"auth_token", "ct0"}:
            return pairs
        raise ChannelUnavailable(
            "X_TWSCRAPE_COOKIE must contain auth_token and ct0; cookie values were not logged"
        )

    if not STORAGE_STATE_FILE.exists():
        raise ChannelUnavailable(
            "twscrape unavailable: x_auth.json is missing and X_TWSCRAPE_COOKIE is not set"
        )
    try:
        state = json.loads(STORAGE_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ChannelUnavailable(f"twscrape cookie state could not be read: {error}") from error
    cookies = state.get("cookies") if isinstance(state, dict) else None
    if not isinstance(cookies, list):
        raise ChannelUnavailable("twscrape cookie state has no cookies list")
    values = {
        item.get("name"): item.get("value")
        for item in cookies
        if isinstance(item, dict) and item.get("name") in {"auth_token", "ct0"}
    }
    if not all(isinstance(values.get(name), str) and values[name] for name in ("auth_token", "ct0")):
        raise ChannelUnavailable("twscrape cookie state lacks auth_token or ct0")
    return {name: values[name] for name in ("auth_token", "ct0")}


def _twscrape_account_name() -> str:
    name = os.environ.get("X_TWSCRAPE_USERNAME", "x_authorized_account").strip()
    if not name or any(character.isspace() for character in name):
        raise ValueError("X_TWSCRAPE_USERNAME must be a non-empty name without whitespace")
    return name


async def _validate_twscrape_pool(pool: Any, expected_username: str) -> None:
    """Fail closed unless the dedicated pool contains zero or one safe account."""
    getter = getattr(pool, "get_all", None)
    if not callable(getter):
        raise ChannelUnavailable("twscrape pool cannot enumerate accounts safely")
    try:
        accounts = await _collect_items(getter())
    except Exception as error:
        if is_twscrape_safety_error(error):
            raise XSafetyStop(f"twscrape account pool safety stop: {error}") from error
        raise ChannelUnavailable(f"twscrape account pool could not be inspected: {error}") from error

    expected = expected_username.casefold()
    usernames: list[str] = []
    for account in accounts:
        username = _get_value(account, "username")
        if not isinstance(username, str) or not username.strip():
            raise ChannelUnavailable("twscrape account pool contains an account without a username")
        if _get_value(account, "proxy"):
            raise ChannelUnavailable("twscrape dedicated account has a proxy configured")
        usernames.append(username.strip())
    if len(usernames) > 1 or any(username.casefold() != expected for username in usernames):
        raise ChannelUnavailable(
            "twscrape dedicated DB contains an unexpected or extra account; refusing to send traffic"
        )


async def _add_cookie_account(pool: Any, username: str, cookies: dict[str, str]) -> None:
    """Add exactly one cookie account; never fall back to password login."""
    adder = getattr(pool, "add_account_cookies", None)
    if not callable(adder):
        raise ChannelUnavailable("twscrape pool has no add_account_cookies API")
    cookie_header = f"auth_token={cookies['auth_token']}; ct0={cookies['ct0']}"
    try:
        signature = inspect.signature(adder)
    except (TypeError, ValueError) as error:
        raise ChannelUnavailable("twscrape account API signature is unavailable") from error
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) < 2 and not any(
        parameter.kind is inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    ):
        raise ChannelUnavailable("twscrape add_account_cookies needs username and cookie header")
    await _maybe_await(adder(username, cookie_header))


def _new_twscrape_api(module: Any, wait_timeout: float) -> Any:
    api_class = getattr(module, "API", None)
    if not callable(api_class):
        raise ChannelUnavailable("twscrape does not expose API")
    try:
        parameters = inspect.signature(api_class).parameters
    except (TypeError, ValueError) as error:
        raise ChannelUnavailable("twscrape API signature is unavailable") from error
    if "raise_when_no_account" not in parameters:
        raise ChannelUnavailable("twscrape API cannot fail closed when no account is available")
    kwargs: dict[str, Any] = {"raise_when_no_account": True}
    if "wait_timeout" in parameters:
        kwargs["wait_timeout"] = wait_timeout
    try:
        return api_class(str(TWSCRAPE_DB), **kwargs)
    except TypeError as error:
        raise ChannelUnavailable("twscrape API could not be initialized safely") from error


async def collect_twscrape(
    report_date: str,
    accounts: list[dict],
    *,
    sleep: Callable[[float], Any] | None = None,
    random_uniform: Callable[[float, float], float] | None = None,
) -> ChannelResult:
    """Use one cookie account and sequential twscrape queries only."""
    if os.environ.get("X_TWSCRAPE_ENABLED", "1").strip().casefold() in {"0", "false", "no", "off"}:
        raise ChannelUnavailable("twscrape is disabled by X_TWSCRAPE_ENABLED")
    if os.environ.get("TWS_HTTP_BACKEND") == "curl":
        raise ChannelUnavailable(
            "twscrape refuses TWS_HTTP_BACKEND=curl for the one-account safety requirement"
        )
    try:
        module = importlib.import_module("twscrape")
    except ModuleNotFoundError as error:
        raise ChannelUnavailable("twscrape is not installed") from error
    delay_config = parse_safe_delay_config()
    limit = max_results_per_query()
    cookies = _cookie_pair_from_storage()
    TWSCRAPE_DB.parent.mkdir(parents=True, exist_ok=True)
    api = _new_twscrape_api(module, min(delay_config.max_seconds, 60.0))
    pool = getattr(api, "pool", None)
    if pool is None:
        raise ChannelUnavailable("twscrape API has no account pool")
    username = _twscrape_account_name()
    await _validate_twscrape_pool(pool, username)
    try:
        await _add_cookie_account(pool, username, cookies)
    except Exception as error:
        if is_twscrape_safety_error(error):
            raise XSafetyStop(f"twscrape account setup safety stop: {error}") from error
        raise
    await _validate_twscrape_pool(pool, username)

    tweets: list[dict] = []
    completed_accounts: list[str] = []
    query_started = False
    for index, account in enumerate(accounts):
        await pace_between_accounts(index, len(accounts), delay_config, sleep, random_uniform)
        query = build_search_query(account["x_handle"], report_date)
        print(f"  twscrape 搜索 @{account['x_handle']} ({account['display_name']})...")
        try:
            search = getattr(api, "search", None)
            if not callable(search):
                raise ChannelUnavailable("twscrape API has no search method")
            query_started = True
            raw_items = await _collect_items(_call_with_supported_kwargs(search, query, limit=limit))
            for raw_item in raw_items[:limit]:
                normalized = normalize_twscrape_tweet(raw_item, account, report_date)
                if normalized is not None:
                    tweets.append(normalized)
            completed_accounts.append(account["source_id"])
        except XNormalizationUnavailable:
            raise
        except ChannelUnavailable:
            raise
        except Exception as error:
            if is_twscrape_safety_error(error):
                raise XSafetyStop(
                    f"twscrape safety stop for @{account['x_handle']}: {error}",
                    tweets=tweets,
                    completed_accounts=completed_accounts,
                    failed_accounts=[(account["source_id"], account["x_handle"], account["display_name"], str(error))],
                ) from error
            if query_started:
                raise XSafetyStop(
                    f"twscrape upstream safety stop for @{account['x_handle']}: {error}",
                    tweets=tweets,
                    completed_accounts=completed_accounts,
                    failed_accounts=[(account["source_id"], account["x_handle"], account["display_name"], str(error))],
                ) from error
            raise ChannelTransient(
                f"twscrape ordinary upstream error for @{account['x_handle']}: {type(error).__name__}: {error}"
            ) from error
    return ChannelResult(
        CHANNEL_TWSCRAPE,
        tweets=tweets,
        completed_accounts=completed_accounts,
        metadata={**delay_config.metadata, "max_results_per_query": limit},
    )




def parse_x_datetime(dt_str: str) -> datetime:
    """解析 X 的 <time datetime> 为带时区的 UTC datetime。"""
    normalized = f"{dt_str[:-1]}+00:00" if dt_str.endswith("Z") else dt_str
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("X datetime must include a timezone")
    return parsed


async def search_account(
    page,
    handle: str,
    name: str,
    date_str: str,
    source_id: str | None = None,
    max_results: int | None = None,
) -> tuple[list[dict], str | None]:
    """搜索单个账号；返回候选和可审计的账号级错误。"""
    limit = max_results_per_query() if max_results is None else max_results
    query = build_search_query(handle, date_str)
    url = "https://x.com/search?" + urlencode({"q": query, "src": "typed_query", "f": "live"})

    print(f"  搜索 @{handle} ({name})...")
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if response is None:
            raise RuntimeError("X search navigation returned no HTTP response")
        if response.status in {401, 403, 429}:
            raise XSafetyStop(f"X search returned safety HTTP {response.status}")
        if response.status >= 400:
            raise RuntimeError(f"X search returned HTTP {response.status}")
        await page.wait_for_timeout(2500)

        if not await is_x_authenticated(page):
            raise XLoginRequired("X redirected the search page to a login/onboarding wall")

        tweets = []
        extraction_errors = []
        articles = (await page.query_selector_all('article[data-testid="tweet"]'))[:limit]

        for index, article in enumerate(articles, start=1):
            try:
                time_el = await article.query_selector("time")
                if not time_el:
                    extraction_errors.append(f"tweet {index}: missing time element")
                    continue
                dt_attr = await time_el.get_attribute("datetime")
                if not dt_attr:
                    extraction_errors.append(f"tweet {index}: missing time datetime")
                    continue

                utc_time = parse_x_datetime(dt_attr)
                bj_time = utc_time.astimezone(TZ_BEIJING)
                if bj_time.strftime("%Y-%m-%d") != date_str:
                    continue

                text_el = await article.query_selector('[data-testid="tweetText"]')
                text = await text_el.inner_text() if text_el else ""
                if not text.strip():
                    extraction_errors.append(f"tweet {index}: missing or empty tweet text")
                    continue

                link_el = await article.query_selector('a[href*="/status/"]')
                href = await link_el.get_attribute("href") if link_el else None
                if not href:
                    extraction_errors.append(f"tweet {index}: missing status URL")
                    continue
                post_url = urljoin("https://x.com", href)

                tweets.append(
                    {
                        "source_id": source_id or f"x-{handle.casefold()}",
                        "author": name,
                        "handle": handle,
                        "utc_time": utc_time.isoformat(),
                        "bj_time": bj_time.isoformat(),
                        "text": text,
                        "url": post_url,
                    }
                )
            except Exception as error:
                extraction_errors.append(f"tweet {index}: {type(error).__name__}: {error}")

        if extraction_errors:
            detail = "; ".join(extraction_errors[:3])
            if len(extraction_errors) > 3:
                detail += f"; and {len(extraction_errors) - 3} more"
            error = f"tweet extraction failed for {len(extraction_errors)} item(s): {detail}"
            print(f"    失败: {error}")
            return tweets, error

        print(f"    {len(tweets)} 条窗口内帖子")
        return tweets, None
    except (XLoginRequired, XSafetyStop):
        raise
    except Exception as error:
        if is_x_safety_error(error):
            raise XSafetyStop(f"X search safety stop for @{handle}: {error}") from error
        detail = f"{type(error).__name__}: {error}"
        print(f"    失败: {detail}")
        return [], detail


async def assert_authenticated(page) -> None:
    """Fail clearly instead of treating an unauthenticated session as zero results."""
    try:
        response = await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
    except Exception as error:
        raise XLoginRequired(f"X home navigation failed: {error}") from error
    if response is None:
        raise XLoginRequired("X home navigation returned no HTTP response")
    if response.status in {401, 403, 429}:
        raise XSafetyStop(f"X home navigation returned safety HTTP {response.status}")
    if response.status >= 400:
        raise XLoginRequired(f"X home navigation returned HTTP {response.status}")
    await page.wait_for_timeout(3000)
    if not await is_x_authenticated(page):
        raise XLoginRequired(
            "X session is missing or expired; run scripts/setup_x_login.py"
        )


async def _validate_context_authentication(context) -> None:
    """Validate a context before exposing it to collection callers."""
    page = await context.new_page()
    try:
        await assert_authenticated(page)
    finally:
        await page.close()


async def _close_context_quietly(context) -> None:
    try:
        await context.close()
    except Exception:
        pass


async def open_x_context(playwright, headless: bool):
    """Use an authenticated persistent profile, with exported auth as a fallback."""
    if not PROFILE_DIR.exists() and not STORAGE_STATE_FILE.exists():
        raise XLoginRequired("No X profile or x_auth.json found; run scripts/setup_x_login.py")

    chrome_executable = resolve_chrome_executable()
    persistent_error = None

    if PROFILE_DIR.exists():
        persistent_options = {
            "user_data_dir": str(PROFILE_DIR),
            "headless": headless,
            "viewport": {"width": 1280, "height": 900},
        }
        if chrome_executable:
            persistent_options["executable_path"] = chrome_executable
        context = None
        try:
            context = await playwright.chromium.launch_persistent_context(**persistent_options)
            await _validate_context_authentication(context)
            print(f"登录会话: authenticated persistent profile ({PROFILE_DIR})")
            return context, None
        except XSafetyStop:
            await _close_context_quietly(context)
            raise
        except Exception as error:
            persistent_error = error
            await _close_context_quietly(context)
            if chrome_executable:
                print(f"persistent Chrome profile unavailable or unauthenticated ({error})，尝试 Playwright Chromium...")
                chromium_options = {
                    key: value for key, value in persistent_options.items() if key != "executable_path"
                }
                context = None
                try:
                    context = await playwright.chromium.launch_persistent_context(**chromium_options)
                    await _validate_context_authentication(context)
                    print(f"登录会话: authenticated persistent profile ({PROFILE_DIR})")
                    return context, None
                except XSafetyStop:
                    await _close_context_quietly(context)
                    raise
                except Exception as chromium_error:
                    persistent_error = chromium_error
                    await _close_context_quietly(context)
            else:
                print(f"persistent profile unavailable or unauthenticated: {error}")

    if not STORAGE_STATE_FILE.exists():
        raise XLoginRequired(
            "X persistent profile could not be opened and x_auth.json is missing; "
            "run scripts/setup_x_login.py"
        ) from persistent_error

    browser_options = {"headless": headless}
    if chrome_executable:
        browser_options["executable_path"] = chrome_executable
    try:
        browser = await playwright.chromium.launch(**browser_options)
    except Exception as error:
        if chrome_executable:
            print(f"Chrome auth fallback unavailable ({error})，使用 Playwright Chromium...")
            browser = await playwright.chromium.launch(
                **{key: value for key, value in browser_options.items() if key != "executable_path"}
            )
        else:
            raise

    try:
        context = await browser.new_context(
            storage_state=str(STORAGE_STATE_FILE),
            viewport={"width": 1280, "height": 900},
        )
    except Exception as error:
        await browser.close()
        raise XLoginRequired(f"x_auth.json could not be loaded: {error}") from error
    print(f"登录会话: exported state fallback ({STORAGE_STATE_FILE})")
    return context, browser


async def collect_playwright(
    report_date: str,
    accounts: list[dict],
    *,
    headless: bool = False,
    sleep: Callable[[float], Any] | None = None,
    random_uniform: Callable[[float, float], float] | None = None,
) -> ChannelResult:
    """Final, existing Playwright channel with sequential conservative pacing."""
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as error:
        raise ChannelUnavailable("Playwright is not installed") from error

    delay_config = parse_safe_delay_config()
    limit = max_results_per_query()
    all_tweets: list[dict] = []
    failed_accounts: list[tuple[str, str, str, str]] = []
    completed_accounts: list[str] = []
    async with async_playwright() as playwright:
        context, browser = await open_x_context(playwright, headless)
        try:
            page = await context.new_page()
            await assert_authenticated(page)
            for index, account in enumerate(accounts):
                await pace_between_accounts(
                    index, len(accounts), delay_config, sleep, random_uniform
                )
                try:
                    tweets, error = await search_account(
                        page,
                        account["x_handle"],
                        account["display_name"],
                        report_date,
                        account["source_id"],
                        limit,
                    )
                except (XLoginRequired, XSafetyStop) as safety_error:
                    raise XSafetyStop(
                        str(safety_error),
                        tweets=all_tweets,
                        failed_accounts=failed_accounts,
                        completed_accounts=completed_accounts,
                    ) from safety_error
                all_tweets.extend(tweets)
                if error:
                    if is_x_safety_error(RuntimeError(error)):
                        raise XSafetyStop(
                            f"Playwright safety stop for @{account['x_handle']}: {error}",
                            tweets=all_tweets,
                            failed_accounts=failed_accounts + [(account["source_id"], account["x_handle"], account["display_name"], str(error))],
                            completed_accounts=completed_accounts,
                        )
                    failed_accounts.append(
                        (account["source_id"], account["x_handle"], account["display_name"], error)
                    )
                else:
                    completed_accounts.append(account["source_id"])
        finally:
            await context.close()
            if browser:
                await browser.close()
    return ChannelResult(
        CHANNEL_PLAYWRIGHT,
        tweets=all_tweets,
        failed_accounts=failed_accounts,
        completed_accounts=completed_accounts,
        status="partial" if failed_accounts else "complete",
        metadata={**delay_config.metadata, "max_results_per_query": limit},
    )


async def run_ordered_channels(
    report_date: str,
    accounts: list[dict],
    *,
    headless: bool = False,
    runners: list[tuple[str, Callable[..., Any]]] | None = None,
    sleep: Callable[[float], Any] | None = None,
    random_uniform: Callable[[float, float], float] | None = None,
) -> tuple[ChannelResult, dict[str, Any]]:
    """Run Playwright, then twscrape for only unfinished accounts."""
    channel_runners = runners or [
        (CHANNEL_PLAYWRIGHT, collect_playwright),
        (CHANNEL_TWSCRAPE, collect_twscrape),
    ]
    pending = {account["source_id"]: account for account in accounts}
    tweets: list[dict] = []
    seen_urls: set[str] = set()
    completed: set[str] = set()
    failed: dict[str, tuple[str, str, str, str]] = {}
    attempted: list[str] = []
    unavailable: list[dict[str, str]] = []
    channel_completed: dict[str, int] = {}
    channel_errors: list[str] = []
    last_channel: str | None = None

    def validate_result_accounts(result: ChannelResult, requested: list[dict]) -> tuple[list[str], list[tuple[str, str, str, str]]]:
        requested_by_id = {account["source_id"]: account for account in requested}
        requested_ids = set(requested_by_id)
        completed_accounts = list(result.completed_accounts)
        if len(set(completed_accounts)) != len(completed_accounts) or any(source_id not in requested_by_id for source_id in completed_accounts):
            raise ChannelUnavailable(f"{result.channel} returned an invalid completed account mapping")
        failures = list(result.failed_accounts)
        failure_ids: set[str] = set()
        for failure in failures:
            if not isinstance(failure, (tuple, list)) or len(failure) != 4 or failure[0] not in requested_by_id or failure[0] in failure_ids or failure[0] in completed_accounts:
                raise ChannelUnavailable(f"{result.channel} returned an invalid failed account mapping")
            failure_ids.add(failure[0])
        if result.status not in {"complete", "partial", "failed"}:
            raise ChannelUnavailable(f"{result.channel} returned an invalid status")
        if result.status == "complete" and (set(completed_accounts) != requested_ids or failures):
            raise ChannelUnavailable(
                f"{result.channel} reported complete without explicitly completing every requested account"
            )
        return completed_accounts, [tuple(failure) for failure in failures]

    def merge_result(channel: str, result: ChannelResult, requested: list[dict], completed_accounts: list[str], failures: list[tuple[str, str, str, str]]) -> None:
        nonlocal last_channel
        last_channel = channel
        for tweet in result.tweets:
            url = tweet.get("url") if isinstance(tweet, dict) else None
            key = _normalise_post_url(url) if isinstance(url, str) else None
            if key and key not in seen_urls:
                seen_urls.add(key)
                tweets.append(tweet)
        explicit = set(completed_accounts) & set(pending)
        completed.update(explicit)
        for failure in failures:
            failed[failure[0]] = failure
            channel_errors.append(f"{channel} @{failure[1]}: {failure[3]}")
        channel_completed[channel] = channel_completed.get(channel, 0) + len(explicit)
        if result.error:
            channel_errors.append(f"{channel}: {result.error}")
        for source_id in explicit:
            pending.pop(source_id, None)
            failed.pop(source_id, None)

    for channel, runner in channel_runners:
        if not pending:
            break
        attempted.append(channel)
        requested = list(pending.values())
        try:
            runner_kwargs = {"sleep": sleep}
            if random_uniform is not None:
                runner_kwargs["random_uniform"] = random_uniform
            if channel == CHANNEL_PLAYWRIGHT:
                runner_kwargs["headless"] = headless
            result = await _maybe_await(
                _call_with_supported_kwargs(runner, report_date, requested, **runner_kwargs)
            )
            if not isinstance(result, ChannelResult):
                raise ChannelUnavailable(f"{channel} returned an invalid channel result")
            reported_completed, reported_failures = validate_result_accounts(result, requested)
            safety_failures = [failure for failure in reported_failures if is_x_safety_error(RuntimeError(failure[3]))]
            safety_error = result.error if result.error and is_x_safety_error(RuntimeError(result.error)) else None
            if safety_failures or safety_error:
                raise XSafetyStop(
                    safety_error or f"{channel} safety stop for @{safety_failures[0][1]}: {safety_failures[0][3]}",
                    tweets=tweets + list(result.tweets),
                    completed_accounts=sorted(completed | set(reported_completed)),
                    failed_accounts=reported_failures,
                )
            merge_result(channel, result, requested, reported_completed, reported_failures)
        except XSafetyStop as error:
            requested_ids = {account["source_id"] for account in requested}
            safety_completed = set(error.completed_accounts) & requested_ids
            completed.update(safety_completed)
            if safety_completed:
                channel_completed[channel] = channel_completed.get(channel, 0) + len(safety_completed)
            for failure in error.failed_accounts:
                failed[failure[0]] = failure
            for account in requested:
                if account["source_id"] not in completed and account["source_id"] not in failed:
                    failed[account["source_id"]] = (account["source_id"], account["x_handle"], account["display_name"], str(error))
            for tweet in error.tweets:
                url = tweet.get("url", "") if isinstance(tweet, dict) else ""
                key = _normalise_post_url(url) if isinstance(url, str) else ""
                if key and key not in seen_urls:
                    seen_urls.add(key)
                    tweets.append(tweet)
            channel_errors.append(f"{channel}: {error}")
            last_channel = channel
            break
        except (ChannelUnavailable, ChannelTransient) as error:
            unavailable.append({"channel": channel, "error": str(error)})
            continue
        except XLoginRequired as error:
            for account in requested:
                failed[account["source_id"]] = (account["source_id"], account["x_handle"], account["display_name"], str(error))
            channel_errors.append(f"{channel}: {error}")
            last_channel = channel
            break
        except Exception as error:
            text = f"{type(error).__name__}: {error}"
            if is_x_safety_error(error) or (channel == CHANNEL_TWSCRAPE and is_twscrape_safety_error(error)):
                for account in requested:
                    failed[account["source_id"]] = (account["source_id"], account["x_handle"], account["display_name"], text)
                channel_errors.append(f"{channel}: {text}")
                last_channel = channel
                break
            unavailable.append({"channel": channel, "error": text})

    if pending and attempted:
        for account in pending.values():
            if account["source_id"] not in failed and account["source_id"] not in completed:
                failed[account["source_id"]] = (
                    account["source_id"], account["x_handle"], account["display_name"],
                    "all remaining X channels unavailable",
                )
    if not pending:
        status = "complete"
    elif completed:
        status = "partial"
    else:
        status = "failed"
    if not attempted:
        status = "failed"
    outcome = ChannelResult(
        last_channel or (attempted[-1] if attempted else CHANNEL_PLAYWRIGHT),
        tweets=tweets,
        failed_accounts=list(failed.values()),
        status=status,
        error="; ".join(channel_errors) if channel_errors else ("all X collection channels were unavailable" if status == "failed" else None),
        completed_accounts=sorted(completed),
        metadata={"channel_completed_accounts": channel_completed, "channel_errors": channel_errors},
    )
    completed_channels = [
        channel for channel in X_CHANNEL_ORDER
        if channel in attempted and channel_completed.get(channel, 0) > 0
    ]
    selected = "+".join(completed_channels) if completed_channels else None
    return outcome, {
        "selected_channel": selected,
        "attempted_channels": attempted,
        "unavailable_channels": unavailable,
        "channel_completed_accounts": channel_completed,
        "channel_errors": channel_errors,
    }


async def main(
    date_str: str,
    headless: bool = False,
    overwrite: bool = False,
    output_suffix: str = "",
):
    report_date = parse_report_date(date_str).isoformat()
    if output_suffix and not re.fullmatch(r"[A-Za-z0-9_-]+", output_suffix):
        raise ValueError("output suffix may contain only letters, numbers, underscores, and hyphens")

    output_dir = PROJECT_ROOT / "x_outputs"
    output_dir.mkdir(exist_ok=True)
    suffix = f"_{output_suffix}" if output_suffix else ""
    output_file = output_dir / f"{report_date}_x_raw_materials{suffix}.txt"
    structured_file = sidecar_path(output_file)
    if (output_file.exists() or structured_file.exists()) and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing X raw materials or sidecar: {output_file}. "
            "Move it aside or use a new report date after confirming the workflow state."
        )

    registry = load_registry()
    all_accounts = get_x_accounts(registry)
    official_count = sum(
        account.get("category") == "official/company account" for account in all_accounts
    )
    print(f"X 供需搜索 — 目标日期: {report_date}")
    print(f"种子账号: {len(all_accounts) - official_count} 个人 + {official_count} 官方")
    print(f"搜索词: {SEARCH_QUERY}")
    print()

    outcome, channel_metadata = await run_ordered_channels(
        report_date,
        all_accounts,
        headless=headless,
    )
    all_tweets = outcome.tweets
    failed_accounts = outcome.failed_accounts
    metadata = dict(outcome.metadata)
    if outcome.error:
        metadata["channel_error"] = outcome.error
    selected_channel = channel_metadata.get("selected_channel")
    attempted_channels = channel_metadata.get("attempted_channels", [])
    unavailable_channels = channel_metadata.get("unavailable_channels", [])
    status = outcome.status
    method = selected_channel or "none (all channels unavailable)"
    output = [
        f"X 原始候选 — {report_date}\n",
        f"采集时间: {datetime.now(TZ_BEIJING).isoformat()}\n",
        f"选定通道: {method}\n",
        f"尝试通道: {', '.join(attempted_channels) or '无'}\n",
        f"不可用通道: {', '.join(item['channel'] for item in unavailable_channels) or '无'}\n",
        "采集方法: ordered Playwright -> twscrape\n",
        f"搜索词: {SEARCH_QUERY}\n",
        f"账号批次: {len(all_accounts) - official_count} 个人 + {official_count} 官方\n",
        f"账号审计: {len(outcome.completed_accounts)}/{len(all_accounts)} 完成，失败 {len(failed_accounts)}\n",
        f"各通道完成账户数: {json.dumps(channel_metadata.get('channel_completed_accounts', {}), ensure_ascii=False, sort_keys=True)}\n",
        f"采集状态: {status}\n",
        f"失败账号数: {len(failed_accounts)}\n",
    ]
    if unavailable_channels:
        output.append("通道不可用原因:\n")
        for item in unavailable_channels:
            output.append(f"  {item['channel']}: {item['error']}\n")
    if outcome.error:
        output.append(f"通道错误: {outcome.error}\n")
    if failed_accounts:
        output.append("失败账号:\n")
        for _source_id, handle, name, error in failed_accounts:
            output.append(f"  @{handle} ({name}): {error}\n")
    else:
        output.append("失败账号: 无\n")
    output.extend(
        [
            "=" * 60 + "\n\n",
            f"总计候选: {len(all_tweets)} 条\n\n",
            "=" * 60 + "\n\n",
        ]
    )

    for index, tweet in enumerate(all_tweets, 1):
        precision = tweet.get("published_at_precision")
        if precision == "query_date":
            utc_display = f"{tweet['published_at']} (query_date; exact time unavailable)"
            bj_display = utc_display
        else:
            utc_display = tweet.get("utc_time", "unavailable")
            bj_display = tweet.get("bj_time", "unavailable")
        output.extend(
            [
                f"[{index}] @{tweet['handle']} ({tweet['author']})\n",
                f"    UTC: {utc_display}\n",
                f"    北京: {bj_display}\n",
                f"    文本: {tweet['text']}\n",
                f"    链接: {tweet['url']}\n",
                "\n",
            ]
        )

    atomic_write_text(output_file, "".join(output), overwrite=overwrite)
    atomic_write_json(
        structured_file,
        build_sidecar(
            report_date,
            all_tweets,
            failed_accounts,
            status=status,
            selected_channel=selected_channel,
            attempted_channels=attempted_channels,
            unavailable_channels=unavailable_channels,
            metadata=metadata,
            accounts_total=len(all_accounts),
            accounts_completed=len(outcome.completed_accounts),
            channel_completed_accounts=channel_metadata.get("channel_completed_accounts", {}),
        ),
    )
    if status == "failed":
        if outcome.error and "login" in outcome.error.casefold():
            raise XLoginRequired(outcome.error)
        raise XCollectionFailure(outcome.error or "all X collection channels failed")
    if status == "partial":
        print(f"\n部分完成: {len(all_tweets)} 条候选 -> {output_file}")
        raise XPartialFailure(outcome.error or "X collection stopped after a partial result")

    print(f"\n完成: {len(all_tweets)} 条候选 -> {output_file}")
    return output_file


async def check_login(headless: bool = True):
    """Check the active X profile without creating or changing report files."""
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        context, browser = await open_x_context(playwright, headless)
        try:
            page = await context.new_page()
            await assert_authenticated(page)
            print("X login check passed: authenticated home navigation is available")
        finally:
            await context.close()
            if browser:
                await browser.close()


if __name__ == "__main__":
    if "--check-login" in sys.argv:
        try:
            asyncio.run(check_login(headless=True))
        except XLoginRequired as error:
            print(f"X login required: {error}", file=sys.stderr)
            sys.exit(2)
        except XSafetyStop as error:
            print(f"X safety stop: {error}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    if len(sys.argv) < 2:
        python_path = "C:/Users/Zhemin/.codex/tools/browser-use/Scripts/python.exe"
        print(f"用法: {python_path} scripts/x_search.py <DATE> [--headless]")
        print(f"示例: {python_path} scripts/x_search.py 2026-07-13")
        print(f"      {python_path} scripts/x_search.py 2026-07-13 --headless")
        sys.exit(1)

    date = sys.argv[1]
    headless = "--headless" in sys.argv
    overwrite = "--overwrite" in sys.argv
    output_suffix = ""
    for index, argument in enumerate(sys.argv[2:], start=2):
        if argument.startswith("--output-suffix="):
            output_suffix = argument.split("=", 1)[1]
        elif argument == "--output-suffix" and index + 1 < len(sys.argv):
            output_suffix = sys.argv[index + 1]
        elif argument == "--web-access-input" or argument.startswith("--web-access-input="):
            print("unsupported option --web-access-input; use Playwright -> twscrape", file=sys.stderr)
            sys.exit(1)
    try:
        asyncio.run(main(date, headless, overwrite, output_suffix))
    except XLoginRequired as error:
        print(f"X login required: {error}", file=sys.stderr)
        sys.exit(2)
    except XCollectionFailure as error:
        print(f"X collection failed: {error}", file=sys.stderr)
        sys.exit(5)
    except FileExistsError as error:
        print(f"X raw-material output already exists: {error}", file=sys.stderr)
        sys.exit(3)
    except XPartialFailure as error:
        print(f"X raw-material collection partial: {error}", file=sys.stderr)
        sys.exit(4)

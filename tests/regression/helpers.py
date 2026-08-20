"""Shared helpers for the tests/regression harness (hq-gbl.2).

These are small, dependency-light utilities used by conftest.py and the
regression tests themselves: unique naming, structured-content lookups,
error-shape assertions, and a read-after-write polling helper for the
Things URL-scheme lag documented in CLAUDE.md / REGRESSION_SPIKE_FINDINGS.md.
"""
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

SANDBOX_PREFIX = "hq-gbl-reg "


def ts() -> str:
    """A unique, sortable UTC timestamp suffix for sandbox object names."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def sandbox_title(name: str) -> str:
    """Prefix a name with the sandbox marker so it's trivially identifiable
    (and sweepable) as a regression-harness object.

    Example: sandbox_title("project") -> "hq-gbl-reg project <ts>"
    """
    return f"{SANDBOX_PREFIX}{name} {ts()}"


def items_by_uuid(structured: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Index a list-tool's structured_content['items'] by uuid.

    Works for both the {"items": [...]} list envelope and the
    {"item": {...}} single-item envelope (the latter is wrapped in a
    single-entry dict keyed by its own uuid).
    """
    if "items" in structured:
        return {item["uuid"]: item for item in structured["items"] if "uuid" in item}
    if "item" in structured and "uuid" in structured["item"]:
        return {structured["item"]["uuid"]: structured["item"]}
    return {}


def read_back(
    todo_id: str,
    predicate: Callable[[Optional[Dict[str, Any]]], bool],
    timeout: float = 20.0,
    interval: float = 0.25,
) -> Optional[Dict[str, Any]]:
    """Poll things.py for `todo_id` until `predicate(record)` is true or
    `timeout` elapses; returns the last-seen record (possibly None).

    Things URL-scheme writes (things:///add, things:///update, things:///json)
    are processed asynchronously - things.py reads directly from Things'
    local SQLite database and can lag such a write by a second or more (see
    CLAUDE.md and REGRESSION_SPIKE_FINDINGS.md's step-4 measurements, which
    saw one outlier as high as ~18.65s) - default timeout is set generously
    (20s) per that finding rather than the originally-documented 3s poll
    window.
    """
    import things

    deadline = time.monotonic() + timeout
    record: Optional[Dict[str, Any]] = None
    while True:
        try:
            record = things.get(todo_id, trashed=None)
        except TypeError:
            # area/tag ids: things.get(..., trashed=None) raises TypeError
            # (trashed isn't accepted by areas()/tags()) - retry bare.
            record = things.get(todo_id)
        if predicate(record):
            return record
        if time.monotonic() >= deadline:
            return record
        time.sleep(interval)


def assert_read_error(result: Dict[str, Any], code: str) -> None:
    """Assert a read-tool structured error: success False, exact lower_snake
    'error' code, and a non-empty string 'message'."""
    assert result.get("success") is False, f"expected success=False, got {result!r}"
    assert result.get("error") == code, (
        f"expected error code {code!r}, got {result.get('error')!r} (full: {result!r})"
    )
    message = result.get("message")
    assert isinstance(message, str) and message, (
        f"expected non-empty string 'message', got {message!r} (full: {result!r})"
    )


def assert_write_error(result: Dict[str, Any], code: str) -> None:
    """Assert a write-tool structured error: success False, exact
    UPPER_SNAKE_CASE 'error' code, and a non-empty string 'message'."""
    assert result.get("success") is False, f"expected success=False, got {result!r}"
    assert result.get("error") == code, (
        f"expected error code {code!r}, got {result.get('error')!r} (full: {result!r})"
    )
    message = result.get("message")
    assert isinstance(message, str) and message, (
        f"expected non-empty string 'message', got {message!r} (full: {result!r})"
    )


def track_ids(existing: List[str], *ids: Optional[str]) -> None:
    """Append any non-empty ids in `ids` to `existing`, in place."""
    for item_id in ids:
        if item_id:
            existing.append(item_id)

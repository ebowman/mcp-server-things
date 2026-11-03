"""hq-ov3: _collect_minimal_uuids fails loudly on incomplete unpaged reads."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regression import test_seed_oracle as so  # noqa: E402


class FakeMCP:
    def __init__(self, fn):
        self.fn = fn
        self.calls = []

    def call_sync(self, tool, **kwargs):
        self.calls.append((tool, kwargs))
        return self.fn(**kwargs)


def _items(*ids):
    return [{"uuid": i} for i in ids]


def test_unpaged_complete():
    mcp = FakeMCP(lambda **k: {"items": _items("a", "b"), "count": 2, "total": 2})
    assert so._collect_minimal_uuids(mcp, "get_x", {}) == {"a", "b"}


def test_unpaged_total_exceeds_count():
    mcp = FakeMCP(lambda **k: {"items": _items("a"), "total": 5})
    with pytest.raises(AssertionError, match="get_due_in_days"):
        so._collect_minimal_uuids(mcp, "get_due_in_days", {"limit": 1})


def test_unpaged_truncated():
    mcp = FakeMCP(lambda **k: {"items": _items("a"), "total": 1, "truncated": True})
    with pytest.raises(AssertionError, match="get_recent"):
        so._collect_minimal_uuids(mcp, "get_recent", {})


def test_unpaged_missing_total_tolerated():
    mcp = FakeMCP(lambda **k: {"items": _items("a", "b")})
    assert so._collect_minimal_uuids(mcp, "get_x", {}) == {"a", "b"}


def test_paged_two_pages():
    def fn(offset=0, **k):
        if offset == 0:
            return {"items": _items("a", "b"), "total": 3, "next_offset": 2}
        return {"items": _items("c"), "total": 3}

    assert so._collect_minimal_uuids(
        FakeMCP(fn), "get_anytime", {}, paged=True) == {"a", "b", "c"}


def test_paged_never_ending(monkeypatch):
    monkeypatch.setattr(so, "_MAX_PAGES", 3)

    def fn(offset=0, **k):
        return {"items": _items(f"u{offset}"), "total": 999, "next_offset": offset + 1}

    mcp = FakeMCP(fn)
    with pytest.raises(AssertionError, match="still paging"):
        so._collect_minimal_uuids(mcp, "get_anytime", {}, paged=True)
    assert len(mcp.calls) == 3

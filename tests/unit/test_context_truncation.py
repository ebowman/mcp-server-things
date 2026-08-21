"""Tests for hq-cal.2: deterministic (non-relevance-ranked) budget truncation,
plus the explicit truncated/truncation_hint envelope signal.

Bug: ContextAwareResponseManager.optimize_response silently dropped items via
relevance-ranked pagination when the ~80KB response budget was exceeded, even
when the caller passed no explicit `limit`. `total` reported the full
pre-truncation count, but the dropped items were unreachable (list tools have
no `offset`). This file pins:
  1. Truncation preserves original item order (deterministic prefix, no
     relevance re-ranking).
  2. The envelope carries `truncated: True` and a `truncation_hint` string
     (in `meta`) iff truncation actually fired.
  3. `ThingsMCPServer._read_result` propagates `truncated`/`truncation_hint`
     to the top level of structured_content when present, and omits them
     entirely (not False) when truncation did not fire.
"""

from things_mcp.context_manager import (
    ContextAwareResponseManager,
    ContextBudget,
    ResponseMode,
)
from things_mcp.server import ThingsMCPServer


def _make_item(i: int, note_size: int = 500) -> dict:
    """A synthetic todo-shaped item, ordered by `i`, with padded notes so a
    list of these items can be made to exceed the response budget."""
    return {
        "uuid": f"id-{i:05d}",
        "title": f"Todo {i}",
        "type": "to-do",
        "status": "incomplete",
        "notes": "x" * note_size,
        "dueDate": None,
        "modificationDate": "2026-08-01 10:00:00",
        "creationDate": "2026-08-01 10:00:00",
        "tags": [],
        "project": None,
        "projectTitle": None,
        "heading": None,
        "headingTitle": None,
        "start": "Anytime",
        "startDate": None,
        "inheritedSomeday": False,
        "reminderTime": None,
    }


def _small_budget_manager() -> ContextAwareResponseManager:
    """A manager with a tiny budget so a modest synthetic list reliably
    exceeds it, without needing thousands of items."""
    return ContextAwareResponseManager(ContextBudget(max_response_size=5_000))


class TestDeterministicTruncation:
    def test_oversized_list_truncates_to_prefix_in_original_order(self):
        """Given a synthetic oversized list, optimize_response must return a
        prefix of the input in its original order - not a relevance-ranked
        re-ordering."""
        manager = _small_budget_manager()
        items = [_make_item(i) for i in range(200)]

        response = manager.optimize_response(
            items, "get_anytime", ResponseMode.STANDARD, {}
        )

        assert response["meta"]["truncated"] is True
        returned = response["data"]
        assert len(returned) < len(items)

        # Deterministic prefix: returned items' uuids must equal the first-N
        # uuids of the original input, in the same order.
        expected_prefix = [item["uuid"] for item in items[: len(returned)]]
        actual = [item["uuid"] for item in returned]
        assert actual == expected_prefix

    def test_truncated_envelope_carries_hint_and_correct_counts(self):
        manager = _small_budget_manager()
        items = [_make_item(i) for i in range(200)]

        response = manager.optimize_response(
            items, "get_anytime", ResponseMode.STANDARD, {}
        )

        meta = response["meta"]
        assert meta["truncated"] is True
        assert isinstance(meta["truncation_hint"], str) and meta["truncation_hint"]
        assert meta["count"] == len(response["data"])
        assert meta["total"] == len(items)
        assert meta["count"] < meta["total"]

    def test_under_budget_list_has_no_truncated_key(self):
        """A list that fits within budget must not carry a truncated key at
        all (absent, not False)."""
        manager = ContextAwareResponseManager(ContextBudget(max_response_size=80_000))
        items = [_make_item(i, note_size=10) for i in range(5)]

        response = manager.optimize_response(
            items, "get_anytime", ResponseMode.STANDARD, {}
        )

        assert "truncated" not in response["meta"]
        assert "truncation_hint" not in response["meta"]
        assert response["meta"]["count"] == len(items)


class TestReadResultTruncationPropagation:
    def test_read_result_surfaces_truncated_and_hint_at_top_level(self):
        server = ThingsMCPServer()
        synthetic_response = {
            "data": [{"uuid": "1", "title": "a"}, {"uuid": "2", "title": "b"}],
            "meta": {
                "mode": "standard",
                "count": 2,
                "total": 500,
                "truncated": True,
                "more": 498,
                "truncation_hint": "Response exceeded the size budget; 2 of 500 items returned.",
            },
        }

        result = server._read_result(synthetic_response, mode="standard", total=500)

        assert result["truncated"] is True
        assert result["truncation_hint"] == (
            "Response exceeded the size budget; 2 of 500 items returned."
        )
        assert result["count"] == 2
        assert result["total"] == 500

    def test_read_result_omits_truncated_key_when_not_truncated(self):
        server = ThingsMCPServer()
        synthetic_response = {
            "data": [{"uuid": "1", "title": "a"}],
            "meta": {"mode": "standard", "count": 1},
        }

        result = server._read_result(synthetic_response, mode="standard", total=1)

        assert "truncated" not in result
        assert "truncation_hint" not in result

    def test_read_result_list_input_never_carries_truncated_key(self):
        """The raw-list branch of _read_result (tools that bypass
        optimize_response entirely) has no meta to inspect and must never
        fabricate a truncated key."""
        server = ThingsMCPServer()
        items = [{"uuid": "1", "title": "a"}]

        result = server._read_result(items, mode="standard", total=1)

        assert "truncated" not in result
        assert "truncation_hint" not in result

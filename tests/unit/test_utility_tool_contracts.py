"""hq-gbl.16: Unit tests (mocked) for health_check, queue_status,
context_stats, get_server_capabilities, and get_usage_recommendations
failure-branch contracts, plus get_usage_recommendations's get_todos
dataset-size branching.

Per CLAUDE.md's "Structured error contract" section, these five are
utility/diagnostic tools: on failure they return a best-effort diagnostic
payload with a top-level 'error' string and NO 'success' key at all - not
the read-tool ({"success": false, "error": "<snake_case>"}) or write-tool
({"success": false, "error": "<UPPER_SNAKE>"}) structured-error contract.
This file patches the underlying calls each tool makes to raise, and
asserts exactly that best-effort shape (error key present, success key
absent, plus each tool's documented fallback key(s)).

Follows the same Client(server.mcp) + mocked ThingsTools pattern as
tests/unit/test_structured_output.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastmcp import Client

from things_mcp.server import ThingsMCPServer


def _make_server_with_mock_tools(**overrides):
    """Create a ThingsMCPServer with a MagicMock ThingsTools layer.

    Mirrors tests/unit/test_structured_output.py's helper of the same name.
    """
    server = ThingsMCPServer()
    mock_tools = MagicMock()
    mock_tools.tag_validation_service = None
    for method_name, return_value in overrides.items():
        setattr(mock_tools, method_name, AsyncMock(return_value=return_value))
    server.tools = mock_tools
    return server


async def _call(server, tool_name, **kwargs):
    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(tool_name, kwargs)
    return result.structured_content


def _assert_no_success_key_with_error(payload):
    assert isinstance(payload, dict), payload
    assert "error" in payload, payload
    assert "success" not in payload, payload


# ---------------------------------------------------------------------------
# health_check failure branch
# ---------------------------------------------------------------------------


class TestHealthCheckFailure:
    @pytest.mark.asyncio
    async def test_is_things_running_raises(self):
        server = _make_server_with_mock_tools()
        with patch.object(
            server.applescript_manager,
            "is_things_running",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            payload = await _call(server, "health_check")

        _assert_no_success_key_with_error(payload)
        assert payload["server_status"] == "unhealthy"
        assert payload["error"] == "boom"
        assert isinstance(payload.get("timestamp"), str) and payload["timestamp"]


# ---------------------------------------------------------------------------
# queue_status failure branch
# ---------------------------------------------------------------------------


class TestQueueStatusFailure:
    @pytest.mark.asyncio
    async def test_get_operation_queue_raises(self):
        server = _make_server_with_mock_tools()
        with patch(
            "things_mcp.server.get_operation_queue",
            AsyncMock(side_effect=RuntimeError("queue boom")),
        ):
            payload = await _call(server, "queue_status")

        _assert_no_success_key_with_error(payload)
        assert payload["error"] == "queue boom"
        assert isinstance(payload.get("timestamp"), str) and payload["timestamp"]


# ---------------------------------------------------------------------------
# context_stats failure branch
# ---------------------------------------------------------------------------


class TestContextStatsFailure:
    @pytest.mark.asyncio
    async def test_get_context_usage_stats_raises(self):
        server = _make_server_with_mock_tools()
        with patch.object(
            server.context_manager,
            "get_context_usage_stats",
            side_effect=RuntimeError("context boom"),
        ):
            payload = await _call(server, "context_stats")

        _assert_no_success_key_with_error(payload)
        assert payload["error"] == "context boom"
        assert payload.get("context_management") == (
            "Context awareness is active but stats unavailable"
        )


# ---------------------------------------------------------------------------
# get_server_capabilities failure branch
# ---------------------------------------------------------------------------


class TestServerCapabilitiesFailure:
    @pytest.mark.asyncio
    async def test_registered_tool_count_raises(self):
        server = _make_server_with_mock_tools()
        with patch.object(
            server,
            "_registered_tool_count",
            AsyncMock(side_effect=RuntimeError("capabilities boom")),
        ):
            payload = await _call(server, "get_server_capabilities")

        _assert_no_success_key_with_error(payload)
        assert payload["error"] == "capabilities boom"
        fallback = payload.get("fallback_info")
        assert isinstance(fallback, dict), payload
        for key in ("server_name", "basic_functionality", "capabilities_discovery"):
            assert key in fallback, f"fallback_info missing {key!r}: {fallback!r}"


# ---------------------------------------------------------------------------
# get_usage_recommendations failure branch
# ---------------------------------------------------------------------------


class TestUsageRecommendationsFailure:
    @pytest.mark.asyncio
    async def test_get_context_usage_stats_raises(self):
        """The outer try/except wraps the whole handler, so a raise from
        context_manager.get_context_usage_stats() (called unconditionally,
        near the top, before the operation-specific branches) is caught by
        the same outer except and produces the tool's own documented
        fallback shape."""
        server = _make_server_with_mock_tools()
        with patch.object(
            server.context_manager,
            "get_context_usage_stats",
            side_effect=RuntimeError("recs boom"),
        ):
            payload = await _call(server, "get_usage_recommendations")

        _assert_no_success_key_with_error(payload)
        assert payload["error"] == "recs boom"
        fallback = payload.get("fallback_recommendations")
        assert isinstance(fallback, dict), payload
        assert fallback.get("safe_defaults") == {
            "mode": "auto",
            "limit": 25,
            "include_items": False,
        }
        assert "guidance" in fallback, fallback


# ---------------------------------------------------------------------------
# get_usage_recommendations's get_todos branch: dataset-size thresholds
# (0 / <=10 / <=50 / >50), sampled via self.tools.get_todos(None, False).
# ---------------------------------------------------------------------------


class TestUsageRecommendationsGetTodosBranch:
    async def _get_todos_recommendation(self, todo_count):
        todos = [{"uuid": f"id{i}"} for i in range(todo_count)]
        server = _make_server_with_mock_tools(get_todos=todos)
        payload = await _call(
            server, "get_usage_recommendations", operation="get_todos"
        )
        assert "get_todos" in payload, payload
        return payload["get_todos"]

    @pytest.mark.asyncio
    async def test_zero_todos(self):
        rec = await self._get_todos_recommendation(0)
        assert rec["suggested_mode"] == "standard"
        assert rec["reason"] == "No todos found - standard mode provides complete view"
        assert rec["next_actions"] == ["Check get_inbox()", "Try get_projects()"]
        assert rec["estimated_response_size_kb"] == 0.1

    @pytest.mark.asyncio
    async def test_ten_or_fewer_todos(self):
        rec = await self._get_todos_recommendation(10)
        assert rec["suggested_mode"] == "detailed"
        assert rec["suggested_limit"] is None
        assert rec["reason"] == "Small dataset - detailed mode is safe"
        assert rec["estimated_response_size_kb"] == pytest.approx(10 * 1.2)
        assert rec["include_items"] == "optional"

    @pytest.mark.asyncio
    async def test_fifty_or_fewer_todos(self):
        rec = await self._get_todos_recommendation(50)
        assert rec["suggested_mode"] == "standard"
        assert rec["suggested_limit"] == 30
        assert rec["reason"] == "Medium dataset - standard mode with limit"
        assert rec["estimated_response_size_kb"] == 30
        assert rec["include_items"] is False

    @pytest.mark.asyncio
    async def test_more_than_fifty_todos(self):
        rec = await self._get_todos_recommendation(51)
        assert rec["suggested_mode"] == "summary"
        assert rec["suggested_limit"] is None
        assert rec["reason"] == "Large dataset detected - start with summary"
        assert rec["estimated_response_size_kb"] == 2
        assert rec["next_steps"] == "Use summary insights to decide on detailed queries"
        assert rec["include_items"] is False

    @pytest.mark.asyncio
    async def test_get_todos_sampling_raises_falls_back_to_auto(self):
        """A failure specific to the get_todos sampling call (not the outer
        try/except) is caught by its own inner try/except and produces a
        degraded-but-successful 'auto' recommendation, not the tool-level
        fallback_recommendations shape."""
        server = _make_server_with_mock_tools()
        server.tools.get_todos = AsyncMock(side_effect=RuntimeError("sample boom"))

        payload = await _call(
            server, "get_usage_recommendations", operation="get_todos"
        )

        assert "fallback_recommendations" not in payload, payload
        rec = payload["get_todos"]
        assert rec["suggested_mode"] == "auto"
        assert rec["fallback"] is True
        assert rec["error"] == "sample boom"

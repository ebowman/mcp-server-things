"""hq-gbl.16: Regression (live) for health_check, queue_status, context_stats,
get_server_capabilities, and get_usage_recommendations.

These five tools are pure server-introspection/diagnostics - they take no
sandbox object ids and never write to Things - so this file does not use the
`sandbox`/`seeded` fixtures. It exercises them through the real MCP tool
boundary (the `mcp` fixture) against the real live server, matching the rest
of tests/regression.

Per CLAUDE.md, these are "Utility/diagnostic tools" - on failure they return
a best-effort diagnostic payload with a top-level 'error' string and NO
'success' key at all (not the read/write structured-error contract). This
file's happy-path assertions are therefore about the tools' own documented
success-path fields, not the read/write error contract; the failure-path
('error' key present, no 'success' key) is covered by the companion unit
file test_utility_tool_contracts.py, which mocks the underlying calls to
raise.

Discovered (not fixed - out of scope for this bead): `queue_status` and
`get_server_capabilities` both call `operation_queue.get_operation_queue()`,
which lazily creates a module-level singleton `OperationQueue` and starts an
`asyncio.create_task(...)` worker bound to whichever event loop was running
at the time. `queue_status`/`get_server_capabilities`.get_queue_status's
`_worker_task.done()` check on that task from a *different* (later,
freshly-created) event loop hangs indefinitely rather than raising -
reproduced live outside pytest with as few as two sequential
`asyncio.run(...)`-wrapped calls to either tool. This file therefore calls
`queue_status` and `get_server_capabilities` (and any other tool that
transitively touches the operation queue) each exactly ONCE, and batches
every call that touches the queue into a single shared event loop (one
`async def test_...` coroutine, one implicit asyncio.run via
pytest-asyncio) rather than the usual one-`mcp.call_sync`-per-test pattern
used elsewhere in this suite (each of which is its own asyncio.run(), i.e.
its own event loop) - see the task report's "Discovered" note for the
filed followup.
"""
from datetime import datetime

import pytest

pytestmark = pytest.mark.live


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_healthy_shape(self, mcp):
        result = mcp.call_sync("health_check")
        assert result.get("server_status") == "healthy", result
        assert result.get("things_running") is True, result
        assert result.get("applescript_available") is True, result
        timestamp = result.get("timestamp")
        assert isinstance(timestamp, str) and timestamp, result
        # Must be ISO-parseable (datetime.now().isoformat() format).
        datetime.fromisoformat(timestamp)


# ---------------------------------------------------------------------------
# context_stats
# ---------------------------------------------------------------------------


class TestContextStats:
    def test_keys_and_optimization_status(self, mcp):
        result = mcp.call_sync("context_stats")
        for key in (
            "total_budget_kb",
            "max_response_size_kb",
            "warning_threshold_kb",
            "available_for_response_kb",
            "reserved_for_reasoning_pct",
        ):
            assert key in result, f"context_stats missing {key!r}: {result!r}"

        optimization_status = result.get("optimization_status")
        assert isinstance(optimization_status, dict), result
        expected_booleans = {
            "auto_mode_enabled": True,
            "smart_defaults_active": True,
            "context_aware_responses": True,
            "dynamic_field_filtering": True,
        }
        assert optimization_status == expected_booleans, optimization_status

        recommendations = result.get("recommendations")
        assert isinstance(recommendations, list) and recommendations, result
        assert all(isinstance(r, str) for r in recommendations), recommendations


# ---------------------------------------------------------------------------
# get_usage_recommendations
#
# None of these branches touch the operation queue, so each can safely use
# the usual one-call-per-test call_sync pattern (each its own event loop).
# ---------------------------------------------------------------------------


class TestUsageRecommendations:
    def test_no_operation_general_branch(self, mcp):
        result = mcp.call_sync("get_usage_recommendations")
        assert "general" in result, result
        general = result["general"]
        for key in ("discovery_workflow", "performance_tips", "error_prevention"):
            assert key in general, f"general missing {key!r}: {general!r}"
        assert "context_guidance" in result, result
        assert "system_status" in result, result

    def test_get_todos_operation_branch(self, mcp):
        result = mcp.call_sync("get_usage_recommendations", operation="get_todos")
        assert "get_todos" in result, result
        op = result["get_todos"]
        assert "suggested_mode" in op, op
        assert "reason" in op, op

    def test_bulk_move_records_operation_branch(self, mcp):
        result = mcp.call_sync(
            "get_usage_recommendations", operation="bulk_move_records"
        )
        assert "bulk_move_records" in result, result
        op = result["bulk_move_records"]
        for key in (
            "max_concurrent",
            "pre_check",
            "progress_monitoring",
            "estimated_time_per_item",
            "note",
        ):
            assert key in op, f"bulk_move_records missing {key!r}: {op!r}"

    def test_add_todo_operation_branch(self, mcp):
        result = mcp.call_sync("get_usage_recommendations", operation="add_todo")
        assert "add_todo" in result, result
        op = result["add_todo"]
        assert "tag_strategy" in op, op
        assert "available_tags_count" in op, op
        assert isinstance(op["available_tags_count"], int), op
        assert "suggested_workflow" in op, op

    def test_unknown_operation_falls_through_to_no_branch(self, mcp):
        """An operation name that matches none of the known branches
        (get_todos/bulk_move_records/add_todo) produces neither a
        per-operation key nor the 'general' key - the tool's if/elif chain
        is keyed on `if operation:` vs the specific elif branches, so an
        unrecognized non-empty operation string falls through all of them
        with no key added at all."""
        result = mcp.call_sync(
            "get_usage_recommendations", operation="unknown_op"
        )
        assert "unknown_op" not in result, result
        assert "general" not in result, result
        # Still returns the common envelope fields regardless of operation.
        assert "timestamp" in result, result
        assert "context_status" in result, result
        assert "context_guidance" in result, result
        assert "system_status" in result, result


# ---------------------------------------------------------------------------
# queue_status + get_server_capabilities: both transitively call
# operation_queue.get_operation_queue() - see the module docstring's
# "Discovered" note. Both live in a single async test sharing one event
# loop (via `await mcp.call(...)`, not `call_sync`) so the module-level
# queue singleton's worker task is only ever touched from the loop it was
# created in.
# ---------------------------------------------------------------------------


class TestQueueTouchingTools:
    @pytest.mark.asyncio
    async def test_queue_status_and_server_capabilities(self, mcp, live_server):
        # --- queue_status ---
        queue_result = await mcp.call("queue_status")
        assert "queue_status" in queue_result, queue_result
        assert "active_operations" in queue_result, queue_result
        assert "timestamp" in queue_result, queue_result
        assert isinstance(queue_result["queue_status"], dict), queue_result
        assert isinstance(queue_result["active_operations"], list), queue_result
        nested = queue_result["queue_status"]
        for key in (
            "queue_size",
            "active_operations",
            "completed_operations_history",
            "max_concurrent",
            "statistics",
        ):
            assert key in nested, f"queue_status.queue_status missing {key!r}: {nested!r}"
        datetime.fromisoformat(queue_result["timestamp"])

        # --- get_server_capabilities ---
        capabilities_result = await mcp.call("get_server_capabilities")

        # Query the real FastMCP server's own tool registry directly (same
        # call server.py's _registered_tool_count itself makes), within the
        # same running event loop as the two calls above.
        tools = await live_server.mcp.list_tools()
        registered_names = {t.name for t in tools}

        assert len(registered_names) == 41, registered_names
        assert capabilities_result["server_info"]["total_tools"] == 41, (
            capabilities_result["server_info"]
        )
        assert capabilities_result["api_coverage"]["total_tools"] == 41, (
            capabilities_result["api_coverage"]
        )
        assert capabilities_result["server_info"]["total_tools"] == len(
            registered_names
        )

        assert "get_todos" in registered_names
        assert "health_check" in registered_names
        assert "get_server_capabilities" in registered_names

        from things_mcp import __version__

        assert capabilities_result["server_info"]["version"] == __version__, (
            capabilities_result["server_info"]
        )

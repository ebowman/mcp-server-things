"""FastMCP middleware for Things tool-result contracts."""

from collections.abc import Mapping
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import ToolResult

# Every mutating tool. A ``success: false`` result from one of these is a
# failure regardless of the shape/case of its ``error`` code (delete_todo uses
# lower_snake codes; bulk tools may return no code of their own). Read and
# utility tools are never flagged. tests/unit/test_write_error_signaling.py
# forces every registered tool to be classified so this cannot drift.
WRITE_TOOLS = frozenset(
    {
        "add_todo",
        "update_todo",
        "bulk_update_todos",
        "delete_todo",
        "add_project",
        "update_project",
        "add_area",
        "update_area",
        "add_tags",
        "remove_tags",
        "create_tag",
        "move_record",
        "bulk_move_records",
        "add_checklist_items",
        "prepend_checklist_items",
        "replace_checklist_items",
    }
)


def _is_write_failure(tool_name: Any, content: Any) -> bool:
    """Return whether a write tool's structured content reports failure."""
    return (
        tool_name in WRITE_TOOLS
        and isinstance(content, Mapping)
        and content.get("success") is False
    )


class WriteErrorSignalingMiddleware(Middleware):
    """Expose structured write-tool failures as MCP tool errors."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        result = await call_next(context)
        tool_name = getattr(context.message, "name", None)
        if isinstance(result, ToolResult) and _is_write_failure(
            tool_name, result.structured_content
        ):
            return result.model_copy(update={"is_error": True})
        return result

"""FastMCP middleware for Things tool-result contracts."""

from collections.abc import Mapping
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import ToolResult


def _is_structured_write_error(content: Any) -> bool:
    """Return whether content matches the canonical write-error contract."""
    if not isinstance(content, Mapping) or content.get("success") is not False:
        return False

    error_code = content.get("error")
    return isinstance(error_code, str) and error_code.isupper()


class WriteErrorSignalingMiddleware(Middleware):
    """Expose canonical structured write failures as MCP tool errors."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        result = await call_next(context)
        if isinstance(result, ToolResult) and _is_structured_write_error(
            result.structured_content
        ):
            return result.model_copy(update={"is_error": True})
        return result

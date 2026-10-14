"""MCP-boundary call helper shared by the regression harness and its offline
unit test (tests/unit/test_regression_harness_contract.py).

Contract (hq-090, following PR #16's WriteErrorSignalingMiddleware):
structured write failures now carry MCP ``isError: true``. The client is
called with ``raise_on_error=False`` so such results come back as a normal
result object with ``structured_content`` intact; only results with no
structured content (a raised tool exception or a pydantic argument
validation error) map to ``{"tool_error": <text>}``.
"""

from typing import Any, Dict


def check_error_signaling(result: Any, tool_name: str) -> None:
    """Assert PR #16's isError invariant on a client CallToolResult."""
    sc = result.structured_content
    if not isinstance(sc, dict) or "success" not in sc:
        return
    if sc.get("success") is False:
        code = sc.get("error")
        # Only UPPER_SNAKE write-error codes are asserted. lower_snake read
        # errors and code-less failures are deliberately not checked here
        # (hq-v9k is about to change their signaling).
        if isinstance(code, str) and code.isupper():
            assert result.is_error is True, (
                f"{tool_name}: write failure {code!r} must set MCP isError=True"
            )
    elif sc.get("success") is True:
        assert result.is_error is False, (
            f"{tool_name}: success=True result must not set MCP isError"
        )


async def call_tool_structured(client: Any, tool_name: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Call ``tool_name`` on an already-entered fastmcp Client."""
    result = await client.call_tool(tool_name, kwargs, raise_on_error=False)
    check_error_signaling(result, tool_name)
    if result.structured_content is not None:
        return result.structured_content
    text = result.content[0].text if result.content else None
    if result.is_error or text is not None:
        return {"tool_error": text}
    return {}

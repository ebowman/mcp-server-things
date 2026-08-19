"""Shared error-shape helper for write/utility tool structured errors.

Companion to `read_operations.read_error` (the read-tool contract). This
module has no dependencies on the rest of `tools_helpers` so it can be
imported from `move_operations.py` and `scheduling/todo_operations.py`
(outside the `tools_helpers` package) without introducing a circular
import.
"""

from typing import Any, Dict


def write_error(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    """Build the canonical structured-error shape for a write tool/operation.

    Single source of truth for the write-tool error contract:
    ``{"success": False, "error": "<UPPER_SNAKE_CODE>", "message": "<human text>", ...}``.
    This mirrors ``read_operations.read_error`` but uses UPPER_SNAKE_CASE
    codes (matching the convention already established by
    ``VALIDATION_ERROR`` / ``TARGET_COMPLETED`` / ``NO_VALID_TAGS``) rather
    than the read-tool contract's lower_snake_case codes - the two
    contracts are deliberately distinct so callers can tell at a glance
    (or via a simple `.isupper()` check) whether an error came from a read
    or a write/mutating operation.

    Args:
        code: Short, stable, machine-readable UPPER_SNAKE_CASE error code
            (e.g. 'NOT_FOUND', 'INVALID_WHEN', 'APPLESCRIPT_ERROR'). Stable
            across releases - clients may switch on this value.
        message: Human-readable explanation of the error.
        **extra: Additional fields to merge into the result (e.g. 'field',
            'invalid_value', 'hint', 'tag_info').

    Returns:
        A dict with 'success', 'error', 'message', plus any extra fields.
    """
    return {"success": False, "error": code, "message": message, **extra}

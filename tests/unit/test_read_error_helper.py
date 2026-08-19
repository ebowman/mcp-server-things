"""Tests for the shared read-tool structured-error helper (hq-f0w.19).

There is exactly one implementation of the canonical read-tool error shape
(``tools_helpers.read_operations.read_error``); ``ThingsMCPServer._read_error``
(server.py) delegates to it rather than re-implementing the dict literal, so
the tools layer and the server-tool layer can never diverge on shape.
"""

from things_mcp.server import ThingsMCPServer
from things_mcp.tools_helpers.read_operations import read_error


class TestReadErrorHelperParity:
    """ThingsMCPServer._read_error and tools_helpers.read_operations.read_error
    must produce byte-for-byte identical output for the same inputs."""

    def test_same_shape_with_no_extra_fields(self):
        server_result = ThingsMCPServer._read_error("invalid_mode", "bad mode")
        tools_result = read_error("invalid_mode", "bad mode")

        assert server_result == tools_result
        assert server_result == {
            "success": False,
            "error": "invalid_mode",
            "message": "bad mode",
        }

    def test_same_shape_with_extra_fields(self):
        server_result = ThingsMCPServer._read_error(
            "unknown_tag", "Unknown tag 'X'.", tag="X", suggestions=["x"]
        )
        tools_result = read_error(
            "unknown_tag", "Unknown tag 'X'.", tag="X", suggestions=["x"]
        )

        assert server_result == tools_result
        assert server_result == {
            "success": False,
            "error": "unknown_tag",
            "message": "Unknown tag 'X'.",
            "tag": "X",
            "suggestions": ["x"],
        }

    def test_server_helper_delegates_to_tools_layer_function(self):
        """ThingsMCPServer._read_error must not hand-build the dict itself -
        it should be the exact same function object's output, not just an
        equal-looking literal that could silently drift."""
        assert ThingsMCPServer._read_error("code", "msg") == read_error("code", "msg")

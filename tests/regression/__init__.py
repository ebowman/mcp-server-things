"""Regression harness for the Things 3 MCP server against a real, running
Things 3 (hq-gbl epic).

This package is entirely opt-in: see conftest.py's
`pytest_collection_modifyitems` for the same gate used by tests/live
(THINGS_MCP_LIVE_TESTS=1 AND Things 3 actually running).
"""

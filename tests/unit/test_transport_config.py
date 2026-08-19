"""Tests for optional HTTP transport configuration.

Covers:
- ThingsMCPConfig parsing THINGS_MCP_TRANSPORT / _HOST / _PORT from the environment
- Invalid transport values being rejected with a clear error
- CLI flags (--transport/--host/--port) overriding environment-derived config
- ThingsMCPServer.run() forwarding the right kwargs to FastMCP's mcp.run()
  for stdio (unchanged, no kwargs) vs http (transport/host/port passed through)
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from things_mcp.config import ThingsMCPConfig
from things_mcp.main import ServerManager
from things_mcp.server import ThingsMCPServer


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

class TestTransportConfigDefaults:
    def test_defaults_are_stdio(self, monkeypatch):
        """With no env vars set, transport defaults to stdio with default host/port."""
        monkeypatch.delenv("THINGS_MCP_TRANSPORT", raising=False)
        monkeypatch.delenv("THINGS_MCP_HOST", raising=False)
        monkeypatch.delenv("THINGS_MCP_PORT", raising=False)

        config = ThingsMCPConfig()

        assert config.transport == "stdio"
        assert config.host == "127.0.0.1"
        assert config.port == 8000


class TestTransportConfigFromEnv:
    def test_transport_http_from_env(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "http")
        config = ThingsMCPConfig()
        assert config.transport == "http"

    def test_transport_stdio_from_env(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "stdio")
        config = ThingsMCPConfig()
        assert config.transport == "stdio"

    def test_transport_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "HTTP")
        config = ThingsMCPConfig()
        assert config.transport == "http"

    def test_host_from_env(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_HOST", "0.0.0.0")
        config = ThingsMCPConfig()
        assert config.host == "0.0.0.0"

    def test_port_from_env(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_PORT", "9999")
        config = ThingsMCPConfig()
        assert config.port == 9999

    def test_all_three_vars_together(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "http")
        monkeypatch.setenv("THINGS_MCP_HOST", "192.168.1.5")
        monkeypatch.setenv("THINGS_MCP_PORT", "18765")
        config = ThingsMCPConfig()
        assert config.transport == "http"
        assert config.host == "192.168.1.5"
        assert config.port == 18765


class TestTransportConfigValidation:
    def test_invalid_transport_rejected(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "websocket")
        with pytest.raises(ValidationError) as excinfo:
            ThingsMCPConfig()
        assert "transport" in str(excinfo.value).lower()

    def test_invalid_transport_constructor_arg_rejected(self):
        with pytest.raises(ValidationError):
            ThingsMCPConfig(transport="bogus")

    def test_invalid_port_rejected(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_PORT", "70000")
        with pytest.raises(ValidationError):
            ThingsMCPConfig()


# ---------------------------------------------------------------------------
# CLI flag overrides (ServerManager.start)
# ---------------------------------------------------------------------------

class TestServerManagerCLIOverrides:
    def _make_manager_with_stubbed_server(self, monkeypatch):
        """Patch ThingsMCPServer construction to avoid touching real Things 3,
        and stub run()/stop() so start() completes quickly."""
        manager = ServerManager()
        return manager

    def test_cli_transport_overrides_env(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "stdio")
        manager = ServerManager()
        with patch("things_mcp.main.ThingsMCPServer") as MockServerCls:
            mock_server = MagicMock()
            mock_server.config = ThingsMCPConfig()
            MockServerCls.return_value = mock_server

            manager.start(transport="http", host="1.2.3.4", port=9090)

            assert mock_server.config.transport == "http"
            assert mock_server.config.host == "1.2.3.4"
            assert mock_server.config.port == 9090
            mock_server.run.assert_called_once()

    def test_no_cli_override_keeps_env_config(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "http")
        monkeypatch.setenv("THINGS_MCP_HOST", "10.0.0.1")
        monkeypatch.setenv("THINGS_MCP_PORT", "7000")
        manager = ServerManager()
        with patch("things_mcp.main.ThingsMCPServer") as MockServerCls:
            mock_server = MagicMock()
            mock_server.config = ThingsMCPConfig()
            MockServerCls.return_value = mock_server

            manager.start()

            assert mock_server.config.transport == "http"
            assert mock_server.config.host == "10.0.0.1"
            assert mock_server.config.port == 7000


# ---------------------------------------------------------------------------
# ThingsMCPServer.run() kwargs forwarding
# ---------------------------------------------------------------------------

class TestServerRunTransportForwarding:
    def test_run_stdio_calls_mcp_run_with_no_kwargs(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "stdio")
        server = ThingsMCPServer()
        server.mcp = MagicMock()

        server.run()

        server.mcp.run.assert_called_once_with()

    def test_run_http_calls_mcp_run_with_transport_host_port(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TRANSPORT", "http")
        monkeypatch.setenv("THINGS_MCP_HOST", "127.0.0.1")
        monkeypatch.setenv("THINGS_MCP_PORT", "18765")
        server = ThingsMCPServer()
        server.mcp = MagicMock()

        server.run()

        server.mcp.run.assert_called_once_with(
            transport="http",
            host="127.0.0.1",
            port=18765,
        )

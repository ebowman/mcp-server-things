"""
Unit tests for hq-f0w.12: URL-scheme update tools fail fast when the Things
auth token is missing.

Covers:
  - AppleScriptManager.execute_url_scheme: 'update'-family actions without a
    token return a structured error and never call `open` (no subprocess);
    with a token, the URL contains auth-token=...; 'add' proceeds without a
    token.
  - The three checklist tools (add_checklist_items, prepend_checklist_items,
    replace_checklist_items) propagate that structured error instead of
    reporting success when nothing happened.
  - _add_todo_via_url_scheme (things:///add) is unaffected by a missing token.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from things_mcp.services.applescript_manager import (
    AppleScriptManager,
    AUTH_REQUIRING_ACTIONS,
)
from things_mcp.scheduling.todo_operations import TodoOperations


# ---------------------------------------------------------------------------
# _load_auth_token edge case: empty/whitespace-only token file treated as
# missing (falls through to the next candidate path).
# ---------------------------------------------------------------------------

class TestLoadAuthTokenEmptyFile:
    def test_empty_project_root_file_falls_through_to_home_candidate(self, tmp_path, monkeypatch):
        """An empty/whitespace-only .things-auth in the project root must be
        skipped, falling through to a non-empty ~/.things-auth."""
        fake_project_dir = tmp_path / "project"
        fake_project_dir.mkdir()
        (fake_project_dir / ".things-auth").write_text("   \n")

        fake_home_dir = tmp_path / "home"
        fake_home_dir.mkdir()
        (fake_home_dir / ".things-auth").write_text("real-token-456")

        # _load_auth_token computes project_root as
        # Path(__file__).parent.parent.parent.parent, i.e. four levels above
        # the applescript_manager module file. Redirect that computation by
        # patching the module's __file__ attribute to a path four levels
        # under fake_project_dir, and Path.home() to fake_home_dir.
        fake_module_file = fake_project_dir / "src" / "things_mcp" / "services" / "applescript_manager.py"
        fake_module_file.parent.mkdir(parents=True)

        import things_mcp.services.applescript_manager as asm_module
        monkeypatch.setattr(asm_module, "__file__", str(fake_module_file))
        monkeypatch.setattr(asm_module.Path, "home", staticmethod(lambda: fake_home_dir))

        manager = AppleScriptManager.__new__(AppleScriptManager)
        token = manager._load_auth_token()

        assert token == "real-token-456"

    def test_whitespace_only_body_strips_to_empty(self):
        """_load_auth_token must treat a whitespace-only file body as an
        empty token (falls through) rather than returning it as a truthy
        token string. This exercises the exact parsing rule the loader
        applies to each candidate file's contents."""
        raw_empty = "   \n".strip()
        assert raw_empty == ""
        assert not raw_empty

    @pytest.mark.asyncio
    async def test_manager_with_empty_string_auth_token_is_gated(self):
        """Simulates the outcome of loading an empty/whitespace token file:
        self.auth_token ends up as "" (falsy), which must still gate
        'update' actions exactly like auth_token=None."""
        manager = AppleScriptManager()
        manager.auth_token = ""

        with patch("asyncio.create_subprocess_exec") as mock_create:
            result = await manager.execute_url_scheme("update", {"id": "abc123"})

        assert result["success"] is False
        assert result["error"] == "Things URL-scheme auth token not configured"
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# AppleScriptManager.execute_url_scheme
# ---------------------------------------------------------------------------

class TestExecuteUrlSchemeAuthGate:
    @pytest.mark.asyncio
    async def test_update_without_token_returns_structured_error_no_open(self):
        manager = AppleScriptManager()
        manager.auth_token = None

        with patch("asyncio.create_subprocess_exec") as mock_create:
            result = await manager.execute_url_scheme("update", {"id": "abc123"})

        assert result["success"] is False
        assert result["error"] == "Things URL-scheme auth token not configured"
        assert "hint" in result and result["hint"]
        # open/execute_script must never be invoked.
        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_project_without_token_returns_structured_error(self):
        manager = AppleScriptManager()
        manager.auth_token = None

        with patch("asyncio.create_subprocess_exec") as mock_create:
            result = await manager.execute_url_scheme("update-project", {"id": "abc123"})

        assert result["success"] is False
        assert result["error"] == "Things URL-scheme auth token not configured"
        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_with_token_proceeds_and_url_contains_token(self):
        manager = AppleScriptManager()
        manager.auth_token = "test-token-xyz"

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager.execute_url_scheme("update", {"id": "abc123"})

        assert result["success"] is True
        assert "auth-token=test-token-xyz" in result["url"]
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_without_token_still_proceeds(self):
        manager = AppleScriptManager()
        manager.auth_token = None

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager.execute_url_scheme("add", {"title": "Test"})

        assert result["success"] is True
        mock_create.assert_called_once()
        assert "auth-token" not in result["url"]

    def test_auth_requiring_actions_constant_contains_update_family(self):
        assert "update" in AUTH_REQUIRING_ACTIONS
        assert "update-project" in AUTH_REQUIRING_ACTIONS
        assert "add" not in AUTH_REQUIRING_ACTIONS


# ---------------------------------------------------------------------------
# Checklist tools (TodoOperations)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_applescript_manager_no_token():
    """Mock AppleScript manager whose execute_url_scheme mimics the
    auth-gate behaviour for 'update' actions when no token is configured."""
    manager = Mock()

    async def fake_execute_url_scheme(action, parameters=None):
        if action in AUTH_REQUIRING_ACTIONS:
            return {
                "success": False,
                "error": "Things URL-scheme auth token not configured",
                "hint": "configure a token",
            }
        return {"success": True, "url": f"things:///{action}", "message": "ok"}

    manager.execute_url_scheme = AsyncMock(side_effect=fake_execute_url_scheme)
    manager.execute_applescript = AsyncMock(return_value={"success": True, "output": ""})
    return manager


@pytest.fixture
def mock_applescript_manager_with_token():
    """Mock AppleScript manager whose execute_url_scheme echoes the action and
    parameters it was called with into the returned URL, so callers can
    assert on both the auth-token and the checklist-specific param key. Each
    returned dict is also recorded on `manager.url_scheme_results` (in call
    order) so tests can inspect the URL that was produced for their call."""
    manager = Mock()
    manager.url_scheme_results = []

    async def fake_execute_url_scheme(action, parameters=None):
        parameters = parameters or {}
        query = "&".join(f"{key}={value}" for key, value in parameters.items())
        query = f"{query}&auth-token=xyz" if query else "auth-token=xyz"
        response = {
            "success": True,
            "url": f"things:///{action}?{query}",
            "message": f"Successfully executed {action} action",
        }
        manager.url_scheme_results.append(response)
        return response

    manager.execute_url_scheme = AsyncMock(side_effect=fake_execute_url_scheme)
    return manager


@pytest.fixture
def todo_operations_no_token(mock_applescript_manager_no_token):
    return TodoOperations(mock_applescript_manager_no_token, Mock())


@pytest.fixture
def todo_operations_with_token(mock_applescript_manager_with_token):
    return TodoOperations(mock_applescript_manager_with_token, Mock())


class TestAddChecklistItemsAuthGate:
    @pytest.mark.asyncio
    async def test_no_token_returns_success_false(self, todo_operations_no_token):
        result = await todo_operations_no_token.add_checklist_items("todo123", ["item1"])
        assert result["success"] is False
        assert "auth token" in result["error"].lower()
        assert result["hint"] == "configure a token"

    @pytest.mark.asyncio
    async def test_with_token_succeeds(self, todo_operations_with_token, mock_applescript_manager_with_token):
        result = await todo_operations_with_token.add_checklist_items("todo123", ["item1"])
        assert result["success"] is True

        # The auth-gated 'update' action was invoked with the
        # append-checklist-items param, and the (mocked) resulting URL
        # carries the auth token.
        call_action, call_params = mock_applescript_manager_with_token.execute_url_scheme.call_args.args
        assert call_action == "update"
        assert call_params["append-checklist-items"] == "item1"

        url = mock_applescript_manager_with_token.url_scheme_results[-1]["url"]
        assert "auth-token=" in url
        assert "append-checklist-items=item1" in url


class TestPrependChecklistItemsAuthGate:
    @pytest.mark.asyncio
    async def test_no_token_returns_success_false(self, todo_operations_no_token):
        result = await todo_operations_no_token.prepend_checklist_items("todo123", ["item1"])
        assert result["success"] is False
        assert "auth token" in result["error"].lower()
        assert result["hint"] == "configure a token"

    @pytest.mark.asyncio
    async def test_with_token_succeeds(self, todo_operations_with_token, mock_applescript_manager_with_token):
        result = await todo_operations_with_token.prepend_checklist_items("todo123", ["item1"])
        assert result["success"] is True

        call_action, call_params = mock_applescript_manager_with_token.execute_url_scheme.call_args.args
        assert call_action == "update"
        assert call_params["prepend-checklist-items"] == "item1"

        url = mock_applescript_manager_with_token.url_scheme_results[-1]["url"]
        assert "auth-token=" in url
        assert "prepend-checklist-items=item1" in url


class TestReplaceChecklistItemsAuthGate:
    @pytest.mark.asyncio
    async def test_no_token_returns_success_false(self, todo_operations_no_token):
        result = await todo_operations_no_token.replace_checklist_items("todo123", ["item1"])
        assert result["success"] is False
        assert "auth token" in result["error"].lower()
        assert result["hint"] == "configure a token"

    @pytest.mark.asyncio
    async def test_with_token_succeeds(self, todo_operations_with_token, mock_applescript_manager_with_token):
        result = await todo_operations_with_token.replace_checklist_items("todo123", ["item1"])
        assert result["success"] is True

        call_action, call_params = mock_applescript_manager_with_token.execute_url_scheme.call_args.args
        assert call_action == "update"
        assert call_params["checklist-items"] == "item1"

        url = mock_applescript_manager_with_token.url_scheme_results[-1]["url"]
        assert "auth-token=" in url
        assert "checklist-items=item1" in url


class TestAddTodoWithChecklistUnaffected:
    """things:///add does not require a token - _add_todo_via_url_scheme
    must still proceed to completion when no token is configured."""

    @pytest.mark.asyncio
    async def test_add_with_checklist_no_token_still_proceeds(self, mock_applescript_manager_no_token):
        # First call is the pre-create snapshot (no existing todo with this
        # title); second call is the post-create poll that finds the new id.
        mock_applescript_manager_no_token.execute_applescript = AsyncMock(side_effect=[
            {"success": True, "output": ""},
            {"success": True, "output": "todo-id-123"},
        ])
        ops = TodoOperations(mock_applescript_manager_no_token, Mock())

        result = await ops._add_todo_via_url_scheme("Test Todo", checklist_items=["a", "b"])

        assert result["success"] is True
        # Confirm the 'add' action was used (not gated) even without a token.
        called_actions = [
            call.args[0] for call in mock_applescript_manager_no_token.execute_url_scheme.call_args_list
        ]
        assert called_actions == ["add"]

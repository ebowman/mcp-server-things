"""
Unit tests for the AppleScript Manager.

Tests AppleScript execution, URL scheme handling, caching, error handling,
and retry logic with comprehensive mocking to avoid Things 3 dependency.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any, List

from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.config import ThingsMCPConfig


class TestAppleScriptManagerInit:
    """Test AppleScript Manager initialization."""
    
    def test_init_with_default_config(self):
        """Test initialization with default configuration.""" 
        manager = AppleScriptManager()
        
        assert manager.timeout == 45  # default timeout
        assert manager.retry_count == 3  # default retry count
        # Cache removed in hybrid implementation
        assert hasattr(manager, 'auth_token')
    
    def test_init_with_custom_config(self):
        """Test initialization with custom configuration."""
        manager = AppleScriptManager(timeout=60, retry_count=5)
        
        assert manager.timeout == 60
        assert manager.retry_count == 5
        # Cache removed in hybrid implementation
        assert hasattr(manager, 'auth_token')
    
    def test_init_without_dependencies(self):
        """Test initialization without optional dependencies."""
        manager = AppleScriptManager()
        
        # Should initialize without error
        assert manager.timeout == 45
        assert manager.retry_count == 3
        # Cache removed in hybrid implementation


class TestAppleScriptExecution:
    """Test AppleScript execution functionality."""
    
    @pytest.fixture
    def manager_with_mocks(self):
        """Fixture providing manager with mocked dependencies."""
        manager = AppleScriptManager(timeout=5, retry_count=2)
        # Cache removed in hybrid implementation, no need to clear
        return manager
    
    @pytest.mark.asyncio
    async def test_execute_applescript_success(self, manager_with_mocks):
        """Test successful AppleScript execution."""
        script = 'tell application "Things3" to return version'
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock successful subprocess execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"3.20.1", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is True
            assert result["output"] == "3.20.1"
            assert "execution_time" in result
            
            # Verify subprocess was called correctly
            mock_create.assert_called_once_with(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
    
    @pytest.mark.asyncio
    async def test_execute_applescript_failure(self, manager_with_mocks):
        """Test failed AppleScript execution."""
        script = 'invalid applescript'
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock failed subprocess execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"syntax error")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is False
            assert "syntax error" in result["error"]
    
    @pytest.mark.asyncio
    async def test_execute_applescript_timeout(self, manager_with_mocks):
        """Test AppleScript execution timeout."""
        script = 'delay 10'
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_process.kill = AsyncMock()
            mock_process.wait = AsyncMock()
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is False
            assert "timed out" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_execute_applescript_with_caching(self, manager_with_mocks):
        """Test AppleScript execution with caching."""
        script = 'tell application "Things3" to return version'
        cache_key = "todos_all"  # Use a cache key pattern that gets cached
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock successful subprocess execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"3.20.1", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            # First call should execute and cache
            result1 = await manager_with_mocks.execute_applescript(script, cache_key)
            assert result1["success"] is True
            assert result1["output"] == "3.20.1"
            
            # Second call should also execute (no caching in hybrid mode)
            result2 = await manager_with_mocks.execute_applescript(script, cache_key)
            assert result2["success"] is True
            assert result2["output"] == "3.20.1"  
            
            # Both calls should have been made
            assert mock_create.call_count == 2


class TestURLSchemeExecution:
    """Test URL scheme execution functionality."""
    
    @pytest.fixture
    def manager_with_mocks(self):
        """Fixture providing manager with mocked dependencies."""
        return AppleScriptManager()
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_success(self, manager_with_mocks):
        """Test successful URL scheme execution."""
        action = "add"
        parameters = {"title": "Test Todo", "notes": "Test notes"}
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock successful subprocess execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            assert "url" in result
            assert "things:///add" in result["url"]
            assert "message" in result
            
            # Verify the URL was constructed correctly
            expected_url_parts = ["title=Test%20Todo", "notes=Test%20notes"]
            for part in expected_url_parts:
                assert part in result["url"]
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_with_complex_parameters(self, manager_with_mocks):
        """Test URL scheme execution with complex parameters."""
        action = "add"
        parameters = {
            "title": "Complex Todo",
            "tags": ["work", "urgent"],
            "when": "today",
            "deadline": "2024-12-31",
            "list-id": "project-123"
        }
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            url = result["url"]
            
            # Check that all parameters are properly encoded
            assert "title=Complex%20Todo" in url
            assert "tags=work%2Curgent" in url  # Comma-separated list
            assert "when=today" in url
            assert "deadline=2024-12-31" in url
            assert "list-id=project-123" in url
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_failure(self, manager_with_mocks):
        """Test failed URL scheme execution."""
        action = "invalid_action"
        parameters = {"title": "Test"}
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Invalid URL scheme")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is False
            assert "Invalid URL scheme" in result["error"]
            assert "url" in result
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_without_parameters(self, manager_with_mocks):
        """Test URL scheme execution without parameters."""
        action = "show"

        # Make the test hermetic: the manager auto-loads a token from a gitignored
        # .things-auth / ~/.things-auth if present, which would otherwise leak into
        # the URL and make this assertion environment-dependent.
        manager_with_mocks.auth_token = None

        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager_with_mocks.execute_url_scheme(action)

            assert result["success"] is True
            assert result["url"] == "things:///show"  # No params, no auth token configured

    @pytest.mark.asyncio
    async def test_execute_url_scheme_with_auth_token(self, manager_with_mocks):
        """Test URL scheme execution includes auth token when configured."""
        action = "show"

        # Configure auth token on the manager
        manager_with_mocks.auth_token = "test-token-123"

        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager_with_mocks.execute_url_scheme(action)

            assert result["success"] is True
            assert result["url"].startswith("things:///show")
            assert "auth-token=test-token-123" in result["url"]
    
    @pytest.mark.asyncio
    async def test_url_parameter_encoding(self, manager_with_mocks):
        """Test URL parameter encoding handles special characters."""
        action = "add"
        parameters = {
            "title": "Todo with special chars: @#$%^&*()!",
            "notes": "Notes with\nnewlines and\ttabs",
            "tags": ["tag with spaces", "tag/with/slashes"]
        }
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            url = result["url"]
            
            # Special characters should be URL encoded
            assert "%20" in url  # Space
            assert "%0A" in url or "\\n" in url  # Newline (might be escaped differently)
            assert "%2C" in url  # Comma in tags
            
            # Should not contain unencoded special characters
            assert " " not in url.split("?")[1] if "?" in url else True
            assert "\n" not in url
            assert "\t" not in url


def _redirect_auth_candidates(tmp_path, monkeypatch):
    """Redirect AppleScriptManager's auth-token candidate paths (project
    root + home) to empty tmp_path directories, returning
    (fake_project_dir, fake_home_dir). Hermetic against a real
    .things-auth/~/.things-auth possibly present on the machine running the
    suite - mirrors the helper of the same purpose in
    test_url_scheme_auth_gate.py."""
    fake_project_dir = tmp_path / "project"
    fake_project_dir.mkdir(exist_ok=True)
    fake_home_dir = tmp_path / "home"
    fake_home_dir.mkdir(exist_ok=True)

    fake_module_file = fake_project_dir / "src" / "things_mcp" / "services" / "applescript_manager.py"
    fake_module_file.parent.mkdir(parents=True, exist_ok=True)

    import things_mcp.services.applescript_manager as asm_module
    monkeypatch.setattr(asm_module, "__file__", str(fake_module_file))
    monkeypatch.setattr(asm_module.Path, "home", staticmethod(lambda: fake_home_dir))
    return fake_project_dir, fake_home_dir


class TestAuthTokenReloadOnMiss:
    """hq-wsa.4: a token file created after the manager was constructed is
    picked up on the next gated call, without constructing a new manager or
    restarting the server."""

    @pytest.mark.asyncio
    async def test_token_file_appearing_after_init_is_picked_up_without_new_manager(
        self, tmp_path, monkeypatch
    ):
        fake_project_dir, _ = _redirect_auth_candidates(tmp_path, monkeypatch)

        # No token file exists yet at construction time.
        manager = AppleScriptManager()
        assert manager.auth_token is None

        with patch('asyncio.create_subprocess_exec') as mock_create:
            result = await manager.execute_url_scheme("update", {"id": "abc123"})
        assert result["success"] is False
        assert result["error"] == "AUTH_TOKEN_NOT_CONFIGURED"
        mock_create.assert_not_called()

        # Token file appears after construction (simulating the user
        # configuring it at runtime, with the server left running).
        (fake_project_dir / ".things-auth").write_text("late-token-789")

        # Same manager instance, no restart - the next gated call must pick
        # it up.
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager.execute_url_scheme("update", {"id": "abc123"})

        assert result["success"] is True
        assert "auth-token=late-token-789" in result["url"]
        assert manager.auth_token == "late-token-789"

    @pytest.mark.asyncio
    async def test_already_loaded_token_is_not_reloaded(self, tmp_path, monkeypatch):
        """reload_auth_token_if_missing is a no-op once a token is loaded -
        it must not re-read the filesystem (and must not be fooled by a
        DIFFERENT token file appearing later) once auth_token is truthy."""
        fake_project_dir, _ = _redirect_auth_candidates(tmp_path, monkeypatch)
        (fake_project_dir / ".things-auth").write_text("original-token")

        manager = AppleScriptManager()
        assert manager.auth_token == "original-token"

        # Change the file on disk after construction - since a token is
        # already loaded, reload_auth_token_if_missing must leave it alone.
        (fake_project_dir / ".things-auth").write_text("different-token")

        reloaded = manager.reload_auth_token_if_missing()
        assert reloaded == "original-token"
        assert manager.auth_token == "original-token"

    def test_empty_then_valid_home_candidate_resolves_via_reload(self, tmp_path, monkeypatch):
        """Combines the empty-file-falls-through behavior with reload: an
        empty project-root file at construction time (no token loaded),
        then a valid ~/.things-auth appearing later, is picked up by
        reload_auth_token_if_missing()."""
        fake_project_dir, fake_home_dir = _redirect_auth_candidates(tmp_path, monkeypatch)
        (fake_project_dir / ".things-auth").write_text("   \n")

        manager = AppleScriptManager()
        assert manager.auth_token is None

        (fake_home_dir / ".things-auth").write_text("home-token-999")

        reloaded = manager.reload_auth_token_if_missing()
        assert reloaded == "home-token-999"
        assert manager.auth_token == "home-token-999"


class TestAuthTokenCheckedPathsTrace:
    """hq-wsa.4: _load_auth_token's resolution trace, and its presence on
    the AUTH_TOKEN_NOT_CONFIGURED envelope - path + status only, never the
    token value itself."""

    def test_trace_shape_all_missing(self, tmp_path, monkeypatch):
        _redirect_auth_candidates(tmp_path, monkeypatch)

        manager = AppleScriptManager.__new__(AppleScriptManager)
        token, trace = manager._load_auth_token()

        assert token is None
        assert [entry["status"] for entry in trace] == ["missing", "missing", "missing"]
        for entry in trace:
            assert set(entry.keys()) == {"path", "status"}

    def test_trace_shape_empty_then_matched(self, tmp_path, monkeypatch):
        fake_project_dir, fake_home_dir = _redirect_auth_candidates(tmp_path, monkeypatch)
        (fake_project_dir / ".things-auth").write_text("   \n")
        (fake_home_dir / ".things-auth").write_text("real-token")

        manager = AppleScriptManager.__new__(AppleScriptManager)
        token, trace = manager._load_auth_token()

        assert token == "real-token"
        statuses = [entry["status"] for entry in trace]
        # .things-auth (empty) -> things-auth.txt (missing) -> ~/.things-auth (matched)
        assert statuses == ["empty", "missing", "matched"]
        # Never leak the token value itself into the trace.
        for entry in trace:
            assert "real-token" not in str(entry)

    def test_trace_shape_unreadable(self, tmp_path, monkeypatch):
        fake_project_dir, _ = _redirect_auth_candidates(tmp_path, monkeypatch)
        bad_file = fake_project_dir / ".things-auth"
        bad_file.mkdir()  # A directory, not a file - read_text() raises.

        manager = AppleScriptManager.__new__(AppleScriptManager)
        token, trace = manager._load_auth_token()

        assert token is None
        assert trace[0]["status"] == "unreadable"

    @pytest.mark.asyncio
    async def test_checked_paths_on_auth_gate_error(self, tmp_path, monkeypatch):
        _redirect_auth_candidates(tmp_path, monkeypatch)
        manager = AppleScriptManager()

        with patch('asyncio.create_subprocess_exec') as mock_create:
            result = await manager.execute_url_scheme("update", {"id": "abc123"})

        assert result["success"] is False
        assert result["error"] == "AUTH_TOKEN_NOT_CONFIGURED"
        assert "hint" in result and result["hint"]
        assert "checked_paths" in result
        assert [entry["status"] for entry in result["checked_paths"]] == [
            "missing", "missing", "missing"
        ]
        mock_create.assert_not_called()


class TestThingsAvailabilityCheck:
    """Test Things 3 availability checking."""
    
    @pytest.fixture
    def manager_with_mocks(self):
        """Fixture providing manager with mocked dependencies."""
        return AppleScriptManager()
    
    @pytest.mark.asyncio
    async def test_check_things_availability_success(self, manager_with_mocks):
        """Test successful Things 3 availability check."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"true", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.is_things_running()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_things_availability_failure(self, manager_with_mocks):
        """Test Things 3 availability check when Things is not available."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Application is not running")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.is_things_running()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_check_things_availability_timeout(self, manager_with_mocks):
        """Test Things 3 availability check timeout."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_process.kill = AsyncMock()
            mock_process.wait = AsyncMock()
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.is_things_running()
            
            assert result is False


class TestRetryLogic:
    """Test retry logic for failed operations."""
    
    @pytest.fixture
    def manager_with_retries(self):
        """Fixture providing manager with retry configuration."""
        return AppleScriptManager(timeout=5, retry_count=2)
    
    @pytest.mark.asyncio
    async def test_applescript_retry_success_on_second_attempt(self, manager_with_retries):
        """Test AppleScript retry succeeds on second attempt."""
        script = 'tell application "Things3" to return version'
        
        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:
            
            # First call fails, second succeeds
            process1 = AsyncMock()
            process1.communicate.return_value = (b"", b"Temporary error")
            process1.returncode = 1
            
            process2 = AsyncMock()
            process2.communicate.return_value = (b"3.21.15", b"") # Use actual Things version
            process2.returncode = 0
            
            mock_create.side_effect = [process1, process2]
            
            result = await manager_with_retries.execute_applescript(script)
            
            assert result["success"] is True
            assert result["output"] == "3.21.15"
            assert mock_create.call_count == 2
            assert mock_sleep.call_count == 1  # One retry delay
    
    @pytest.mark.asyncio
    async def test_applescript_retry_exhausted(self, manager_with_retries):
        """Test AppleScript retry exhaustion after all attempts fail."""
        script = 'tell application "Things3" to return version'
        
        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:
            
            # All attempts fail
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Persistent error")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            result = await manager_with_retries.execute_applescript(script)
            
            assert result["success"] is False
            assert "Persistent error" in result["error"]
            assert mock_create.call_count == 2  # Initial + 1 retry (retry_count=2)
            assert mock_sleep.call_count == 1  # One retry delay
    
    # URL scheme retry test removed - retry logic is already tested for AppleScript execution
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self, manager_with_retries):
        """Test exponential backoff delay calculation."""
        script = 'failing script'
        
        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:
            
            # All attempts fail
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Error")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            await manager_with_retries.execute_applescript(script)
            
            # Check that sleep was called with exponential backoff
            sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
            assert len(sleep_calls) == 1  # 1 retry (retry_count=2 -> initial + 1 retry)
            assert sleep_calls[0] == 1  # First retry: 2^0 = 1


class TestRetryOnErrorStdout:
    """hq-c7a: rc=0 osascript results whose stdout is the in-script
    "ERROR:"-prefixed convention (move_operations.py's
    _build_project_move_script/_build_area_move_script/_get_todo_info,
    tag_service.py's tag-creation script - `on error errMsg / return
    "ERROR: " & errMsg`) must be retried the same as a nonzero returncode,
    since Things 3 intermittently errors under rapid back-to-back
    AppleEvents even though the osascript process itself still exits 0.
    """

    @pytest.fixture
    def manager_with_retries(self):
        """Fixture providing manager with retry configuration."""
        return AppleScriptManager(timeout=5, retry_count=3)

    @pytest.mark.asyncio
    async def test_error_stdout_retried_then_exhausted_returns_as_is(self, manager_with_retries):
        """rc=0 + 'ERROR: ...' stdout on every attempt -> retried up to the
        bound (attempt count == retry_count), then returned exactly as
        produced (success=True, output starts with 'ERROR:') rather than
        being wrapped in a different failure envelope - callers such as
        move_operations.py parse `output.startswith("ERROR:")` on the
        raw result and must keep working unchanged on final exhaustion."""
        script = 'tell application "Things3" to return "ERROR: " & "boom"'

        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:

            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"ERROR: boom", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager_with_retries.execute_applescript(script)

            assert mock_create.call_count == 3  # retried up to retry_count
            assert mock_sleep.call_count == 2  # backoff before each retry
            # Returned exactly as produced - same shape callers already parse.
            assert result["success"] is True
            assert result["output"] == "ERROR: boom"

    @pytest.mark.asyncio
    async def test_normal_stdout_not_retried(self, manager_with_retries):
        """rc=0 + normal (non-'ERROR:') stdout -> no retry, single attempt."""
        script = 'tell application "Things3" to return "MOVED to project abc"'

        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:

            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"MOVED to project abc", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager_with_retries.execute_applescript(script)

            assert mock_create.call_count == 1
            assert mock_sleep.call_count == 0
            assert result["success"] is True
            assert result["output"] == "MOVED to project abc"

    @pytest.mark.asyncio
    async def test_nonzero_returncode_retry_unchanged(self, manager_with_retries):
        """rc!=0 -> existing retry behavior unchanged (retried up to the
        bound, final failure wrapped in the generic 'Failed after N
        attempts' envelope, not returned as-is)."""
        script = 'tell application "Things3" to return version'

        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:

            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Persistent error")
            mock_process.returncode = 1
            mock_create.return_value = mock_process

            result = await manager_with_retries.execute_applescript(script)

            assert mock_create.call_count == 3
            assert mock_sleep.call_count == 2
            assert result["success"] is False
            assert "Persistent error" in result["error"]
            assert "Failed after 3 attempts" in result["error"]

    @pytest.mark.asyncio
    async def test_success_on_second_attempt_after_error_stdout(self, manager_with_retries):
        """rc=0 'ERROR:' stdout on attempt 1, normal success on attempt 2 ->
        success returned, exactly one retry consumed."""
        script = 'tell application "Things3" to move theTodo'

        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:

            process1 = AsyncMock()
            process1.communicate.return_value = (b"ERROR: Things got confused", b"")
            process1.returncode = 0

            process2 = AsyncMock()
            process2.communicate.return_value = (b"MOVED to project abc", b"")
            process2.returncode = 0

            mock_create.side_effect = [process1, process2]

            result = await manager_with_retries.execute_applescript(script)

            assert mock_create.call_count == 2
            assert mock_sleep.call_count == 1
            assert result["success"] is True
            assert result["output"] == "MOVED to project abc"

    @pytest.mark.asyncio
    async def test_error_stdout_leading_whitespace_still_detected(self, manager_with_retries):
        """Output is stripped before the prefix check - leading/trailing
        whitespace around the 'ERROR:' prefix must not defeat detection."""
        script = 'tell application "Things3" to return "  ERROR: boom  "'

        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:

            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"  ERROR: boom  ", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager_with_retries.execute_applescript(script)

            assert mock_create.call_count == 3
            assert result["success"] is True
            # Executor strips stdout into `output` regardless of retry path.
            assert result["output"] == "ERROR: boom"

    @pytest.mark.asyncio
    async def test_error_substring_not_at_start_not_retried(self, manager_with_retries):
        """A payload that merely *contains* 'ERROR:' but does not start
        with it (e.g. legitimate note text) must NOT be treated as
        retryable - only an exact prefix match triggers retry."""
        script = 'tell application "Things3" to return notes'

        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:

            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b"Remember: ERROR: handling notes are due Friday", b""
            )
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await manager_with_retries.execute_applescript(script)

            assert mock_create.call_count == 1
            assert mock_sleep.call_count == 0
            assert result["success"] is True
            assert result["output"] == "Remember: ERROR: handling notes are due Friday"



"""Unit tests for hq-f0w.5: add_todo heading/list_title honoured on every path.

Covers:
- heading (no checklist) takes the URL-scheme branch and the built URL
  contains heading + list.
- heading without a target project returns a structured error without
  calling Things.
- heading + checklist still works (regression).
- list_title resolves to a project or an area on the AppleScript path.
- ambiguous / unknown list_title returns a structured error.
- list_id pointing at an area uses `set area of ...`.
- list_id containing a double quote cannot break the script (escaped).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote

from things_mcp.pure_applescript_scheduler import PureAppleScriptScheduler
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager with real URL building."""
    manager = MagicMock(spec=AppleScriptManager)
    manager.execute_applescript = AsyncMock()
    manager.execute_url_scheme = AsyncMock()
    return manager


def id_lookup_side_effect(new_id):
    """Build an execute_applescript side_effect list for
    _add_todo_via_url_scheme's snapshot-then-poll id lookup (hq-nxu.12):
    the first call is the pre-create snapshot (no existing todo with this
    title), the second is the post-create poll that finds the new id."""
    return [
        {"success": True, "output": ""},
        {"success": True, "output": new_id},
    ]


@pytest.fixture
def scheduler(mock_applescript_manager):
    return PureAppleScriptScheduler(mock_applescript_manager)


class TestHeadingUrlSchemeBranch:
    """heading (with or without checklist) must take the URL-scheme path."""

    @pytest.mark.asyncio
    async def test_heading_no_checklist_uses_url_scheme(self, scheduler, mock_applescript_manager):
        """add_todo(title, list_id=P, heading=H) with no checklist emits a
        things:///add URL containing heading and list-id, and does not touch
        the AppleScript-creation path."""
        mock_applescript_manager.execute_url_scheme.return_value = {
            "success": True,
            "url": "things:///add?title=heading%20test&list=PROJECT123&heading=Research",
        }
        mock_applescript_manager.execute_applescript.side_effect = id_lookup_side_effect("new-todo-id")

        with patch("things_mcp.scheduling.todo_operations.things.tasks", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.get", return_value={"type": "project"}):
            result = await scheduler.add_todo(
                title="heading test", list_id="PROJECT123", heading="Research"
            )

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        action, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert action == "add"
        assert params["heading"] == "Research"
        assert params["list-id"] == "PROJECT123"

    @pytest.mark.asyncio
    async def test_heading_without_project_returns_structured_error(self, scheduler, mock_applescript_manager):
        """heading given but neither list_id nor list_title provided ->
        structured error, no call to Things at all."""
        result = await scheduler.add_todo(title="orphan heading todo", heading="Somewhere")

        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"
        assert "heading requires a target project" in result["message"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heading_with_list_title_no_project_id_still_errors_if_missing(self, scheduler, mock_applescript_manager):
        """heading passed with list_title (not list_id) is accepted as a valid target."""
        mock_applescript_manager.execute_url_scheme.return_value = {"success": True, "url": "things:///add"}
        mock_applescript_manager.execute_applescript.side_effect = id_lookup_side_effect("abc123")

        with patch("things_mcp.scheduling.todo_operations.things.tasks", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[{"uuid": "P1", "title": "Work"}]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await scheduler.add_todo(title="lt heading todo", list_title="Work", heading="Phase 1")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        # list_title is resolved to a concrete id before being sent as
        # 'list-id' (same resolution as the AppleScript branch), not
        # passed through raw as 'list'.
        assert params["list-id"] == "P1"
        assert params["heading"] == "Phase 1"

    @pytest.mark.asyncio
    async def test_heading_plus_checklist_regression(self, scheduler, mock_applescript_manager):
        """heading + checklist_items together still works (regression check)."""
        mock_applescript_manager.execute_url_scheme.return_value = {"success": True, "url": "things:///add"}
        mock_applescript_manager.execute_applescript.side_effect = id_lookup_side_effect("todo-with-checklist")

        with patch("things_mcp.scheduling.todo_operations.things.tasks", return_value=[{"title": "Research"}]), \
             patch("things_mcp.scheduling.todo_operations.things.get", return_value={"type": "project"}):
            result = await scheduler.add_todo(
                title="heading + checklist",
                list_id="PROJECT123",
                heading="Research",
                checklist_items=["Item 1", "Item 2"],
            )

        assert result["success"] is True
        assert result["checklist_count"] == 2
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["heading"] == "Research"
        assert params["checklist-items"] == "Item 1\nItem 2"

    @pytest.mark.asyncio
    async def test_heading_not_found_in_project_adds_warning(self, scheduler, mock_applescript_manager):
        """If the heading does not exist in the resolved project, a warning is
        added to the response (Things silently ignores an unknown heading)."""
        mock_applescript_manager.execute_url_scheme.return_value = {"success": True, "url": "things:///add"}
        mock_applescript_manager.execute_applescript.side_effect = id_lookup_side_effect("todo-x")

        with patch("things_mcp.scheduling.todo_operations.things.tasks", return_value=[{"title": "Other Heading"}]), \
             patch("things_mcp.scheduling.todo_operations.things.get", return_value={"type": "project"}):
            result = await scheduler.add_todo(
                title="missing heading todo", list_id="PROJECT123", heading="Nonexistent"
            )

        assert result["success"] is True
        assert "warnings" in result
        assert any("Nonexistent" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_heading_with_special_chars_percent_encoded(self, scheduler, mock_applescript_manager):
        """Heading titles containing & / ? # % must be percent-encoded in the
        built URL (build_things_url already url-encodes all param values -
        verify end to end via the real formatter)."""
        from things_mcp.services.applescript_manager import AppleScriptManager as RealManager

        real_manager = RealManager()
        real_manager.executor = MagicMock()
        # First call is the pre-create id snapshot (empty); every call
        # after (the URL open + the post-create poll) reports the new id,
        # so the poll resolves on its first iteration instead of running
        # out the full lookup deadline.
        real_manager.executor.execute_script = AsyncMock(
            side_effect=[{"success": True, "output": ""}] + [{"success": True, "output": "new-id"}] * 5
        )
        real_scheduler = PureAppleScriptScheduler(real_manager)

        with patch("things_mcp.scheduling.todo_operations.things.tasks", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.get", return_value={"type": "project"}):
            await real_scheduler.add_todo(
                title="weird heading todo",
                list_id="PROJECT123",
                heading="A&B?C#D%E",
            )

        # await_args_list[0] is the pre-create snapshot script (issued
        # before the URL-scheme call); the URL open script is the second
        # call.
        url_open_script = real_manager.executor.execute_script.await_args_list[1].args[0]
        assert "A&B?C#D%E" not in url_open_script
        assert "heading=A%26B%3FC%23D%25E" in url_open_script


class TestListTitleResolutionAppleScriptPath:
    """list_title must resolve on the AppleScript (non-heading, non-checklist) path."""

    @pytest.mark.asyncio
    async def test_list_title_resolves_to_project(self, scheduler, mock_applescript_manager):
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True, "output": "todo-in-project"
        }

        with patch("things_mcp.scheduling.todo_operations.things.projects",
                   return_value=[{"uuid": "PROJ-1", "title": "Website Redesign"}]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await scheduler.add_todo(title="X", list_title="Website Redesign")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'project id "PROJ-1"' in script
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_title_resolves_to_area(self, scheduler, mock_applescript_manager):
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True, "output": "todo-in-area"
        }

        with patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.areas",
                   return_value=[{"uuid": "AREA-1", "title": "Personal"}]):
            result = await scheduler.add_todo(title="X", list_title="Personal")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'area id "AREA-1"' in script

    @pytest.mark.asyncio
    async def test_list_title_ambiguous_returns_structured_error(self, scheduler, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects",
                   return_value=[{"uuid": "PROJ-1", "title": "Ops"}]), \
             patch("things_mcp.scheduling.todo_operations.things.areas",
                   return_value=[{"uuid": "AREA-1", "title": "Ops"}]):
            result = await scheduler.add_todo(title="X", list_title="Ops")

        assert result["success"] is False
        assert result["error"] == "AMBIGUOUS_TARGET"
        assert "ambiguous" in result["message"]
        assert "PROJ-1" in result["message"]
        assert "AREA-1" in result["message"]
        assert "project:PROJ-1" in result["ids"]
        assert "area:AREA-1" in result["ids"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_title_unknown_returns_structured_error(self, scheduler, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await scheduler.add_todo(title="X", list_title="Does Not Exist")

        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"
        assert "does not match any project or area" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()


class TestListIdResolutionAndEscaping:
    """list_id must resolve project-vs-area via things.get and be escaped safely."""

    @pytest.mark.asyncio
    async def test_list_id_project_uses_set_project(self, scheduler, mock_applescript_manager):
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True, "output": "todo-1"
        }

        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "uuid": "PROJ-1"}):
            result = await scheduler.add_todo(title="X", list_id="PROJ-1")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'project id "PROJ-1"' in script

    @pytest.mark.asyncio
    async def test_list_id_area_uses_set_area(self, scheduler, mock_applescript_manager):
        """An area uuid passed as list_id places the todo in the area."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True, "output": "todo-2"
        }

        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "area", "uuid": "AREA-1"}):
            result = await scheduler.add_todo(title="X", list_id="AREA-1")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'area id "AREA-1"' in script
        assert "project id" not in script

    @pytest.mark.asyncio
    async def test_list_id_unknown_returns_structured_error(self, scheduler, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get", return_value=None):
            result = await scheduler.add_todo(title="X", list_id="bogus-id")

        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"
        assert "does not match any known project or area" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_id_with_double_quote_is_escaped(self, scheduler, mock_applescript_manager):
        """A list_id containing a double quote cannot break out of the
        AppleScript string literal."""
        malicious_id = 'abc" & (do shell script "touch /tmp/pwned") & "'
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True, "output": "todo-3"
        }

        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "uuid": malicious_id}):
            result = await scheduler.add_todo(title="X", list_id=malicious_id)

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        # The raw unescaped payload must never appear verbatim in the script.
        assert 'project id "abc" & (do shell script' not in script
        # Backslash-escaped quote confirms escape_string was applied.
        assert '\\"' in script

    @pytest.mark.asyncio
    async def test_list_id_lookup_exception_falls_back_to_project(self, scheduler, mock_applescript_manager):
        """If things.get() itself raises (e.g. Things DB unreadable / Full
        Disk Access missing), add_todo(list_id=...) must not refuse the
        write - it should fall back to the pre-bead behavior of treating
        list_id as a project id, since this used to work via AppleScript
        alone with no things.py database dependency."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True, "output": "todo-fallback"
        }

        with patch("things_mcp.scheduling.todo_operations.things.get",
                   side_effect=RuntimeError("Things database is unreadable")):
            result = await scheduler.add_todo(title="X", list_id="PROJ-UNREADABLE-DB")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'project id "PROJ-UNREADABLE-DB"' in script


class TestListTitleResolutionUrlSchemePath:
    """list_title must resolve on the URL-scheme (heading/checklist) path too,
    not be passed through raw as 'list' - an unresolved/ambiguous title would
    otherwise silently succeed with the to-do landing in the Inbox."""

    @pytest.mark.asyncio
    async def test_heading_with_unknown_list_title_returns_structured_error(self, scheduler, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await scheduler.add_todo(title="X", list_title="Does Not Exist", heading="Phase 1")

        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"
        assert "does not match any project or area" in result["message"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heading_with_ambiguous_list_title_returns_structured_error(self, scheduler, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects",
                   return_value=[{"uuid": "PROJ-1", "title": "Ops"}]), \
             patch("things_mcp.scheduling.todo_operations.things.areas",
                   return_value=[{"uuid": "AREA-1", "title": "Ops"}]):
            result = await scheduler.add_todo(title="X", list_title="Ops", heading="Phase 1")

        assert result["success"] is False
        assert result["error"] == "AMBIGUOUS_TARGET"
        assert "ambiguous" in result["message"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_checklist_with_list_title_resolves_to_list_id(self, scheduler, mock_applescript_manager):
        """checklist_items + list_title (no heading) also resolves list_title
        to a concrete id and sends it as 'list-id', not raw as 'list'."""
        mock_applescript_manager.execute_url_scheme.return_value = {"success": True, "url": "things:///add"}
        mock_applescript_manager.execute_applescript.side_effect = id_lookup_side_effect("todo-checklist-lt")

        with patch("things_mcp.scheduling.todo_operations.things.projects",
                   return_value=[{"uuid": "PROJ-1", "title": "Website Redesign"}]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await scheduler.add_todo(
                title="X", list_title="Website Redesign", checklist_items=["Item 1"]
            )

        assert result["success"] is True
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["list-id"] == "PROJ-1"
        assert "list" not in params

    @pytest.mark.asyncio
    async def test_heading_with_list_title_resolving_to_area_uses_list_id(self, scheduler, mock_applescript_manager):
        """A list_title that resolves to an area (not a project) is sent as
        'list-id' too - the Things URL scheme accepts an area id there."""
        mock_applescript_manager.execute_url_scheme.return_value = {"success": True, "url": "things:///add"}
        mock_applescript_manager.execute_applescript.side_effect = id_lookup_side_effect("todo-area-lt")

        with patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.areas",
                   return_value=[{"uuid": "AREA-1", "title": "Personal"}]), \
             patch("things_mcp.scheduling.todo_operations.things.tasks", return_value=[]):
            result = await scheduler.add_todo(
                title="X", list_title="Personal", heading="Errands"
            )

        assert result["success"] is True
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["list-id"] == "AREA-1"

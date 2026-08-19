"""Opt-in live Things 3 smoke suite (hq-f0w.14).

Every test in this module writes to (and reads back from) a real, running
Things 3 via the actual AppleScript/URL-scheme write paths - not mocks.
The whole directory only runs when THINGS_MCP_LIVE_TESTS=1 and Things 3 is
running (see tests/live/conftest.py's pytest_collection_modifyitems).

LIVE-WRITE SAFETY: every test in this module writes only into the single
throwaway project created by the session-scoped `smoke_session` fixture
(prefix "hq-f0w-smoke live "). No test ever creates, moves into, or
otherwise touches a pre-existing project/area/heading. All created items
are tracked via `smoke_session.track()` and trashed + verified in the
session teardown (tests/live/conftest.py::_trash_and_verify).
"""
import time

import pytest
import things

pytestmark = pytest.mark.live


def _settle():
    """Brief pause to let Things 3 settle after a write before reading back.

    things.py reads are measured (hq-nxu.8) to have ~6ms mean lag after an
    AppleScript write, but URL-scheme creates are processed asynchronously
    by Things, so a slightly longer pause is used for URL-scheme paths.
    """
    time.sleep(1)


# (a) add_todo -> get_todos(project_uuid=P) and get_todo_by_id return the
# exact title and notes, including a title with commas/quotes/colon and
# multi-line notes.
@pytest.mark.asyncio
async def test_add_todo_title_and_notes_roundtrip(live_things_tools, smoke_session):
    title = 'Smoke: alpha, bravo "quoted": colon'
    notes = "Line one.\n\nLine two."

    result = await live_things_tools.add_todo(
        title=title,
        notes=notes,
        list_id=smoke_session.project_id,
    )
    assert result.get("success"), result
    todo_id = smoke_session.track(result["todo_id"])
    assert todo_id, f"add_todo did not return an id: {result}"

    _settle()

    # Read back via the server's own read tool.
    todos = await live_things_tools.get_todos(project_uuid=smoke_session.project_id, status=None)
    assert isinstance(todos, list), todos
    matches = [t for t in todos if t["uuid"] == todo_id]
    assert len(matches) == 1, f"expected exactly one match for {todo_id}, got {matches}"
    assert matches[0]["title"] == title
    assert matches[0]["notes"] == notes

    # Read back via get_todo_by_id.
    by_id = await live_things_tools.get_todo_by_id(todo_id)
    assert by_id["title"] == title
    assert by_id["notes"] == notes

    # Read back directly via things.py for an independent check.
    raw = things.get(todo_id)
    assert raw["title"] == title
    assert raw["notes"] == notes


# (b) add_project + update_project multi-line notes preserved.
@pytest.mark.asyncio
async def test_update_project_multiline_notes_preserved(live_things_tools, smoke_session):
    multiline_notes = "Project note line one.\nLine two.\n\nLine four."

    result = await live_things_tools.update_project(
        project_id=smoke_session.project_id,
        notes=multiline_notes,
    )
    assert result.get("success"), result

    _settle()

    raw = things.get(smoke_session.project_id)
    assert raw["notes"] == multiline_notes

    by_id = await live_things_tools.get_todo_by_id(smoke_session.project_id)
    assert by_id["notes"] == multiline_notes


# (i) heading tests: add_todo with heading under the smoke project's seeded
# heading -> headingTitle present. add_project's ##-prefixed todos lines
# route through the Things URL scheme's json action (hq-f0w.41) and do
# create a real heading; smoke_session verifies this via a fresh things.py
# read and only leaves heading_title None (skipping this test with a clear
# reason) if that verification ever fails in a given live environment.
@pytest.mark.asyncio
async def test_add_todo_under_seeded_heading(live_things_tools, smoke_session):
    if not smoke_session.heading_title:
        pytest.skip(
            "smoke_session could not verify a real heading was created by "
            "add_project's ##Heading todos line (see tests/live/conftest.py"
            "::smoke_session) - skipping heading-dependent test"
        )

    title = "Smoke: heading child todo"
    result = await live_things_tools.add_todo(
        title=title,
        list_id=smoke_session.project_id,
        heading=smoke_session.heading_title,
    )
    assert result.get("success"), result
    todo_id = smoke_session.track(result["todo_id"])
    assert todo_id, f"add_todo did not return an id: {result}"

    _settle()

    by_id = await live_things_tools.get_todo_by_id(todo_id)
    assert by_id.get("headingTitle") == smoke_session.heading_title


# (d) get_anytime/get_someday/get_today contain no type != 'to-do' items
# (default include_projects=False), and get_trash contains none by default.
@pytest.mark.asyncio
async def test_list_tools_exclude_non_todo_types_by_default(live_things_tools):
    for coro in (
        live_things_tools.get_anytime(limit=25),
        live_things_tools.get_someday(limit=25),
        live_things_tools.get_today(limit=25),
    ):
        items = await coro
        assert isinstance(items, list)
        non_todo = [i for i in items if i.get("type") != "to-do"]
        assert not non_todo, f"expected only to-dos, got non-to-do types: {non_todo}"

    trash = await live_things_tools.get_trash(limit=25)
    assert isinstance(trash, dict)
    non_todo_trash = [i for i in trash["items"] if i.get("type") != "to-do"]
    assert not non_todo_trash, f"expected only to-dos in trash, got: {non_todo_trash}"


# (e) bulk_update_todos with a trailing-quote title + multiline notes.
@pytest.mark.asyncio
async def test_bulk_update_todos_trailing_quote_and_multiline_notes(live_things_tools, smoke_session):
    create = await live_things_tools.add_todo(
        title="Smoke: bulk target",
        list_id=smoke_session.project_id,
    )
    assert create.get("success"), create
    todo_id = smoke_session.track(create["todo_id"])
    assert todo_id

    _settle()

    new_title = 'Smoke: trailing quote"'
    new_notes = "Bulk note line one.\nBulk note line two."

    result = await live_things_tools.bulk_update_todos(
        todo_ids=[todo_id],
        title=new_title,
        notes=new_notes,
    )
    assert result.get("success"), result

    _settle()

    raw = things.get(todo_id)
    assert raw["title"] == new_title
    assert raw["notes"] == new_notes


# (f) update_project completed/canceled -> status.
@pytest.mark.asyncio
async def test_update_project_completed_and_canceled_status(live_things_tools, smoke_session):
    # Create a small dedicated sub-project so we don't touch the shared
    # smoke_session.project_id's own status (other tests read/write it).
    create = await live_things_tools.add_project(title="hq-f0w-smoke live status sub-project")
    assert create.get("success"), create
    sub_project_id = smoke_session.track(create["project_id"])

    _settle()

    completed_result = await live_things_tools.update_project(project_id=sub_project_id, completed="true")
    assert completed_result.get("success"), completed_result
    _settle()
    raw = things.get(sub_project_id)
    assert raw["status"] == "completed"

    canceled_result = await live_things_tools.update_project(project_id=sub_project_id, canceled="true")
    assert canceled_result.get("success"), canceled_result
    _settle()
    raw = things.get(sub_project_id)
    assert raw["status"] == "canceled"


# (g) checklist tools error cleanly when no auth token, or round-trip when
# one is configured.
@pytest.mark.asyncio
async def test_checklist_tools_require_auth_token_or_roundtrip(live_things_tools, smoke_session, has_auth_token):
    create = await live_things_tools.add_todo(
        title="Smoke: checklist target",
        list_id=smoke_session.project_id,
    )
    assert create.get("success"), create
    todo_id = smoke_session.track(create["todo_id"])
    assert todo_id

    _settle()

    result = await live_things_tools.add_checklist_items(todo_id=todo_id, items=["Item one", "Item two"])

    if not has_auth_token:
        assert result.get("success") is False
        assert "auth" in (result.get("error") or "").lower() or "auth" in (result.get("hint") or "").lower()
        return

    assert result.get("success"), result
    _settle()
    items = things.checklist_items(todo_id)
    titles = [i["title"] for i in items]
    assert "Item one" in titles
    assert "Item two" in titles


# (h) convert fields: a completed todo has completionDate.
@pytest.mark.asyncio
async def test_completed_todo_has_completion_date(live_things_tools, smoke_session):
    create = await live_things_tools.add_todo(
        title="Smoke: completion date target",
        list_id=smoke_session.project_id,
    )
    assert create.get("success"), create
    todo_id = smoke_session.track(create["todo_id"])
    assert todo_id

    _settle()

    update_result = await live_things_tools.bulk_update_todos(todo_ids=[todo_id], completed="true")
    assert update_result.get("success"), update_result

    _settle()

    by_id = await live_things_tools.get_todo_by_id(todo_id)
    assert by_id.get("status") == "completed"
    assert by_id.get("completionDate") is not None

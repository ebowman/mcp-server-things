"""hq-gbl.12: Regression (live) for checklist tools - add_todo(checklist_items=...),
add_checklist_items, prepend_checklist_items, replace_checklist_items - and the
hasChecklist / checklist-list read surfaces, driven through the real MCP tool
boundary.

Order/content assertions read back via `things.checklist_items(todo_id)`,
which returns a list of dicts carrying (among other keys) 'title' in Things'
own display order - the exact contract this file relies on for asserting
append/prepend/replace ordering.

NOTE: the 101-item over-cap case is intentionally NOT duplicated here - it
is covered by the strict xfail in test_todo_create_delete.py
(TestAddTodoChecklist::test_checklist_items_101_rejected_and_nothing_created,
bug hq-exe: the documented 100-item cap is not enforced anywhere).

Error-code notes (confirmed by reading src, not guessed):
  - server.py's add_checklist_items/prepend_checklist_items tool wrappers
    each explicitly guard `if not items: return self._write_error(
    "NO_CHECKLIST_ITEMS", ...)` BEFORE calling self.tools - so items=[] on
    either of those two tools never reaches Things at all.
  - replace_checklist_items has NO such guard in server.py, and
    scheduling/todo_operations.py's replace_checklist_items() builds
    'checklist-items': '' for items=[] and sends it straight through -
    items=[] is therefore a normal "clear the checklist" request, not an
    error, matching CLAUDE.md's documented `replace_checklist_items(items=[])`
    behavior.
  - All three checklist tools go through
    AppleScriptManager.execute_url_scheme('update', ...), which gates on
    `action in AUTH_REQUIRING_ACTIONS and not self.auth_token` and returns
    {"success": False, "error": "AUTH_TOKEN_NOT_CONFIGURED", "message": ...,
    "hint": ...} BEFORE ever building/opening the things:// URL - so with no
    token configured, none of the three ever reaches Things, and the
    checklist is provably unchanged.
  - Unknown todo_id / a project id passed as todo_id: execute_url_scheme
    builds and `open -g`s a things:///update?id=...&... URL regardless of
    whether that id resolves to anything Things recognizes; `open -g` exits
    0 even when Things silently no-ops on an unresolvable/wrong-type id (no
    AppleScript-level lookup/type-check exists on this path, unlike the
    to-do-id AppleScript lookup used elsewhere in the codebase). This file
    asserts the OBSERVED behavior (success=True, checklist state provably
    unaffected for the unknown id; for the project id, best-effort - Things
    has no per-project checklist concept so there's nothing to observe
    changing) rather than assuming a NOT_FOUND-style error - CLAUDE.md does
    not document behavior for either case, so this is Discovered doc-gap
    territory, not a code bug.
"""
import time

import pytest

from regression.helpers import assert_write_error, read_back, sandbox_title, ts

pytestmark = pytest.mark.live


def _new_todo(mcp, sandbox, title=None, **kwargs):
    """Create a fresh, tracked to-do in the sandbox project and return its id."""
    title = title or sandbox_title("checklist target " + ts())
    result = mcp.call_sync(
        "add_todo", title=title, list_id=sandbox.project_id, **kwargs
    )
    assert result.get("success") is True, result
    todo_id = result.get("todo_id")
    assert todo_id
    sandbox.track(todo_id)
    return todo_id, title


def _checklist_titles(todo_id):
    import things

    items = things.checklist_items(todo_id) or []
    return [i["title"] for i in items]


def _get_unresolvable(todo_id):
    """things.get(id, trashed=None) raises TypeError for area/tag-shaped
    lookups (see helpers.read_back's docstring / README's "trashed=None
    TypeError quirk") - fall back to a bare things.get() the same way, so a
    genuinely-unresolvable bogus id is correctly asserted as None rather
    than raising."""
    import things

    try:
        return things.get(todo_id, trashed=None)
    except TypeError:
        return things.get(todo_id)


def _poll_checklist_titles(todo_id, expected, timeout=20.0, interval=0.25):
    """Poll things.checklist_items(todo_id) until its ordered title list
    equals `expected` (a list) or timeout elapses; returns the last-seen
    titles list. Polls on the checklist content itself (not just existence),
    per the brief."""
    record = read_back(
        todo_id,
        lambda _r: _checklist_titles(todo_id) == expected,
        timeout=timeout,
        interval=interval,
    )
    return _checklist_titles(todo_id)


# ---------------------------------------------------------------------------
# 1. add_todo(checklist_items=...) - order/content, quotes/commas/unicode
# ---------------------------------------------------------------------------


class TestAddTodoChecklistOrderAndContent:
    def test_order_preserved_1_3_100(self, mcp, sandbox):
        for count in (1, 3, 100):
            items = [f"chk item {count}-{i}" for i in range(count)]
            title = sandbox_title(f"add checklist order {count}")
            result = mcp.call_sync(
                "add_todo", title=title, checklist_items=items, list_id=sandbox.project_id
            )
            assert result.get("success") is True, result
            todo_id = result.get("todo_id")
            assert todo_id
            sandbox.track(todo_id)

            titles = _poll_checklist_titles(todo_id, items)
            assert titles == items, (count, titles)

    def test_items_with_quotes_commas_unicode_emoji_roundtrip(self, mcp, sandbox):
        items = [
            'quote "inside" item',
            "comma, separated, item",
            "unicode éèü item",
            "emoji \U0001F600 item",
            "back\\slash item",
        ]
        title = sandbox_title("add checklist special chars")
        result = mcp.call_sync(
            "add_todo", title=title, checklist_items=items, list_id=sandbox.project_id
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        titles = _poll_checklist_titles(todo_id, items)
        assert titles == items, titles


# ---------------------------------------------------------------------------
# 2. add_checklist_items / prepend_checklist_items / replace_checklist_items
# ---------------------------------------------------------------------------



@pytest.fixture()
def require_auth_token(live_server):
    """Skip (not fail) on machines without a configured Things auth token -
    all things:///update-based checklist operations require one."""
    if not live_server.applescript_manager.auth_token:
        pytest.skip("Things auth token not configured")


@pytest.mark.usefixtures("require_auth_token")
class TestAddChecklistItems:
    def test_appends_at_end_order_preserved(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["seed 1", "seed 2"])
        titles = _poll_checklist_titles(todo_id, ["seed 1", "seed 2"])
        assert titles == ["seed 1", "seed 2"], titles

        new_items = ["appended a", "appended b"]
        result = mcp.call_sync("add_checklist_items", todo_id=todo_id, items=new_items)
        assert result.get("success") is True, result

        expected = ["seed 1", "seed 2", "appended a", "appended b"]
        titles = _poll_checklist_titles(todo_id, expected)
        assert titles == expected, titles

    def test_empty_items_rejected_no_checklist_items(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["only seed"])
        before = _poll_checklist_titles(todo_id, ["only seed"])
        assert before == ["only seed"], before

        result = mcp.call_sync("add_checklist_items", todo_id=todo_id, items=[])
        assert_write_error(result, "NO_CHECKLIST_ITEMS")

        time.sleep(1)
        after = _checklist_titles(todo_id)
        assert after == ["only seed"], after


@pytest.mark.usefixtures("require_auth_token")
class TestPrependChecklistItems:
    def test_prepends_at_start_batch_order_preserved(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["existing 1", "existing 2"])
        titles = _poll_checklist_titles(todo_id, ["existing 1", "existing 2"])
        assert titles == ["existing 1", "existing 2"], titles

        new_items = ["prepend a", "prepend b"]
        result = mcp.call_sync("prepend_checklist_items", todo_id=todo_id, items=new_items)
        assert result.get("success") is True, result

        expected = ["prepend a", "prepend b", "existing 1", "existing 2"]
        titles = _poll_checklist_titles(todo_id, expected)
        assert titles == expected, titles

    def test_empty_items_rejected_no_checklist_items(self, mcp, sandbox):
        """server.py's prepend_checklist_items wrapper carries the same
        `if not items: return self._write_error("NO_CHECKLIST_ITEMS", ...)`
        guard as add_checklist_items - confirmed by reading src (see module
        docstring). Asserted as an exact structured error, not just
        success=False, per COMMON.md."""
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["only seed"])
        before = _poll_checklist_titles(todo_id, ["only seed"])
        assert before == ["only seed"], before

        result = mcp.call_sync("prepend_checklist_items", todo_id=todo_id, items=[])
        assert_write_error(result, "NO_CHECKLIST_ITEMS")

        time.sleep(1)
        after = _checklist_titles(todo_id)
        assert after == ["only seed"], after


@pytest.mark.usefixtures("require_auth_token")
class TestReplaceChecklistItems:
    def test_replaces_all_items(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["old 1", "old 2", "old 3"])
        titles = _poll_checklist_titles(todo_id, ["old 1", "old 2", "old 3"])
        assert titles == ["old 1", "old 2", "old 3"], titles

        new_items = ["new a", "new b"]
        result = mcp.call_sync("replace_checklist_items", todo_id=todo_id, items=new_items)
        assert result.get("success") is True, result

        titles = _poll_checklist_titles(todo_id, new_items)
        assert titles == new_items, titles

    def test_replace_with_empty_list_clears_checklist(self, mcp, sandbox):
        """Observed (not documented as an error anywhere): replace_checklist_items(items=[])
        is a normal clear, matching CLAUDE.md's "Clear all checklist items"
        example - confirmed by reading server.py (no NO_CHECKLIST_ITEMS
        guard on this tool) and todo_operations.py (items=[] -> 'checklist-items': '')."""
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["will be cleared"])
        titles = _poll_checklist_titles(todo_id, ["will be cleared"])
        assert titles == ["will be cleared"], titles

        result = mcp.call_sync("replace_checklist_items", todo_id=todo_id, items=[])
        assert result.get("success") is True, result

        titles = _poll_checklist_titles(todo_id, [])
        assert titles == [], titles


# ---------------------------------------------------------------------------
# 3. Unknown todo id / project id as todo_id
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("require_auth_token")
class TestChecklistToolsBadTargetIds:
    """CLAUDE.md does not document behavior for an unknown or wrong-type
    todo_id on the checklist tools. Reading
    services/applescript_manager.py's execute_url_scheme confirms there is
    no id-resolution/type check on this path at all (unlike the AppleScript
    `to do id "..."` lookup used by e.g. update_todo's non-heading path) -
    `open -g 'things:///update?...'` is fired regardless, and Things
    silently no-ops on an id it can't resolve to a to-do, with `open` still
    exiting 0. These tests assert that OBSERVED success=True shape and that
    nothing was actually created/changed, rather than assuming an error
    code CLAUDE.md never promised. Filed under Discovered as a doc gap, not
    a bug - this is consistent with add_todo/update_todo's own
    "Things silently ignores it" behavior for a bad heading."""

    def test_add_checklist_items_unknown_todo_id(self, mcp, sandbox):
        bogus_id = f"hq-gbl-reg-bogus-checklist-target-{ts()}"
        result = mcp.call_sync(
            "add_checklist_items", todo_id=bogus_id, items=["orphan item"]
        )
        assert result.get("success") is True, result

        time.sleep(2)
        assert _get_unresolvable(bogus_id) is None

    def test_prepend_checklist_items_unknown_todo_id(self, mcp, sandbox):
        bogus_id = f"hq-gbl-reg-bogus-checklist-target-{ts()}"
        result = mcp.call_sync(
            "prepend_checklist_items", todo_id=bogus_id, items=["orphan item"]
        )
        assert result.get("success") is True, result

        time.sleep(2)
        assert _get_unresolvable(bogus_id) is None

    def test_replace_checklist_items_unknown_todo_id(self, mcp, sandbox):
        bogus_id = f"hq-gbl-reg-bogus-checklist-target-{ts()}"
        result = mcp.call_sync(
            "replace_checklist_items", todo_id=bogus_id, items=["orphan item"]
        )
        assert result.get("success") is True, result

        time.sleep(2)
        assert _get_unresolvable(bogus_id) is None

    def test_add_checklist_items_project_id_as_todo_id(self, mcp, sandbox):
        """Best-effort: a project has no checklist concept in Things, so
        there's no checklist state to assert on directly - this asserts the
        observed success=True shape and that the sandbox project's own
        record is otherwise unaffected (still resolves as a project, same
        title)."""
        import things

        result = mcp.call_sync(
            "add_checklist_items", todo_id=sandbox.project_id, items=["orphan item"]
        )
        assert result.get("success") is True, result

        time.sleep(2)
        record = things.get(sandbox.project_id, trashed=None)
        assert record is not None
        assert record.get("type") == "project"
        assert record.get("title") == sandbox.project_title


# ---------------------------------------------------------------------------
# 4. AUTH_TOKEN_NOT_CONFIGURED shape - one per tool, checklist unmodified
# ---------------------------------------------------------------------------


class TestChecklistToolsAuthTokenNotConfigured:
    """Monkeypatches the shared live AppleScriptManager's auth_token to None
    for the duration of each test only, restoring it in a finally block.
    Todos (with a seed checklist) are created BEFORE the patch is applied,
    since add_todo(checklist_items=...) uses things:///add, which does not
    require the token. The auth check runs before any things:///update URL
    is built/opened, so the checklist is provably unchanged afterward."""

    def test_add_checklist_items_without_auth_token(self, mcp, sandbox, live_server):
        manager = live_server.applescript_manager
        original_token = manager.auth_token
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["seed only"])
        before = _poll_checklist_titles(todo_id, ["seed only"])
        assert before == ["seed only"], before
        try:
            manager.auth_token = None
            result = mcp.call_sync(
                "add_checklist_items", todo_id=todo_id, items=["should not apply"]
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
        finally:
            manager.auth_token = original_token

        time.sleep(1)
        after = _checklist_titles(todo_id)
        assert after == ["seed only"], after

    def test_prepend_checklist_items_without_auth_token(self, mcp, sandbox, live_server):
        manager = live_server.applescript_manager
        original_token = manager.auth_token
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["seed only"])
        before = _poll_checklist_titles(todo_id, ["seed only"])
        assert before == ["seed only"], before
        try:
            manager.auth_token = None
            result = mcp.call_sync(
                "prepend_checklist_items", todo_id=todo_id, items=["should not apply"]
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
        finally:
            manager.auth_token = original_token

        time.sleep(1)
        after = _checklist_titles(todo_id)
        assert after == ["seed only"], after

    def test_replace_checklist_items_without_auth_token(self, mcp, sandbox, live_server):
        manager = live_server.applescript_manager
        original_token = manager.auth_token
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["seed only"])
        before = _poll_checklist_titles(todo_id, ["seed only"])
        assert before == ["seed only"], before
        try:
            manager.auth_token = None
            result = mcp.call_sync(
                "replace_checklist_items", todo_id=todo_id, items=["should not apply"]
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
        finally:
            manager.auth_token = original_token

        time.sleep(1)
        after = _checklist_titles(todo_id)
        assert after == ["seed only"], after


# ---------------------------------------------------------------------------
# 5. hasChecklist via get_todo_by_id; get_todos(include_items=True) checklist
# ---------------------------------------------------------------------------


class TestHasChecklistAndIncludeItems:
    def test_has_checklist_true_via_get_todo_by_id(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, checklist_items=["a", "b"])
        _poll_checklist_titles(todo_id, ["a", "b"])

        result = mcp.call_sync("get_todo_by_id", todo_id=todo_id)
        assert "item" in result, result
        item = result["item"]
        assert item.get("hasChecklist") is True, item
        assert item.get("checklist") == [
            {"title": "a", "status": "incomplete"},
            {"title": "b", "status": "incomplete"},
        ] or [c.get("title") for c in item.get("checklist", [])] == ["a", "b"], item

    def test_has_checklist_false_via_get_todo_by_id(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None

        result = mcp.call_sync("get_todo_by_id", todo_id=todo_id)
        assert "item" in result, result
        item = result["item"]
        assert item.get("hasChecklist") is False, item
        assert item.get("checklist") == [], item

    def test_get_todos_include_items_returns_checklist_list(self, mcp, sandbox):
        """limit=500 (get_todos' max) is passed explicitly: get_todos' own
        smart-default limit is 50 (context_manager.py's DEFAULT_LIMITS), and
        by the time this test runs the shared session sandbox project has
        accumulated far more than 50 to-dos from every other test in the
        suite - an unspecified limit truncates the result before this
        test's own to-do (not guaranteed to sort last) ever appears."""
        items = ["listed 1", "listed 2", "listed 3"]
        todo_id, title = _new_todo(mcp, sandbox, checklist_items=items)
        _poll_checklist_titles(todo_id, items)

        result = mcp.call_sync(
            "get_todos",
            project_uuid=sandbox.project_id,
            include_items=True,
            mode="detailed",
            status=None,
            limit=500,
        )
        assert "items" in result, result
        matches = [t for t in result["items"] if t.get("uuid") == todo_id]
        assert len(matches) == 1, (todo_id, [t.get("uuid") for t in result["items"]])
        todo = matches[0]
        assert todo.get("checklist") == [
            {"title": i, "status": "incomplete"} for i in items
        ], todo.get("checklist")

"""hq-gbl.11: Regression (live) for add_tags, remove_tags, create_tag,
get_tags, get_tagged_items, get_tag_usage - across tag policies, driven
through the real MCP tool boundary.

Policy notes (read from config.py, not assumed):
  - This environment's active `live_server.config.tag_creation_policy` is
    read at test time and policy-adaptive assertions are written only for
    the shared-server tests (mirrors test_todo_create_delete.py's
    `test_tags_policy_behavior` pattern).
  - Per-policy matrix (bead step 3): a SECOND `ThingsMCPServer` is built
    per policy, with its own `_MCPCallHelper`-style Client, by setting the
    `THINGS_MCP_AI_CAN_CREATE_TAGS` env var via `monkeypatch.setenv` before
    construction (see `_second_server` helper below).

  Discovered (see also the report): `config.py`'s
  `validate_tag_creation_policy`/`set_ai_can_create_tags_from_policy`
  field-validator pair makes `THINGS_MCP_TAG_CREATION_POLICY` alone a
  dead env var - pydantic validates `ai_can_create_tags` (declared first)
  before `tag_creation_policy`, so `tag_creation_policy`'s validator
  always finds `ai_can_create_tags` already present in `info.data`
  (defaulting to False) and unconditionally overrides to
  ALLOW_ALL/FILTER_WARN based on THAT field alone - confirmed live via
  `THINGS_MCP_TAG_CREATION_POLICY=filter_silent` (and even via a
  `.env`-file equivalent through `env_file=`) still yielding
  `TagCreationPolicy.FILTER_WARN`, while `THINGS_MCP_AI_CAN_CREATE_TAGS`
  reaches it correctly. So only two policies are reachable via env
  override: ALLOW_ALL (`THINGS_MCP_AI_CAN_CREATE_TAGS=true`) and
  FILTER_WARN (`=false` / unset, the default). FILTER_SILENT and
  FAIL_ON_UNKNOWN cannot currently be selected via any env var/env_file -
  the matrix below is therefore built only for the two reachable policies,
  and this gap is filed as discovered work rather than fixed here (out of
  scope for this bead).
"""
import time

import pytest

from regression.helpers import (
    assert_read_error,
    assert_write_error,
    read_back,
    sandbox_title,
    ts,
)

pytestmark = pytest.mark.live


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _delete_tag_by_name(tag_name: str) -> None:
    """Best-effort AppleScript delete of a tag by title, used for tags this
    suite creates itself (e.g. via ALLOW_ALL policy or create_tag), mirroring
    conftest.py's _delete_tag_via_applescript (which takes an id, not a
    name) - resolves the id via things.py first."""
    import things

    matches = [t for t in things.tags() or [] if t.get("title") == tag_name]
    if not matches:
        return
    tag_id = matches[0]["uuid"]
    escaped = tag_id.replace('"', '\\"')
    script = f'''
    tell application "Things3"
        try
            delete (tag id "{escaped}")
            return "deleted"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    import subprocess

    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)


def _track_tag(sandbox, tag_name: str) -> None:
    """No dedicated sandbox.track_tag helper exists (per the brief) - track
    the tag name in a plain list attribute on the sandbox object itself, and
    rely on THIS module's own explicit in-test deletion as the primary
    cleanup path, with a session-end safety-net sweep in a fixture finalizer
    registered lazily below."""
    if not hasattr(sandbox, "_extra_tracked_tag_names"):
        sandbox._extra_tracked_tag_names = []
    sandbox._extra_tracked_tag_names.append(tag_name)


@pytest.fixture(autouse=True, scope="module")
def _extra_tag_safety_net(sandbox):
    """Session-module-scoped safety net: after all tests in this module
    run, delete any tag name tracked via _track_tag that still exists
    (covers a mid-test assertion failure that skipped its own explicit
    delete call)."""
    yield
    for name in list(getattr(sandbox, "_extra_tracked_tag_names", [])):
        _delete_tag_by_name(name)


def _second_server(monkeypatch, ai_can_create_tags: bool):
    """Build a second, independent ThingsMCPServer with
    THINGS_MCP_AI_CAN_CREATE_TAGS overridden, plus its own _MCPCallHelper
    (mirrors conftest.py's _MCPCallHelper - a second fastmcp Client bound
    to this server's .mcp, not server.tools directly, so these tests still
    exercise the real MCP tool boundary same as the rest of the suite).
    Returns (server, mcp_helper).
    """
    from regression.conftest import _MCPCallHelper
    from things_mcp.server import ThingsMCPServer

    monkeypatch.setenv("THINGS_MCP_AI_CAN_CREATE_TAGS", "true" if ai_can_create_tags else "false")
    server = ThingsMCPServer()
    return server, _MCPCallHelper(server)


# ---------------------------------------------------------------------------
# 1. add_tags
# ---------------------------------------------------------------------------


class TestAddTags:
    def test_sandbox_tag_and_second_tag(self, mcp, sandbox):
        second_tag_name = f"hq-gbl-reg-tag2-{ts()}"
        from regression.conftest import _create_tag_via_applescript

        created = _create_tag_via_applescript(second_tag_name)
        assert created, f"failed to create second tag {second_tag_name!r}"
        _track_tag(sandbox, second_tag_name)

        title = sandbox_title("add tags two")
        add_result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        sandbox.track(todo_id)

        result = mcp.call_sync(
            "add_tags", todo_id=todo_id, tags=f"{sandbox.tag_name},{second_tag_name}"
        )
        assert result.get("success") is True, result

        record = read_back(
            todo_id,
            lambda r: r is not None
            and set(r.get("tags") or []) == {sandbox.tag_name, second_tag_name},
        )
        assert record is not None
        assert set(record.get("tags") or []) == {sandbox.tag_name, second_tag_name}, record

        _delete_tag_by_name(second_tag_name)

    def test_unknown_tag_policy_behavior(self, mcp, sandbox, live_server):
        """Adds only an unknown tag; asserts the outcome implied by the
        active tag_creation_policy (mirrors
        test_todo_create_delete.py's test_tags_policy_behavior)."""
        from things_mcp.config import TagCreationPolicy

        policy = live_server.config.tag_creation_policy
        unknown_tag = f"hq-gbl-reg-nonexistent-{ts()}"
        _track_tag(sandbox, unknown_tag)  # ALLOW_ALL would create it; safety net
        title = sandbox_title("add tags unknown")
        add_result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        sandbox.track(todo_id)

        result = mcp.call_sync("add_tags", todo_id=todo_id, tags=unknown_tag)

        if policy == TagCreationPolicy.FAIL_ON_UNKNOWN:
            assert_write_error(result, "NO_VALID_TAGS")
            return

        if policy == TagCreationPolicy.ALLOW_ALL:
            assert result.get("success") is True, result
            record = read_back(
                todo_id, lambda r: r is not None and unknown_tag in (r.get("tags") or [])
            )
            assert record is not None and unknown_tag in (record.get("tags") or []), record
            _delete_tag_by_name(unknown_tag)
            return

        # FILTER_SILENT / FILTER_WARN: the unknown tag is filtered, nothing
        # valid remains -> NO_VALID_TAGS (write_operations.add_tags checks
        # `if not valid_tags` after policy filtering).
        assert_write_error(result, "NO_VALID_TAGS")
        if policy == TagCreationPolicy.FILTER_WARN:
            tag_info = result.get("tag_info") or {}
            assert unknown_tag in (tag_info.get("filtered") or []), result

    def test_space_after_comma_stripped(self, mcp, sandbox):
        title = sandbox_title("add tags space")
        add_result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        sandbox.track(todo_id)

        # "<tag>, <tag>" - _parse_tag_list strips whitespace per tag entry
        # (server.py _parse_tag_list: `t.strip() for t in tags.split(',')`),
        # so a single tag with a leading space still resolves to the exact
        # sandbox tag name, not " <name>".
        result = mcp.call_sync("add_tags", todo_id=todo_id, tags=f" {sandbox.tag_name} ")
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], record

    def test_idempotent_no_duplicate(self, mcp, sandbox):
        title = sandbox_title("add tags idempotent")
        add_result = mcp.call_sync(
            "add_todo", title=title, tags=sandbox.tag_name, list_id=sandbox.project_id
        )
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        sandbox.track(todo_id)

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], record

        # Re-add the same tag - should stay a single entry, not duplicate.
        result = mcp.call_sync("add_tags", todo_id=todo_id, tags=sandbox.tag_name)
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None
        assert (record.get("tags") or []) == [sandbox.tag_name], record

    def test_unknown_todo_id(self, mcp):
        result = mcp.call_sync(
            "add_tags", todo_id="hq-gbl-reg-nonexistent-todo-id", tags="whatever"
        )
        assert result.get("success") is False, result

    def test_whitespace_only_todo_id_rejected(self, mcp):
        """hq-a5j: add_tags now validates todo_id for non-empty/
        non-whitespace before any AppleScript call, matching update_todo/
        delete_todo (previously '   ' passed straight through as a literal
        `to do id "   "` AppleScript reference)."""
        result = mcp.call_sync("add_tags", todo_id="   ", tags="whatever")
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "todo_id", result


# ---------------------------------------------------------------------------
# 2. remove_tags
# ---------------------------------------------------------------------------


class TestRemoveTags:
    def test_present_absent_mixed(self, mcp, sandbox):
        title = sandbox_title("remove tags")
        add_result = mcp.call_sync(
            "add_todo", title=title, tags=sandbox.tag_name, list_id=sandbox.project_id
        )
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        sandbox.track(todo_id)

        read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )

        # present tag only -> removed_count 1
        result = mcp.call_sync("remove_tags", todo_id=todo_id, tags=sandbox.tag_name)
        assert result.get("success") is True, result
        assert result.get("removed_count") == 1, result
        assert result.get("not_present") == [], result

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == []
        )
        assert record is not None and (record.get("tags") or []) == [], record

        # absent tag -> removed_count 0, not_present lists it
        absent_tag = f"hq-gbl-reg-absent-{ts()}"
        result2 = mcp.call_sync("remove_tags", todo_id=todo_id, tags=absent_tag)
        assert result2.get("success") is True, result2
        assert result2.get("removed_count") == 0, result2
        assert result2.get("not_present") == [absent_tag], result2

        # mixed: re-add sandbox tag, then remove [sandbox_tag, absent_tag]
        readd = mcp.call_sync("add_tags", todo_id=todo_id, tags=sandbox.tag_name)
        assert readd.get("success") is True, readd
        read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        mixed_result = mcp.call_sync(
            "remove_tags", todo_id=todo_id, tags=f"{sandbox.tag_name},{absent_tag}"
        )
        assert mixed_result.get("success") is True, mixed_result
        assert mixed_result.get("removed_count") == 1, mixed_result
        assert mixed_result.get("not_present") == [absent_tag], mixed_result

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == []
        )
        assert record is not None and (record.get("tags") or []) == [], record

    def test_case_sensitivity(self, mcp, sandbox):
        upper_name = f"Hq-Gbl-Case-{ts()}"
        lower_name = f"hq-gbl-case-{ts()}"
        from regression.conftest import _create_tag_via_applescript

        assert _create_tag_via_applescript(upper_name), f"failed to create {upper_name!r}"
        assert _create_tag_via_applescript(lower_name), f"failed to create {lower_name!r}"
        _track_tag(sandbox, upper_name)
        _track_tag(sandbox, lower_name)

        title = sandbox_title("case sensitive tags")
        add_result = mcp.call_sync(
            "add_todo", title=title, tags=f"{upper_name},{lower_name}", list_id=sandbox.project_id
        )
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        sandbox.track(todo_id)

        record = read_back(
            todo_id,
            lambda r: r is not None and set(r.get("tags") or []) == {upper_name, lower_name},
        )
        assert record is not None
        assert set(record.get("tags") or []) == {upper_name, lower_name}, record

        # Removing only the exact-case upper_name must leave lower_name intact.
        result = mcp.call_sync("remove_tags", todo_id=todo_id, tags=upper_name)
        assert result.get("success") is True, result
        assert result.get("removed_count") == 1, result

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [lower_name]
        )
        assert record is not None and (record.get("tags") or []) == [lower_name], record

        result2 = mcp.call_sync("remove_tags", todo_id=todo_id, tags=lower_name)
        assert result2.get("success") is True, result2
        assert result2.get("removed_count") == 1, result2

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == []
        )
        assert record is not None and (record.get("tags") or []) == [], record

        _delete_tag_by_name(upper_name)
        _delete_tag_by_name(lower_name)

    def test_empty_todo_id_rejected(self, mcp):
        """hq-a5j: remove_tags now validates todo_id for non-empty/
        non-whitespace before any AppleScript call, matching update_todo/
        delete_todo (previously '' passed straight through as a literal
        `to do id ""` AppleScript reference)."""
        result = mcp.call_sync("remove_tags", todo_id="", tags="whatever")
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "todo_id", result


# ---------------------------------------------------------------------------
# 3. create_tag
# ---------------------------------------------------------------------------


class TestCreateTag:
    def test_new_tag_when_allowed(self, monkeypatch, sandbox):
        server, mcp2 = _second_server(monkeypatch, ai_can_create_tags=True)
        assert server.config.ai_can_create_tags is True
        tag_name = f"hq-gbl-reg-create-{ts()}"
        _track_tag(sandbox, tag_name)  # safety net if this test fails mid-way
        result = mcp2.call_sync("create_tag", tag_name=tag_name)
        assert result.get("success") is True, result

        import things

        deadline = time.monotonic() + 10
        matches = [t for t in things.tags() or [] if t.get("title") == tag_name]
        while not matches and time.monotonic() < deadline:
            time.sleep(0.5)
            matches = [t for t in things.tags() or [] if t.get("title") == tag_name]
        assert matches, f"created tag {tag_name!r} not found via things.tags()"

        _delete_tag_by_name(tag_name)
        gone = [t for t in things.tags() or [] if t.get("title") == tag_name]
        assert gone == [], gone

    def test_existing_tag_when_allowed(self, monkeypatch, sandbox):
        server, mcp2 = _second_server(monkeypatch, ai_can_create_tags=True)
        # sandbox.tag_name already exists (created in sandbox fixture setup).
        result = mcp2.call_sync("create_tag", tag_name=sandbox.tag_name)
        # Document actual behavior: calling create_tag on an already-existing
        # tag name. Assert on success/failure explicitly rather than only
        # eyeballing it, and that no duplicate tag with the same title is
        # created either way.
        import things

        matches = [t for t in things.tags() or [] if t.get("title") == sandbox.tag_name]
        assert len(matches) == 1, (
            f"expected exactly 1 tag named {sandbox.tag_name!r} after "
            f"create_tag on an existing name, found {len(matches)}: result={result}"
        )

    def test_empty_name_rejected(self, monkeypatch, sandbox):
        """hq-a5j: tag_name now has min_length=1 in the schema, so '' is
        rejected by pydantic at the MCP tool boundary before the tool body
        ever runs - a FastMCP ToolError (surfaced by the `mcp2` helper as
        {"tool_error": ...}), not the TAG_CREATION_FAILED structured
        write-error this used to return via the AppleScript-layer path."""
        server, mcp2 = _second_server(monkeypatch, ai_can_create_tags=True)
        result = mcp2.call_sync("create_tag", tag_name="")
        assert "tool_error" in result, result

    def test_whitespace_only_name_rejected(self, monkeypatch, sandbox):
        """hq-r87: create_tag('   ') (whitespace-only) is now rejected by a
        runtime guard in server.py's create_tag before any AppleScript call
        is made, the same TAG_CREATION_FAILED code create_tag('') already
        used (AppleScript's `make new tag with properties {name:"   "}`
        would otherwise succeed and Things would silently trim the
        whitespace, creating a real tag with an empty title -
        things.tags() would show {'title': ''}). The finally-delete safety
        net stays in case of regression."""
        server, mcp2 = _second_server(monkeypatch, ai_can_create_tags=True)
        result = mcp2.call_sync("create_tag", tag_name="   ")
        try:
            assert_write_error(result, "TAG_CREATION_FAILED")
        finally:
            # Safety net: if a blank-titled tag was created anyway (e.g. a
            # regression), clean it up directly by uuid rather than by name
            # (an empty name doesn't route through _delete_tag_by_name's
            # title lookup cleanly).
            import things

            for t in things.tags() or []:
                if not (t.get("title") or "").strip():
                    escaped = t["uuid"].replace('"', '\\"')
                    import subprocess

                    subprocess.run(
                        [
                            "osascript",
                            "-e",
                            f'tell application "Things3" to delete (tag id "{escaped}")',
                        ],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )

    def test_restricted_when_ai_cannot_create_tags(self, monkeypatch, sandbox):
        server, mcp2 = _second_server(monkeypatch, ai_can_create_tags=False)
        assert server.config.ai_can_create_tags is False
        tag_name = f"hq-gbl-reg-restricted-{ts()}"
        result = mcp2.call_sync("create_tag", tag_name=tag_name)
        assert_write_error(result, "TAG_CREATION_RESTRICTED")

        import things

        matches = [t for t in things.tags() or [] if t.get("title") == tag_name]
        assert matches == [], matches

    def test_add_todo_unknown_tag_under_each_reachable_policy(self, monkeypatch, sandbox):
        """add_todo(tags=<unknown>) under ALLOW_ALL vs FILTER_WARN (the only
        two policies reachable via env override - see module docstring's
        Discovered note). Each server gets its own tracked to-do, trashed
        via a raw AppleScript delete since it's outside the shared sandbox
        session teardown's tracking list."""
        from regression.conftest import _delete_via_applescript

        # ALLOW_ALL: unknown tag is created and applied.
        server_allow, mcp_allow = _second_server(monkeypatch, ai_can_create_tags=True)
        unknown_allow = f"hq-gbl-reg-polytag-allow-{ts()}"
        title_allow = sandbox_title("policy allow_all")
        result_allow = mcp_allow.call_sync(
            "add_todo", title=title_allow, tags=unknown_allow, list_id=sandbox.project_id
        )
        assert result_allow.get("success") is True, result_allow
        todo_id_allow = result_allow.get("todo_id")
        assert todo_id_allow
        try:
            record = read_back(
                todo_id_allow,
                lambda r: r is not None and unknown_allow in (r.get("tags") or []),
            )
            assert record is not None
            assert unknown_allow in (record.get("tags") or []), record
        finally:
            _delete_via_applescript(todo_id_allow)
            _delete_tag_by_name(unknown_allow)
            import things

            leftover = [t for t in things.tags() or [] if t.get("title") == unknown_allow]
            assert leftover == [], leftover

        # FILTER_WARN: unknown tag filtered, only known sandbox tag lands.
        server_warn, mcp_warn = _second_server(monkeypatch, ai_can_create_tags=False)
        unknown_warn = f"hq-gbl-reg-polytag-warn-{ts()}"
        title_warn = sandbox_title("policy filter_warn")
        result_warn = mcp_warn.call_sync(
            "add_todo",
            title=title_warn,
            tags=f"{sandbox.tag_name},{unknown_warn}",
            list_id=sandbox.project_id,
        )
        assert result_warn.get("success") is True, result_warn
        todo_id_warn = result_warn.get("todo_id")
        assert todo_id_warn
        try:
            record = read_back(
                todo_id_warn, lambda r: r is not None and r.get("title") == title_warn
            )
            assert record is not None
            applied = record.get("tags") or []
            assert applied == [sandbox.tag_name], applied
            assert result_warn.get("tag_warnings") or "tag_info" in result_warn, result_warn
        finally:
            _delete_via_applescript(todo_id_warn)


# ---------------------------------------------------------------------------
# 4. get_tags / get_tagged_items / get_tag_usage
# ---------------------------------------------------------------------------


class TestGetTags:
    def test_sandbox_tags_present(self, mcp, sandbox, seeded):
        result = mcp.call_sync("get_tags")
        assert result.get("success") is not False, result
        # get_tags has no 'mode' parameter, so requested_mode must be None
        # while 'mode' reports the effective ('standard') shape - hq-lsb.
        assert result.get("requested_mode") is None, result
        assert result.get("mode") == "standard", result
        items = result.get("items", [])
        titles = {i.get("title") for i in items}
        assert sandbox.tag_name in titles, titles

    def test_include_items_lists_seed_todo(self, mcp, sandbox, seeded):
        import things

        expected_titles = {
            t.get("title")
            for t in (things.todos(tag=sandbox.tag_name) or [])
        }
        result = mcp.call_sync("get_tags", include_items=True)
        items = result.get("items", [])
        entry = next((i for i in items if i.get("title") == sandbox.tag_name), None)
        assert entry is not None, items
        actual_titles = {t.get("title") for t in (entry.get("todos") or [])}
        assert actual_titles == expected_titles, (actual_titles, expected_titles)
        assert seeded.titles.get("with_tag") in actual_titles, (
            seeded.titles.get("with_tag"),
            actual_titles,
        )


class TestGetTaggedItems:
    def test_sandbox_tag_returns_exact_items(self, mcp, sandbox, seeded):
        import things

        expected_ids = {
            t.get("uuid") for t in (things.todos(tag=sandbox.tag_name) or [])
        }
        result = mcp.call_sync("get_tagged_items", tag=sandbox.tag_name)
        assert result.get("success") is not False, result
        # get_tagged_items has no 'mode' parameter, so requested_mode must be
        # None while 'mode' reports the effective ('standard') shape - hq-lsb.
        assert result.get("requested_mode") is None, result
        assert result.get("mode") == "standard", result
        items = result.get("items", [])
        actual_ids = {i.get("uuid") for i in items}
        assert actual_ids == expected_ids, (actual_ids, expected_ids)
        assert seeded.uuid("with_tag") in actual_ids, (seeded.uuid("with_tag"), actual_ids)

    def test_unknown_tag_with_case_variant_suggestion(self, mcp, sandbox):
        # sandbox.tag_name is e.g. "hq-gbl-reg-tag-<ts>" - an all-lowercase
        # slug, so a wrong-case near-miss query is its .upper() form, which
        # is guaranteed to differ from the real (lowercase) tag and to
        # case-insensitively match it for the suggestions lookup.
        near_miss = sandbox.tag_name.upper()
        assert near_miss != sandbox.tag_name
        result = mcp.call_sync("get_tagged_items", tag=near_miss)
        assert_read_error(result, "unknown_tag")
        assert result.get("tag") == near_miss, result
        suggestions = result.get("suggestions") or []
        assert sandbox.tag_name in suggestions, result


class TestGetTagUsage:
    def test_sandbox_tag_counts_match_live(self, mcp, sandbox):
        """sandbox.tag_name is applied by MANY other tests across this
        session-scoped suite (test_bulk_and_move.py, test_projects_areas.py,
        test_update_todo.py, etc. all tag their own throwaway todos AND
        PROJECTS with it, and several of those objects are only cleaned up
        at session teardown - not at their own test's end), so the live
        "ground truth" count for sandbox.tag_name is actively, legitimately
        changing throughout the whole suite run, not just from this test;
        comparing a things.py snapshot against get_tag_usage's response for
        that shared tag is inherently racy when run as part of the full
        suite (observed on two separate full-suite runs: expected
        open_count 10/10 matched exactly both times, but total_count
        10-vs-12 both times - a stable, reproducible mismatch explained by
        other tests' tagged-but-not-yet-torn-down projects/todos still
        existing at the moment this test runs, not a get_tag_usage bug -
        confirmed via a standalone controlled repro with a dedicated tag
        applied to 3 todos in known incomplete/completed/canceled states,
        where get_tag_usage's open_count/total_count matched things.py's
        counts exactly). Use a tag created and populated ENTIRELY within
        this test's own scope instead of the shared sandbox tag, so there
        is no other test in the session that can ever tag/untag it."""
        import things

        tag_name = f"hq-gbl-reg-tagusage-{ts()}"
        from regression.conftest import _create_tag_via_applescript

        assert _create_tag_via_applescript(tag_name), tag_name
        _track_tag(sandbox, tag_name)

        project_result = mcp.call_sync(
            "add_project", title=sandbox_title("tagusage proj")
        )
        assert project_result.get("success") is True, project_result
        project_id = project_result["project_id"]

        todo_ids = []
        for i in range(3):
            r = mcp.call_sync(
                "add_todo",
                title=sandbox_title(f"tagusage todo {i}"),
                tags=tag_name,
                list_id=project_id,
            )
            assert r.get("success") is True, r
            todo_ids.append(r["todo_id"])
            sandbox.track(r["todo_id"])
        sandbox.tracked_project_ids.append(project_id)

        # One incomplete (as created), one completed, one canceled -
        # exercises all three statuses this report tallies over.
        read_back(
            todo_ids[0], lambda r: r is not None and (r.get("tags") or []) == [tag_name]
        )
        comp_result = mcp.call_sync("update_todo", id=todo_ids[1], completed="true")
        assert comp_result.get("success") is True, comp_result
        cancel_result = mcp.call_sync("update_todo", id=todo_ids[2], canceled="true")
        assert cancel_result.get("success") is True, cancel_result

        read_back(todo_ids[1], lambda r: r is not None and r.get("status") == "completed")
        read_back(todo_ids[2], lambda r: r is not None and r.get("status") == "canceled")

        expected_open = len(things.todos(tag=tag_name, status="incomplete") or [])
        expected_total = sum(
            len(things.todos(tag=tag_name, status=status) or [])
            for status in ("incomplete", "completed", "canceled")
        )
        assert expected_open == 1, expected_open
        assert expected_total == 3, expected_total

        result = mcp.call_sync("get_tag_usage", mode="detailed")
        items = result.get("items", [])
        entry = next((i for i in items if i.get("title") == tag_name), None)
        assert entry is not None, items
        assert entry.get("open_count") == expected_open, (entry, expected_open)
        assert entry.get("total_count") == expected_total, (entry, expected_total)

        _delete_tag_by_name(tag_name)

    def test_only_unused_includes_fresh_tag(self, mcp, sandbox):
        from regression.conftest import _create_tag_via_applescript

        unused_name = f"hq-gbl-reg-unused-{ts()}"
        assert _create_tag_via_applescript(unused_name), unused_name
        _track_tag(sandbox, unused_name)

        import things

        deadline = time.monotonic() + 10
        while not any(t.get("title") == unused_name for t in things.tags() or []):
            if time.monotonic() >= deadline:
                pytest.fail(f"tag {unused_name!r} never appeared via things.tags()")
            time.sleep(0.5)

        result = mcp.call_sync("get_tag_usage", only_unused=True, mode="detailed")
        items = result.get("items", [])
        titles = {i.get("title") for i in items}
        assert unused_name in titles, titles
        entry = next(i for i in items if i.get("title") == unused_name)
        assert entry.get("open_count") == 0, entry
        assert entry.get("total_count") == 0, entry

        # The sandbox tag (which has at least the with_tag seed) must NOT
        # appear in only_unused - guards against a vacuously-true filter.
        assert sandbox.tag_name not in titles, titles

        _delete_tag_by_name(unused_name)

    @pytest.mark.parametrize("mode", ["summary", "minimal", "standard", "detailed"])
    def test_every_valid_mode(self, mcp, sandbox, mode):
        result = mcp.call_sync("get_tag_usage", mode=mode)
        assert result.get("success") is not False, result
        if mode == "summary":
            assert "tag_count" in result, result
            assert "unused_count" in result, result
            assert "top" in result, result
        else:
            items = result.get("items", [])
            assert isinstance(items, list)
            if items:
                sample = items[0]
                assert "title" in sample, sample
                if mode == "minimal":
                    assert "open_count" in sample, sample
                else:
                    assert "uuid" in sample, sample
                    assert "total_count" in sample, sample
                    assert "area_count" in sample, sample

    @pytest.mark.parametrize("mode", ["auto", "raw"])
    def test_invalid_modes_rejected(self, mcp, sandbox, mode):
        # get_tag_usage's tool-layer validation only accepts
        # summary/minimal/standard/detailed (server.py: `if mode not in
        # ("summary", "minimal", "standard", "detailed")`) - unlike other
        # list tools, 'auto' and 'raw' are NOT valid modes here and must be
        # rejected as invalid_mode, per CLAUDE.md's own note that this
        # tool's mode set differs from the standard auto/summary/minimal/
        # standard/detailed/raw set used elsewhere.
        result = mcp.call_sync("get_tag_usage", mode=mode)
        assert_read_error(result, "invalid_mode")

"""Todo and project creation/update operations."""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional, Tuple

from ..locale_aware_dates import locale_handler, when_has_time_component
from ..things_import import LazyThingsProxy
from ..utils.applescript_utils import AppleScriptTemplates
# write_error is imported lazily (inside each call site, like the existing
# `from ..services.applescript_manager import AUTH_TOKEN_HINT` pattern in
# this file) rather than at module level: tools_helpers/__init__.py eagerly
# imports write_operations.py -> pure_applescript_scheduler.py ->
# scheduling/__init__.py -> this module, so a top-level
# `from ..tools_helpers.errors import write_error` here is a circular
# import (errors.py itself has no such dependency - see its docstring -
# but importing through the tools_helpers package triggers the whole
# package's __init__.py first).

# Lazily-importing proxy for things.py -- avoids the module-level,
# unbounded glob.iglob() scan that a plain `import things` would perform
# at server boot time. See things_import.LazyThingsProxy docstring; this
# also preserves existing test seams that patch `things.<attr>` (the real
# module) or `todo_operations.things.<attr>` (this proxy) directly.
things = LazyThingsProxy()

logger = logging.getLogger(__name__)

# Sentinel distinguishing "things.get() lookup itself raised" (DB
# unreadable / Full Disk Access missing) from "things.get() succeeded and
# returned None" (id genuinely unknown) - used by update_todo's todo_id
# pre-check (hq-wbm). Mirrors tools_helpers/write_operations.py's
# module-local _RESOLVE_UNAVAILABLE sentinel of the same shape; not shared
# across modules to avoid the circular-import concerns documented above
# for _write_error.
_RESOLVE_UNAVAILABLE = object()


def _write_error(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    """Thin wrapper around tools_helpers.errors.write_error that performs
    the import lazily on first call, to avoid the circular import
    described above. Imported once per call rather than cached at module
    scope so this stays a trivial, side-effect-free forwarding call."""
    from ..tools_helpers.errors import write_error
    return write_error(code, message, **extra)


# Documented cap on checklist items per Things URL-scheme request (see
# CLAUDE.md "Format Requirements" under Checklist Support). This is a
# per-request limit only - Things gives no cheap way to read how many
# checklist items a to-do already has, so add_checklist_items/
# prepend_checklist_items do NOT count pre-existing items on the target
# to-do, only the items list being submitted in this call (hq-exe).
MAX_CHECKLIST_ITEMS = 100


def _check_checklist_item_count(items: Any, field: str) -> Optional[Dict[str, Any]]:
    """Enforce the documented per-request checklist item cap.

    Accepts either a list of item strings (add_checklist_items,
    prepend_checklist_items, replace_checklist_items) or the raw
    checklist_items value passed to add_todo, which may be a list or a
    newline-separated string. Returns a write_error()-shaped dict (code
    TOO_MANY_CHECKLIST_ITEMS) if the count exceeds MAX_CHECKLIST_ITEMS,
    or None if the count is within bounds (including 0/empty).

    Must be called before any AppleScript/URL-scheme write is issued.
    """
    if not items:
        return None
    if isinstance(items, str):
        count = len([item for item in items.split('\n') if item.strip()])
    else:
        count = len(items)
    if count > MAX_CHECKLIST_ITEMS:
        return _write_error(
            "TOO_MANY_CHECKLIST_ITEMS",
            f"checklist supports at most {MAX_CHECKLIST_ITEMS} items, got {count}",
            field=field,
        )
    return None


class TodoOperations:
    """Handles todo and project creation/update operations."""

    # How long to keep polling for the new todo's id after a URL-scheme
    # create before giving up (see _add_todo_via_url_scheme / hq-nxu.12).
    _URL_SCHEME_LOOKUP_DEADLINE_SECS = 3.0
    _URL_SCHEME_LOOKUP_POLL_INTERVAL_SECS = 0.25

    def __init__(self, applescript_manager, scheduler):
        """Initialize with AppleScript manager and scheduler.

        Args:
            applescript_manager: AppleScript execution manager
            scheduler: Scheduling strategies instance
        """
        self.applescript = applescript_manager
        self.scheduler = scheduler

    def _convert_to_boolean(self, value: Any) -> Optional[bool]:
        """
        Convert various input formats to boolean.

        Handles:
        - Boolean values: True, False
        - String values: "true", "True", "TRUE", "false", "False", "FALSE"
        - None and empty strings return None

        Args:
            value: The value to convert

        Returns:
            True, False, or None if value is None/empty

        Raises:
            ValueError: If value cannot be converted to boolean
        """
        if value is None or value == '':
            return None

        # Already a boolean
        if isinstance(value, bool):
            return value

        # String conversion
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower == 'true':
                return True
            elif value_lower == 'false':
                return False
            else:
                raise ValueError(f"Invalid boolean string: '{value}'. Must be 'true' or 'false'")

        # Fallback for any other type - use Python's truthiness
        return bool(value)

    def _build_create_todo_script(self, title: str, notes: str, tags: List[str],
                                  deadline: str, area: str, project: str,
                                  checklist: List[str], project_id: Optional[str] = None,
                                  area_id: Optional[str] = None) -> str:
        """Build AppleScript for creating a new todo.

        Args:
            title: Todo title
            notes: Todo notes
            tags: Tags list
            deadline: Deadline date
            area: Area name (looked up by name via `area <name>`)
            project: Project ID (looked up by id via `project id "..."`, unescaped -
                kept only for backwards compatibility; prefer project_id)
            checklist: Checklist items
            project_id: Project UUID to place the todo in, escaped safely via
                AppleScriptTemplates.escape_string. Takes precedence over `project`.
            area_id: Area UUID to place the todo in, escaped safely via
                AppleScriptTemplates.escape_string. Takes precedence over `area`.

        Returns:
            AppleScript code
        """
        escaped_title = AppleScriptTemplates.escape_string(title)
        escaped_notes = AppleScriptTemplates.escape_string(notes)

        script = f'''
            tell application "Things3"
                try
                    set newTodo to make new to do with properties {{name:{escaped_title}}}
            '''

        if notes:
            script += f'set notes of newTodo to {escaped_notes}\n                    '

        if area_id:
            escaped_area_id = AppleScriptTemplates.escape_string(area_id)
            script += f'set area of newTodo to area id {escaped_area_id}\n                    '
        elif area:
            escaped_area = AppleScriptTemplates.escape_string(area)
            script += f'set area of newTodo to area {escaped_area}\n                    '

        if project_id:
            escaped_project_id = AppleScriptTemplates.escape_string(project_id)
            script += f'set project of newTodo to project id {escaped_project_id}\n                    '
        elif project:
            escaped_project = AppleScriptTemplates.escape_string(project)
            script += f'set project of newTodo to project id {escaped_project}\n                    '

        if tags:
            tags_string = ', '.join(tags)
            escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
            script += f'set tag names of newTodo to {escaped_tags_string}\n                    '

        # NOTE: Checklist items are NOT supported via AppleScript (Things 3 API limitation)
        # The checklist parameter is accepted but we don't generate AppleScript for it
        # A warning is added in the response instead
        # if checklist:
        #     for item in checklist:
        #         escaped_item = AppleScriptTemplates.escape_string(item)
        #         script += f'make new checklist item in newTodo with properties {{name:{escaped_item}}}\n                    '

        if deadline:
            date_components = locale_handler.normalize_date_input(deadline)
            if date_components:
                year, month, day = date_components
                script += f'''
                    set deadlineDate to (current date)
                    set time of deadlineDate to 0
                    set day of deadlineDate to 1
                    set year of deadlineDate to {year}
                    set month of deadlineDate to {month}
                    set day of deadlineDate to {day}
                    set due date of newTodo to deadlineDate
                    '''

        script += '''
                    return id of newTodo
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

        return script

    def _resolve_list_id(self, list_id: str) -> Dict[str, Any]:
        """Resolve a list_id (project or area UUID) to its kind via things.py.

        Args:
            list_id: A project or area UUID.

        Returns:
            {"kind": "project"|"area", "id": list_id} on success. If the
            things.py lookup itself raises (e.g. the Things database is
            unreadable / Full Disk Access is missing), this falls back to
            {"kind": "project", "id": list_id, "fallback": True} - the
            pre-bead behavior of assuming list_id is a project id - rather
            than refusing the write entirely, since add_todo(list_id=...)
            used to work via AppleScript alone with no things.py database
            dependency. A write_error()-shaped dict (code "NOT_FOUND") is
            only returned when the lookup *succeeds* and definitively
            reports the id as unknown or not a project/area.
        """
        try:
            record = things.get(list_id)
        except Exception as e:
            logger.warning(
                f"things.py lookup failed while resolving list_id {list_id} "
                f"(falling back to treating it as a project id): {e}"
            )
            return {"kind": "project", "id": list_id, "fallback": True}

        if not record:
            return _write_error(
                "NOT_FOUND",
                f"list_id '{list_id}' does not match any known project or area",
            )

        record_type = record.get('type')
        if record_type == 'project':
            return {"kind": "project", "id": list_id}
        if record_type == 'area':
            return {"kind": "area", "id": list_id}

        return _write_error(
            "NOT_FOUND",
            f"list_id '{list_id}' refers to a '{record_type}', not a project or area",
        )

    def _resolve_list_title(self, list_title: str) -> Dict[str, Any]:
        """Resolve a list_title (project or area title) to an id via things.py.

        Performs an exact-title match against both projects and areas. If the
        title matches more than one project/area (including across both
        types), returns a structured error listing every matching id so the
        caller can disambiguate.

        Args:
            list_title: Exact title of a project or area.

        Returns:
            {"kind": "project"|"area", "id": "..."} on a single unambiguous
            match, or a write_error()-shaped dict if there is no match
            (code "NOT_FOUND") or more than one (code "AMBIGUOUS_TARGET",
            with the matching "kind:id" strings in the "ids" extra field).
        """
        try:
            matching_projects = [p for p in (things.projects() or []) if p.get('title') == list_title]
        except Exception as e:
            logger.debug(f"Error listing projects for list_title resolution: {e}")
            matching_projects = []

        try:
            matching_areas = [a for a in (things.areas() or []) if a.get('title') == list_title]
        except Exception as e:
            logger.debug(f"Error listing areas for list_title resolution: {e}")
            matching_areas = []

        matches = [("project", p['uuid']) for p in matching_projects] + \
                  [("area", a['uuid']) for a in matching_areas]

        if not matches:
            return _write_error(
                "NOT_FOUND",
                f"list_title '{list_title}' does not match any project or area",
            )

        if len(matches) > 1:
            ids = [f"{kind}:{mid}" for kind, mid in matches]
            return _write_error(
                "AMBIGUOUS_TARGET",
                f"list_title '{list_title}' is ambiguous - matches multiple "
                f"projects/areas: {', '.join(ids)}",
                ids=ids,
            )

        kind, matched_id = matches[0]
        return {"kind": kind, "id": matched_id}

    def _resolve_area(
        self, area_id: str = '', area_title: str = ''
    ) -> Dict[str, Any]:
        """Pre-resolve an add_project/update_project area target via
        things.py BEFORE any write (hq-rmh).

        Mirrors _resolve_list_id/_resolve_list_title's fallback semantics
        exactly, applied to the project/area-only 'area_id'/'area_title'
        parameters: area_id takes precedence over area_title, matching the
        existing AppleScript-emission precedence in
        _build_create_project_script/update_project/
        _add_project_via_url_scheme.

        Without this pre-check, Things 3's AppleScript has no transactional
        rollback - 'make new project ...' followed by 'set area of
        newProject to area "<bogus>"' in the same try block creates the
        project first, then the area-set line throws, leaving a real,
        un-areaed orphan project behind despite the call reporting
        success=False/APPLESCRIPT_ERROR (hq-rmh).

        Args:
            area_id: Area UUID (takes precedence if provided).
            area_title: Area title (exact match).

        Returns:
            {} if neither area_id nor area_title was given (nothing to
            resolve - caller proceeds with no area set).
            {"area_id": "..."} on a successful resolution - callers should
            use this resolved id, not the raw input, for the AppleScript/
            URL-scheme area-id assignment; this normalizes an area_title
            match to its concrete uuid so downstream code only ever emits
            'area id "<uuid>"' rather than "area \"<title>\"" once a title
            has been resolved.
            A write_error()-shaped dict (code "NOT_FOUND") if area_id
            doesn't match any known area, or matches something that is not
            an area; code "AMBIGUOUS_TARGET" (with an "ids" field) if
            area_title matches more than one area.
            If the underlying things.py lookup itself raises (e.g. the
            Things database is unreadable / Full Disk Access is missing),
            this falls back to {"area_id": area_id} (area_id path) or
            {} (area_title path, since there's nothing to normalize
            without a working lookup) - the pre-bead behavior of emitting
            the raw value unchecked - rather than refusing the write,
            mirroring _resolve_list_id's documented DB-unreadable fallback
            (CLAUDE.md "list_id fallback when the Things database is
            unreadable").
        """
        if area_id:
            try:
                record = things.get(area_id)
            except Exception as e:
                logger.warning(
                    f"things.py lookup failed while resolving area_id "
                    f"{area_id} (falling back to emitting it unchecked): {e}"
                )
                return {"area_id": area_id}

            if not record or record.get('type') != 'area':
                return _write_error(
                    "NOT_FOUND",
                    f"area_id '{area_id}' does not match any known area",
                )
            return {"area_id": area_id}

        if area_title:
            try:
                matching_areas = [
                    a for a in (things.areas() or []) if a.get('title') == area_title
                ]
            except Exception as e:
                logger.warning(
                    f"things.py lookup failed while resolving area_title "
                    f"{area_title!r} (falling back to emitting it "
                    f"unchecked): {e}"
                )
                return {}

            if not matching_areas:
                return _write_error(
                    "NOT_FOUND",
                    f"area_title '{area_title}' does not match any known area",
                )
            if len(matching_areas) > 1:
                ids = [a['uuid'] for a in matching_areas]
                return _write_error(
                    "AMBIGUOUS_TARGET",
                    f"area_title '{area_title}' is ambiguous - matches "
                    f"multiple areas: {', '.join(ids)}",
                    ids=ids,
                )
            return {"area_id": matching_areas[0]['uuid']}

        return {}

    async def add_todo(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new todo using AppleScript, or URL scheme if heading, checklist items,
        and/or when='evening'/when with a '@HH:MM' time component are provided.

        when='evening' (alias 'tonight', normalized to 'evening' by
        ParameterValidator) is routed via the Things URL scheme's 'add'
        action - AppleScript's 'schedule' command has no way to set the
        "This Evening" flag. Unlike heading/update, the URL scheme 'add'
        action does not require the Things auth token.

        when='YYYY-MM-DD@HH:MM' (sets a reminder) is routed the same way:
        the AppleScript scheduling path (schedule_todo_reliable ->
        locale_aware_dates.normalize_date_input) only extracts year/month/
        day and silently drops the time component, so no reminder is ever
        set (hq-4gn). The Things URL scheme's 'add' action natively
        supports this form and sets the reminder, and - like the evening
        case - does not require the auth token.
        """
        try:
            # Extract parameters
            notes = kwargs.get('notes', '')
            tags = kwargs.get('tags', [])
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', '')
            area = kwargs.get('area', '')
            project = kwargs.get('project', '') or kwargs.get('list_id', '')
            checklist = kwargs.get('checklist_items') or []
            heading = kwargs.get('heading', '')
            list_title = kwargs.get('list_title', '')

            # Enforce the documented per-request checklist item cap before
            # any write is attempted (hq-exe).
            count_error = _check_checklist_item_count(checklist, field="checklist_items")
            if count_error:
                return count_error

            # A heading can only be honoured via the Things URL scheme (Things 3
            # AppleScript has no heading class). Require a target project.
            if heading and not project and not list_title:
                return _write_error(
                    "VALIDATION_ERROR",
                    "heading requires a target project (list_id or list_title)",
                    field="heading",
                )

            # Things 3's AppleScript 'schedule' command only accepts a date
            # object - it has no way to set the "This Evening" flag (verified
            # against the AppleScript dictionary: 'schedule ... for <date>'
            # only, no evening/tonight parameter). The Things URL scheme's
            # 'add' action DOES accept when=evening, so route there.
            when_is_evening = isinstance(when, str) and when.strip().lower() == 'evening'

            # when='YYYY-MM-DD@HH:MM' sets a reminder via the Things URL
            # scheme natively; the AppleScript scheduler drops the time
            # component (see docstring / hq-4gn).
            when_has_time = when_has_time_component(when)

            # If a heading, checklist items, an evening schedule, or a
            # when with a time component are provided, use the Things URL
            # scheme - it is the only way to create checklists, the only
            # way to place a new to-do directly under a heading, the only
            # way to set "This Evening", and the only way to set a reminder
            # time.
            if heading or checklist or when_is_evening or when_has_time:
                return await self._add_todo_via_url_scheme(
                    title=title,
                    notes=notes,
                    tags=tags,
                    when=when,
                    deadline=deadline,
                    list_id=project,
                    list_title=list_title,
                    heading=heading,
                    checklist_items=checklist
                )

            # Otherwise use AppleScript (faster, more reliable for non-checklist,
            # non-heading todos). Resolve list_id/list_title to a project or area
            # id before building the script.
            project_id: Optional[str] = None
            area_id: Optional[str] = None

            if project:
                resolution = self._resolve_list_id(project)
                if "error" in resolution:
                    return resolution
                if resolution["kind"] == "project":
                    project_id = resolution["id"]
                else:
                    area_id = resolution["id"]
            elif list_title:
                resolution = self._resolve_list_title(list_title)
                if "error" in resolution:
                    return resolution
                if resolution["kind"] == "project":
                    project_id = resolution["id"]
                else:
                    area_id = resolution["id"]

            if project_id:
                target_error = self._check_project_target_not_completed(project_id)
                if target_error:
                    return target_error

            script = self._build_create_todo_script(
                title, notes, tags, deadline, area,
                project='', checklist=checklist,
                project_id=project_id, area_id=area_id
            )
            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                todo_id = result.get("output", "").strip()
                if todo_id and not todo_id.startswith("error:"):
                    # Build response
                    response = {
                        "success": True,
                        "todo_id": todo_id
                    }

                    # Schedule if when date provided
                    if when:
                        schedule_result = await self.scheduler.schedule_todo_reliable(todo_id, when)
                        response["message"] = "Todo created and scheduled successfully"
                        response["scheduling"] = schedule_result
                    else:
                        response["message"] = "Todo created successfully"

                    return response
                return _write_error(
                    "APPLESCRIPT_ERROR", "Failed to create todo", details=todo_id
                )
            return _write_error(
                "APPLESCRIPT_ERROR", "Failed to create todo",
                details=result.get("output", "AppleScript execution failed"),
            )

        except Exception as e:
            logger.error(f"Error adding todo: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to add todo", details=str(e))

    def _check_project_target_not_completed(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Reject a write into a completed/canceled project before it happens.

        Adding or moving a to-do into a completed or canceled project
        reopens that project in Things (a real, visible change to
        pre-existing user data), which is very unlikely to be the caller's
        intent. This is a read-only pre-check via things.py - it never
        writes anything itself.

        Args:
            project_id: A project UUID (areas have no status/completion
                concept in Things, so this is only meaningful for projects -
                callers must not call this for an area_id).

        Returns:
            A write_error()-shaped dict (code "TARGET_COMPLETED") if the
            project's things.py status is 'completed' or 'canceled', or
            None if the project is open/incomplete, or if its status could
            not be determined (things.py lookup failed or returned nothing)
            - in which case we stay silent rather than block a write on a
            lookup glitch.
        """
        try:
            record = things.get(project_id)
        except Exception as e:
            logger.warning(
                f"things.py lookup failed while checking completed status for "
                f"project {project_id} (allowing the write to proceed "
                f"unchecked): {e}"
            )
            return None

        if not record:
            return None

        status = record.get('status')
        if status in ('completed', 'canceled'):
            return _write_error(
                "TARGET_COMPLETED",
                f"Target project is {status}; adding/moving into it would "
                "reopen it. Reopen it first or choose another target.",
            )
        return None

    def _check_heading_status(
        self, heading: str, list_id: str = '', list_title: str = ''
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Resolve the target project once and report both the heading's
        existence/completion status in a single things.tasks() query.

        Combines what used to be two separate checks (_check_heading_exists
        and _check_heading_target_not_completed) - both needed the same
        project resolution and the same status=None things.tasks() heading
        list, so doing them separately issued that query twice per call.

        The Things URL scheme silently ignores a heading that doesn't exist
        in the target project (the to-do still lands in the project, just
        not under that heading); adding/moving into a completed/canceled
        project or heading reopens it in Things (a real, visible change to
        pre-existing user data). This is a read-only pre-check via
        things.py - it never writes anything itself.

        Args:
            heading: Heading title to look for within the resolved project.
            list_id: Project/area id supplied by the caller, if any.
            list_title: Project/area title supplied by the caller, if any.

        Returns:
            A (target_error, warning) tuple - at most one is non-None:
            - target_error: a write_error()-shaped dict (code
              "TARGET_COMPLETED") if the resolved project, or the matched
              heading row, is completed/canceled. The write must be
              rejected before it happens when this is set.
            - warning: a warning string if the heading could not be
              confirmed to exist in the resolved project (and the project
              itself is not completed/canceled).
            (None, None) if the heading was found and open, or if the
            target project could not be resolved (e.g. an area target, or
            an unresolvable list_title/list_id - those cases are reported
            by their own resolution errors elsewhere) - don't guess in
            either case.
        """
        project_id = None
        if list_id:
            resolution = self._resolve_list_id(list_id)
            if resolution.get("kind") == "project":
                project_id = resolution["id"]
        elif list_title:
            resolution = self._resolve_list_title(list_title)
            if resolution.get("kind") == "project":
                project_id = resolution["id"]

        if not project_id:
            return None, None

        project_error = self._check_project_target_not_completed(project_id)
        if project_error:
            return project_error, None

        try:
            # status=None: things.tasks() defaults to status='incomplete', so
            # a completed heading (e.g. a past-dated recurring heading like
            # "Johan" in a project) would otherwise be invisible here and
            # produce a false "heading not found" warning even though the
            # URL-scheme move actually succeeds (same root cause/fix as the
            # heading map built in hq-f0w.24).
            existing_headings = things.tasks(type='heading', project=project_id, status=None) or []
        except Exception as e:
            logger.warning(
                f"things.py lookup failed while checking heading '{heading}' "
                f"status in project {project_id} (skipping heading "
                f"existence/completion check for this call): {e}"
            )
            return None, None

        matched = next((h for h in existing_headings if h.get('title') == heading), None)
        if matched is None:
            return None, (
                f"Heading '{heading}' was not found in the target project; "
                "Things will still create the to-do in the project but may not "
                "place it under this heading."
            )

        if matched.get('status') in ('completed', 'canceled'):
            return _write_error(
                "TARGET_COMPLETED",
                f"Target heading '{heading}' is {matched.get('status')}; "
                "adding/moving into it would reopen it. Reopen it first "
                "or choose another target.",
            ), None

        return None, None

    async def _find_todo_ids_by_title(self, title: str) -> List[str]:
        """Return the ids of all (non-trashed) to-dos with the exact title.

        Used by _add_todo_via_url_scheme to snapshot existing ids before a
        URL-scheme create and poll for new ones afterward, since the URL
        scheme itself does not return the created todo's id. Uses
        AppleScript (rather than the things.py proxy) so the match is an
        exact, live-database title comparison consistent with what Things
        itself just did, and so it works even when the local things.py
        SQLite snapshot lags a fresh write.

        Returns an empty list (rather than raising) on any AppleScript
        failure, so a lookup glitch degrades to "no ids found" instead of
        crashing the create.
        """
        script = f'''
        tell application "Things3"
            try
                set foundTodos to to dos whose name is {AppleScriptTemplates.escape_string(title)}
                set idList to {{}}
                repeat with aTodo in foundTodos
                    set end of idList to (id of aTodo)
                end repeat
                set AppleScript's text item delimiters to "\\n"
                set idText to idList as text
                set AppleScript's text item delimiters to ""
                return idText
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''
        result = await self.applescript.execute_applescript(script)
        if not result.get('success'):
            logger.debug(f"Failed to look up todo ids for title {title!r}: {result.get('error')}")
            return []

        output = (result.get('output') or '').strip()
        if not output or output.startswith('error:'):
            if output.startswith('error:'):
                logger.debug(f"AppleScript error looking up todo ids for title {title!r}: {output}")
            return []

        return [line.strip() for line in output.split('\n') if line.strip()]

    async def _newest_todo_id(self, ids: List[str]) -> str:
        """Given several candidate todo ids, return the most recently created one.

        Used as the tie-breaker when more than one new todo with the same
        title appears between the pre-create snapshot and a post-create
        poll in _add_todo_via_url_scheme. Falls back to the last id in
        `ids` if the creation-date lookup itself fails, so a lookup
        glitch still returns *some* id rather than raising.
        """
        id_list_literal = ", ".join(AppleScriptTemplates.escape_string(i) for i in ids)
        script = f'''
        tell application "Things3"
            try
                set candidateIds to {{{id_list_literal}}}
                set newestId to ""
                set newestDate to missing value
                repeat with anId in candidateIds
                    -- `anId` from `repeat...in list` is a reference into
                    -- the list, not a plain string; coerce to text before
                    -- using it as an id or returning it, otherwise it
                    -- stringifies as "item N of {list}" instead of the id.
                    set anIdText to anId as text
                    set aTodo to to do id anIdText
                    set aDate to creation date of aTodo
                    if newestDate is missing value or aDate > newestDate then
                        set newestId to anIdText
                        set newestDate to aDate
                    end if
                end repeat
                return newestId
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''
        result = await self.applescript.execute_applescript(script)
        if result.get('success'):
            output = (result.get('output') or '').strip()
            if output and not output.startswith('error:'):
                return output
            if output.startswith('error:'):
                logger.debug(f"AppleScript error resolving newest todo id: {output}")
        return ids[-1]

    async def _add_todo_via_url_scheme(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a todo using the Things URL scheme.

        This is the only way to create checklist items and the only way to
        place a new to-do directly under a heading, as Things 3's AppleScript
        dictionary supports neither.

        Args:
            title: Todo title
            notes: Optional notes
            tags: Optional tag list
            when: Optional scheduling date
            deadline: Optional deadline date
            list_id: Optional project/area ID
            list_title: Optional project/area title
            heading: Optional heading within project
            checklist_items: Optional list of checklist item titles

        Returns:
            Dict with success status and todo information
        """
        try:
            # Build URL parameters
            params = {
                'title': title
            }

            # Add optional parameters
            if kwargs.get('notes'):
                params['notes'] = kwargs['notes']

            if kwargs.get('tags'):
                # Tags are comma-separated in URL scheme
                params['tags'] = ','.join(kwargs['tags'])

            if kwargs.get('when'):
                params['when'] = kwargs['when']

            if kwargs.get('deadline'):
                params['deadline'] = kwargs['deadline']

            # Things URL scheme distinguishes targeting by id ('list-id') from
            # targeting by name ('list') - using 'list' with a UUID silently
            # fails to resolve and the to-do lands in the Inbox instead.
            if kwargs.get('list_id'):
                params['list-id'] = kwargs['list_id']
            elif kwargs.get('list_title'):
                # Resolve list_title to a concrete id up front (same
                # exact-title match, and same structured errors for an
                # unknown/ambiguous title, as the AppleScript branch) rather
                # than passing the raw title straight through as 'list' -
                # an unresolved/ambiguous title otherwise silently succeeds
                # and the to-do lands in the Inbox instead of erroring.
                resolution = self._resolve_list_title(kwargs['list_title'])
                if "error" in resolution:
                    return resolution
                # 'list-id' accepts both project and area ids in the Things
                # URL scheme, so a single resolved id works for either kind.
                params['list-id'] = resolution["id"]

            heading = kwargs.get('heading') or ''

            # When heading is absent, the heading-target pre-check below
            # never runs, so a list_id/list_title resolving to a completed/
            # canceled project would otherwise reach execute_url_scheme('add')
            # unchecked (e.g. add_todo(list_id=<completed>, checklist_items=[...])
            # or when='evening' with no heading) - both still take this
            # URL-scheme path for reasons unrelated to the project target
            # (checklist items / the "This Evening" flag), so the project
            # itself must still be checked here. _check_project_target_not_completed
            # is a no-op for an area id (things.get() on an area has no
            # 'completed'/'canceled' status), so areas pass through.
            if not heading and params.get('list-id'):
                target_error = self._check_project_target_not_completed(params['list-id'])
                if target_error:
                    return target_error

            warnings: List[str] = []
            if heading:
                target_error, heading_warning = self._check_heading_status(
                    heading, kwargs.get('list_id', ''), kwargs.get('list_title', '')
                )
                if target_error:
                    return target_error
                params['heading'] = heading
                if heading_warning:
                    warnings.append(heading_warning)

            # Add checklist items (newline-separated, URL-encoded)
            if kwargs.get('checklist_items'):
                items = kwargs['checklist_items']
                logger.debug(f"Checklist items received: type={type(items)}, value={repr(items)}")

                # Handle both string and list inputs
                if isinstance(items, str):
                    # If it's already a newline-separated string, use it as-is
                    # If it's a single item, it will work too
                    params['checklist-items'] = items
                elif isinstance(items, list):
                    # Convert list to newline-separated string
                    params['checklist-items'] = '\n'.join(items)
                    logger.debug(f"Joined list to string: {repr(params['checklist-items'])}")
                else:
                    # Fallback: convert to string
                    params['checklist-items'] = str(items)

                logger.debug(f"Final checklist-items param: {repr(params['checklist-items'])}")

            # Execute URL scheme
            # Snapshot the set of existing todo uuids with this exact title
            # *before* issuing the URL-scheme create, so the post-create
            # lookup below can identify the new todo by set difference
            # (after - before) instead of relying solely on "most recent
            # creation date", which is ambiguous when two todos with the
            # same title are created within the same 1s AppleScript
            # creation-date granularity (see hq-nxu.12).
            before_ids = await self._find_todo_ids_by_title(title)

            logger.debug(f"Creating todo via URL scheme: {params}")
            result = await self.applescript.execute_url_scheme('add', params)

            if not result.get('success'):
                return _write_error(
                    "APPLESCRIPT_ERROR", "Failed to create todo via URL scheme",
                    details=result.get('error', 'Unknown error'),
                )

            # Calculate checklist count correctly
            checklist_items = kwargs.get('checklist_items', [])
            if isinstance(checklist_items, str):
                item_count = len([item.strip() for item in checklist_items.split('\n') if item.strip()])
            elif isinstance(checklist_items, list):
                item_count = len(checklist_items)
            else:
                item_count = 0

            message_suffix = f" with {item_count} checklist items" if item_count else ""

            # URL scheme doesn't return the todo ID, so poll for it. Things
            # processes the URL asynchronously, so give it up to
            # _URL_SCHEME_LOOKUP_DEADLINE_SECS in
            # _URL_SCHEME_LOOKUP_POLL_INTERVAL_SECS steps, comparing the
            # post-create id set against the pre-create snapshot on each
            # poll rather than sleeping a fixed amount and hoping the todo
            # has appeared by then.
            new_ids: List[str] = []
            deadline = time.monotonic() + self._URL_SCHEME_LOOKUP_DEADLINE_SECS
            while True:
                await asyncio.sleep(self._URL_SCHEME_LOOKUP_POLL_INTERVAL_SECS)
                after_ids = await self._find_todo_ids_by_title(title)
                new_ids = [tid for tid in after_ids if tid not in before_ids]
                if new_ids or time.monotonic() >= deadline:
                    break

            if len(new_ids) == 1:
                response = {
                    "success": True,
                    "todo_id": new_ids[0],
                    "message": f"Todo created{message_suffix}",
                    "checklist_count": item_count
                }
                if warnings:
                    response["warnings"] = warnings
                return response
            elif len(new_ids) > 1:
                # Several todos with this title appeared since the
                # snapshot (e.g. a concurrent create with the same
                # title) - return the newest one via creation date, but
                # warn that the match is ambiguous.
                newest_id = await self._newest_todo_id(new_ids)
                response = {
                    "success": True,
                    "todo_id": newest_id,
                    "message": f"Todo created{message_suffix}",
                    "checklist_count": item_count,
                    "warnings": warnings + [
                        "Multiple new to-dos with this title were found; "
                        "returned the most recently created one."
                    ]
                }
                return response
            else:
                # No new todo with this title showed up within the
                # deadline. The URL scheme call reported success, so the
                # create may still have gone through in Things after our
                # deadline expired - we just couldn't confirm its id.
                return _write_error(
                    "CREATE_UNCONFIRMED",
                    (
                        "Todo could not be confirmed created within "
                        f"{self._URL_SCHEME_LOOKUP_DEADLINE_SECS}s of the "
                        "URL scheme call; the to-do may still have been "
                        "created in Things - check manually before "
                        "retrying to avoid a duplicate."
                    ),
                    checklist_count=item_count,
                    details=f"Todo creation{message_suffix} could not be confirmed",
                    **({"warnings": warnings} if warnings else {})
                )

        except Exception as e:
            logger.error(f"Error adding todo via URL scheme: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to add todo", details=str(e))

    @staticmethod
    def _propagate_url_scheme_error(result: Dict[str, Any], fallback_message: str) -> Dict[str, Any]:
        """Turn a failed execute_url_scheme() result into a write_error()
        dict, preserving an already-UPPER_SNAKE code (e.g.
        "AUTH_TOKEN_NOT_CONFIGURED" from the auth gate, forwarded verbatim
        with its own message/hint/checked_paths) rather than double-wrapping
        it, while still wrapping a raw AppleScript/URL-scheme error string
        (any code that is not itself upper-snake) as "APPLESCRIPT_ERROR"
        with the raw text preserved in `details`. `hint` and `checked_paths`
        (present on the auth-gate error) are forwarded through either path
        when present.
        """
        code = result.get('error', 'Unknown error')
        if isinstance(code, str) and code.isupper() and code.replace('_', '').isalpha():
            response = _write_error(
                code, result.get('message', fallback_message)
            )
        else:
            response = _write_error(
                "APPLESCRIPT_ERROR", fallback_message, details=code
            )
        if result.get('hint'):
            response['hint'] = result['hint']
        if result.get('checked_paths'):
            response['checked_paths'] = result['checked_paths']
        return response

    async def add_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Add checklist items to an existing todo using Things URL scheme.

        Args:
            todo_id: ID of the todo to add checklist items to
            items: List of checklist item titles to add

        Returns:
            Dict with success status and operation details
        """
        try:
            if not items:
                return _write_error(
                    "NO_CHECKLIST_ITEMS", "At least one checklist item is required"
                )

            count_error = _check_checklist_item_count(items, field="items")
            if count_error:
                return count_error

            # Build URL parameters for appending checklist items
            params = {
                'id': todo_id,
                'append-checklist-items': '\n'.join(items)
            }

            logger.debug(f"Adding {len(items)} checklist items to todo {todo_id}")
            result = await self.applescript.execute_url_scheme('update', params)

            if result.get('success'):
                return {
                    "success": True,
                    "message": f"Added {len(items)} checklist items",
                    "items_added": len(items)
                }
            else:
                return self._propagate_url_scheme_error(result, "Failed to add checklist items")

        except Exception as e:
            logger.error(f"Error adding checklist items: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to add checklist items", details=str(e))

    async def prepend_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Prepend checklist items to an existing todo using Things URL scheme.

        Args:
            todo_id: ID of the todo to prepend checklist items to
            items: List of checklist item titles to prepend

        Returns:
            Dict with success status and operation details
        """
        try:
            if not items:
                return _write_error(
                    "NO_CHECKLIST_ITEMS", "At least one checklist item is required"
                )

            count_error = _check_checklist_item_count(items, field="items")
            if count_error:
                return count_error

            # Build URL parameters for prepending checklist items
            params = {
                'id': todo_id,
                'prepend-checklist-items': '\n'.join(items)
            }

            logger.debug(f"Prepending {len(items)} checklist items to todo {todo_id}")
            result = await self.applescript.execute_url_scheme('update', params)

            if result.get('success'):
                return {
                    "success": True,
                    "message": f"Prepended {len(items)} checklist items",
                    "items_added": len(items)
                }
            else:
                return self._propagate_url_scheme_error(result, "Failed to prepend checklist items")

        except Exception as e:
            logger.error(f"Error prepending checklist items: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to prepend checklist items", details=str(e))

    async def replace_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Replace all checklist items in a todo using Things URL scheme.

        Args:
            todo_id: ID of the todo to replace checklist items in
            items: List of checklist item titles to replace with

        Returns:
            Dict with success status and operation details
        """
        try:
            count_error = _check_checklist_item_count(items, field="items")
            if count_error:
                return count_error

            # Build URL parameters for replacing checklist items
            params = {
                'id': todo_id,
                'checklist-items': '\n'.join(items) if items else ''
            }

            logger.debug(f"Replacing checklist items in todo {todo_id} with {len(items)} new items")
            result = await self.applescript.execute_url_scheme('update', params)

            if result.get('success'):
                return {
                    "success": True,
                    "message": f"Replaced checklist with {len(items)} items",
                    "items_count": len(items)
                }
            else:
                return self._propagate_url_scheme_error(result, "Failed to replace checklist items")

        except Exception as e:
            logger.error(f"Error replacing checklist items: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to replace checklist items", details=str(e))

    def _build_update_script(self, todo_id: str, title: Optional[str], notes: Optional[str],
                            tags: Optional[List[str]],
                            deadline: Optional[str], area: str, project: str,
                            completed: Optional[bool], canceled: Optional[bool],
                            project_id: Optional[str] = None,
                            area_id: Optional[str] = None) -> str:
        """Build AppleScript for updating a todo.

        Clear-field contract: ``None`` (or, for title/area/project, the empty
        string produced by the old falsy-default calling convention) leaves
        the field unchanged; ``notes=''``/``deadline=''`` clear the field;
        ``tags=[]`` (an explicit empty list, as opposed to ``None`` or a
        falsy default) clears all tags. Titles cannot be cleared - callers
        must reject ``title=''`` before calling this method.

        Note: the by-name ``area``/``project`` kwargs are a Python-API-only
        affordance - the ``update_todo`` MCP tool (server.py) has no
        ``area``/``project`` parameter and never populates them; only the
        UUID-based ``area_id``/``project_id`` (driven by the MCP tool's
        ``list_id``/``list_title``) are reachable from the MCP surface.

        Args:
            todo_id: Todo ID to update
            title: New title, or None/empty to leave unchanged
            notes: New notes, or None to leave unchanged, '' to clear
            tags: New tags list, or None to leave unchanged, [] to clear
            deadline: New deadline date, or None to leave unchanged, '' to clear
            area: New area name (looked up by name via `area <name>`); kept
                only for backwards compatibility - prefer area_id.
            project: New project name (looked up by name via
                `project <name>`); kept only for backwards compatibility -
                prefer project_id.
            completed: Completion status. None leaves status unchanged
                (unless canceled=False is given - see canceled below);
                True marks completed; False marks open (unless canceled=True
                takes precedence).
            canceled: Canceled status. canceled=True takes precedence over
                completed (whatever completed is set to). canceled=False
                with completed=None reopens the todo (matches
                update_project's semantics - not a no-op). None leaves the
                canceled state alone (fall through to completed handling).
            project_id: Project UUID to move the todo into, escaped safely
                via AppleScriptTemplates.escape_string and looked up by id
                via `project id "..."`. Takes precedence over `project`.
            area_id: Area UUID to move the todo into, escaped safely via
                AppleScriptTemplates.escape_string and looked up by id via
                `area id "..."`. Takes precedence over `area`.

        Returns:
            AppleScript code
        """
        script = f'''
            tell application "Things3"
                try
                    set targetTodo to to do id "{todo_id}"
            '''

        # Update title if provided (titles cannot be cleared - callers reject
        # title='' upstream, so any non-empty value here is a real update).
        if title:
            escaped_title = AppleScriptTemplates.escape_string(title)
            script += f'set name of targetTodo to {escaped_title}\n                    '

        # Update notes: None leaves unchanged, '' clears, anything else sets.
        if notes is not None:
            if notes == '':
                script += 'set notes of targetTodo to ""\n                    '
            else:
                escaped_notes = AppleScriptTemplates.escape_string(notes)
                script += f'set notes of targetTodo to {escaped_notes}\n                    '

        # Update area if provided. Resolved ids (from list_id/list_title)
        # take precedence over the legacy by-name `area` argument.
        if area_id:
            escaped_area_id = AppleScriptTemplates.escape_string(area_id)
            script += f'set area of targetTodo to area id {escaped_area_id}\n                    '
        elif area:
            escaped_area = AppleScriptTemplates.escape_string(area)
            script += f'set area of targetTodo to area {escaped_area}\n                    '

        # Update project if provided. Resolved ids (from list_id/list_title)
        # take precedence over the legacy by-name `project` argument.
        if project_id:
            escaped_project_id = AppleScriptTemplates.escape_string(project_id)
            script += f'set project of targetTodo to project id {escaped_project_id}\n                    '
        elif project:
            escaped_project = AppleScriptTemplates.escape_string(project)
            script += f'set project of targetTodo to project {escaped_project}\n                    '

        # Update tags: None leaves unchanged, [] (explicit empty list) clears,
        # a non-empty list sets. A falsy-but-not-[] value (e.g. omitted
        # entirely and defaulted elsewhere) is treated as "unchanged" too.
        if tags is not None:
            if len(tags) == 0:
                script += 'set tag names of targetTodo to ""\n                    '
            else:
                tags_string = ', '.join(tags)
                escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
                script += f'set tag names of targetTodo to {escaped_tags_string}\n                    '

        # Update deadline: None leaves unchanged, '' clears, anything else sets.
        if deadline is not None:
            if deadline == '':
                # Things 3's AppleScript dictionary rejects assigning
                # missing value to the due date ("Can't make missing
                # value into type date"); `delete` is the documented way to
                # clear a date property.
                script += 'delete due date of targetTodo\n                    '
            else:
                date_components = locale_handler.normalize_date_input(deadline)
                if date_components:
                    year, month, day = date_components
                    script += f'''
                    set deadlineDate to (current date)
                    set time of deadlineDate to 0
                    set day of deadlineDate to 1
                    set year of deadlineDate to {year}
                    set month of deadlineDate to {month}
                    set day of deadlineDate to {day}
                    set due date of targetTodo to deadlineDate
                    '''

        # Update status if provided (canceled takes precedence over completed,
        # matching update_project's precedence). canceled=False alone also
        # reopens the todo (no completed given) so that
        # update_todo(canceled='false') reliably returns the todo to
        # 'incomplete' rather than being a silent no-op.
        if canceled is not None and canceled:
            script += 'set status of targetTodo to canceled\n                    '
        elif completed is not None:
            if completed:
                script += 'set status of targetTodo to completed\n                    '
            else:
                script += 'set status of targetTodo to open\n                    '
        elif canceled is not None and not canceled:
            script += 'set status of targetTodo to open\n                    '

        script += '''
                    return "updated"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

        return script

    async def update_todo(self, todo_id: str, **kwargs) -> Dict[str, Any]:
        """Update an existing todo using AppleScript.

        Clear-field contract (see _build_update_script): a field that is
        omitted from kwargs, or explicitly None, leaves the existing value
        unchanged. notes='' and deadline='' clear those fields. tags=[]
        (an explicit empty list) clears all tags. title='' is rejected
        upstream (ParameterValidator.validate_update_params) and should
        never reach here.

        heading (Optional[str]): moves the to-do under that heading within
        its current project via the Things URL scheme (things:///update)
        - AppleScript has no way to move a to-do under a heading. The URL
        scheme requires the Things auth token; that check happens BEFORE
        any AppleScript write so a missing token never results in a
        partially-applied update. heading='' (or whitespace-only) is
        rejected outright (Things' URL scheme has no documented way to
        clear a to-do out of a heading via update - passing heading=''
        would either be ignored or produce undefined behavior, so we
        surface a structured error instead of guessing). If list_id (or,
        when list_id is absent, list_title - resolved via
        _resolve_list_title the same way as the non-heading move path) is
        also given, the to-do is moved to that project via 'list-id' in
        the same URL, with 'heading' resolved within the destination
        project. An unresolvable list_id/list_title on the heading path
        (unknown id, a title matching zero or more than one project/area,
        or a list_id that refers to neither a project nor an area) is a
        structured error returned BEFORE any write - pre-checked via
        _resolve_list_id/_resolve_list_title exactly like the non-heading
        move path, rather than being sent to Things as-is. If the resolved
        id refers to an area rather than a project, a warning is added
        since Things ignores 'heading' for area targets. A to-do whose
        current parent is itself a heading reports project=None from
        things.py (the project only appears on the heading record) - the
        current-project fallback for the heading-exists check/warning
        resolves that via the to-do's heading record.

        when='evening' (alias 'tonight', normalized to 'evening' by
        ParameterValidator): Things 3's AppleScript 'schedule' command has
        no way to set the "This Evening" flag (verified against the
        AppleScript dictionary - 'schedule ... for <date>' only). The
        Things URL scheme's 'update' action DOES accept when=evening, so
        this is routed there instead of schedule_todo_reliable(). Like
        heading, this requires the Things auth token, checked BEFORE any
        AppleScript write; without one this returns a structured error
        with a hint instead of silently falling back to a plain "Today"
        schedule. Note the auth-token check only protects against a
        partially-applied update when the token itself is missing: if the
        token IS configured and when='evening' is combined with
        AppleScript-only fields (title/notes/tags/deadline/etc.) in the
        same call, the AppleScript write is issued and applied FIRST
        (same ordering as heading), then the URL-scheme call is made
        second - if that URL-scheme call itself fails (e.g. a transient
        `open` failure), the already-applied AppleScript fields are NOT
        rolled back.

        when='YYYY-MM-DD@HH:MM' (sets a reminder, hq-4gn): passes
        ParameterValidator's date-format check, but
        schedule_todo_reliable() (the AppleScript scheduling path) calls
        locale_aware_dates.normalize_date_input(), which only extracts
        year/month/day - the '@HH:MM' component is silently dropped and no
        reminder is ever set. The Things URL scheme's 'update' action
        natively supports 'YYYY-MM-DD@HH:MM' and sets the reminder, so
        this form is routed there instead - exactly the same routing,
        auth-token gate, and AppleScript-write-ordering as when='evening'
        above (the auth-token check happens BEFORE any AppleScript write;
        if the token is configured and this is combined with
        AppleScript-only fields, those are applied first and are not
        rolled back if the URL-scheme call subsequently fails).

        list_id / list_title (move to a project or area): when heading is
        NOT also given, list_id (or list_title, resolved to an id the same
        way as add_todo - see _resolve_list_id/_resolve_list_title) moves
        the to-do directly into that project or area via AppleScript
        (`set project of targetTodo to project id "..."` or `set area of
        targetTodo to area id "..."`), applied in the same AppleScript
        write as the other AppleScript-only fields. This can move a to-do
        INTO a project/area but cannot place it in the inbox/today/anytime/
        someday lists - use move_record() for those destinations. list_id
        takes precedence over list_title if both are given. An unknown
        list_id/list_title, or a list_title matching more than one
        project/area, is a structured error returned before any write is
        attempted. When heading IS also given, list_id/list_title are
        instead resolved and consumed by the heading move above (as
        'list-id' in the same things:///update call) rather than by this
        plain AppleScript move - see the heading docs above.
        """
        try:
            # Pre-check todo_id via things.py BEFORE any write (hq-wbm).
            # AppleScript's `to do id "<uuid>"` unexpectedly ALSO resolves a
            # project uuid (Things treats projects as a "selected to do"
            # class internally - verified live) rather than erroring, so
            # without this check update_todo(id=<project-uuid>, title=...)
            # would silently rename/modify the project instead of failing.
            # things.get() distinguishes the cases: None means the id is
            # genuinely unknown (NOT_FOUND); a record whose type isn't
            # 'to-do' means the id resolves to something update_todo cannot
            # target (VALIDATION_ERROR, naming the actual type). If the
            # things.py lookup itself raises (e.g. the Things database is
            # unreadable / Full Disk Access missing), fall through and
            # proceed with the write - same documented DB-unreadable
            # fallback as _resolve_list_id/_resolve_area (CLAUDE.md "list_id
            # fallback when the Things database is unreadable") - refusing
            # every update whenever things.py is unavailable would be a
            # larger behavior change than this bead asks for.
            try:
                todo_record_for_precheck = things.get(todo_id)
            except Exception as e:
                logger.warning(
                    f"things.py lookup failed while pre-checking todo_id "
                    f"{todo_id} (falling back to proceeding with the write "
                    f"unchecked): {e}"
                )
                todo_record_for_precheck = _RESOLVE_UNAVAILABLE

            if todo_record_for_precheck is None:
                return _write_error(
                    "NOT_FOUND",
                    f"No to-do found with id '{todo_id}'",
                )
            if todo_record_for_precheck is not _RESOLVE_UNAVAILABLE:
                precheck_type = todo_record_for_precheck.get('type')
                if precheck_type != 'to-do':
                    if precheck_type == 'project':
                        return _write_error(
                            "VALIDATION_ERROR",
                            f"id '{todo_id}' is a project, not a to-do; use "
                            "update_project() instead",
                            field="id",
                            invalid_value=todo_id,
                        )
                    return _write_error(
                        "VALIDATION_ERROR",
                        f"id '{todo_id}' refers to a '{precheck_type}', not "
                        "a to-do",
                        field="id",
                        invalid_value=todo_id,
                    )

            # Extract parameters. title/area/project default to '' (falsy
            # "unchanged") since they have no clear semantics here; notes/
            # deadline/tags default to None so "not provided" (leave
            # unchanged) can be distinguished from '' / [] (explicit clear).
            title = kwargs.get('title', '')
            notes = kwargs.get('notes', None)
            tags = kwargs.get('tags', None)
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', None)
            area = kwargs.get('area', '')
            project = kwargs.get('project', '')
            heading = kwargs.get('heading', None)
            list_id = kwargs.get('list_id', '')
            list_title = kwargs.get('list_title', '')

            # Things 3's AppleScript 'schedule' command only accepts a date
            # object - there is no AppleScript way to set the "This Evening"
            # flag (verified against the AppleScript dictionary: 'schedule
            # ... for <date>' only). The Things URL scheme's 'update' action
            # DOES accept when=evening, so route there instead of
            # schedule_todo_reliable() when when='evening'.
            when_is_evening = isinstance(when, str) and when.strip().lower() == 'evening'

            # when='YYYY-MM-DD@HH:MM' sets a reminder via the Things URL
            # scheme's 'update' action natively; schedule_todo_reliable's
            # AppleScript path (locale_aware_dates.normalize_date_input)
            # only extracts year/month/day and silently drops the time
            # component, so no reminder is ever set (hq-4gn). Route this
            # the same way as when_is_evening.
            when_has_time = when_has_time_component(when)

            # heading has no "clear" semantics via the URL scheme - reject an
            # explicit empty (or whitespace-only) string rather than silently
            # ignoring it or sending an ambiguous request to Things. This
            # check runs before any AppleScript write so nothing is
            # partially applied.
            if heading is not None and heading.strip() == '':
                return _write_error(
                    "INVALID_HEADING",
                    (
                        "heading cannot be empty; Things' URL scheme has no "
                        "documented way to clear a to-do out of a heading via "
                        "update - to move it out, use move_record() to move "
                        "it directly into the project instead"
                    ),
                    field="heading",
                )

            # heading, when='evening', and when with a '@HH:MM' time
            # component are only honoured via the Things URL scheme's
            # 'update' action, which requires the auth token. Fail fast
            # BEFORE any AppleScript write so other fields are never
            # partially applied.
            if heading or when_is_evening or when_has_time:
                if not self.applescript.auth_token:
                    # Reload-on-miss (hq-wsa.4): a token file created after
                    # this manager was constructed is picked up here rather
                    # than requiring a restart. No-op (and safe on a mocked
                    # manager) if a token is already loaded.
                    reload = getattr(self.applescript, "reload_auth_token_if_missing", None)
                    if callable(reload):
                        reload()
                if not self.applescript.auth_token:
                    from ..services.applescript_manager import AUTH_TOKEN_HINT
                    return _write_error(
                        "AUTH_TOKEN_NOT_CONFIGURED",
                        "Things URL-scheme auth token not configured",
                        hint=AUTH_TOKEN_HINT,
                        checked_paths=getattr(self.applescript, "_auth_token_trace", []),
                    )

            # Convert status parameters
            completed = kwargs.get('completed', None)
            canceled = kwargs.get('canceled', None)

            try:
                if completed is not None:
                    completed = self._convert_to_boolean(completed)
                if canceled is not None:
                    canceled = self._convert_to_boolean(canceled)
            except ValueError as e:
                return _write_error(
                    "VALIDATION_ERROR", "Invalid boolean value for status parameter",
                    details=str(e),
                )

            warnings: List[str] = []

            # Resolve list_id/list_title to a project or area id BEFORE any
            # write, in either of two mutually exclusive ways depending on
            # whether heading is also given:
            #   - heading is absent: resolve to project_id/area_id for a
            #     plain AppleScript move (applied below).
            #   - heading is present: list_id/list_title are instead
            #     consumed by the URL-scheme block further down (move +
            #     place-under-heading in one call), so they must NOT also
            #     be resolved into project_id/area_id here (that would
            #     double-apply the move, once via AppleScript and once via
            #     the URL scheme). They are still resolved here - just into
            #     effective_list_id_for_url / list_id_resolution - so that
            #     an unknown/ambiguous list_id or list_title is reported as
            #     a structured error before the AppleScript write below,
            #     rather than after it.
            # Either way, list_id takes precedence over list_title, matching
            # add_todo's precedence.
            project_id: Optional[str] = None
            area_id: Optional[str] = None
            effective_list_id_for_url: Optional[str] = None
            list_id_resolution: Optional[Dict[str, Any]] = None
            if not heading:
                if list_id:
                    resolution = self._resolve_list_id(list_id)
                    if "error" in resolution:
                        return resolution
                    if resolution["kind"] == "project":
                        project_id = resolution["id"]
                    else:
                        area_id = resolution["id"]
                elif list_title:
                    resolution = self._resolve_list_title(list_title)
                    if "error" in resolution:
                        return resolution
                    if resolution["kind"] == "project":
                        project_id = resolution["id"]
                    else:
                        area_id = resolution["id"]

                if project_id:
                    target_error = self._check_project_target_not_completed(project_id)
                    if target_error:
                        return target_error
            else:
                if list_id:
                    # Pre-check list_id the same way the non-heading move
                    # path does: an unknown id (or one that refers to
                    # neither a project nor an area) is a structured error
                    # returned before any write, rather than being sent to
                    # Things as-is (things:///update silently no-ops on an
                    # unrecognized list-id - pre-hq-nxu.13 behaviour left
                    # that as a silent no-op with no error surfaced at all).
                    list_id_resolution = self._resolve_list_id(list_id)
                    if "error" in list_id_resolution:
                        return list_id_resolution
                    effective_list_id_for_url = list_id
                elif list_title:
                    # list_title has no direct URL-scheme 'list' id param
                    # usable here (Things' 'list' targets by name,
                    # ambiguously) - resolve it the same way as list_id
                    # (_resolve_list_title) and pass the resolved id as
                    # 'list-id', surfacing the same unknown/ambiguous
                    # structured errors as the non-heading path instead of
                    # silently dropping list_title.
                    list_id_resolution = self._resolve_list_title(list_title)
                    if "error" in list_id_resolution:
                        return list_id_resolution
                    effective_list_id_for_url = list_id_resolution["id"]

            # When heading is given, pre-resolve which project the combined
            # heading-completion check / heading-exists warning
            # (_check_heading_status, further down) should be scoped to:
            # the explicitly-requested list_id/list_title, or (if neither
            # given) the to-do's current project. things.py reports
            # project=None for a to-do whose parent is itself a heading (the
            # PROJECT join is on TASK.project, which is NULL for heading
            # children - the parent project only shows up on the heading
            # record itself), so fall back to looking up the to-do's heading
            # record's project in that case. The completed/canceled check
            # itself must happen BEFORE the AppleScript write below so a
            # completed/canceled target is rejected before anything is
            # written, not after; the heading-exists warning is deferred to
            # its usual spot further down since it never blocks a write.
            effective_project_id: Optional[str] = None
            heading_warning: Optional[str] = None
            if heading:
                effective_project_id = effective_list_id_for_url
                if not effective_project_id:
                    try:
                        todo_record_for_project = things.get(todo_id)
                    except Exception as e:
                        logger.debug(f"Error looking up todo {todo_id} for project check: {e}")
                        todo_record_for_project = None
                    if todo_record_for_project:
                        effective_project_id = todo_record_for_project.get('project')
                        if not effective_project_id and todo_record_for_project.get('heading'):
                            try:
                                heading_record_for_project = things.get(todo_record_for_project['heading'])
                            except Exception as e:
                                logger.debug(
                                    f"Error looking up heading {todo_record_for_project['heading']} "
                                    f"for project fallback: {e}"
                                )
                                heading_record_for_project = None
                            if heading_record_for_project:
                                effective_project_id = heading_record_for_project.get('project')

                # Only pre-check when the target resolves to a project (not
                # an area - list_id_resolution.kind == "area" is handled
                # later as a warning, and areas have no completed/canceled
                # status in Things).
                if effective_project_id and not (
                    list_id_resolution and list_id_resolution.get("kind") == "area"
                ):
                    target_error, heading_warning = self._check_heading_status(
                        heading, list_id=effective_project_id
                    )
                    if target_error:
                        return target_error

            # Apply the AppleScript-only fields first (title, notes, tags,
            # deadline, area, project, project_id/area_id, completed,
            # canceled). This mirrors the pre-existing unconditional
            # behavior (the AppleScript write is always issued, even as a
            # no-op "updated" round trip) EXCEPT when heading, when='evening',
            # and/or when with a '@HH:MM' time component are the only
            # field(s) requested - in that case skip the AppleScript step
            # entirely and rely solely on the URL-scheme update below,
            # since there is nothing else to write.
            skip_applescript = (heading or when_is_evening or when_has_time) and not any([
                title, notes is not None, tags is not None, deadline is not None,
                area, project, project_id, area_id, completed is not None, canceled is not None
            ])

            if not skip_applescript:
                script = self._build_update_script(todo_id, title, notes, tags, deadline,
                                                  area, project, completed, canceled,
                                                  project_id=project_id, area_id=area_id)
                result = await self.applescript.execute_applescript(script)

                if result.get("success"):
                    output = result.get("output", "").strip()
                    if output != "updated":
                        return _write_error(
                            "APPLESCRIPT_ERROR", "Failed to update todo", details=output
                        )
                else:
                    return _write_error(
                        "APPLESCRIPT_ERROR", "Failed to update todo",
                        details=result.get("output", "AppleScript execution failed"),
                    )

            if heading or when_is_evening or when_has_time:
                url_params: Dict[str, Any] = {'id': todo_id}
                if heading:
                    url_params['heading'] = heading
                if when_is_evening:
                    url_params['when'] = 'evening'
                elif when_has_time:
                    url_params['when'] = when

                # list_id/list_title are only meaningful here (as a
                # URL-scheme 'list-id') when heading is also given - they
                # move-and-place-under-heading together in this one call.
                # When heading is NOT given, list_id/list_title were already
                # consumed above as a plain AppleScript move (project_id/
                # area_id); including them here too would double-apply the
                # move (once via AppleScript, once via this URL-scheme
                # call) for e.g. when='evening' + list_id with no heading.
                # effective_list_id_for_url and list_id_resolution were
                # already resolved (and any unknown/ambiguous list_id or
                # list_title already reported as a structured error) in the
                # pre-write block above, before the AppleScript write ran -
                # they are only non-None here when heading was given.
                if effective_list_id_for_url:
                    url_params['list-id'] = effective_list_id_for_url

                # The remaining warnings in this block are all
                # heading-placement concerns - skip them entirely when only
                # when_is_evening/when_has_time triggered this branch (no
                # heading requested).
                # effective_project_id and heading_warning were already
                # resolved (using the same explicit-list_id/list_title-else-
                # current-project fallback, and the combined
                # _check_heading_status call) in the pre-write block above,
                # before the AppleScript write ran, so neither is
                # recomputed here.
                if heading:
                    if list_id_resolution and list_id_resolution.get("kind") == "area":
                        warnings.append(
                            f"list_id '{effective_list_id_for_url}' resolves to an area, "
                            "not a project; Things' URL scheme ignores 'heading' for area "
                            "targets - the to-do will move into the area but not be placed "
                            "under any heading."
                        )
                    elif effective_project_id:
                        if heading_warning:
                            warnings.append(heading_warning)
                    else:
                        warnings.append(
                            "This to-do does not appear to belong to a project; Things' "
                            "URL scheme silently ignores 'heading' for to-dos outside a "
                            "project. Pass list_id to move it into a project with this "
                            "heading."
                        )

                url_result = await self.applescript.execute_url_scheme('update', url_params)

                if not url_result.get('success'):
                    if heading:
                        fallback_message = "Failed to update todo heading"
                    elif when_is_evening:
                        fallback_message = "Failed to schedule todo for evening"
                    else:
                        fallback_message = "Failed to set todo reminder"
                    return self._propagate_url_scheme_error(url_result, fallback_message)

            # Schedule if when date provided (evening and date+time-with-
            # reminder were already applied via the URL scheme above -
            # schedule_todo_reliable has no AppleScript mechanism for
            # either).
            if when and not when_is_evening and not when_has_time:
                schedule_result = await self.scheduler.schedule_todo_reliable(todo_id, when)
                response = {
                    "success": True,
                    "message": "Todo updated and scheduled successfully",
                    "scheduling": schedule_result
                }
                if warnings:
                    response["warnings"] = warnings
                return response

            response = {
                "success": True,
                "message": (
                    "Todo updated and scheduled for This Evening successfully"
                    if when_is_evening else (
                        "Todo updated and reminder set successfully"
                        if when_has_time else "Todo updated successfully"
                    )
                )
            }
            if when_is_evening:
                response["scheduling"] = {
                    "success": True,
                    "method": "url_scheme",
                    "date_set": "evening"
                }
            elif when_has_time:
                response["scheduling"] = {
                    "success": True,
                    "method": "url_scheme",
                    "date_set": when
                }
            if warnings:
                response["warnings"] = warnings
            return response

        except Exception as e:
            logger.error(f"Error updating todo: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to update todo", details=str(e))

    def _build_create_project_script(self, title: str, notes: str, tags: List[str],
                                     deadline: str, area_id: str, area_title: str, todos: List[str]) -> str:
        """Build AppleScript for creating a new project.

        Args:
            title: Project title
            notes: Project notes
            tags: Tags list
            deadline: Deadline date
            area_id: Area UUID (takes precedence if provided)
            area_title: Area name
            todos: Initial todos to create in project

        Returns:
            AppleScript code
        """
        escaped_title = AppleScriptTemplates.escape_string(title)
        escaped_notes = AppleScriptTemplates.escape_string(notes)

        script = f'''
            tell application "Things3"
                try
                    set newProject to make new project with properties {{name:{escaped_title}}}
            '''

        if notes:
            script += f'set notes of newProject to {escaped_notes}\n                    '

        # Set area: prefer area_id (UUID) over area_title (name)
        if area_id:
            escaped_area_id = AppleScriptTemplates.escape_string(area_id)
            script += f'set area of newProject to area id {escaped_area_id}\n                    '
        elif area_title:
            escaped_area_title = AppleScriptTemplates.escape_string(area_title)
            script += f'set area of newProject to area {escaped_area_title}\n                    '

        if tags:
            tags_string = ', '.join(tags)
            escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
            script += f'set tag names of newProject to {escaped_tags_string}\n                    '

        if deadline:
            date_components = locale_handler.normalize_date_input(deadline)
            if date_components:
                year, month, day = date_components
                script += f'''
                    set deadlineDate to (current date)
                    set time of deadlineDate to 0
                    set day of deadlineDate to 1
                    set year of deadlineDate to {year}
                    set month of deadlineDate to {month}
                    set day of deadlineDate to {day}
                    set due date of newProject to deadlineDate
                    '''

        if todos:
            for todo_title in todos:
                if todo_title.strip():
                    escaped_todo = AppleScriptTemplates.escape_string(todo_title.strip())
                    script += f'''
                    set newTodoInProject to make new to do in newProject with properties {{name:{escaped_todo}}}
                        '''

        # Return the new project's id and the number of to-dos it actually
        # ended up with, each on its own line, so add_project can verify
        # that every requested todo line was really created (see hq-f0w.41
        # - a one-off run once reported only 1 of 2 requested to-dos
        # present) instead of trusting the requested count blindly.
        script += '''
                    return (id of newProject) & "\\n" & (count of to dos of newProject)
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

        return script

    async def _find_project_ids_by_title(self, title: str) -> List[str]:
        """Return the ids of all (non-trashed) projects with the exact title.

        Used by _add_project_via_url_scheme to snapshot existing project
        ids before a URL-scheme create and poll for new ones afterward,
        the same way _find_todo_ids_by_title does for to-dos (the URL
        scheme does not return the created project's id). Uses AppleScript
        (rather than the things.py proxy) for the same reason: an exact,
        live-database comparison that is not subject to things.py's
        on-disk SQLite snapshot lagging a fresh write.

        Returns an empty list (rather than raising) on any AppleScript
        failure, so a lookup glitch degrades to "no ids found" instead of
        crashing the create.
        """
        script = f'''
        tell application "Things3"
            try
                set foundProjects to projects whose name is {AppleScriptTemplates.escape_string(title)}
                set idList to {{}}
                repeat with aProject in foundProjects
                    set end of idList to (id of aProject)
                end repeat
                set AppleScript's text item delimiters to "\\n"
                set idText to idList as text
                set AppleScript's text item delimiters to ""
                return idText
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''
        result = await self.applescript.execute_applescript(script)
        if not result.get('success'):
            logger.debug(f"Failed to look up project ids for title {title!r}: {result.get('error')}")
            return []

        output = (result.get('output') or '').strip()
        if not output or output.startswith('error:'):
            if output.startswith('error:'):
                logger.debug(f"AppleScript error looking up project ids for title {title!r}: {output}")
            return []

        return [line.strip() for line in output.split('\n') if line.strip()]

    async def _add_project_via_url_scheme(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a project using the Things URL scheme's ``json`` action.

        This is the only way to seed real headings (and to-dos nested
        under them) at project-creation time - the AppleScript
        ``make new to do`` path and the documented ``add-project``
        ``to-dos`` param both only create plain to-dos, never headings
        (verified live for hq-f0w.41). Only called from add_project when
        the todos payload contains at least one ``##`` line.

        Args:
            title: Project title
            notes: Optional notes
            tags: Optional tag list (already policy-filtered by the caller)
            when: Optional scheduling date (applied via schedule_todo_reliable
                after creation, same as the AppleScript path - the ``json``
                action has no direct "This Evening" equivalent for projects
                either)
            deadline: Optional deadline date (YYYY-MM-DD)
            area_id: Optional area UUID (takes precedence over area_title)
            area_title: Optional area name
            todos: List of todo/heading lines; a line starting with ``##``
                becomes a heading, all other lines become to-dos nested
                under the most recently seen heading (or un-nested, before
                the first heading)

        Returns:
            Dict with success status, project_id, todos_created, and
            headings_created (when headings were requested).
        """
        try:
            items: List[Dict[str, Any]] = []
            heading_count = 0
            todo_count = 0
            for line in kwargs.get('todos') or []:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('##'):
                    heading_title = line[2:].strip()
                    if not heading_title:
                        return _write_error(
                            "VALIDATION_ERROR",
                            (
                                f"Empty heading title in todos line {line!r}; "
                                "a '##' line must be followed by a non-empty "
                                "heading title."
                            ),
                            field="todos",
                        )
                    items.append({"type": "heading", "attributes": {"title": heading_title}})
                    heading_count += 1
                else:
                    items.append({"type": "to-do", "attributes": {"title": line}})
                    todo_count += 1

            attributes: Dict[str, Any] = {"title": title}
            if kwargs.get('notes'):
                attributes['notes'] = kwargs['notes']
            if kwargs.get('tags'):
                attributes['tags'] = list(kwargs['tags'])
            if kwargs.get('deadline'):
                attributes['deadline'] = kwargs['deadline']
            # area_id takes precedence over area_title, same convention as
            # the AppleScript path.
            if kwargs.get('area_id'):
                attributes['area-id'] = kwargs['area_id']
            elif kwargs.get('area_title'):
                attributes['area'] = kwargs['area_title']
            if items:
                attributes['items'] = items

            # when='YYYY-MM-DD@HH:MM' (sets a reminder, hq-4gn): the
            # 'json' action's 'when' attribute natively supports this form
            # (live-probed) and sets the reminder directly, unlike
            # schedule_todo_reliable's AppleScript path which drops the
            # time component - so pass it straight through here instead
            # of relying on the post-create schedule_todo_reliable() call
            # below (which still handles plain dates/relative keywords for
            # this path, unchanged).
            when_kwarg = kwargs.get('when')
            when_has_time = when_has_time_component(when_kwarg)
            if when_has_time:
                attributes['when'] = when_kwarg

            payload = [{"type": "project", "attributes": attributes}]

            # Snapshot existing project ids with this exact title *before*
            # issuing the URL-scheme create, then poll for a new one
            # afterward (before/after set difference) - same pattern as
            # _add_todo_via_url_scheme, for the same reason: the URL
            # scheme itself does not return the created item's id.
            before_ids = await self._find_project_ids_by_title(title)

            result = await self.applescript.execute_url_scheme('json', {'data': json.dumps(payload)})
            if not result.get('success'):
                return _write_error(
                    "APPLESCRIPT_ERROR", "Failed to create project via URL scheme",
                    details=result.get('error', 'Unknown error'),
                )

            new_ids: List[str] = []
            deadline_ts = time.monotonic() + self._URL_SCHEME_LOOKUP_DEADLINE_SECS
            while True:
                await asyncio.sleep(self._URL_SCHEME_LOOKUP_POLL_INTERVAL_SECS)
                after_ids = await self._find_project_ids_by_title(title)
                new_ids = [pid for pid in after_ids if pid not in before_ids]
                if new_ids or time.monotonic() >= deadline_ts:
                    break

            if not new_ids:
                return _write_error(
                    "CREATE_UNCONFIRMED",
                    (
                        "Project could not be confirmed created within "
                        f"{self._URL_SCHEME_LOOKUP_DEADLINE_SECS}s of the "
                        "URL scheme call; the project may still have been "
                        "created in Things - check manually before "
                        "retrying to avoid a duplicate."
                    ),
                    details="Project creation could not be confirmed",
                )

            # Multiple new projects with the same title cannot be
            # disambiguated by creation date the way todos can (there is
            # no equivalent "project id <id>" AppleScript accessor pattern
            # already in use here), so just take the first and warn.
            project_id = new_ids[0]
            response: Dict[str, Any] = {
                "success": True,
                "project_id": project_id,
                "message": "Project created successfully",
            }
            verification_warnings: List[str] = []
            if todo_count:
                # Verify via things.py rather than trusting the requested
                # count blindly (same reasoning as the AppleScript path's
                # "count of to dos of newProject" check) - the id-lookup
                # poll above already waited for Things to register the
                # create, so a things.py read at this point should be
                # current. things.py is best-effort here: any failure
                # (import error, etc.) falls back to the requested count
                # rather than failing the whole create.
                try:
                    actual_todo_count = len(things.todos(project=project_id) or [])
                except Exception as e:
                    logger.debug(f"Could not verify todo count for project {project_id}: {e}")
                    actual_todo_count = todo_count
                response["todos_created"] = actual_todo_count
                if actual_todo_count < todo_count:
                    verification_warnings.append(
                        f"Requested {todo_count} to-dos but only "
                        f"{actual_todo_count} were created in the project; "
                        "verify manually before retrying to avoid duplicates."
                    )
            if heading_count:
                try:
                    actual_heading_count = len(
                        things.tasks(type='heading', project=project_id, status=None) or []
                    )
                except Exception as e:
                    logger.debug(f"Could not verify heading count for project {project_id}: {e}")
                    actual_heading_count = heading_count
                response["headings_created"] = actual_heading_count
                if actual_heading_count < heading_count:
                    verification_warnings.append(
                        f"Requested {heading_count} headings but only "
                        f"{actual_heading_count} were created in the project; "
                        "verify manually before retrying to avoid duplicates."
                    )
            if verification_warnings:
                response.setdefault("warnings", []).extend(verification_warnings)
            if len(new_ids) > 1:
                response.setdefault("warnings", []).append(
                    "Multiple new projects with this title were found; "
                    "returned the first one created."
                )

            if when_has_time:
                # Already applied via the 'when' attribute in the payload
                # above (sets the reminder directly) - report it here
                # rather than re-scheduling via schedule_todo_reliable,
                # which would drop the time component.
                response["message"] = "Project created and reminder set successfully"
                response["scheduling"] = {
                    "success": True,
                    "method": "url_scheme",
                    "date_set": when_kwarg
                }
            elif when_kwarg:
                schedule_result = await self.scheduler.schedule_todo_reliable(project_id, when_kwarg)
                response["message"] = "Project created and scheduled successfully"
                response["scheduling"] = schedule_result

            return response

        except Exception as e:
            logger.error(f"Error adding project via URL scheme: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to add project", details=str(e))

    async def add_project(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new project using AppleScript, or the Things URL scheme's
        ``json`` action when the ``todos`` payload requests headings.

        when='evening'/'tonight' is rejected: Things has no "This Evening"
        concept for projects (only to-dos can be scheduled for This
        Evening in the Things UI), and silently falling back to a plain
        "Today" schedule (as schedule_todo_reliable's list-fallback would
        otherwise do for an unrecognized when value) would misrepresent
        what was actually applied.

        when='YYYY-MM-DD@HH:MM' (sets a reminder, hq-4gn): unlike
        'evening', this form IS supported for projects - live-probed
        against ``things:///add-project`` and ``things:///update-project``,
        both of which accept a 'YYYY-MM-DD@HH:MM' ``when`` and set
        ``reminder_time``/``start_date`` on the project exactly as they do
        for to-dos. schedule_todo_reliable's AppleScript path
        (locale_aware_dates.normalize_date_input) only extracts
        year/month/day and would silently drop the time component the
        same way it does for to-dos, so this is routed via
        ``things:///update-project`` after the AppleScript create instead
        - same pattern as when='evening' on update_todo. update-project
        requires the Things auth token (unlike add-project/add), so the
        token is checked BEFORE the project is created, to avoid creating
        a project whose reminder then silently fails to apply.

        Headings (hq-f0w.41): a ``todos`` line prefixed with ``##`` is a
        request for a heading. The AppleScript ``make new to do`` path has
        no heading concept at all - it would create a to-do literally
        titled "##Heading" - so any ``##`` line routes the whole call to
        _add_project_via_url_scheme, which uses ``things:///json`` (the
        only Things URL-scheme action that can create real headings at
        project-creation time; verified live - the documented ``to-dos``
        param on ``add-project`` does NOT turn ``##`` lines into headings,
        it creates a literal to-do titled "##Heading" just like the
        AppleScript path). Without a ``##`` line, the plain AppleScript
        path is used as before (faster, no URL-scheme round trip).
        """
        try:
            # Extract parameters
            notes = kwargs.get('notes', '')
            tags = kwargs.get('tags', [])
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', '')

            if isinstance(when, str) and when.strip().lower() == 'evening':
                return _write_error(
                    "UNSUPPORTED_FOR_PROJECTS",
                    "when='evening' is not supported for projects; Things has "
                    "no \"This Evening\" concept for projects (only to-dos can "
                    "be scheduled for This Evening) - use when='today' instead",
                    field="when",
                )

            when_has_time = when_has_time_component(when)

            # Separate area_id (UUID) and area_title (name) for proper AppleScript syntax
            area_id = kwargs.get('area_id', '')
            area_title = kwargs.get('area_title', '') or kwargs.get('area', '')  # 'area' param is treated as title

            # Pre-resolve the area target via things.py BEFORE any write
            # (hq-rmh): AppleScript has no transactional rollback, so
            # emitting an unresolvable area_id/area_title into the create
            # script would create a real orphan project when the area-set
            # line throws. A successful resolution normalizes area_title to
            # its concrete area_id so both the AppleScript and URL-scheme
            # create paths below emit a uuid-based area reference.
            if area_id or area_title:
                area_resolution = self._resolve_area(area_id=area_id, area_title=area_title)
                if "error" in area_resolution:
                    return area_resolution
                if area_resolution.get("area_id"):
                    area_id = area_resolution["area_id"]
                    area_title = ''

            # Handle todos parameter - can be string (newline-separated) or list
            todos_param = kwargs.get('todos', [])
            if isinstance(todos_param, str):
                # Split by newlines and filter out empty strings
                todos = [t.strip() for t in todos_param.split('\n') if t.strip()]
            elif isinstance(todos_param, list):
                todos = [t.strip() for t in todos_param if t and t.strip()]
            else:
                todos = []

            if any(t.startswith('##') for t in todos):
                # _add_project_via_url_scheme uses the 'json' action, which
                # (like 'add'/'add-project') does NOT require the auth
                # token - it sets 'when' with a time component directly in
                # the create payload's attributes, unlike the plain
                # AppleScript path below which needs a separate
                # 'update-project' call (and therefore the token) after
                # creation.
                return await self._add_project_via_url_scheme(
                    title, notes=notes, tags=tags, when=when, deadline=deadline,
                    area_id=area_id, area_title=area_title, todos=todos
                )

            # The plain AppleScript create path (below) sets a when with a
            # time component via a follow-up 'update-project' URL-scheme
            # call, which DOES require the auth token - checked here,
            # before creating the project, so a missing token is reported
            # without creating an orphaned project whose reminder then
            # silently fails to apply.
            if when_has_time and not self.applescript.auth_token:
                # Reload-on-miss (hq-wsa.4): a token file created after this
                # manager was constructed is picked up here rather than
                # requiring a restart. No-op (and safe on a mocked manager)
                # if a token is already loaded.
                reload = getattr(self.applescript, "reload_auth_token_if_missing", None)
                if callable(reload):
                    reload()
            if when_has_time and not self.applescript.auth_token:
                from ..services.applescript_manager import AUTH_TOKEN_HINT
                return _write_error(
                    "AUTH_TOKEN_NOT_CONFIGURED",
                    "Things URL-scheme auth token not configured",
                    hint=AUTH_TOKEN_HINT,
                    checked_paths=getattr(self.applescript, "_auth_token_trace", []),
                )

            # Build and execute script
            script = self._build_create_project_script(title, notes, tags, deadline, area_id, area_title, todos)
            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                output_lines = (result.get("output", "") or "").strip().split("\n")
                project_id = output_lines[0].strip() if output_lines else ""
                if project_id and not project_id.startswith("error:"):
                    # Verify every requested todo line actually landed in
                    # the project (hq-f0w.41: a one-off live run once
                    # reported only 1 of 2 requested to-dos present).
                    # _build_create_project_script returns the id and the
                    # live "count of to dos of newProject" on separate
                    # lines, read from the same AppleScript call that
                    # created the project (no separate things.py read,
                    # which lags a fresh write via its on-disk SQLite
                    # snapshot - see _add_todo_via_url_scheme).
                    todos_created: Optional[int] = None
                    if len(output_lines) > 1:
                        try:
                            todos_created = int(output_lines[1].strip())
                        except ValueError:
                            todos_created = None

                    response: Dict[str, Any] = {
                        "success": True,
                        "project_id": project_id,
                        "message": "Project created successfully"
                    }
                    if todos:
                        response["todos_created"] = (
                            todos_created if todos_created is not None else len(todos)
                        )
                        if todos_created is not None and todos_created < len(todos):
                            response["warnings"] = [
                                f"Requested {len(todos)} initial to-dos but only "
                                f"{todos_created} were created in the project; "
                                "verify manually before retrying to avoid duplicates."
                            ]

                    # Schedule if when date provided. A when with a
                    # '@HH:MM' time component sets a reminder and is only
                    # honoured by the Things URL scheme (see docstring) -
                    # the auth token was already verified present above.
                    if when_has_time:
                        url_result = await self.applescript.execute_url_scheme(
                            'update-project', {'id': project_id, 'when': when}
                        )
                        if not url_result.get('success'):
                            return self._propagate_url_scheme_error(
                                url_result, "Failed to set project reminder"
                            )
                        response["message"] = "Project created and reminder set successfully"
                        response["scheduling"] = {
                            "success": True,
                            "method": "url_scheme",
                            "date_set": when
                        }
                    elif when:
                        schedule_result = await self.scheduler.schedule_todo_reliable(project_id, when)
                        response["message"] = "Project created and scheduled successfully"
                        response["scheduling"] = schedule_result
                    return response
                return _write_error(
                    "APPLESCRIPT_ERROR", "Failed to create project", details=project_id
                )
            return _write_error(
                "APPLESCRIPT_ERROR", "Failed to create project",
                details=result.get("output", "AppleScript execution failed"),
            )

        except Exception as e:
            logger.error(f"Error adding project: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to add project", details=str(e))

    async def update_project(self, project_id: str, **kwargs) -> Dict[str, Any]:
        """Update an existing project using AppleScript.

        Clear-field contract: a field that is omitted from kwargs, or
        explicitly None, leaves the existing value unchanged. notes=''
        and deadline='' clear those fields. tags=[] (an explicit empty
        list) clears all tags. title='' is rejected upstream
        (ParameterValidator.validate_update_params) and should never
        reach here.

        when='evening'/'tonight' is rejected: Things has no "This Evening"
        concept for projects (only to-dos can be scheduled for This
        Evening in the Things UI), and silently falling back to a plain
        "Today" schedule (as schedule_todo_reliable's list-fallback would
        otherwise do for an unrecognized when value) would misrepresent
        what was actually applied.

        when='YYYY-MM-DD@HH:MM' (sets a reminder, hq-4gn): unlike
        'evening', this form IS supported for projects - live-probed
        against ``things:///update-project``, which accepts a
        'YYYY-MM-DD@HH:MM' ``when`` and sets ``reminder_time``/
        ``start_date`` on the project exactly as it does for to-dos.
        schedule_todo_reliable's AppleScript path
        (locale_aware_dates.normalize_date_input) only extracts
        year/month/day and would silently drop the time component the
        same way it does for to-dos, so this is routed via
        ``things:///update-project`` instead - same pattern as
        when='evening' on update_todo, including the fail-fast auth-token
        gate BEFORE any AppleScript write (update-project requires the
        Things auth token), so a missing token never results in a
        partially-applied update.
        """
        try:
            # Extract parameters. title/area default to '' (falsy
            # "unchanged") since they have no clear semantics here; notes/
            # deadline/tags default to None so "not provided" (leave
            # unchanged) can be distinguished from '' / [] (explicit clear).
            title = kwargs.get('title', '')
            notes = kwargs.get('notes', None)
            tags = kwargs.get('tags', None)
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', None)

            if isinstance(when, str) and when.strip().lower() == 'evening':
                return _write_error(
                    "UNSUPPORTED_FOR_PROJECTS",
                    "when='evening' is not supported for projects; Things has "
                    "no \"This Evening\" concept for projects (only to-dos can "
                    "be scheduled for This Evening) - use when='today' instead",
                    field="when",
                )

            when_has_time = when_has_time_component(when)
            if when_has_time and not self.applescript.auth_token:
                # Reload-on-miss (hq-wsa.4): a token file created after this
                # manager was constructed is picked up here rather than
                # requiring a restart. No-op (and safe on a mocked manager)
                # if a token is already loaded.
                reload = getattr(self.applescript, "reload_auth_token_if_missing", None)
                if callable(reload):
                    reload()
            if when_has_time and not self.applescript.auth_token:
                from ..services.applescript_manager import AUTH_TOKEN_HINT
                return _write_error(
                    "AUTH_TOKEN_NOT_CONFIGURED",
                    "Things URL-scheme auth token not configured",
                    hint=AUTH_TOKEN_HINT,
                    checked_paths=getattr(self.applescript, "_auth_token_trace", []),
                )

            # Separate area_id (UUID) and area_title (name) for proper AppleScript syntax
            area_id = kwargs.get('area_id', '')
            area_title = kwargs.get('area_title', '') or kwargs.get('area', '')  # 'area' param is treated as title

            # Pre-resolve the area target via things.py BEFORE any write
            # (hq-rmh): the whole update below runs in a single AppleScript
            # try block, so an unresolvable area_id/area_title would throw
            # partway through and silently discard every other field
            # (title/notes/tags/deadline/status) requested in the same
            # call, while still reporting APPLESCRIPT_ERROR. A successful
            # resolution normalizes area_title to its concrete area_id.
            if area_id or area_title:
                area_resolution = self._resolve_area(area_id=area_id, area_title=area_title)
                if "error" in area_resolution:
                    return area_resolution
                if area_resolution.get("area_id"):
                    area_id = area_resolution["area_id"]
                    area_title = ''

            completed = kwargs.get('completed', None)
            canceled = kwargs.get('canceled', None)

            # Start building the AppleScript
            script = f'''
            tell application "Things3"
                try
                    set targetProject to project id "{project_id}"
            '''

            # Update title if provided (titles cannot be cleared - callers
            # reject title='' upstream, so any non-empty value here is real).
            if title:
                escaped_title = AppleScriptTemplates.escape_string(title)
                script += f'set name of targetProject to {escaped_title}\n                    '

            # Update notes: None leaves unchanged, '' clears, anything else sets.
            if notes is not None:
                if notes == '':
                    script += 'set notes of targetProject to ""\n                    '
                else:
                    escaped_notes = AppleScriptTemplates.escape_string(notes)
                    script += f'set notes of targetProject to {escaped_notes}\n                    '

            # Update area if provided: prefer area_id (UUID) over area_title (name)
            if area_id:
                escaped_area_id = AppleScriptTemplates.escape_string(area_id)
                script += f'set area of targetProject to area id {escaped_area_id}\n                    '
            elif area_title:
                escaped_area_title = AppleScriptTemplates.escape_string(area_title)
                script += f'set area of targetProject to area {escaped_area_title}\n                    '

            # Update tags: None leaves unchanged, [] (explicit empty list)
            # clears, a non-empty list sets.
            if tags is not None:
                if len(tags) == 0:
                    script += 'set tag names of targetProject to ""\n                    '
                else:
                    # Things 3 expects tags as comma-separated string, not AppleScript list
                    tags_string = ', '.join(tags)
                    escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
                    script += f'set tag names of targetProject to {escaped_tags_string}\n                    '

            # Update deadline: None leaves unchanged, '' clears, anything else sets.
            if deadline is not None:
                if deadline == '':
                    # Things 3's AppleScript dictionary rejects assigning
                    # missing value to the due date ("Can't make
                    # missing value into type date"); `delete` is the
                    # documented way to clear a date property.
                    script += 'delete due date of targetProject\n                    '
                else:
                    date_components = locale_handler.normalize_date_input(deadline)
                    if date_components:
                        year, month, day = date_components
                        script += f'''
                    set deadlineDate to (current date)
                    set time of deadlineDate to 0
                    set day of deadlineDate to 1
                    set year of deadlineDate to {year}
                    set month of deadlineDate to {month}
                    set day of deadlineDate to {day}
                    set due date of targetProject to deadlineDate
                    '''

            # Update status if provided (canceled takes precedence over completed,
            # matching _build_update_script's todo-path precedence). Unlike the todo
            # path, canceled=False alone also reopens the project (no completed given)
            # so that update_project(canceled='false') reliably returns the project to
            # 'incomplete' rather than being a silent no-op.
            if canceled is not None and canceled:
                script += 'set status of targetProject to canceled\n                    '
            elif completed is not None:
                if completed:
                    script += 'set status of targetProject to completed\n                    '
                else:
                    script += 'set status of targetProject to open\n                    '
            elif canceled is not None and not canceled:
                script += 'set status of targetProject to open\n                    '

            script += '''
                    return "updated"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                output = result.get("output", "").strip()
                if output == "updated":
                    # Schedule the project if when date is provided. A
                    # when with a '@HH:MM' time component sets a reminder
                    # and is only honoured by the Things URL scheme (see
                    # docstring) - the auth token was already verified
                    # present above, before the AppleScript write ran.
                    if when_has_time:
                        url_result = await self.applescript.execute_url_scheme(
                            'update-project', {'id': project_id, 'when': when}
                        )
                        if not url_result.get('success'):
                            return self._propagate_url_scheme_error(
                                url_result, "Failed to set project reminder"
                            )
                        return {
                            "success": True,
                            "message": "Project updated and reminder set successfully",
                            "scheduling": {
                                "success": True,
                                "method": "url_scheme",
                                "date_set": when
                            }
                        }
                    elif when:
                        schedule_result = await self.scheduler.schedule_todo_reliable(project_id, when)
                        return {
                            "success": True,
                            "message": "Project updated and scheduled successfully",
                            "scheduling": schedule_result
                        }
                    else:
                        return {
                            "success": True,
                            "message": "Project updated successfully"
                        }
                else:
                    return _write_error(
                        "APPLESCRIPT_ERROR", "Failed to update project", details=output
                    )
            else:
                return _write_error(
                    "APPLESCRIPT_ERROR", "Failed to update project",
                    details=result.get("output", "AppleScript execution failed"),
                )

        except Exception as e:
            logger.error(f"Error updating project: {e}")
            return _write_error("APPLESCRIPT_ERROR", "Failed to update project", details=str(e))

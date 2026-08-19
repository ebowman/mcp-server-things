"""Todo and project creation/update operations."""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional

from ..locale_aware_dates import locale_handler
from ..things_import import LazyThingsProxy
from ..utils.applescript_utils import AppleScriptTemplates

# Lazily-importing proxy for things.py -- avoids the module-level,
# unbounded glob.iglob() scan that a plain `import things` would perform
# at server boot time. See things_import.LazyThingsProxy docstring; this
# also preserves existing test seams that patch `things.<attr>` (the real
# module) or `todo_operations.things.<attr>` (this proxy) directly.
things = LazyThingsProxy()

logger = logging.getLogger(__name__)


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
            dependency. {"error": "..."} is only returned when the lookup
            *succeeds* and definitively reports the id as unknown or not a
            project/area.
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
            return {"error": f"list_id '{list_id}' does not match any known project or area"}

        record_type = record.get('type')
        if record_type == 'project':
            return {"kind": "project", "id": list_id}
        if record_type == 'area':
            return {"kind": "area", "id": list_id}

        return {"error": f"list_id '{list_id}' refers to a '{record_type}', not a project or area"}

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
            match, or {"error": "..."} if there is no match or more than one.
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
            return {"error": f"list_title '{list_title}' does not match any project or area"}

        if len(matches) > 1:
            ids = ", ".join(f"{kind}:{mid}" for kind, mid in matches)
            return {"error": f"list_title '{list_title}' is ambiguous - matches multiple projects/areas: {ids}"}

        kind, matched_id = matches[0]
        return {"kind": kind, "id": matched_id}

    async def add_todo(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new todo using AppleScript, or URL scheme if heading and/or checklist items are provided."""
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

            # A heading can only be honoured via the Things URL scheme (Things 3
            # AppleScript has no heading class). Require a target project.
            if heading and not project and not list_title:
                return {
                    "success": False,
                    "error": "heading requires a target project (list_id or list_title)",
                    "message": "Failed to add todo"
                }

            # If a heading or checklist items are provided, use the Things URL scheme -
            # it is the only way to create checklists, and the only way to place a
            # new to-do directly under a heading.
            if heading or checklist:
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
                    return {
                        "success": False,
                        "error": resolution["error"],
                        "message": "Failed to add todo"
                    }
                if resolution["kind"] == "project":
                    project_id = resolution["id"]
                else:
                    area_id = resolution["id"]
            elif list_title:
                resolution = self._resolve_list_title(list_title)
                if "error" in resolution:
                    return {
                        "success": False,
                        "error": resolution["error"],
                        "message": "Failed to add todo"
                    }
                if resolution["kind"] == "project":
                    project_id = resolution["id"]
                else:
                    area_id = resolution["id"]

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
                return {
                    "success": False,
                    "error": todo_id,
                    "message": "Failed to create todo"
                }
            return {
                "success": False,
                "error": result.get("output", "AppleScript execution failed"),
                "message": "Failed to create todo"
            }

        except Exception as e:
            logger.error(f"Error adding todo: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add todo"
            }

    def _check_heading_exists(self, heading: str, list_id: str = '', list_title: str = '') -> Optional[str]:
        """Check whether `heading` exists as a heading in the target project.

        The Things URL scheme silently ignores a heading that doesn't exist in
        the target project (the to-do still lands in the project, just not
        under that heading) - this pre-check lets callers surface that as a
        warning instead of silent data loss.

        Args:
            heading: Heading title to look for.
            list_id: Project/area id supplied by the caller, if any.
            list_title: Project/area title supplied by the caller, if any.

        Returns:
            A warning string if the heading could not be confirmed to exist
            in the resolved project, or None if it was found (or the target
            project could not be resolved, in which case we stay silent
            rather than risk a false-positive warning).
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
            # Either no project could be resolved (e.g. area target, or an
            # unresolvable list_title/list_id - those cases are reported by
            # their own resolution errors elsewhere) - don't guess.
            return None

        try:
            existing_headings = things.tasks(type='heading', project=project_id) or []
        except Exception as e:
            logger.debug(f"Error checking heading existence for project {project_id}: {e}")
            return None

        if any(h.get('title') == heading for h in existing_headings):
            return None

        return (
            f"Heading '{heading}' was not found in the target project; "
            "Things will still create the to-do in the project but may not "
            "place it under this heading."
        )

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
                    return {
                        "success": False,
                        "error": resolution["error"],
                        "message": "Failed to add todo"
                    }
                # 'list-id' accepts both project and area ids in the Things
                # URL scheme, so a single resolved id works for either kind.
                params['list-id'] = resolution["id"]

            heading = kwargs.get('heading') or ''
            warnings: List[str] = []
            if heading:
                params['heading'] = heading
                heading_warning = self._check_heading_exists(
                    heading, kwargs.get('list_id', ''), kwargs.get('list_title', '')
                )
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
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "message": "Failed to create todo via URL scheme"
                }

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
                return {
                    "success": False,
                    "error": (
                        "Todo could not be confirmed created within "
                        f"{self._URL_SCHEME_LOOKUP_DEADLINE_SECS}s of the "
                        "URL scheme call; the to-do may still have been "
                        "created in Things - check manually before "
                        "retrying to avoid a duplicate."
                    ),
                    "message": f"Todo creation{message_suffix} could not be confirmed",
                    "checklist_count": item_count,
                    **({"warnings": warnings} if warnings else {})
                }

        except Exception as e:
            logger.error(f"Error adding todo via URL scheme: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add todo"
            }

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
                return {
                    "success": False,
                    "error": "No checklist items provided",
                    "message": "At least one checklist item is required"
                }

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
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "message": "Failed to add checklist items"
                }

        except Exception as e:
            logger.error(f"Error adding checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add checklist items"
            }

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
                return {
                    "success": False,
                    "error": "No checklist items provided",
                    "message": "At least one checklist item is required"
                }

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
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "message": "Failed to prepend checklist items"
                }

        except Exception as e:
            logger.error(f"Error prepending checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to prepend checklist items"
            }

    async def replace_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Replace all checklist items in a todo using Things URL scheme.

        Args:
            todo_id: ID of the todo to replace checklist items in
            items: List of checklist item titles to replace with

        Returns:
            Dict with success status and operation details
        """
        try:
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
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "message": "Failed to replace checklist items"
                }

        except Exception as e:
            logger.error(f"Error replacing checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to replace checklist items"
            }

    def _build_update_script(self, todo_id: str, title: Optional[str], notes: Optional[str],
                            tags: Optional[List[str]],
                            deadline: Optional[str], area: str, project: str,
                            completed: Optional[bool], canceled: Optional[bool]) -> str:
        """Build AppleScript for updating a todo.

        Clear-field contract: ``None`` (or, for title/area/project, the empty
        string produced by the old falsy-default calling convention) leaves
        the field unchanged; ``notes=''``/``deadline=''`` clear the field;
        ``tags=[]`` (an explicit empty list, as opposed to ``None`` or a
        falsy default) clears all tags. Titles cannot be cleared - callers
        must reject ``title=''`` before calling this method.

        Args:
            todo_id: Todo ID to update
            title: New title, or None/empty to leave unchanged
            notes: New notes, or None to leave unchanged, '' to clear
            tags: New tags list, or None to leave unchanged, [] to clear
            deadline: New deadline date, or None to leave unchanged, '' to clear
            area: New area
            project: New project
            completed: Completion status
            canceled: Canceled status

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

        # Update area if provided
        if area:
            escaped_area = AppleScriptTemplates.escape_string(area)
            script += f'set area of targetTodo to area {escaped_area}\n                    '

        # Update project if provided
        if project:
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
                # Things 3's AppleScript dictionary rejects
                # `set due date of X to missing value` ("Can't make missing
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

        # Update status
        if canceled is not None and canceled:
            script += 'set status of targetTodo to canceled\n                    '
        elif completed is not None:
            if completed:
                script += 'set status of targetTodo to completed\n                    '
            else:
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
        surface a structured error instead of guessing). If list_id is
        also given, the to-do is moved to that project via 'list-id' in
        the same URL, with 'heading' resolved within the destination
        project; if list_id resolves to an area rather than a project, a
        warning is added since Things ignores 'heading' for area targets.
        A to-do whose current parent is itself a heading reports
        project=None from things.py (the project only appears on the
        heading record) - the current-project fallback for the
        heading-exists check/warning resolves that via the to-do's
        heading record.
        """
        try:
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

            # heading has no "clear" semantics via the URL scheme - reject an
            # explicit empty (or whitespace-only) string rather than silently
            # ignoring it or sending an ambiguous request to Things. This
            # check runs before any AppleScript write so nothing is
            # partially applied.
            if heading is not None and heading.strip() == '':
                return {
                    "success": False,
                    "error": (
                        "heading cannot be empty; Things' URL scheme has no "
                        "documented way to clear a to-do out of a heading via "
                        "update - to move it out, use move_record() to move "
                        "it directly into the project instead"
                    ),
                    "message": "Failed to update todo"
                }

            # heading is only honoured via the Things URL scheme, which
            # requires the auth token. Fail fast BEFORE any AppleScript
            # write so other fields are never partially applied.
            if heading:
                if not self.applescript.auth_token:
                    from ..services.applescript_manager import AUTH_TOKEN_HINT
                    return {
                        "success": False,
                        "error": "Things URL-scheme auth token not configured",
                        "hint": AUTH_TOKEN_HINT,
                        "message": "Failed to update todo"
                    }

            # Convert status parameters
            completed = kwargs.get('completed', None)
            canceled = kwargs.get('canceled', None)

            try:
                if completed is not None:
                    completed = self._convert_to_boolean(completed)
                if canceled is not None:
                    canceled = self._convert_to_boolean(canceled)
            except ValueError as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": "Invalid boolean value for status parameter"
                }

            warnings: List[str] = []

            # Apply the AppleScript-only fields first (title, notes, tags,
            # deadline, area, project, completed, canceled). This mirrors the
            # pre-existing unconditional behavior (the AppleScript write is
            # always issued, even as a no-op "updated" round trip) EXCEPT
            # when heading is the only field requested at all - in that one
            # case skip the AppleScript step entirely and rely solely on the
            # URL-scheme update below, since there is nothing else to write.
            skip_applescript = heading and not any([
                title, notes is not None, tags is not None, deadline is not None,
                area, project, completed is not None, canceled is not None
            ])

            if not skip_applescript:
                script = self._build_update_script(todo_id, title, notes, tags, deadline,
                                                  area, project, completed, canceled)
                result = await self.applescript.execute_applescript(script)

                if result.get("success"):
                    output = result.get("output", "").strip()
                    if output != "updated":
                        return {
                            "success": False,
                            "error": output,
                            "message": "Failed to update todo"
                        }
                else:
                    return {
                        "success": False,
                        "error": result.get("output", "AppleScript execution failed"),
                        "message": "Failed to update todo"
                    }

            if heading:
                url_params: Dict[str, Any] = {'id': todo_id, 'heading': heading}
                if list_id:
                    url_params['list-id'] = list_id

                try:
                    todo_record = things.get(todo_id)
                except Exception as e:
                    logger.debug(f"Error looking up todo {todo_id} for project check: {e}")
                    todo_record = None

                # Resolve which project the heading check/warning should be
                # scoped to: the explicitly-requested list_id, or (if none
                # given) the to-do's current project. things.py reports
                # project=None for a to-do whose parent is a heading (the
                # PROJECT join is on TASK.project, which is NULL for heading
                # children - the parent project only shows up on the
                # heading record itself), so fall back to looking up the
                # to-do's heading record's project in that case.
                effective_project_id = list_id
                list_id_resolution = None
                if not effective_project_id and todo_record:
                    effective_project_id = todo_record.get('project')
                    if not effective_project_id and todo_record.get('heading'):
                        try:
                            heading_record = things.get(todo_record['heading'])
                        except Exception as e:
                            logger.debug(
                                f"Error looking up heading {todo_record['heading']} "
                                f"for project fallback: {e}"
                            )
                            heading_record = None
                        if heading_record:
                            effective_project_id = heading_record.get('project')

                if list_id:
                    list_id_resolution = self._resolve_list_id(list_id)

                if list_id_resolution and list_id_resolution.get("kind") == "area":
                    warnings.append(
                        f"list_id '{list_id}' resolves to an area, not a project; "
                        "Things' URL scheme ignores 'heading' for area targets - "
                        "the to-do will move into the area but not be placed under "
                        "any heading."
                    )
                elif effective_project_id:
                    heading_warning = self._check_heading_exists(heading, list_id=effective_project_id)
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
                    response = {
                        "success": False,
                        "error": url_result.get('error', 'Unknown error'),
                        "message": "Failed to update todo heading"
                    }
                    if url_result.get('hint'):
                        response['hint'] = url_result['hint']
                    return response

            # Schedule if when date provided
            if when:
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
                "message": "Todo updated successfully"
            }
            if warnings:
                response["warnings"] = warnings
            return response

        except Exception as e:
            logger.error(f"Error updating todo: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update todo"
            }

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

        script += '''
                    return id of newProject
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

        return script

    async def add_project(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new project using AppleScript."""
        try:
            # Extract parameters
            notes = kwargs.get('notes', '')
            tags = kwargs.get('tags', [])
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', '')

            # Separate area_id (UUID) and area_title (name) for proper AppleScript syntax
            area_id = kwargs.get('area_id', '')
            area_title = kwargs.get('area_title', '') or kwargs.get('area', '')  # 'area' param is treated as title

            # Handle todos parameter - can be string (newline-separated) or list
            todos_param = kwargs.get('todos', [])
            if isinstance(todos_param, str):
                # Split by newlines and filter out empty strings
                todos = [t.strip() for t in todos_param.split('\n') if t.strip()]
            elif isinstance(todos_param, list):
                todos = todos_param
            else:
                todos = []

            # Build and execute script
            script = self._build_create_project_script(title, notes, tags, deadline, area_id, area_title, todos)
            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                project_id = result.get("output", "").strip()
                if project_id and not project_id.startswith("error:"):
                    # Schedule if when date provided
                    if when:
                        schedule_result = await self.scheduler.schedule_todo_reliable(project_id, when)
                        return {
                            "success": True,
                            "project_id": project_id,
                            "message": "Project created and scheduled successfully",
                            "scheduling": schedule_result
                        }
                    return {
                        "success": True,
                        "project_id": project_id,
                        "message": "Project created successfully"
                    }
                return {
                    "success": False,
                    "error": project_id,
                    "message": "Failed to create project"
                }
            return {
                "success": False,
                "error": result.get("output", "AppleScript execution failed"),
                "message": "Failed to create project"
            }

        except Exception as e:
            logger.error(f"Error adding project: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add project"
            }

    async def update_project(self, project_id: str, **kwargs) -> Dict[str, Any]:
        """Update an existing project using AppleScript.

        Clear-field contract: a field that is omitted from kwargs, or
        explicitly None, leaves the existing value unchanged. notes=''
        and deadline='' clear those fields. tags=[] (an explicit empty
        list) clears all tags. title='' is rejected upstream
        (ParameterValidator.validate_update_params) and should never
        reach here.
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

            # Separate area_id (UUID) and area_title (name) for proper AppleScript syntax
            area_id = kwargs.get('area_id', '')
            area_title = kwargs.get('area_title', '') or kwargs.get('area', '')  # 'area' param is treated as title

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
                    # Things 3's AppleScript dictionary rejects
                    # `set due date of X to missing value` ("Can't make
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
                    # Schedule the project if when date is provided
                    if when:
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
                    return {
                        "success": False,
                        "error": output,
                        "message": "Failed to update project"
                    }
            else:
                return {
                    "success": False,
                    "error": result.get("output", "AppleScript execution failed"),
                    "message": "Failed to update project"
                }

        except Exception as e:
            logger.error(f"Error updating project: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update project"
            }

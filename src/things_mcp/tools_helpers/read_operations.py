"""Read operations for Things 3 - uses things.py for fast direct database access."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta

from ..things_import import LazyThingsProxy
from ..services.applescript_manager import AppleScriptManager
from ..response_optimizer import ResponseOptimizer
from .helpers import ToolsHelpers

# Lazily-importing proxy for things.py -- avoids the module-level,
# unbounded glob.iglob() scan that a plain `import things` would perform
# at server boot time. See things_import.LazyThingsProxy docstring; this
# also preserves existing test seams that patch `things.<attr>` (the real
# module) or `read_operations.things.<attr>` (this proxy) directly.
things = LazyThingsProxy()

logger = logging.getLogger(__name__)


class ListWithTotal(list):
    """A plain list that also carries the pre-limit/offset total item count.

    Used by search_todos/search_advanced/get_logbook so their public
    signature and behavior stay exactly `List[Dict]` (existing callers doing
    `isinstance(result, list)`, `len(result)`, `result == []`, `result[0]`
    etc. keep working unchanged) while still giving server.py a way to read
    the true pre-limit total via the `.total_count` attribute for the
    `total` field in `_read_result`. Falls back to `len(self)` if a caller
    (e.g. an older mock) returns a plain list without setting it.
    """

    total_count: int = None

    def __new__(cls, iterable=(), total_count: Optional[int] = None):
        obj = super().__new__(cls)
        return obj

    def __init__(self, iterable=(), total_count: Optional[int] = None):
        super().__init__(iterable)
        self.total_count = total_count if total_count is not None else len(self)


def _get_someday_project_ids() -> set:
    """Return the set of project UUIDs whose start state is 'Someday'.

    Things UI hides tasks that live inside a Someday project from Today,
    Anytime, and Upcoming, even if things.py reports the individual task
    itself as scheduled for today/anytime. This loads the set of Someday
    project UUIDs once so callers can filter tasks accordingly.

    Defensive: any failure talking to things.py results in an empty set,
    which means no filtering is applied (todos are kept).

    Returns:
        Set of project UUIDs with start == 'Someday'. Empty set on error
        or if there are no Someday projects.
    """
    try:
        someday_projects = things.projects(start='Someday') or []
        return {p['uuid'] for p in someday_projects if p.get('uuid')}
    except Exception as e:
        logger.debug(f"Error loading Someday project ids: {e}")
        return set()


def _build_unknown_tag_error(tag: str) -> Dict[str, Any]:
    """Build a structured error for a tag that things.py did not recognize.

    Things 3 tag matching is exact-case (e.g. 'llm-wiki' and 'LLM-WIKI' are
    different tags to things.py), and things.py raises ValueError when asked
    for a tag it doesn't recognize rather than returning an empty list. This
    distinguishes that "unknown/wrong-case tag" case from a genuinely empty
    (zero-item) tag by returning a structured error with case-insensitive
    suggestions pulled from the live tag list, instead of silently returning [].

    Args:
        tag: The tag string that was requested and rejected by things.py.

    Returns:
        Dict with success=False, error='unknown_tag', the offending tag, and
        a (possibly empty) list of case-insensitive title matches from
        things.tags() to help the caller find the correctly-cased tag.
    """
    suggestions: List[str] = []
    try:
        all_tags = things.tags() or []
        tag_lower = tag.lower()
        suggestions = [
            t.get('title', t.get('name', ''))
            for t in all_tags
            if t.get('title', t.get('name', '')).lower() == tag_lower
        ]
    except Exception as e:
        logger.debug(f"Error building tag suggestions for '{tag}': {e}")

    return {
        'success': False,
        'error': 'unknown_tag',
        'tag': tag,
        'suggestions': suggestions,
    }


def _resolve_heading_project(heading_uuid: str, cache: Dict[str, Optional[str]]) -> Optional[str]:
    """Resolve a heading UUID to its parent project UUID, with per-call caching.

    Args:
        heading_uuid: UUID of the heading to resolve.
        cache: Dict used to memoize heading UUID -> project UUID (or None)
            lookups for the duration of a single filtering call.

    Returns:
        The parent project UUID, or None if the heading is missing/deleted
        or otherwise cannot be resolved.
    """
    if heading_uuid in cache:
        return cache[heading_uuid]

    project_uuid = None
    try:
        heading = things.get(heading_uuid)
        if heading:
            project_uuid = heading.get('project')
    except Exception as e:
        logger.debug(f"Error resolving heading {heading_uuid}: {e}")
        project_uuid = None

    cache[heading_uuid] = project_uuid
    return project_uuid


def _is_in_someday_project(todo: Dict[str, Any], someday_project_ids: set,
                            heading_cache: Dict[str, Optional[str]]) -> bool:
    """Check whether a todo belongs to a Someday project, directly or via heading.

    Args:
        todo: Raw things.py todo dict (must have 'project'/'heading' keys as
            provided by things.py, prior to convert_todo() field renaming).
        someday_project_ids: Set of project UUIDs with start == 'Someday'.
        heading_cache: Per-call cache for heading -> project UUID lookups.

    Returns:
        True if the todo should be treated as belonging to a Someday project.
    """
    if not someday_project_ids:
        return False

    project_uuid = todo.get('project')
    if project_uuid:
        return project_uuid in someday_project_ids

    heading_uuid = todo.get('heading')
    if heading_uuid:
        resolved_project = _resolve_heading_project(heading_uuid, heading_cache)
        if resolved_project:
            return resolved_project in someday_project_ids

    return False


def filter_someday_project_tasks(todos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out tasks that belong to Someday projects.

    Matches Things UI behavior: tasks belonging to a project whose start
    state is 'Someday' are hidden from Today, Anytime, and Upcoming views,
    even when things.py reports the individual task as scheduled/anytime.
    Handles both tasks directly assigned to a Someday project and tasks
    parented under a heading that belongs to a Someday project.

    Todos without a project (standalone) are always kept. Any error while
    resolving Someday project/heading membership is treated defensively as
    "not Someday" (the todo is kept).

    Args:
        todos: List of raw things.py todo dicts.

    Returns:
        Filtered list excluding todos that belong to Someday projects.
    """
    someday_project_ids = _get_someday_project_ids()
    if not someday_project_ids:
        return todos

    heading_cache: Dict[str, Optional[str]] = {}
    return [
        todo for todo in todos
        if not _is_in_someday_project(todo, someday_project_ids, heading_cache)
    ]


def _fetch_list(things_fn, include_projects: bool) -> List[Dict[str, Any]]:
    """Call a things.py list function (inbox/today/upcoming/anytime/someday/trash),
    filtering out headings always and projects unless include_projects is True.

    By default, queries with type='to-do' so filtering happens at the things.py
    query level (not only post-hoc). When include_projects is True, queries
    with no type filter (to get both to-dos and projects) and then drops any
    item whose type == 'heading' post-hoc, since things.py list wrappers don't
    support fetching multiple explicit types in one call.

    Items lacking a 'type' key (e.g. in unit test mocks) are treated as to-do
    and always kept.
    """
    def _normalize(data) -> List[Dict[str, Any]]:
        if data is None:
            return []
        if isinstance(data, dict):
            return [data]
        if hasattr(data, '__iter__') and not isinstance(data, list):
            return list(data)
        return data

    if not include_projects:
        result = _normalize(things_fn(type='to-do'))
        # Defensive post-hoc filter in case a mocked/older things.py ignores
        # the type= kwarg and returns an unfiltered mix.
        return [t for t in result if t.get('type', 'to-do') != 'project'
                and t.get('type', 'to-do') != 'heading']

    result = _normalize(things_fn())
    return [t for t in result if t.get('type', 'to-do') != 'heading']


class ReadOperations:
    """Read operations using things.py for fast direct database access."""

    def __init__(self, applescript_manager: AppleScriptManager, response_optimizer: ResponseOptimizer):
        """Initialize read operations.

        Args:
            applescript_manager: AppleScript manager for fallback queries
            response_optimizer: Response optimizer for field optimization
        """
        self.applescript = applescript_manager
        self.response_optimizer = response_optimizer

    async def get_todos(self, project_uuid: Optional[str] = None, include_items: Optional[bool] = None,
                       status: Optional[str] = 'incomplete') -> List[Dict]:
        """Get todos with hybrid approach: AppleScript for projects, things.py otherwise.

        BUG FIX: When querying by project_uuid, use AppleScript to avoid sync timing issues.

        Args:
            project_uuid: Optional project UUID to filter by
            include_items: Include checklist items
            status: Filter by status - 'incomplete' (default), 'completed', 'canceled', or None for all
        """
        # Use AppleScript for project queries to avoid database sync timing issues
        if project_uuid:
            try:
                applescript_todos = await self.applescript.get_todos(project_uuid=project_uuid)

                result = []
                for todo in applescript_todos:
                    todo_status = todo.get('status', 'open').lower()
                    if todo_status == 'open':
                        todo_status = 'incomplete'

                    if status is None or todo_status == status:
                        converted = ToolsHelpers.convert_applescript_todo(todo)
                        result.append(converted)

                logger.debug(f"Retrieved {len(result)} todos for project {project_uuid} via AppleScript")

                # Best-effort enrichment: the AppleScript read path has no
                # heading concept, so headingTitle/heading/projectTitle/start
                # are missing from convert_applescript_todo's output. Fill
                # them in from things.py's own project-scoped query, keyed by
                # uuid. Never let this fail the call - AppleScript data is
                # still returned as-is if things.py is unavailable/errors.
                try:
                    things_rows = things.todos(project=project_uuid)
                    by_uuid = {row['uuid']: row for row in things_rows if row.get('uuid')}
                    for todo in result:
                        row = by_uuid.get(todo.get('uuid'))
                        if row:
                            todo['heading'] = row.get('heading')
                            todo['headingTitle'] = row.get('heading_title')
                            todo['projectTitle'] = row.get('project_title')
                            todo['start'] = row.get('start')
                except Exception as e:
                    logger.debug(
                        f"Best-effort heading/start enrichment failed for project {project_uuid}: {e}"
                    )

                return result
            except Exception as e:
                logger.error(f"AppleScript query failed for project {project_uuid}, falling back to things.py: {e}")

        # Use things.py for all other queries
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_todos_sync, project_uuid, include_items, status)

    def _get_todos_sync(self, project_uuid: Optional[str] = None, include_items: Optional[bool] = None,
                       status: Optional[str] = 'incomplete') -> List[Dict]:
        """Synchronous implementation of get_todos using things.py."""
        try:
            if project_uuid:
                todos = things.todos(project=project_uuid)
            else:
                if status == 'incomplete':
                    todos = things.todos(status='incomplete')
                elif status == 'completed':
                    todos = things.todos(status='completed')
                elif status == 'canceled':
                    todos = things.todos(status='canceled')
                elif status is None:
                    all_todos = []
                    all_todos.extend(things.todos(status='incomplete'))
                    all_todos.extend(things.todos(status='completed'))
                    all_todos.extend(things.todos(status='canceled'))
                    todos = all_todos
                else:
                    todos = things.todos()

            result = []
            for todo in todos:
                converted = ToolsHelpers.convert_todo(todo)

                if include_items and todo.get('uuid'):
                    try:
                        items = things.checklist_items(todo['uuid'])
                        converted['checklist'] = [{'title': i['title'], 'status': i['status']} for i in items]
                    except Exception as e:
                        logger.error(f"Error getting checklist items: {e}")

                result.append(converted)

            return result

        except Exception as e:
            logger.error(f"Error in _get_todos_sync: {e}")
            return []

    async def get_projects(self, include_items: bool = False) -> List[Dict]:
        """Get all projects using things.py."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_projects_sync, include_items)

    def _get_projects_sync(self, include_items: bool = False) -> List[Dict]:
        """Synchronous implementation using things.py."""
        try:
            projects = things.projects()
            result = []

            for project in projects:
                converted = ToolsHelpers.convert_project(project)

                if include_items and project.get('uuid'):
                    try:
                        project_todos = things.todos(project=project['uuid'])
                        converted['todos'] = [ToolsHelpers.convert_todo(t) for t in project_todos]
                    except Exception as e:
                        logger.error(f"Error getting project todos: {e}")

                result.append(converted)

            return result

        except Exception as e:
            logger.error(f"Error in _get_projects_sync: {e}")
            return []

    async def get_areas(self, include_items: bool = False) -> List[Dict]:
        """Get all areas using things.py."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_areas_sync, include_items)

    def _get_areas_sync(self, include_items: bool = False) -> List[Dict]:
        """Synchronous implementation using things.py."""
        try:
            areas = things.areas()
            result = []

            for area in areas:
                converted = ToolsHelpers.convert_area(area)

                if include_items and area.get('uuid'):
                    try:
                        area_projects = things.projects(area=area['uuid'])
                        converted['projects'] = [ToolsHelpers.convert_project(p) for p in area_projects]

                        area_todos = things.todos(area=area['uuid'])
                        converted['todos'] = [ToolsHelpers.convert_todo(t) for t in area_todos]
                    except Exception as e:
                        logger.error(f"Error getting area items: {e}")

                result.append(converted)

            return result

        except Exception as e:
            logger.error(f"Error in _get_areas_sync: {e}")
            return []

    async def get_tags(self, include_items: bool = False) -> List[Dict]:
        """Get all tags using things.py."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_tags_sync, include_items)

    def _get_tags_sync(self, include_items: bool) -> List[Dict]:
        """Synchronous implementation using things.py."""
        try:
            tags = things.tags()
            result = []

            for tag in tags:
                tag_dict = {
                    'title': tag.get('title', tag.get('name', '')),
                    'shortcut': tag.get('shortcut')
                }

                if include_items:
                    tag_title = tag.get('title', tag.get('name', ''))
                    try:
                        tagged_todos = things.todos(tag=tag_title)
                        tag_dict['todos'] = [ToolsHelpers.convert_todo(t) for t in tagged_todos]
                        tag_dict['count'] = len(tagged_todos)
                    except Exception as e:
                        logger.error(f"Error getting tagged items: {e}")
                        tag_dict['todos'] = []
                        tag_dict['count'] = 0
                else:
                    tag_title = tag.get('title', tag.get('name', ''))
                    try:
                        tagged_todos = things.todos(tag=tag_title)
                        tag_dict['count'] = len(tagged_todos)
                    except Exception as e:
                        logger.error(f"Error counting tagged items: {e}")
                        tag_dict['count'] = 0

                result.append(tag_dict)

            return result

        except Exception as e:
            logger.error(f"Error in _get_tags_sync: {e}")
            return []

    async def get_tag_usage(self, only_unused: bool = False, mode: str = 'standard') -> Dict[str, Any]:
        """Report per-tag usage counts (open/total/area) in a single pass over todos,
        projects, and areas.

        Useful for weekly-review tag cleanup: surfaces every tag's open, total, and
        area item counts, sorted by usage (highest first), with an option to list only
        unused tags.

        Caveats:
            - Title collisions: usage is keyed by tag *title*, not uuid. If a parent tag
              and one of its child tags (or any two distinct tags) share the exact same
              title, their usage counts are silently merged into a single row and the
              reported `uuid` is whichever tag `things.tags()` returned last for that
              title. This mirrors Things 3's own display (tags are shown by title), but
              means merged rows cannot be disambiguated by uuid alone.
            - Area tags: tags applied only to Areas (not to any todo or project) are now
              counted via `area_count` and included in `total_count`, so they will not
              appear as "unused" if used solely on an area. Areas have no open/closed
              state, so area usage never contributes to `open_count`.

        Args:
            only_unused: If True, only include tags with total_count == 0.
            mode: Response mode - 'summary', 'minimal', 'standard', or 'detailed'.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_tag_usage_sync, only_unused, mode)

    def _get_tag_usage_sync(self, only_unused: bool, mode: str) -> Dict[str, Any]:
        """Synchronous implementation using things.py, single pass over all items.

        Note on title collisions: usage is keyed by tag title (not uuid). If two tags
        share the same title (e.g. a parent tag and a same-named child tag), their
        counts are merged into one row and only one uuid is retained (see
        `get_tag_usage` docstring for details).
        """
        try:
            tags = things.tags()

            # Initialize counts keyed by tag title, preserving uuid for each known tag.
            usage: Dict[str, Dict[str, Any]] = {}
            for tag in tags:
                title = tag.get('title', tag.get('name', ''))
                usage[title] = {
                    'title': title,
                    'uuid': tag.get('uuid'),
                    'open_count': 0,
                    'total_count': 0,
                    'area_count': 0,
                }

            def get_entry(tag_title: str) -> Dict[str, Any]:
                entry = usage.get(tag_title)
                if entry is None:
                    # Tag referenced on an item but not returned by things.tags();
                    # track it anyway so counts aren't silently dropped.
                    entry = {
                        'title': tag_title,
                        'uuid': None,
                        'open_count': 0,
                        'total_count': 0,
                        'area_count': 0,
                    }
                    usage[tag_title] = entry
                return entry

            def tally(items: List[Dict], is_open: bool) -> None:
                for item in items:
                    for tag_title in (item.get('tags') or []):
                        entry = get_entry(tag_title)
                        entry['total_count'] += 1
                        if is_open:
                            entry['open_count'] += 1

            # Single pass over all todos, across every status.
            for status in ('incomplete', 'completed', 'canceled'):
                todos = things.todos(status=status) or []
                tally(todos, is_open=(status == 'incomplete'))

            # Single pass over all projects, across every status.
            for status in ('incomplete', 'completed', 'canceled'):
                projects = things.projects(status=status) or []
                tally(projects, is_open=(status == 'incomplete'))

            # Single pass over all areas. Areas have no open/closed state, so area
            # usage counts toward total_count and area_count only, never open_count.
            areas = things.areas() or []
            for area in areas:
                for tag_title in (area.get('tags') or []):
                    entry = get_entry(tag_title)
                    entry['total_count'] += 1
                    entry['area_count'] += 1

            rows = list(usage.values())

            if only_unused:
                rows = [r for r in rows if r['total_count'] == 0]

            rows.sort(key=lambda r: (-r['open_count'], -r['total_count'], r['title'].lower()))

            return self._format_tag_usage_response(rows, mode)

        except Exception as e:
            logger.error(f"Error in _get_tag_usage_sync: {e}")
            return {'error': str(e), 'tags': []}

    @staticmethod
    def _format_tag_usage_response(rows: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
        """Apply response-mode shaping to tag usage rows (custom schema; not routed
        through the generic ResponseOptimizer/context_manager machinery, which assumes
        a todo/project field schema that doesn't fit tag-usage rows)."""
        unused_count = sum(1 for r in rows if r['total_count'] == 0)

        if mode == 'summary':
            return {
                'tag_count': len(rows),
                'unused_count': unused_count,
                'top': [
                    {'title': r['title'], 'open_count': r['open_count'], 'total_count': r['total_count']}
                    for r in rows[:5]
                ],
            }

        if mode == 'minimal':
            return {
                'tag_count': len(rows),
                'unused_count': unused_count,
                'tags': [{'title': r['title'], 'open_count': r['open_count']} for r in rows],
            }

        # standard / detailed / anything else: full rows
        return {
            'tag_count': len(rows),
            'unused_count': unused_count,
            'tags': rows,
        }

    async def search_todos(
        self, query: str, limit: Optional[int] = None,
        status: Optional[str] = 'incomplete', offset: int = 0
    ) -> List[Dict]:
        """Search todos using things.py.

        Note: filter_someday_project_tasks is NOT applied here - todos that
        live inside a Someday project (and are hidden from Today/Anytime/
        Upcoming in the Things UI) can still match a search.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query, limit, status, offset)

    def _search_sync(
        self, query: str, limit: Optional[int] = None,
        status: Optional[str] = 'incomplete', offset: int = 0
    ) -> List[Dict]:
        """Synchronous search implementation.

        Args:
            query: Text to search for in title/notes (case-insensitive substring match).
            limit: Maximum number of results to return.
            status: 'incomplete' (default, matches things.py's own default and
                preserves backward compatibility), 'completed', 'canceled', or
                None to search all statuses.
            offset: Number of matching results to skip before applying limit
                (same semantics as get_trash's offset). Applied after the full
                filtered match set is collected, before limit.

        Returns:
            A ``ListWithTotal`` - behaves exactly like ``List[Dict]`` for all
            existing callers, but also carries the true pre-limit/offset match
            count on ``.total_count`` (used by server.py to populate `total`).
        """
        try:
            all_todos = things.todos(status=status)
            query_lower = query.lower()

            matches = []
            for todo in all_todos:
                title = todo.get('title', '').lower()
                notes = todo.get('notes', '').lower()

                if query_lower in title or query_lower in notes:
                    matches.append(todo)

            total_count = len(matches)

            windowed = matches[offset:]
            if limit:
                windowed = windowed[:limit]

            results = [ToolsHelpers.convert_todo(todo) for todo in windowed]

            return ListWithTotal(results, total_count=total_count)

        except Exception as e:
            logger.error(f"Error in _search_sync: {e}")
            return ListWithTotal([], total_count=0)

    async def get_inbox(self, limit: Optional[int] = None) -> List[Dict]:
        """Get todos from Inbox."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_inbox_sync, limit)

    def _get_inbox_sync(self, limit: Optional[int] = None) -> List[Dict]:
        """Synchronous implementation."""
        try:
            # Inbox cannot contain projects, so always type='to-do'; headings
            # are never returned (matches Things UI - Inbox is a task-only list).
            inbox_todos = _fetch_list(things.inbox, include_projects=False)

            result = []
            for todo in inbox_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_inbox_sync: {e}")
            return []

    async def get_today(self, limit: Optional[int] = None,
                         include_projects: bool = False) -> List[Dict]:
        """Get todos due today.

        Args:
            limit: Maximum number of items to return.
            include_projects: If True, also include projects that are due
                today. Defaults to False - by default, and always, headings
                are never returned; projects are excluded unless this flag
                is set, matching the Things app's Today list view.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_today_sync, limit, include_projects)

    def _get_today_sync(self, limit: Optional[int] = None,
                         include_projects: bool = False) -> List[Dict]:
        """Synchronous implementation."""
        try:
            today_todos = _fetch_list(things.today, include_projects)
            today_todos = filter_someday_project_tasks(today_todos or [])

            result = []
            for todo in today_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_today_sync: {e}")
            return []

    async def get_upcoming(self, limit: Optional[int] = None,
                            include_projects: bool = False) -> List[Dict]:
        """Get upcoming todos.

        Args:
            limit: Maximum number of items to return.
            include_projects: If True, also include upcoming projects.
                Defaults to False - headings are never returned; projects
                are excluded unless this flag is set, matching the Things
                app's Upcoming list view.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_upcoming_sync, limit, include_projects)

    def _get_upcoming_sync(self, limit: Optional[int] = None,
                            include_projects: bool = False) -> List[Dict]:
        """Synchronous implementation."""
        try:
            upcoming_todos = _fetch_list(things.upcoming, include_projects)
            upcoming_todos = filter_someday_project_tasks(upcoming_todos or [])

            result = []
            for todo in upcoming_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_upcoming_sync: {e}")
            return []

    async def get_anytime(self, limit: Optional[int] = None,
                           include_projects: bool = False) -> List[Dict]:
        """Get todos from Anytime list.

        Args:
            limit: Maximum number of items to return.
            include_projects: If True, also include Anytime projects.
                Defaults to False - headings are never returned; projects
                are excluded unless this flag is set, matching the Things
                app's Anytime list view.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_anytime_sync, limit, include_projects)

    def _get_anytime_sync(self, limit: Optional[int] = None,
                           include_projects: bool = False) -> List[Dict]:
        """Synchronous implementation."""
        try:
            anytime_todos = _fetch_list(things.anytime, include_projects)
            anytime_todos = filter_someday_project_tasks(anytime_todos or [])

            result = []
            for todo in anytime_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_anytime_sync: {e}")
            return []

    async def get_someday(self, limit: Optional[int] = None,
                           include_project_tasks: bool = False,
                           include_projects: bool = False) -> List[Dict]:
        """Get todos from Someday list.

        Args:
            limit: Maximum number of items to return.
            include_project_tasks: If True, also include tasks that live
                inside Someday projects (marked inherited_someday=True in
                the raw dict / inheritedSomeday in the converted todo).
                Defaults to False - by default only native things.someday()
                items are returned, since inherited items on databases with
                many Someday projects can be very large and crowd out the
                native items when responses are paginated/truncated.
            include_projects: If True, also include Someday projects
                themselves. Defaults to False - headings are never returned;
                projects are excluded unless this flag is set, matching the
                Things app's Someday list view.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._get_someday_sync, limit, include_project_tasks, include_projects)

    def _get_someday_sync(self, limit: Optional[int] = None,
                           include_project_tasks: bool = False,
                           include_projects: bool = False) -> List[Dict]:
        """Synchronous implementation."""
        try:
            someday_todos = list(_fetch_list(things.someday, include_projects))

            # things.py doesn't mark a todo as Someday just because its
            # parent project is Someday - it reports the todo's own
            # start state (often Anytime). When include_project_tasks is
            # True, find those "inherited" Someday todos and add them too,
            # so get_someday() matches what the Things UI shows under a
            # Someday project. This is opt-in: on databases with many
            # Someday projects the inherited set can be very large and
            # crowd out native Someday items under response truncation.
            if include_project_tasks:
                someday_project_ids = _get_someday_project_ids()
                if someday_project_ids:
                    existing_uuids = {t.get('uuid') for t in someday_todos}
                    heading_cache: Dict[str, Optional[str]] = {}
                    try:
                        other_todos = things.todos(status='incomplete') or []
                    except Exception as e:
                        logger.debug(f"Error loading todos for inherited Someday check: {e}")
                        other_todos = []

                    for todo in other_todos:
                        uuid = todo.get('uuid')
                        if not uuid or uuid in existing_uuids:
                            continue
                        if _is_in_someday_project(todo, someday_project_ids, heading_cache):
                            todo = dict(todo)
                            todo['inherited_someday'] = True
                            someday_todos.append(todo)
                            existing_uuids.add(uuid)

            result = []
            for todo in someday_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_someday_sync: {e}")
            return []

    async def get_logbook(self, limit: int = 50, period: str = "7d", offset: int = 0) -> List[Dict]:
        """Get completed todos from Logbook."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_logbook_sync, limit, period, offset)

    def _get_logbook_sync(self, limit: int = 50, period: str = "7d", offset: int = 0) -> List[Dict]:
        """Synchronous implementation.

        Args:
            limit: Maximum number of items to return, applied after sorting
                and after offset.
            period: Time window to look back (e.g. '7d').
            offset: Number of sorted items to skip before applying limit
                (same semantics as get_trash's offset).

        Returns:
            A ``ListWithTotal`` - behaves exactly like ``List[Dict]`` for all
            existing callers, but also carries the true pre-limit/offset item
            count within the period on ``.total_count`` (used by server.py to
            populate `total`).
        """
        try:
            completed_todos = things.todos(status='completed')

            days = ToolsHelpers.parse_period_to_days(period)
            cutoff_date = datetime.now() - timedelta(days=days)

            result = []
            for todo in completed_todos:
                completed_date = todo.get('stop_date')
                if completed_date:
                    try:
                        if isinstance(completed_date, str):
                            completed_dt = datetime.fromisoformat(completed_date.replace('Z', '+00:00'))
                        else:
                            completed_dt = completed_date

                        if completed_dt >= cutoff_date:
                            converted_todo = ToolsHelpers.convert_todo(todo)
                            # Store stop_date for sorting
                            converted_todo['_sort_date'] = completed_dt
                            result.append(converted_todo)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Skipping todo with invalid completion date '{completed_date}': {e}")

            # Sort by completion date (most recent first)
            result.sort(key=lambda x: x.get('_sort_date', datetime.min), reverse=True)

            # Remove temporary sort key
            for todo in result:
                todo.pop('_sort_date', None)

            total_count = len(result)

            # Apply offset then limit, after sorting
            windowed = result[offset:]
            windowed = windowed[:limit]

            return ListWithTotal(windowed, total_count=total_count)

        except Exception as e:
            logger.error(f"Error in _get_logbook_sync: {e}")
            return ListWithTotal([], total_count=0)

    async def get_trash(self, limit: int = 50, offset: int = 0,
                         include_projects: bool = False) -> Dict[str, Any]:
        """Get trashed todos with pagination.

        Args:
            limit: Maximum number of items to return.
            offset: Number of items to skip.
            include_projects: If True, also include trashed projects.
                Defaults to False - headings are never returned; projects
                are excluded unless this flag is set, matching the Things
                app's Trash list view.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_trash_sync, limit, offset, include_projects)

    def _get_trash_sync(self, limit: int = 50, offset: int = 0,
                         include_projects: bool = False) -> Dict[str, Any]:
        """Synchronous implementation."""
        try:
            trash_data = _fetch_list(things.trash, include_projects)

            total_count = len(trash_data)

            # Apply pagination
            paginated = trash_data[offset:offset + limit]

            items = [ToolsHelpers.convert_todo(t) for t in paginated]

            return {
                'items': items,
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            }

        except Exception as e:
            logger.error(f"Error in _get_trash_sync: {e}")
            return {
                'items': [],
                'total_count': 0,
                'limit': limit,
                'offset': offset,
                'has_more': False
            }

    async def get_tagged_items(self, tag: str) -> Union[List[Dict], Dict[str, Any]]:
        """Get todos with a specific tag.

        Note: tag matching is case-sensitive (things.py exact-match semantics).
        If ``tag`` doesn't match any existing tag (including wrong-case
        variants of a real tag), a structured error dict is returned instead
        of a list - see ``_get_tagged_items_sync``.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_tagged_items_sync, tag)

    def _get_tagged_items_sync(self, tag: str) -> Union[List[Dict], Dict[str, Any]]:
        """Synchronous implementation.

        Returns:
            A list of converted todo dicts on success. If ``tag`` is unknown
            to things.py (things.py raises ValueError, e.g. for a wrong-case
            variant of a real tag - tag matching is case-sensitive), returns
            a structured error dict instead:
            ``{'success': False, 'error': 'unknown_tag', 'tag': tag,
            'suggestions': [...]}`` where suggestions are case-insensitive
            title matches from ``things.tags()``.
        """
        try:
            tagged_todos = things.todos(tag=tag)
            return [ToolsHelpers.convert_todo(t) for t in tagged_todos]

        except ValueError as e:
            logger.info(f"Unknown tag '{tag}' in _get_tagged_items_sync: {e}")
            return _build_unknown_tag_error(tag)

        except Exception as e:
            logger.error(f"Error in _get_tagged_items_sync: {e}")
            return []

    async def get_project_headings(self, project_id: str) -> Dict[str, Any]:
        """Get the heading structure of a project, in Things' display order.

        Headings cannot be created, renamed, or deleted via the public Things 3
        APIs (there is no AppleScript heading class; the URL scheme can only
        place to-dos under existing headings, or seed headings at project
        creation time via ``add-project`` ``##`` lines). This is a read-only
        view of the heading structure that already exists in a project.

        Args:
            project_id: UUID of the project to read headings from.

        Returns:
            On success: {'items': [{'uuid', 'title', 'index', 'todoCount'}, ...]}
            in Things' own heading order.
            On failure (unknown id, or id resolves to something other than a
            project): {'error': True, 'error_type': ..., 'message': ...}.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_project_headings_sync, project_id)

    def _get_project_headings_sync(self, project_id: str) -> Dict[str, Any]:
        """Synchronous implementation."""
        try:
            project = things.get(project_id)
            if project is None:
                return {
                    'error': True,
                    'error_type': 'not_found',
                    'message': f"No item found with id: {project_id}",
                }
            if project.get('type') != 'project':
                return {
                    'error': True,
                    'error_type': 'invalid_type',
                    'message': (
                        f"Item {project_id} is a '{project.get('type')}', not a project. "
                        "get_project_headings only accepts project ids."
                    ),
                }

            headings = things.tasks(type='heading', project=project_id) or []

            items = []
            for heading in headings:
                heading_uuid = heading.get('uuid')
                open_todos = things.todos(heading=heading_uuid, status='incomplete') or []
                items.append({
                    'uuid': heading_uuid,
                    'title': heading.get('title'),
                    'index': heading.get('index'),
                    'todoCount': len(open_todos),
                })

            return {'items': items}

        except Exception as e:
            logger.error(f"Error in _get_project_headings_sync: {e}")
            return {
                'error': True,
                'error_type': 'internal_error',
                'message': str(e),
            }

    async def get_todo_by_id(self, todo_id: str) -> Dict[str, Any]:
        """Get a specific Things item by ID.

        Resolves any Things item id, not just to-dos - the returned item's
        `type` field ('to-do', 'heading', or 'project') tells you which kind
        it is. Trashed items also resolve; when trashed, the result includes
        `trashed: True`. Raises ValueError if the id does not exist.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_todo_by_id_sync, todo_id)

    def _get_todo_by_id_sync(self, todo_id: str) -> Dict[str, Any]:
        """Synchronous implementation.

        Uses things.get(uuid), which does a direct-by-id lookup against the
        whole database (any type, including trashed items) instead of a
        linear scan over things.todos() (to-do only, excludes trashed). This
        means projects, headings, and trashed items now resolve instead of
        raising 'Todo not found'.
        """
        try:
            item = things.get(todo_id)

            if item is None:
                raise ValueError(f"Todo not found: {todo_id}")

            item_type = item.get('type', 'to-do')

            if item_type == 'project':
                converted = ToolsHelpers.convert_project(item)
            else:
                # 'to-do' and 'heading' both use convert_todo; convert_todo
                # emits item.get('type', 'to-do') as-is, so a heading row
                # (type == 'heading') is preserved correctly.
                converted = ToolsHelpers.convert_todo(item)

                if item_type == 'to-do':
                    try:
                        items = things.checklist_items(todo_id)
                        converted['checklist'] = [{'title': i['title'], 'status': i['status']} for i in items]
                    except (KeyError, TypeError) as e:
                        logger.warning(f"Could not fetch checklist items for todo {todo_id}: {e}")

            if item.get('trashed'):
                converted['trashed'] = True

            return converted

        except Exception as e:
            logger.error(f"Error in _get_todo_by_id_sync: {e}")
            raise

    async def get_due_in_days(self, days: int, include_overdue: bool = True) -> List[Dict[str, Any]]:
        """Get todos due within specified number of days.

        Optimized to use things.py for 10-100x faster performance.
        Searches entire database, not just specific lists.

        Args:
            days: Number of days ahead to check for due todos.
            include_overdue: If True (default), also include todos whose
                deadline is already in the past, matching the historical
                behavior of this tool. If False, only todos with
                today <= deadline <= target date are returned.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_due_in_days_sync, days, include_overdue)

    def _get_due_in_days_sync(self, days: int, include_overdue: bool = True) -> List[Dict[str, Any]]:
        """Synchronous implementation using things.py with deadline filter."""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            target_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

            # things.py only supports a single comparison operator per date
            # field, so fetch the upper bound from the database and, when
            # overdue items should be excluded, post-filter the lower bound
            # in Python (raw deadline/start_date values are 'YYYY-MM-DD'
            # strings and are lexically comparable).
            due_todos = things.todos(deadline=f'<={target_date}', status='incomplete')
            due_todos = filter_someday_project_tasks(due_todos or [])

            if not include_overdue:
                due_todos = [t for t in due_todos if (t.get('deadline') or '') >= today]

            return [ToolsHelpers.convert_todo(t) for t in due_todos]
        except Exception as e:
            logger.error(f"Error in _get_due_in_days_sync: {e}")
            return []

    async def get_todos_due_in_days(self, days: int, include_overdue: bool = True) -> List[Dict[str, Any]]:
        """Alias for get_due_in_days."""
        return await self.get_due_in_days(days, include_overdue=include_overdue)

    async def get_activating_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos activating within specified number of days.

        Optimized to use things.py for 10-100x faster performance.
        Searches entire database, not just specific lists.

        Only todos whose start date falls within the forward window
        (today <= start_date <= target date) are returned; todos that are
        already active (start_date in the past) are excluded.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_activating_in_days_sync, days)

    def _get_activating_in_days_sync(self, days: int) -> List[Dict[str, Any]]:
        """Synchronous implementation using things.py with start_date filter."""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            target_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

            # things.py only supports a single comparison operator per date
            # field, so fetch the upper bound from the database and
            # post-filter the lower bound in Python (raw start_date values
            # are 'YYYY-MM-DD' strings and are lexically comparable).
            activating_todos = things.todos(start_date=f'<={target_date}', status='incomplete')
            activating_todos = filter_someday_project_tasks(activating_todos or [])
            activating_todos = [t for t in activating_todos if (t.get('start_date') or '') >= today]

            return [ToolsHelpers.convert_todo(t) for t in activating_todos]
        except Exception as e:
            logger.error(f"Error in _get_activating_in_days_sync: {e}")
            return []

    async def get_todos_activating_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Alias for get_activating_in_days."""
        return await self.get_activating_in_days(days)

    async def get_todos_upcoming_in_days(self, days: int, mode: Optional[str] = None):
        """Get todos due or activating within specified number of days."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_todos_upcoming_in_days_sync, days)

    def _get_todos_upcoming_in_days_sync(self, days: int) -> List[Dict[str, Any]]:
        """Synchronous implementation using things.py."""
        try:
            all_todos = things.todos(status='incomplete')
            all_todos = filter_someday_project_tasks(all_todos or [])
            now = datetime.now()
            cutoff_date = now + timedelta(days=days)

            results = []
            for todo in all_todos:
                include_todo = False

                due_date = todo.get('deadline')
                if due_date:
                    try:
                        if isinstance(due_date, str):
                            due_dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                        else:
                            due_dt = due_date

                        if due_dt <= cutoff_date:
                            include_todo = True
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Skipping todo with invalid deadline '{due_date}': {e}")

                start_date = todo.get('start_date')
                if not include_todo and start_date:
                    try:
                        if isinstance(start_date, str):
                            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                        else:
                            start_dt = start_date

                        # Only include if start_date is in the future (not past)
                        if start_dt >= now and start_dt <= cutoff_date:
                            include_todo = True
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Skipping todo with invalid start_date '{start_date}': {e}")

                if include_todo:
                    results.append(ToolsHelpers.convert_todo(todo))

            return results

        except Exception as e:
            logger.error(f"Error in _get_todos_upcoming_in_days_sync: {e}")
            return []

    async def search_advanced(self, **filters) -> List[Dict[str, Any]]:
        """Advanced search with multiple filters.

        Optimized to use things.py for 10-100x faster performance.
        NOW SEARCHES ENTIRE DATABASE including todos inside projects!
        (Previously limited to Today, Upcoming, Anytime, Someday, Inbox lists only)

        Note: the ``tag`` filter is case-sensitive (things.py exact-match
        semantics). An unknown/wrong-case tag returns a single-element list
        containing a structured error dict - see ``_search_advanced_sync``.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_advanced_sync, filters)

    def _search_advanced_sync(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Synchronous implementation using things.py with comprehensive filtering.

        Args:
            filters: Dictionary containing search filters:
                - query: Text to search in title/notes
                - status: 'incomplete', 'completed', or 'canceled'. If omitted (or
                  None), ALL statuses are searched - this differs from things.py's
                  own default of 'incomplete', and from search_todos()'s default.
                - type: 'to-do', 'project', 'heading'
                - tag: Tag name to filter by (case-sensitive - things.py does
                  exact-match tag lookups, so e.g. 'Work' and 'work' are
                  different tags)
                - area: Area UUID to filter by
                - start_date: Start date or operator (e.g., '<=2025-12-31', 'future')
                - deadline: Deadline date or operator (e.g., '<=2025-12-31', 'past')
                - project: Project UUID to filter by
                - limit: Maximum number of results

        Note: filter_someday_project_tasks is NOT applied here - todos that live
        inside a Someday project (hidden from Today/Anytime/Upcoming in the Things
        UI) can still match search_advanced.

        Returns:
            A ``ListWithTotal`` of matching todos with full details - behaves
            exactly like ``List[Dict]`` for all existing callers, but also
            carries the true pre-limit/offset match count on ``.total_count``
            (used by server.py to populate `total`). If ``tag`` is unknown
            to things.py (things.py raises ValueError, e.g. for a wrong-case
            variant of a real tag), returns a plain single-element list
            containing a structured error dict: ``[{'success': False, 'error':
            'unknown_tag', 'tag': tag, 'suggestions': [...]}]`` where
            suggestions are case-insensitive title matches from
            ``things.tags()``. This mirrors the existing structured-error
            convention used above for an invalid ``type`` filter.
        """
        try:
            # Extract filters
            query = filters.get('query', '').lower() if filters.get('query') else None
            status = filters.get('status')
            todo_type = filters.get('type')
            tag = filters.get('tag')
            area = filters.get('area')
            start_date = filters.get('start_date')
            deadline = filters.get('deadline')
            project = filters.get('project')
            limit = filters.get('limit')
            offset = filters.get('offset', 0) or 0

            # Validate type against the values things.py's tasks() accepts.
            valid_types = {'to-do', 'project', 'heading'}
            if todo_type and todo_type not in valid_types:
                logger.error(
                    f"Invalid type '{todo_type}' in search_advanced; "
                    f"must be one of {sorted(valid_types)}"
                )
                return [{
                    'error': True,
                    'error_type': 'invalid_parameter',
                    'message': (
                        f"Invalid type '{todo_type}'. "
                        f"Must be one of: {', '.join(sorted(valid_types))}"
                    )
                }]

            # Build things.py query parameters. Unlike things.py itself (which
            # defaults status to 'incomplete'), search_advanced with no status
            # filter searches ALL statuses - explicitly pass status=None so
            # things.todos()/things.tasks() don't fall back to their own default.
            query_params = {}
            if status:
                query_params['status'] = status
            else:
                query_params['status'] = None
            if todo_type:
                query_params['type'] = todo_type
            if tag:
                query_params['tag'] = tag
            if area:
                query_params['area'] = area
            if start_date:
                query_params['start_date'] = start_date
            if deadline:
                query_params['deadline'] = deadline
            if project:
                query_params['project'] = project

            # Query database - this searches ENTIRE database including projects!
            # things.todos() is a thin wrapper around things.tasks(type="to-do", **kwargs),
            # so when the caller supplies their own `type` we must call things.tasks()
            # directly to avoid a "multiple values for keyword argument 'type'" TypeError.
            try:
                if 'type' in query_params:
                    todos = things.tasks(**query_params)
                else:
                    todos = things.todos(**query_params)
            except ValueError as e:
                if tag:
                    logger.info(f"Unknown tag '{tag}' in _search_advanced_sync: {e}")
                    return [_build_unknown_tag_error(tag)]
                raise

            # Filter by query text if provided (things.py doesn't support text search natively)
            matches = []
            for todo in todos:
                # Apply text search filter
                if query:
                    title = todo.get('title', '').lower()
                    notes = todo.get('notes', '').lower()
                    if query not in title and query not in notes:
                        continue

                matches.append(todo)

            total_count = len(matches)

            # Apply offset then limit, after the full filtered match set is known
            windowed = matches[offset:]
            if limit:
                windowed = windowed[:limit]

            results = [ToolsHelpers.convert_todo(todo) for todo in windowed]

            logger.debug(f"search_advanced found {total_count} matching todos using things.py")
            return ListWithTotal(results, total_count=total_count)

        except Exception as e:
            logger.error(f"Error in _search_advanced_sync: {e}")
            return ListWithTotal([], total_count=0)

    async def get_recent(
        self, period: str,
        status: Optional[str] = None,
        type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recently created items.

        Args:
            period: Time period string (e.g. '3d', '1w', '2m', '1y').
            status: Optional status filter - 'incomplete', 'completed', 'canceled',
                or None (default) to include items of ALL statuses. Unlike
                search_todos()/get_todos(), get_recent defaults to including
                completed and canceled items so "recently created items" isn't
                silently restricted to open to-dos.
            type: Optional type filter - 'to-do', 'project', 'heading', or None
                (default) to include to-dos and projects but NOT headings.
                Headings are never user-facing items in list tools by default
                (epic-wide ruling, hq-f0w.3) - pass type='heading' explicitly
                to fetch recently created headings.

        Note: filter_someday_project_tasks is NOT applied here - items inside a
        Someday project (hidden from Today/Anytime/Upcoming in the Things UI) can
        still appear in get_recent results.
        """
        loop = asyncio.get_event_loop()

        def _get_recent_sync():
            try:
                # Query all statuses/types by default (things.tasks() itself
                # defaults status to 'incomplete', which would silently hide
                # recently completed/canceled items and projects).
                all_items = things.tasks(status=status, type=type)
                days = ToolsHelpers.parse_period_to_days(period)
                cutoff_date = datetime.now() - timedelta(days=days)

                # When the caller didn't explicitly ask for headings, drop
                # them - list tools never return headings by default
                # (epic-wide ruling, hq-f0w.3); they're not user-facing items.
                include_headings = (type == 'heading')

                results = []
                for item in all_items:
                    if not include_headings and item.get('type') == 'heading':
                        continue

                    created_date = item.get('created')
                    if created_date:
                        try:
                            if isinstance(created_date, str):
                                created_dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                            else:
                                created_dt = created_date

                            if created_dt >= cutoff_date:
                                results.append(ToolsHelpers.convert_todo(item))
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Skipping item with invalid created date '{created_date}': {e}")

                return results

            except Exception as e:
                logger.error(f"Error in _get_recent_sync: {e}")
                return []

        return await loop.run_in_executor(None, _get_recent_sync)

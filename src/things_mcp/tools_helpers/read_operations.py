"""Read operations for Things 3 - uses things.py for fast direct database access."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import things

from ..services.applescript_manager import AppleScriptManager
from ..response_optimizer import ResponseOptimizer
from .helpers import ToolsHelpers

logger = logging.getLogger(__name__)


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

    async def search_todos(self, query: str, limit: Optional[int] = None) -> List[Dict]:
        """Search todos using things.py."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: Optional[int] = None) -> List[Dict]:
        """Synchronous search implementation."""
        try:
            all_todos = things.todos()
            query_lower = query.lower()

            results = []
            for todo in all_todos:
                title = todo.get('title', '').lower()
                notes = todo.get('notes', '').lower()

                if query_lower in title or query_lower in notes:
                    results.append(ToolsHelpers.convert_todo(todo))

                    if limit and len(results) >= limit:
                        break

            return results

        except Exception as e:
            logger.error(f"Error in _search_sync: {e}")
            return []

    async def get_inbox(self, limit: Optional[int] = None) -> List[Dict]:
        """Get todos from Inbox."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_inbox_sync, limit)

    def _get_inbox_sync(self, limit: Optional[int] = None) -> List[Dict]:
        """Synchronous implementation."""
        try:
            inbox_todos = things.inbox()

            result = []
            for todo in inbox_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_inbox_sync: {e}")
            return []

    async def get_today(self, limit: Optional[int] = None) -> List[Dict]:
        """Get todos due today."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_today_sync, limit)

    def _get_today_sync(self, limit: Optional[int] = None) -> List[Dict]:
        """Synchronous implementation."""
        try:
            today_todos = things.today()

            result = []
            for todo in today_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_today_sync: {e}")
            return []

    async def get_upcoming(self, limit: Optional[int] = None) -> List[Dict]:
        """Get upcoming todos."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_upcoming_sync, limit)

    def _get_upcoming_sync(self, limit: Optional[int] = None) -> List[Dict]:
        """Synchronous implementation."""
        try:
            upcoming_todos = things.upcoming()

            result = []
            for todo in upcoming_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_upcoming_sync: {e}")
            return []

    async def get_anytime(self, limit: Optional[int] = None) -> List[Dict]:
        """Get todos from Anytime list."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_anytime_sync, limit)

    def _get_anytime_sync(self, limit: Optional[int] = None) -> List[Dict]:
        """Synchronous implementation."""
        try:
            anytime_todos = things.anytime()

            result = []
            for todo in anytime_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_anytime_sync: {e}")
            return []

    async def get_someday(self, limit: Optional[int] = None) -> List[Dict]:
        """Get todos from Someday list."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_someday_sync, limit)

    def _get_someday_sync(self, limit: Optional[int] = None) -> List[Dict]:
        """Synchronous implementation."""
        try:
            someday_todos = things.someday()

            result = []
            for todo in someday_todos:
                result.append(ToolsHelpers.convert_todo(todo))

                if limit and len(result) >= limit:
                    break

            return result

        except Exception as e:
            logger.error(f"Error in _get_someday_sync: {e}")
            return []

    async def get_logbook(self, limit: int = 50, period: str = "7d") -> List[Dict]:
        """Get completed todos from Logbook."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_logbook_sync, limit, period)

    def _get_logbook_sync(self, limit: int = 50, period: str = "7d") -> List[Dict]:
        """Synchronous implementation."""
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
                    except Exception:
                        pass

            # Sort by completion date (most recent first)
            result.sort(key=lambda x: x.get('_sort_date', datetime.min), reverse=True)

            # Remove temporary sort key
            for todo in result:
                todo.pop('_sort_date', None)

            # Apply limit after sorting
            return result[:limit]

        except Exception as e:
            logger.error(f"Error in _get_logbook_sync: {e}")
            return []

    async def get_trash(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get trashed todos with pagination."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_trash_sync, limit, offset)

    def _get_trash_sync(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Synchronous implementation."""
        try:
            trash_data = things.trash()

            # Handle different return types from things.trash()
            if hasattr(trash_data, '__iter__') and not isinstance(trash_data, (list, dict)):
                trash_data = list(trash_data)
            if isinstance(trash_data, dict):
                trash_data = [trash_data]

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

    async def get_tagged_items(self, tag: str) -> List[Dict]:
        """Get todos with a specific tag."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_tagged_items_sync, tag)

    def _get_tagged_items_sync(self, tag: str) -> List[Dict]:
        """Synchronous implementation."""
        try:
            tagged_todos = things.todos(tag=tag)
            return [ToolsHelpers.convert_todo(t) for t in tagged_todos]

        except Exception as e:
            logger.error(f"Error in _get_tagged_items_sync: {e}")
            return []

    async def get_todo_by_id(self, todo_id: str) -> Dict[str, Any]:
        """Get a specific todo by ID."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_todo_by_id_sync, todo_id)

    def _get_todo_by_id_sync(self, todo_id: str) -> Dict[str, Any]:
        """Synchronous implementation."""
        try:
            all_todos = things.todos()

            for todo in all_todos:
                if todo.get('uuid') == todo_id:
                    converted = ToolsHelpers.convert_todo(todo)

                    try:
                        items = things.checklist_items(todo_id)
                        converted['checklist'] = [{'title': i['title'], 'status': i['status']} for i in items]
                    except Exception:
                        pass

                    return converted

            raise ValueError(f"Todo not found: {todo_id}")

        except Exception as e:
            logger.error(f"Error in _get_todo_by_id_sync: {e}")
            raise

    async def get_due_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos due within specified number of days.

        Optimized to use things.py for 10-100x faster performance.
        Searches entire database, not just specific lists.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_due_in_days_sync, days)

    def _get_due_in_days_sync(self, days: int) -> List[Dict[str, Any]]:
        """Synchronous implementation using things.py with deadline filter."""
        try:
            target_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

            # Use things.py with deadline operator for fast database query
            due_todos = things.todos(deadline=f'<={target_date}', status='incomplete')

            return [ToolsHelpers.convert_todo(t) for t in due_todos]
        except Exception as e:
            logger.error(f"Error in _get_due_in_days_sync: {e}")
            return []

    async def get_todos_due_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Alias for get_due_in_days."""
        return await self.get_due_in_days(days)

    async def get_activating_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos activating within specified number of days.

        Optimized to use things.py for 10-100x faster performance.
        Searches entire database, not just specific lists.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_activating_in_days_sync, days)

    def _get_activating_in_days_sync(self, days: int) -> List[Dict[str, Any]]:
        """Synchronous implementation using things.py with start_date filter."""
        try:
            target_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

            # Use things.py with start_date operator for fast database query
            activating_todos = things.todos(start_date=f'<={target_date}', status='incomplete')

            return [ToolsHelpers.convert_todo(t) for t in activating_todos]
        except Exception as e:
            logger.error(f"Error in _get_activating_in_days_sync: {e}")
            return []

    async def get_todos_activating_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Alias for get_activating_in_days."""
        return await self.get_activating_in_days(days)

    async def get_upcoming_in_days(self, days: int, mode: Optional[str] = None):
        """Get todos upcoming within specified number of days."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_upcoming_in_days_sync, days)

    def _get_upcoming_in_days_sync(self, days: int) -> List[Dict[str, Any]]:
        """Synchronous implementation using things.py."""
        try:
            all_todos = things.todos(status='incomplete')
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
                    except Exception:
                        pass

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
                    except Exception:
                        pass

                if include_todo:
                    results.append(ToolsHelpers.convert_todo(todo))

            return results

        except Exception as e:
            logger.error(f"Error in _get_upcoming_in_days_sync: {e}")
            return []

    async def get_todos_upcoming_in_days(self, days: int, mode: Optional[str] = None):
        """Alias for get_upcoming_in_days."""
        return await self.get_upcoming_in_days(days, mode)

    async def search_advanced(self, **filters) -> List[Dict[str, Any]]:
        """Advanced search with multiple filters.

        Optimized to use things.py for 10-100x faster performance.
        NOW SEARCHES ENTIRE DATABASE including todos inside projects!
        (Previously limited to Today, Upcoming, Anytime, Someday, Inbox lists only)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_advanced_sync, filters)

    def _search_advanced_sync(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Synchronous implementation using things.py with comprehensive filtering.

        Args:
            filters: Dictionary containing search filters:
                - query: Text to search in title/notes
                - status: 'incomplete', 'completed', 'canceled', or None for all
                - type: 'to-do', 'project', 'heading'
                - tag: Tag name to filter by
                - area: Area UUID to filter by
                - start_date: Start date or operator (e.g., '<=2025-12-31', 'future')
                - deadline: Deadline date or operator (e.g., '<=2025-12-31', 'past')
                - project: Project UUID to filter by
                - limit: Maximum number of results

        Returns:
            List of matching todos with full details
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

            # Build things.py query parameters
            query_params = {}
            if status:
                query_params['status'] = status
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
            todos = things.todos(**query_params)

            # Filter by query text if provided (things.py doesn't support text search natively)
            results = []
            for todo in todos:
                # Apply text search filter
                if query:
                    title = todo.get('title', '').lower()
                    notes = todo.get('notes', '').lower()
                    if query not in title and query not in notes:
                        continue

                # Convert and add to results
                results.append(ToolsHelpers.convert_todo(todo))

                # Apply limit
                if limit and len(results) >= limit:
                    break

            logger.debug(f"search_advanced found {len(results)} todos using things.py")
            return results

        except Exception as e:
            logger.error(f"Error in _search_advanced_sync: {e}")
            return []

    async def get_recent(self, period: str) -> List[Dict[str, Any]]:
        """Get recently created items."""
        loop = asyncio.get_event_loop()

        def _get_recent_sync():
            try:
                all_todos = things.todos()
                days = ToolsHelpers.parse_period_to_days(period)
                cutoff_date = datetime.now() - timedelta(days=days)

                results = []
                for todo in all_todos:
                    created_date = todo.get('created')
                    if created_date:
                        try:
                            if isinstance(created_date, str):
                                created_dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                            else:
                                created_dt = created_date

                            if created_dt >= cutoff_date:
                                results.append(ToolsHelpers.convert_todo(todo))
                        except Exception:
                            pass

                return results

            except Exception as e:
                logger.error(f"Error in _get_recent_sync: {e}")
                return []

        return await loop.run_in_executor(None, _get_recent_sync)

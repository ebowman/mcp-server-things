"""Natural language query engine for Things 3 MCP server."""

from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import re
import calendar


class QueryType(Enum):
    """Types of queries the engine can handle."""
    DUE_IN_PERIOD = "due_in_period"
    COMPLETED_IN_PERIOD = "completed_in_period"
    ACTIVE_IN_PERIOD = "active_in_period"
    OVERDUE = "overdue"
    UPCOMING = "upcoming"
    STATS = "stats"


class NaturalLanguageQueryEngine:
    """Process natural language queries for Things 3 tasks."""
    
    def __init__(self, tools):
        """Initialize with Things tools instance."""
        self.tools = tools
        
        # Define relative date patterns
        self.relative_patterns = {
            r"next (\d+) days?": self._parse_next_days,
            r"next week": lambda: (datetime.now(), datetime.now() + timedelta(days=7)),
            r"next month": lambda: self._get_next_month(),
            r"this week": lambda: self._get_this_week(),
            r"this month": lambda: self._get_this_month(),
            r"last (\d+) days?": self._parse_last_days,
            r"last week": lambda: self._get_last_week(),
            r"last month": lambda: self._get_last_month(),
            r"today": lambda: (datetime.now().replace(hour=0, minute=0, second=0), 
                               datetime.now().replace(hour=23, minute=59, second=59)),
            r"tomorrow": lambda: self._get_tomorrow(),
            r"yesterday": lambda: self._get_yesterday(),
        }
        
    async def query(self, natural_query: str) -> Dict[str, Any]:
        """Process a natural language query.
        
        Examples:
            - "what's due next week"
            - "what did I complete last month"
            - "show me overdue tasks"
            - "what's active this week"
        """
        query_lower = natural_query.lower()
        
        # Detect query type
        if any(word in query_lower for word in ["due", "deadline", "scheduled"]):
            if "overdue" in query_lower:
                return await self._query_overdue()
            else:
                return await self._query_due_in_period(query_lower)
                
        elif any(word in query_lower for word in ["complete", "finish", "done"]):
            return await self._query_completed_in_period(query_lower)
            
        elif any(word in query_lower for word in ["active", "upcoming", "pending"]):
            return await self._query_active_in_period(query_lower)
            
        elif any(word in query_lower for word in ["stats", "summary", "analytics"]):
            return await self._query_stats(query_lower)
            
        else:
            return {
                "success": False,
                "error": "Query not understood",
                "suggestion": "Try queries like: 'what's due next week', 'what did I complete last month', 'show me overdue tasks'"
            }
    
    async def _query_due_in_period(self, query: str) -> Dict[str, Any]:
        """Query tasks due in a specific period."""
        start_date, end_date = self._extract_date_range(query)
        
        if not start_date or not end_date:
            return {
                "success": False,
                "error": "Could not parse date range",
                "query": query
            }
        
        # Get all todos - ThingsTools doesn't have mode parameter
        todos = await self.tools.get_todos()
        
        # Handle both list and dict responses
        if isinstance(todos, dict):
            # If it's from the MCP layer with data structure
            todos = todos.get('data', todos.get('todos', []))
        elif not isinstance(todos, list):
            todos = []
        
        # Filter by due date, deadline, or scheduled date
        due_todos = []
        for todo in todos:
            # Check multiple date fields that might indicate when something is due
            date_to_check = None
            date_field = None
            
            # Priority order: deadline > due_date > start_date > activation_date
            if todo.get("deadline"):
                date_to_check = self._parse_date(todo["deadline"])
                date_field = "deadline"
            elif todo.get("due_date"):
                date_to_check = self._parse_date(todo["due_date"])
                date_field = "due_date"
            elif todo.get("start_date"):
                date_to_check = self._parse_date(todo["start_date"])
                date_field = "start_date"
            elif todo.get("activation_date"):
                date_to_check = self._parse_date(todo["activation_date"])
                date_field = "activation_date"
            
            if date_to_check and start_date <= date_to_check <= end_date:
                todo["_date_field_used"] = date_field
                todo["_parsed_date"] = date_to_check.isoformat()
                due_todos.append(todo)
        
        # Sort by the date we found
        due_todos.sort(key=lambda x: x.get("_parsed_date", ""))
        
        return {
            "success": True,
            "query_type": "due_in_period",
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "description": self._describe_period(start_date, end_date)
            },
            "count": len(due_todos),
            "todos": due_todos,
            "summary": self._generate_summary(due_todos, "due")
        }
    
    async def _query_completed_in_period(self, query: str) -> Dict[str, Any]:
        """Query completed tasks in a specific period."""
        start_date, end_date = self._extract_date_range(query)
        
        if not start_date or not end_date:
            # Default to last 30 days if no period specified
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
        
        # Calculate the period in days
        days_diff = (end_date - start_date).days + 1
        
        # Get logbook entries for the period
        from .tools import ThingsTools
        if isinstance(self.tools, ThingsTools):
            # Use the logbook with appropriate period
            period_str = f"{days_diff}d"
            completed = await self.tools.get_logbook(period=period_str, limit=500)
        else:
            # Fallback to search
            completed = []
        
        # Filter by completion date if we have detailed data
        filtered_completed = []
        for todo in completed:
            completion_date = todo.get("completion_date")
            if completion_date:
                comp_date = self._parse_date(completion_date)
                if comp_date and start_date <= comp_date <= end_date:
                    filtered_completed.append(todo)
            else:
                # If no completion date, include it (logbook should only have completed)
                filtered_completed.append(todo)
        
        return {
            "success": True,
            "query_type": "completed_in_period",
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "description": self._describe_period(start_date, end_date)
            },
            "count": len(filtered_completed),
            "todos": filtered_completed,
            "summary": self._generate_summary(filtered_completed, "completed"),
            "statistics": self._calculate_completion_stats(filtered_completed)
        }
    
    async def _query_active_in_period(self, query: str) -> Dict[str, Any]:
        """Query active/upcoming tasks in a specific period."""
        start_date, end_date = self._extract_date_range(query)
        
        if not start_date or not end_date:
            # Default to next 7 days
            start_date = datetime.now()
            end_date = start_date + timedelta(days=7)
        
        # Get upcoming todos
        upcoming = await self.tools.get_upcoming()
        
        # Filter by activation/start date
        active_todos = []
        for todo in upcoming:
            # Check start date or activation date
            start = todo.get("start_date") or todo.get("activation_date")
            if start:
                task_date = self._parse_date(start)
                if task_date and start_date <= task_date <= end_date:
                    active_todos.append(todo)
        
        return {
            "success": True,
            "query_type": "active_in_period",
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "description": self._describe_period(start_date, end_date)
            },
            "count": len(active_todos),
            "todos": active_todos,
            "summary": self._generate_summary(active_todos, "active")
        }
    
    async def _query_overdue(self) -> Dict[str, Any]:
        """Query overdue tasks."""
        today = datetime.now().replace(hour=0, minute=0, second=0)
        
        # Get all todos - ThingsTools doesn't have mode parameter
        todos = await self.tools.get_todos()
        
        # Handle both list and dict responses
        if isinstance(todos, dict):
            # If it's from the MCP layer with data structure
            todos = todos.get('data', todos.get('todos', []))
        elif not isinstance(todos, list):
            todos = []
        
        # Filter overdue
        overdue_todos = []
        for todo in todos:
            if todo.get("status") == "open":
                # Check for any date field that might indicate overdue
                date_to_check = None
                date_field = None
                
                # Priority: deadline > due_date
                if todo.get("deadline"):
                    date_to_check = self._parse_date(todo["deadline"])
                    date_field = "deadline"
                elif todo.get("due_date"):
                    date_to_check = self._parse_date(todo["due_date"])
                    date_field = "due_date"
                
                if date_to_check and date_to_check < today:
                    # Calculate days overdue
                    days_overdue = (today - date_to_check).days
                    todo["days_overdue"] = days_overdue
                    todo["_date_field_used"] = date_field
                    overdue_todos.append(todo)
        
        # Sort by how overdue they are
        overdue_todos.sort(key=lambda x: x.get("days_overdue", 0), reverse=True)
        
        return {
            "success": True,
            "query_type": "overdue",
            "as_of": today.isoformat(),
            "count": len(overdue_todos),
            "todos": overdue_todos,
            "summary": self._generate_overdue_summary(overdue_todos)
        }
    
    async def _query_stats(self, query: str) -> Dict[str, Any]:
        """Generate statistics for a period."""
        start_date, end_date = self._extract_date_range(query)
        
        if not start_date or not end_date:
            # Default to last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
        
        # Gather data
        todos = await self.tools.get_todos()
        projects = await self.tools.get_projects()
        
        # Calculate statistics
        stats = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "description": self._describe_period(start_date, end_date)
            },
            "totals": {
                "todos": len(todos),
                "projects": len(projects),
                "open_todos": len([t for t in todos if t.get("status") == "open"]),
            },
            "breakdown": {
                "by_status": self._group_by_field(todos, "status"),
                "by_project": self._group_by_field(todos, "project"),
                "by_area": self._group_by_field(todos, "area"),
            }
        }
        
        return {
            "success": True,
            "query_type": "stats",
            "statistics": stats
        }
    
    def _extract_date_range(self, query: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Extract date range from natural language."""
        for pattern, handler in self.relative_patterns.items():
            match = re.search(pattern, query)
            if match:
                if callable(handler):
                    if match.groups():
                        return handler(match.group(1))
                    else:
                        return handler()
        
        return None, None
    
    def _parse_next_days(self, days_str: str) -> Tuple[datetime, datetime]:
        """Parse 'next N days'."""
        days = int(days_str)
        start = datetime.now().replace(hour=0, minute=0, second=0)
        end = start + timedelta(days=days)
        return start, end
    
    def _parse_last_days(self, days_str: str) -> Tuple[datetime, datetime]:
        """Parse 'last N days'."""
        days = int(days_str)
        end = datetime.now().replace(hour=23, minute=59, second=59)
        start = end - timedelta(days=days)
        return start, end
    
    def _get_this_week(self) -> Tuple[datetime, datetime]:
        """Get this week's date range (Monday to Sunday)."""
        today = datetime.now()
        start = today - timedelta(days=today.weekday())  # Monday
        end = start + timedelta(days=6)  # Sunday
        return start.replace(hour=0, minute=0), end.replace(hour=23, minute=59)
    
    def _get_last_week(self) -> Tuple[datetime, datetime]:
        """Get last week's date range."""
        this_week_start, _ = self._get_this_week()
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(seconds=1)
        return start, end
    
    def _get_this_month(self) -> Tuple[datetime, datetime]:
        """Get this month's date range."""
        today = datetime.now()
        start = today.replace(day=1, hour=0, minute=0, second=0)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = today.replace(day=last_day, hour=23, minute=59, second=59)
        return start, end
    
    def _get_last_month(self) -> Tuple[datetime, datetime]:
        """Get last month's date range."""
        today = datetime.now()
        first_of_month = today.replace(day=1)
        last_of_prev_month = first_of_month - timedelta(days=1)
        start = last_of_prev_month.replace(day=1, hour=0, minute=0, second=0)
        end = last_of_prev_month.replace(hour=23, minute=59, second=59)
        return start, end
    
    def _get_next_month(self) -> Tuple[datetime, datetime]:
        """Get next month's date range."""
        today = datetime.now()
        if today.month == 12:
            start = today.replace(year=today.year + 1, month=1, day=1, hour=0, minute=0, second=0)
        else:
            start = today.replace(month=today.month + 1, day=1, hour=0, minute=0, second=0)
        
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = start.replace(day=last_day, hour=23, minute=59, second=59)
        return start, end
    
    def _get_tomorrow(self) -> Tuple[datetime, datetime]:
        """Get tomorrow's date range."""
        tomorrow = datetime.now() + timedelta(days=1)
        start = tomorrow.replace(hour=0, minute=0, second=0)
        end = tomorrow.replace(hour=23, minute=59, second=59)
        return start, end
    
    def _get_yesterday(self) -> Tuple[datetime, datetime]:
        """Get yesterday's date range."""
        yesterday = datetime.now() - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0)
        end = yesterday.replace(hour=23, minute=59, second=59)
        return start, end
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats."""
        if not date_str:
            return None
            
        # Try ISO format first
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            pass
        
        # Try other formats
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except:
                continue
        
        return None
    
    def _describe_period(self, start: datetime, end: datetime) -> str:
        """Generate human-readable period description."""
        days = (end - start).days + 1
        
        if days == 1:
            return start.strftime("%B %d, %Y")
        elif days <= 7:
            return f"{start.strftime('%B %d')} - {end.strftime('%B %d, %Y')}"
        elif days <= 31:
            return f"{days} days ({start.strftime('%b %d')} - {end.strftime('%b %d, %Y')})"
        else:
            months = days // 30
            return f"~{months} months ({start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')})"
    
    def _generate_summary(self, todos: List[Dict], todo_type: str) -> str:
        """Generate a summary of the todos."""
        if not todos:
            return f"No {todo_type} tasks found in this period"
        
        # Group by project
        by_project = {}
        no_project = []
        
        for todo in todos:
            project = todo.get("project")
            if project:
                if project not in by_project:
                    by_project[project] = []
                by_project[project].append(todo)
            else:
                no_project.append(todo)
        
        summary_parts = [f"{len(todos)} {todo_type} task(s)"]
        
        if by_project:
            summary_parts.append(f"across {len(by_project)} project(s)")
        
        if no_project:
            summary_parts.append(f"{len(no_project)} standalone task(s)")
        
        return " - ".join(summary_parts)
    
    def _generate_overdue_summary(self, todos: List[Dict]) -> str:
        """Generate summary for overdue tasks."""
        if not todos:
            return "No overdue tasks! 🎉"
        
        # Group by severity
        critical = [t for t in todos if t.get("days_overdue", 0) > 7]
        warning = [t for t in todos if 3 < t.get("days_overdue", 0) <= 7]
        recent = [t for t in todos if t.get("days_overdue", 0) <= 3]
        
        parts = []
        if critical:
            parts.append(f"{len(critical)} critical (>7 days)")
        if warning:
            parts.append(f"{len(warning)} warning (4-7 days)")
        if recent:
            parts.append(f"{len(recent)} recent (≤3 days)")
        
        return f"{len(todos)} overdue: " + ", ".join(parts)
    
    def _calculate_completion_stats(self, todos: List[Dict]) -> Dict[str, Any]:
        """Calculate completion statistics."""
        if not todos:
            return {"average_per_day": 0, "by_weekday": {}, "by_project": {}}
        
        # Group by date
        by_date = {}
        by_weekday = {i: 0 for i in range(7)}  # Monday=0, Sunday=6
        by_project = {}
        
        for todo in todos:
            comp_date = self._parse_date(todo.get("completion_date", ""))
            if comp_date:
                date_key = comp_date.date().isoformat()
                by_date[date_key] = by_date.get(date_key, 0) + 1
                by_weekday[comp_date.weekday()] += 1
            
            project = todo.get("project", "No Project")
            by_project[project] = by_project.get(project, 0) + 1
        
        # Calculate average
        if by_date:
            avg_per_day = len(todos) / len(by_date)
        else:
            avg_per_day = 0
        
        # Convert weekday numbers to names
        weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        by_weekday_named = {weekday_names[i]: count for i, count in by_weekday.items()}
        
        return {
            "average_per_day": round(avg_per_day, 1),
            "by_weekday": by_weekday_named,
            "by_project": by_project,
            "most_productive_day": max(by_weekday_named, key=by_weekday_named.get) if any(by_weekday_named.values()) else None
        }
    
    def _group_by_field(self, items: List[Dict], field: str) -> Dict[str, int]:
        """Group items by a field and count."""
        grouped = {}
        for item in items:
            value = item.get(field, "Unknown")
            grouped[value] = grouped.get(value, 0) + 1
        return grouped
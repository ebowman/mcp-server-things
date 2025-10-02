"""Simplified hybrid implementation: things.py for reads, AppleScript for writes."""

import logging
from typing import Any, Dict, List, Optional, Union

# Import things.py for backwards compatibility with tests
import things

from .services.applescript_manager import AppleScriptManager
from .pure_applescript_scheduler import PureAppleScriptScheduler
from .services.validation_service import ValidationService
from .services.tag_service import TagValidationService
from .move_operations import MoveOperationsTools
from .config import ThingsMCPConfig
from .response_optimizer import ResponseOptimizer, FieldOptimizationPolicy
from .operation_queue import get_operation_queue, Priority
from .tools_helpers import ToolsHelpers, ReadOperations, WriteOperations, BulkOperations

logger = logging.getLogger(__name__)


class ThingsTools:
    """
    Main Things 3 tools implementation with hybrid approach:
    - Read operations via things.py (fast direct database access)
    - Write operations via AppleScript (full control and reliability)
    - Tag validation and policy enforcement

    This class acts as a facade, delegating to specialized operation modules.
    """

    def __init__(self, applescript_manager: AppleScriptManager, config: Optional[ThingsMCPConfig] = None):
        """Initialize with AppleScript manager and optional configuration.

        Args:
            applescript_manager: AppleScript manager instance for write operations
            config: Optional configuration for tag validation and policies
        """
        self.applescript = applescript_manager
        self.config = config
        self.reliable_scheduler = PureAppleScriptScheduler(applescript_manager)

        # Initialize validation service and advanced move operations for writes
        self.validation_service = ValidationService(applescript_manager)
        self.move_operations = MoveOperationsTools(applescript_manager, self.validation_service)

        # Initialize response optimizer
        self.response_optimizer = ResponseOptimizer(FieldOptimizationPolicy.STANDARD)

        # Initialize tag validation service if config is provided
        self.tag_validation_service = None
        if config:
            self.tag_validation_service = TagValidationService(applescript_manager, config)
            logger.info("Things tools initialized with tag validation service")
        else:
            logger.info("Things tools initialized without tag validation (backward compatibility mode)")

        # Initialize operation modules (Facade Pattern)
        self.read_ops = ReadOperations(
            applescript_manager=applescript_manager,
            response_optimizer=self.response_optimizer
        )

        self.write_ops = WriteOperations(
            applescript_manager=applescript_manager,
            scheduler=self.reliable_scheduler,
            validation_service=self.validation_service,
            move_operations=self.move_operations,
            tag_validation_service=self.tag_validation_service
        )

        self.bulk_ops = BulkOperations(
            applescript_manager=applescript_manager,
            scheduler=self.reliable_scheduler,
            tag_validation_service=self.tag_validation_service
        )

        logger.info("Things tools initialized - reads via things.py, writes via AppleScript")

    # ========== READ OPERATIONS (delegate to ReadOperations) ==========

    async def get_todos(self, project_uuid: Optional[str] = None, include_items: Optional[bool] = None, status: Optional[str] = 'incomplete') -> List[Dict]:
        """Get todos with hybrid approach: AppleScript for projects, things.py otherwise."""
        return await self.read_ops.get_todos(project_uuid=project_uuid, include_items=include_items, status=status)

    async def get_projects(self, include_items: bool = False) -> List[Dict]:
        """Get all projects directly from database."""
        return await self.read_ops.get_projects(include_items=include_items)

    async def get_areas(self, include_items: bool = False) -> List[Dict]:
        """Get all areas directly from database."""
        return await self.read_ops.get_areas(include_items=include_items)

    async def get_tags(self, include_items: bool = False) -> List[Dict]:
        """Get all tags with counts or items - super fast with things.py."""
        return await self.read_ops.get_tags(include_items=include_items)

    async def search_todos(self, query: str, limit: Optional[int] = None) -> List[Dict]:
        """Search todos directly in database with optional limit."""
        return await self.read_ops.search_todos(query=query, limit=limit)

    async def get_inbox(self, limit: Optional[int] = None) -> List[Dict]:
        """Get inbox items directly from database."""
        return await self.read_ops.get_inbox(limit=limit)

    async def get_today(self, limit: Optional[int] = None) -> List[Dict]:
        """Get today items directly from database."""
        return await self.read_ops.get_today(limit=limit)

    async def get_upcoming(self, limit: Optional[int] = None) -> List[Dict]:
        """Get upcoming items directly from database."""
        return await self.read_ops.get_upcoming(limit=limit)

    async def get_anytime(self, limit: Optional[int] = None) -> List[Dict]:
        """Get anytime items directly from database."""
        return await self.read_ops.get_anytime(limit=limit)

    async def get_someday(self, limit: Optional[int] = None) -> List[Dict]:
        """Get someday items directly from database."""
        return await self.read_ops.get_someday(limit=limit)

    async def get_logbook(self, limit: int = 50, period: str = "7d") -> List[Dict]:
        """Get completed items directly from database."""
        return await self.read_ops.get_logbook(limit=limit, period=period)

    async def get_trash(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get trashed items directly from database with pagination."""
        return await self.read_ops.get_trash(limit=limit, offset=offset)

    async def get_tagged_items(self, tag: str) -> List[Dict]:
        """Get items with a specific tag directly from database."""
        return await self.read_ops.get_tagged_items(tag=tag)

    async def get_todo_by_id(self, todo_id: str) -> Dict[str, Any]:
        """Get a specific todo by ID directly from database."""
        return await self.read_ops.get_todo_by_id(todo_id=todo_id)

    async def get_due_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos due within specified days."""
        return await self.read_ops.get_due_in_days(days=days)

    async def get_todos_due_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos due within specified days."""
        return await self.read_ops.get_todos_due_in_days(days=days)

    async def get_activating_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos activating within specified days."""
        return await self.read_ops.get_activating_in_days(days=days)

    async def get_todos_activating_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos activating within specified days."""
        return await self.read_ops.get_todos_activating_in_days(days=days)

    async def get_upcoming_in_days(self, days: int, mode: Optional[str] = None) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Get todos upcoming within specified days using things.py."""
        return await self.read_ops.get_upcoming_in_days(days=days, mode=mode)

    async def get_todos_upcoming_in_days(self, days: int, mode: Optional[str] = None) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Alias for get_upcoming_in_days for compatibility."""
        return await self.read_ops.get_todos_upcoming_in_days(days=days, mode=mode)

    async def search_advanced(self, **filters) -> List[Dict[str, Any]]:
        """Advanced search - delegate to AppleScript scheduler with limit support."""
        return await self.read_ops.search_advanced(**filters)

    async def get_recent(self, period: str) -> List[Dict[str, Any]]:
        """Get recent items."""
        return await self.read_ops.get_recent(period=period)

    # ========== WRITE OPERATIONS (delegate to WriteOperations) ==========

    async def add_todo(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new todo using AppleScript (write operation)."""
        return await self.write_ops.add_todo(title=title, **kwargs)

    async def update_todo(self, todo_id: str, **kwargs) -> Dict[str, Any]:
        """Update a todo using AppleScript (write operation)."""
        return await self.write_ops.update_todo(todo_id=todo_id, **kwargs)

    async def delete_todo(self, todo_id: str) -> Dict[str, Any]:
        """Delete a todo using AppleScript (write operation)."""
        return await self.write_ops.delete_todo(todo_id=todo_id)

    async def add_project(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new project using AppleScript (write operation)."""
        return await self.write_ops.add_project(title=title, **kwargs)

    async def update_project(self, project_id: str, **kwargs) -> Dict[str, Any]:
        """Update a project using AppleScript (write operation)."""
        return await self.write_ops.update_project(project_id=project_id, **kwargs)

    async def move_record(self, todo_id: str, destination_list: str) -> Dict[str, Any]:
        """Move a todo using AppleScript (write operation)."""
        return await self.write_ops.move_record(todo_id=todo_id, destination_list=destination_list)

    async def add_tags(self, todo_id: str, tags: List[str]) -> Dict[str, Any]:
        """Add tags to a todo using AppleScript (write operation)."""
        return await self.write_ops.add_tags(todo_id=todo_id, tags=tags)

    async def remove_tags(self, todo_id: str, tags: List[str]) -> Dict[str, Any]:
        """Remove tags from a todo using AppleScript (write operation)."""
        return await self.write_ops.remove_tags(todo_id=todo_id, tags=tags)

    # ========== BULK OPERATIONS (delegate to BulkOperations) ==========

    async def bulk_update_todos(self, todo_ids: List[str], **kwargs) -> Dict[str, Any]:
        """Update multiple todos with the same changes in a single operation."""
        return await self.bulk_ops.bulk_update_todos(todo_ids=todo_ids, **kwargs)

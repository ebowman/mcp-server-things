"""Write operations for Things 3 - uses AppleScript for reliable writes."""

import logging
from typing import Any, Dict, List, Optional

from ..services.applescript_manager import AppleScriptManager
from ..pure_applescript_scheduler import PureAppleScriptScheduler
from ..services.validation_service import ValidationService
from ..services.tag_service import TagValidationService
from ..move_operations import MoveOperationsTools
from ..parameter_validator import ParameterValidator, ValidationError, create_validation_error_response
from .helpers import ToolsHelpers

logger = logging.getLogger(__name__)


class WriteOperations:
    """Write operations using AppleScript for reliable writes."""

    def __init__(self, applescript_manager: AppleScriptManager, 
                 scheduler: PureAppleScriptScheduler,
                 validation_service: ValidationService,
                 move_operations: MoveOperationsTools,
                 tag_validation_service: Optional[TagValidationService] = None):
        """Initialize write operations.

        Args:
            applescript_manager: AppleScript manager for direct execution
            scheduler: Scheduler for todo/project operations
            validation_service: Validation service
            move_operations: Move operations handler
            tag_validation_service: Optional tag validation service
        """
        self.applescript = applescript_manager
        self.reliable_scheduler = scheduler
        self.validation_service = validation_service
        self.move_operations = move_operations
        self.tag_validation_service = tag_validation_service

    async def _validate_tags_with_policy(self, tags: List[str]) -> Dict[str, List[str]]:
        """Validate tags using policy-aware service if available."""
        if self.tag_validation_service:
            result = await self.tag_validation_service.validate_and_filter_tags(tags)
            return {
                'created': result.created_tags,
                'existing': result.valid_tags,
                'filtered': result.filtered_tags,
                'warnings': result.warnings
            }
        else:
            return {
                'created': [],
                'existing': tags,
                'filtered': [],
                'warnings': []
            }

    async def add_todo(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new todo using AppleScript."""
        try:
            tags = kwargs.get('tags', [])
            tag_validation = None
            if tags and self.tag_validation_service:
                tag_validation = await self._validate_tags_with_policy(tags)

                if tag_validation.get('errors'):
                    return {
                        "success": False,
                        "error": "; ".join(tag_validation['errors']),
                        "message": "Tag validation failed",
                        "tag_info": tag_validation
                    }

                valid_tags = tag_validation.get('existing', []) + tag_validation.get('created', [])
                if valid_tags != tags:
                    kwargs = dict(kwargs)
                    kwargs['tags'] = valid_tags

            result = await self.reliable_scheduler.add_todo(title=title, **kwargs)

            if tag_validation:
                result['tag_info'] = tag_validation

            return result
        except Exception as e:
            logger.error(f"Error adding todo: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add todo"
            }

    async def update_todo(self, todo_id: str, **kwargs) -> Dict[str, Any]:
        """Update a todo using AppleScript."""
        try:
            todo_id = ParameterValidator.validate_non_empty_string(todo_id, 'todo_id')
            validated_params = ParameterValidator.validate_update_params(**kwargs)
            kwargs.update(validated_params)

        except ValidationError as e:
            logger.error(f"Validation error in update_todo: {e}")
            return create_validation_error_response(e)

        try:
            tags = kwargs.get('tags', [])
            tag_validation = None
            if tags and self.tag_validation_service:
                tag_validation = await self._validate_tags_with_policy(tags)

                if tag_validation.get('errors'):
                    return {
                        "success": False,
                        "error": "; ".join(tag_validation['errors']),
                        "message": "Tag validation failed",
                        "tag_info": tag_validation
                    }

                valid_tags = tag_validation.get('existing', []) + tag_validation.get('created', [])
                if valid_tags != tags:
                    kwargs = dict(kwargs)
                    kwargs['tags'] = valid_tags

            result = await self.reliable_scheduler.update_todo(todo_id=todo_id, **kwargs)

            if tag_validation:
                result['tag_info'] = tag_validation

            return result
        except Exception as e:
            logger.error(f"Error updating todo: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update todo"
            }

    async def delete_todo(self, todo_id: str) -> Dict[str, Any]:
        """Delete a todo using AppleScript."""
        try:
            todo_id = ParameterValidator.validate_non_empty_string(todo_id, 'todo_id')

            script = f'''
            tell application "Things3"
                set targetTodo to to do id "{todo_id}"
                delete targetTodo
                return "deleted"
            end tell
            '''
            result = await self.applescript.execute_applescript(script)
            return {
                "success": result.get('success', False),
                "message": "Todo deleted successfully" if result.get('success') else result.get('error', 'Failed to delete todo')
            }
        except Exception as e:
            logger.error(f"Error deleting todo: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to delete todo"
            }

    async def add_project(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new project using AppleScript."""
        try:
            result = await self.reliable_scheduler.add_project(title=title, **kwargs)
            
            tags = kwargs.get('tags', [])
            if tags and self.tag_validation_service:
                tag_validation = await self._validate_tags_with_policy(tags)
                result['tag_info'] = tag_validation
            
            return result
        except Exception as e:
            logger.error(f"Error adding project: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add project"
            }

    async def update_project(self, project_id: str, **kwargs) -> Dict[str, Any]:
        """Update a project using AppleScript."""
        try:
            result = await self.reliable_scheduler.update_project(project_id=project_id, **kwargs)
            
            tags = kwargs.get('tags', [])
            if tags and self.tag_validation_service:
                tag_validation = await self._validate_tags_with_policy(tags)
                result['tag_info'] = tag_validation
            
            return result
        except Exception as e:
            logger.error(f"Error updating project: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update project"
            }

    async def move_record(self, todo_id: str, destination_list: str) -> Dict[str, Any]:
        """Move a todo using AppleScript."""
        try:
            return await self.move_operations.move_record(todo_id, destination_list)
        except Exception as e:
            logger.error(f"Error moving record: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to move record"
            }

    async def add_tags(self, todo_id: str, tags: List[str]) -> Dict[str, Any]:
        """Add tags to a todo using AppleScript."""
        try:
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")] if tags else []

            tag_validation = await self._validate_tags_with_policy(tags)
            
            valid_tags = tag_validation['existing'] + tag_validation['created']
            
            if not valid_tags:
                return {
                    "success": False,
                    "error": "NO_VALID_TAGS",
                    "message": "No valid tags to add",
                    "tag_info": tag_validation
                }
            
            get_tags_script = f'''
            tell application "Things3"
                set targetTodo to to do id "{todo_id}"
                return tag names of targetTodo
            end tell
            '''

            current_tags_result = await self.applescript.execute_applescript(get_tags_script)
            current_tags_str = current_tags_result.get('output', '').strip()

            current_tags = [t.strip() for t in current_tags_str.split(',') if t.strip()] if current_tags_str else []

            all_tags = list(dict.fromkeys(current_tags + valid_tags))

            escaped_tags = [ToolsHelpers.escape_applescript_string(tag).strip('"') for tag in all_tags]
            tag_string = ', '.join(escaped_tags)

            logger.debug(f"add_tags: all_tags={all_tags}, escaped_tags={escaped_tags}, tag_string='{tag_string}'")

            script = f'''
            tell application "Things3"
                set targetTodo to to do id "{todo_id}"
                set tag names of targetTodo to "{tag_string}"
                return "tags_added"
            end tell
            '''

            logger.debug(f"add_tags: Generated script:\n{script}")
            result = await self.applescript.execute_applescript(script)
            return {
                "success": result.get('success', False),
                "message": f"Added {len(valid_tags)} tags successfully" if result.get('success') else result.get('error', 'Failed to add tags'),
                "tag_info": tag_validation
            }
        except Exception as e:
            logger.error(f"Error adding tags: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add tags"
            }

    async def remove_tags(self, todo_id: str, tags: List[str]) -> Dict[str, Any]:
        """Remove tags from a todo using AppleScript."""
        try:
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")] if tags else []

            get_tags_script = f'''
            tell application "Things3"
                set targetTodo to to do id "{todo_id}"
                return tag names of targetTodo
            end tell
            '''

            current_tags_result = await self.applescript.execute_applescript(get_tags_script)
            current_tags_str = current_tags_result.get('output', '').strip()

            current_tags = [t.strip() for t in current_tags_str.split(',') if t.strip()] if current_tags_str else []

            tags_to_remove_set = set(tags)
            remaining_tags = [tag for tag in current_tags if tag not in tags_to_remove_set]

            escaped_tags = [ToolsHelpers.escape_applescript_string(tag).strip('"') for tag in remaining_tags]
            tag_string = ', '.join(escaped_tags) if escaped_tags else ""

            logger.debug(f"remove_tags: current={current_tags}, removing={tags}, remaining={remaining_tags}, tag_string='{tag_string}'")

            if tag_string:
                script = f'''
                tell application "Things3"
                    set targetTodo to to do id "{todo_id}"
                    set tag names of targetTodo to "{tag_string}"
                    return "tags_removed"
                end tell
                '''
            else:
                script = f'''
                tell application "Things3"
                    set targetTodo to to do id "{todo_id}"
                    set tag names of targetTodo to ""
                    return "tags_removed"
                end tell
                '''

            result = await self.applescript.execute_applescript(script)
            return {
                "success": result.get('success', False),
                "message": f"Removed {len(tags)} tags successfully" if result.get('success') else result.get('error', 'Failed to remove tags')
            }
        except Exception as e:
            logger.error(f"Error removing tags: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to remove tags"
            }

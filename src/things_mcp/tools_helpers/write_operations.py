"""Write operations for Things 3 - uses AppleScript for reliable writes."""

import logging
from typing import Any, Dict, List, Optional

from ..services.applescript_manager import AppleScriptManager
from ..pure_applescript_scheduler import PureAppleScriptScheduler
from ..services.validation_service import ValidationService
from ..services.tag_service import TagValidationService
from ..move_operations import MoveOperationsTools
from ..parameter_validator import ParameterValidator, ValidationError, create_validation_error_response
from ..utils.applescript_utils import AppleScriptTemplates
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
                'warnings': result.warnings,
                'errors': result.errors
            }
        else:
            return {
                'created': [],
                'existing': tags,
                'filtered': [],
                'warnings': [],
                'errors': []
            }

    async def _prepare_tags(self, tags: Optional[List[str]]):
        """Validate and filter tags via the policy-aware tag validation service.

        This encapsulates the same validate-before-write pattern used by
        add_todo/update_todo, so add_project/update_project/add_area/update_area
        honour the configured tag_creation_policy the same way todos do.

        Args:
            tags: Requested tag names, or None/empty if no tags were provided.

        Returns:
            A 3-tuple (error_response, valid_tags, tag_info):
              - error_response: a structured error dict if validation rejected
                the operation (e.g. fail_on_unknown policy with unknown tags);
                None otherwise. Callers must return this immediately without
                performing the write when it is not None.
              - valid_tags: the filtered list of tag names to actually send to
                AppleScript (existing + newly created tags), or None if no
                validation was performed (no tags provided, or no
                tag_validation_service configured) - in which case callers
                should fall back to the originally requested tags unmodified.
              - tag_info: the tag_info dict to attach to the result for
                observability, or None if no validation was performed.
        """
        if not tags or not self.tag_validation_service:
            return None, None, None

        tag_validation = await self._validate_tags_with_policy(tags)

        if tag_validation.get('errors'):
            error_response = {
                "success": False,
                "error": "; ".join(tag_validation['errors']),
                "message": "Tag validation failed",
                "tag_info": tag_validation
            }
            return error_response, None, tag_validation

        valid_tags = list(dict.fromkeys(
            tag_validation.get('existing', []) + tag_validation.get('created', [])
        ))
        return None, valid_tags, tag_validation

    async def add_todo(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new todo using AppleScript."""
        try:
            tags = kwargs.get('tags', [])
            error_response, valid_tags, tag_info = await self._prepare_tags(tags)

            if error_response:
                return error_response

            if valid_tags is not None and valid_tags != tags:
                kwargs = dict(kwargs)
                kwargs['tags'] = valid_tags

            result = await self.reliable_scheduler.add_todo(title=title, **kwargs)

            if tag_info:
                result['tag_info'] = tag_info

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
            # An explicit clear request (tags=[] from validate_update_params,
            # as opposed to tags not being provided at all) skips tag policy
            # validation entirely - there is nothing to validate when clearing.
            is_explicit_clear = 'tags' in kwargs and tags == []
            error_response, valid_tags, tag_info = await self._prepare_tags(tags)

            if error_response:
                return error_response

            if is_explicit_clear:
                # Preserve the explicit [] so the update path clears tags,
                # regardless of what _prepare_tags returned for an empty list.
                kwargs['tags'] = []
            elif valid_tags is not None and valid_tags != tags:
                # Policy filtered some/all requested tags. If everything was
                # filtered out, valid_tags == [] here - but that must NOT be
                # confused with an explicit clear request, so we deliberately
                # drop the 'tags' key rather than setting it to [] and leave
                # the todo's existing tags untouched (matches update_area's
                # "all filtered -> no-op" behaviour).
                kwargs = dict(kwargs)
                if valid_tags:
                    kwargs['tags'] = valid_tags
                else:
                    kwargs.pop('tags', None)

            result = await self.reliable_scheduler.update_todo(todo_id=todo_id, **kwargs)

            if tag_info:
                result['tag_info'] = tag_info

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
            tags = kwargs.get('tags', [])
            error_response, valid_tags, tag_info = await self._prepare_tags(tags)

            if error_response:
                return error_response

            if valid_tags is not None and valid_tags != tags:
                kwargs = dict(kwargs)
                kwargs['tags'] = valid_tags

            result = await self.reliable_scheduler.add_project(title=title, **kwargs)

            if tag_info:
                result['tag_info'] = tag_info

            return result
        except Exception as e:
            logger.error(f"Error adding project: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add project"
            }

    async def update_project(self, project_id: str, **kwargs) -> Dict[str, Any]:
        """Update a project using AppleScript.

        Applies the same clear-field validation as update_todo
        (ParameterValidator.validate_update_params): notes='' and
        deadline='' clear those fields, tags='' clears tags, title=''
        is rejected, when='' is rejected. area_id/area_title are passed
        through unvalidated (validate_update_params does not cover them).
        """
        try:
            project_id = ParameterValidator.validate_non_empty_string(project_id, 'project_id')
            # Only re-validate the fields validate_update_params understands;
            # area_id/area_title/area are project-specific and pass through as-is.
            validate_kwargs = {k: v for k, v in kwargs.items()
                                if k in ('title', 'notes', 'tags', 'when', 'deadline',
                                         'completed', 'canceled')}
            validated_params = ParameterValidator.validate_update_params(**validate_kwargs)
            kwargs.update(validated_params)

        except ValidationError as e:
            logger.error(f"Validation error in update_project: {e}")
            return create_validation_error_response(e)

        try:
            tags = kwargs.get('tags', [])
            # An explicit clear request (tags=[] from validate_update_params,
            # as opposed to tags not being provided at all) skips tag policy
            # validation entirely - there is nothing to validate when clearing.
            is_explicit_clear = 'tags' in kwargs and tags == []
            error_response, valid_tags, tag_info = await self._prepare_tags(tags)

            if error_response:
                return error_response

            if is_explicit_clear:
                # Preserve the explicit [] so the update path clears tags,
                # regardless of what _prepare_tags returned for an empty list.
                kwargs['tags'] = []
            elif valid_tags is not None and valid_tags != tags:
                # Policy filtered some/all requested tags. If everything was
                # filtered out, valid_tags == [] here - but that must NOT be
                # confused with an explicit clear request, so we deliberately
                # drop the 'tags' key rather than setting it to [] and leave
                # the project's existing tags untouched (matches update_area's
                # "all filtered -> no-op" behaviour).
                kwargs = dict(kwargs)
                if valid_tags:
                    kwargs['tags'] = valid_tags
                else:
                    kwargs.pop('tags', None)

            result = await self.reliable_scheduler.update_project(project_id=project_id, **kwargs)

            if tag_info:
                result['tag_info'] = tag_info

            return result
        except Exception as e:
            logger.error(f"Error updating project: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update project"
            }

    async def add_area(self, title: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Add a new area using AppleScript.

        Args:
            title: Name of the new area (required, non-empty)
            tags: Optional list of existing tag names to apply to the area.
                  Tags that do not already exist in Things 3 are silently
                  filtered out by Things itself (AI cannot create tags).

        Returns:
            Dict with success status, area_id, title, and message.
        """
        try:
            title = ParameterValidator.validate_non_empty_string(title, 'title')
        except ValidationError as e:
            logger.error(f"Validation error in add_area: {e}")
            return create_validation_error_response(e)

        try:
            error_response, valid_tags, tag_info = await self._prepare_tags(tags)

            if error_response:
                return error_response

            # valid_tags is None when no validation occurred (no tags provided,
            # or no tag_validation_service configured) - fall back to the
            # originally requested tags unmodified, matching prior behaviour.
            effective_tags = valid_tags if valid_tags is not None else tags

            escaped_title = AppleScriptTemplates.escape_string(title)

            script = f'''
            tell application "Things3"
                try
                    set newArea to make new area with properties {{name:{escaped_title}}}
            '''

            if effective_tags:
                tags_string = ', '.join(effective_tags)
                escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
                script += f'set tag names of newArea to {escaped_tags_string}\n                    '

            script += '''
                    return id of newArea
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                output = result.get("output", "").strip()
                if output and not output.startswith("error:"):
                    response = {
                        "success": True,
                        "area_id": output,
                        "title": title,
                        "message": "Area created successfully"
                    }
                    if tag_info:
                        response['tag_info'] = tag_info
                    return response
                return {
                    "success": False,
                    "error": output,
                    "message": "Failed to create area"
                }
            return {
                "success": False,
                "error": result.get("output", "AppleScript execution failed"),
                "message": "Failed to create area"
            }
        except Exception as e:
            logger.error(f"Error adding area: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add area"
            }

    async def update_area(self, area_id: str, title: Optional[str] = None,
                           tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Update an existing area using AppleScript.

        Clear-field contract: title left at None (not provided) leaves the
        existing title unchanged; title='' (or whitespace-only) is rejected
        with a ValidationError - titles cannot be cleared. tags left at
        None (not provided) leaves existing tags unchanged; tags=[] (an
        explicit empty list) clears all tags.

        Args:
            area_id: ID of the area to update (required)
            title: New name for the area (optional; '' is rejected)
            tags: New list of existing tag names to apply to the area
                  (optional). [] clears all tags. Tags that do not already
                  exist in Things 3 are silently filtered out by Things
                  itself (AI cannot create tags).

        Returns:
            Dict with success status and message.
        """
        try:
            area_id = ParameterValidator.validate_non_empty_string(area_id, 'area_id')
            if title is not None and title.strip() == '':
                raise ValidationError('title', 'title cannot be empty', title)
        except ValidationError as e:
            logger.error(f"Validation error in update_area: {e}")
            return create_validation_error_response(e)

        if title is None and tags is None:
            return {
                "success": False,
                "error": "No fields provided to update",
                "message": "Nothing to update"
            }

        try:
            is_explicit_tags_clear = tags is not None and len(tags) == 0
            # An explicit clear request skips tag policy validation entirely -
            # there is nothing to validate when clearing.
            error_response, valid_tags, tag_info = await self._prepare_tags(
                None if is_explicit_tags_clear else tags
            )

            if error_response:
                return error_response

            # valid_tags is None when no validation occurred (no tags provided,
            # or no tag_validation_service configured) - fall back to the
            # originally requested tags unmodified, matching prior behaviour.
            effective_tags = valid_tags if valid_tags is not None else tags

            # If tags were requested but the policy filtered all of them out,
            # skip the "set tag names" statement entirely rather than clearing
            # the area's existing tags. This is distinct from an explicit
            # clear request (tags=[]), which does clear.
            tags_all_filtered = bool(tags) and valid_tags is not None and not valid_tags

            escaped_area_id = AppleScriptTemplates.escape_string(area_id)

            script = f'''
            tell application "Things3"
                try
                    set targetArea to area id {escaped_area_id}
            '''

            if title:
                escaped_title = AppleScriptTemplates.escape_string(title)
                script += f'set name of targetArea to {escaped_title}\n                    '

            if is_explicit_tags_clear:
                script += 'set tag names of targetArea to ""\n                    '
            elif effective_tags:
                tags_string = ', '.join(effective_tags)
                escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
                script += f'set tag names of targetArea to {escaped_tags_string}\n                    '

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
                    response = {
                        "success": True,
                        "message": "Area updated successfully" if not tags_all_filtered
                        else "Area updated successfully (no valid tags to apply; existing tags left unchanged)"
                    }
                    if tag_info:
                        response['tag_info'] = tag_info
                    return response
                if "area id" in output.lower() or "can't get area" in output.lower() or "doesn't understand" in output.lower():
                    return {
                        "success": False,
                        "error": f"Area not found: {area_id}",
                        "message": "Failed to update area"
                    }
                return {
                    "success": False,
                    "error": output,
                    "message": "Failed to update area"
                }
            return {
                "success": False,
                "error": result.get("output", "AppleScript execution failed"),
                "message": "Failed to update area"
            }
        except Exception as e:
            logger.error(f"Error updating area: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update area"
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

            error_response, valid_tags, tag_info = await self._prepare_tags(tags)

            if error_response:
                return error_response

            if valid_tags is None:
                valid_tags = tags

            if not valid_tags:
                return {
                    "success": False,
                    "error": "NO_VALID_TAGS",
                    "message": "No valid tags to add",
                    "tag_info": tag_info
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
            added_count = len(all_tags) - len(current_tags)

            escaped_tags_string = ToolsHelpers.escape_applescript_string(', '.join(all_tags))

            logger.debug(f"add_tags: all_tags={all_tags}, escaped_tags_string={escaped_tags_string}")

            script = f'''
            tell application "Things3"
                set targetTodo to to do id "{todo_id}"
                set tag names of targetTodo to {escaped_tags_string}
                return "tags_added"
            end tell
            '''

            logger.debug(f"add_tags: Generated script:\n{script}")
            result = await self.applescript.execute_applescript(script)
            return {
                "success": result.get('success', False),
                "message": f"Added {added_count} tags successfully" if result.get('success') else result.get('error', 'Failed to add tags'),
                "tag_info": tag_info
            }
        except Exception as e:
            logger.error(f"Error adding tags: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add tags"
            }

    async def add_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Add checklist items to an existing todo."""
        try:
            return await self.reliable_scheduler.add_checklist_items(todo_id, items)
        except Exception as e:
            logger.error(f"Error adding checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add checklist items"
            }

    async def prepend_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Prepend checklist items to an existing todo."""
        try:
            return await self.reliable_scheduler.prepend_checklist_items(todo_id, items)
        except Exception as e:
            logger.error(f"Error prepending checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to prepend checklist items"
            }

    async def replace_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Replace all checklist items in a todo."""
        try:
            return await self.reliable_scheduler.replace_checklist_items(todo_id, items)
        except Exception as e:
            logger.error(f"Error replacing checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to replace checklist items"
            }

    async def remove_tags(self, todo_id: str, tags: List[str]) -> Dict[str, Any]:
        """Remove tags from a todo using AppleScript.

        Note: unlike add_tags, this does NOT apply the configured
        tag_creation_policy. Removal is inherently non-creating - a tag name
        that isn't currently on the todo (whether or not it exists anywhere
        in Things) is simply not present in `remaining_tags` and is reported
        via `not_present`; there is nothing for the policy to filter or
        create.
        """
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
            removed_count = len(current_tags) - len(remaining_tags)
            not_present = [tag for tag in tags if tag not in current_tags]

            logger.debug(
                f"remove_tags: current={current_tags}, removing={tags}, "
                f"remaining={remaining_tags}, removed_count={removed_count}, "
                f"not_present={not_present}"
            )

            if remaining_tags:
                escaped_tags_string = ToolsHelpers.escape_applescript_string(', '.join(remaining_tags))
                script = f'''
                tell application "Things3"
                    set targetTodo to to do id "{todo_id}"
                    set tag names of targetTodo to {escaped_tags_string}
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
            write_succeeded = result.get('success', False)
            # removed_count/not_present describe the write that was attempted;
            # if the AppleScript write itself failed, nothing was actually
            # applied, so report 0 removed rather than the would-be count.
            effective_removed_count = removed_count if write_succeeded else 0
            return {
                "success": write_succeeded,
                "message": f"Removed {removed_count} tags successfully" if write_succeeded else result.get('error', 'Failed to remove tags'),
                "removed_count": effective_removed_count,
                "not_present": not_present
            }
        except Exception as e:
            logger.error(f"Error removing tags: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to remove tags",
                "removed_count": 0
            }

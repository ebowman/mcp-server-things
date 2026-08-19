"""Bulk operations for Things 3 - efficient batch updates via AppleScript."""

import logging
import re
from typing import Any, Dict, List, Optional

from ..services.applescript_manager import AppleScriptManager
from ..pure_applescript_scheduler import PureAppleScriptScheduler
from ..services.tag_service import TagValidationService
from ..parameter_validator import ParameterValidator, ValidationError, create_validation_error_response
from ..locale_aware_dates import locale_handler
from .helpers import ToolsHelpers
from .errors import write_error

logger = logging.getLogger(__name__)


class BulkOperations:
    """Bulk operations for efficient batch updates."""

    def __init__(self, applescript_manager: AppleScriptManager,
                 scheduler: PureAppleScriptScheduler,
                 tag_validation_service: Optional[TagValidationService] = None):
        """Initialize bulk operations.

        Args:
            applescript_manager: AppleScript manager for execution
            scheduler: Scheduler for scheduling operations
            tag_validation_service: Optional tag validation service
        """
        self.applescript = applescript_manager
        self.reliable_scheduler = scheduler
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
                'errors': getattr(result, 'errors', [])
            }
        else:
            return {
                'created': [],
                'existing': tags,
                'filtered': [],
                'warnings': [],
                'errors': []
            }

    async def _validate_bulk_params(self, todo_ids: List[str], kwargs: dict) -> tuple:
        """Validate parameters for bulk update operation.

        Clear-field contract (same as update_todo, via
        ParameterValidator.validate_update_params): notes='' and
        deadline='' clear those fields on every todo; tags='' clears all
        tags on every todo (bypassing tag policy validation entirely,
        since there is nothing to validate when clearing); title='' and
        when='' are rejected with a ValidationError.

        Args:
            todo_ids: List of todo IDs
            kwargs: Update parameters

        Returns:
            Tuple of (validated_ids, validated_kwargs, tag_validation, when_value)

        Raises:
            ValidationError: If validation fails
        """
        # Validate todo IDs
        todo_ids = ParameterValidator.validate_id_list(todo_ids, 'todo_ids')

        # Validate update parameters
        validated_params = ParameterValidator.validate_update_params(**kwargs)
        # Replace kwargs with only validated params (filters out None values)
        kwargs = validated_params

        # Handle tag validation. An explicit clear request (tags=[] from
        # validate_update_params, as opposed to tags not being provided at
        # all) skips tag policy validation entirely and is preserved as [].
        tags = kwargs.get('tags', [])
        is_explicit_clear = 'tags' in kwargs and tags == []
        tag_validation = None
        if tags and self.tag_validation_service:
            tag_validation = await self._validate_tags_with_policy(tags)

            # Check for blocking errors
            if tag_validation.get('errors'):
                raise ValidationError("; ".join(tag_validation['errors']))

            # Update kwargs with only valid tags. If every requested tag was
            # filtered out by policy, drop 'tags' entirely rather than
            # setting it to [] - that must not be confused with an explicit
            # clear request, so the existing tags are left untouched
            # (matches update_area's "all filtered -> no-op" behaviour).
            valid_tags = tag_validation.get('existing', []) + tag_validation.get('created', [])
            if valid_tags != tags:
                kwargs = dict(kwargs)
                if valid_tags:
                    kwargs['tags'] = valid_tags
                else:
                    kwargs.pop('tags', None)
        elif is_explicit_clear:
            kwargs['tags'] = []

        # Extract 'when' for separate scheduling
        when_value = kwargs.pop('when', None)

        return todo_ids, kwargs, tag_validation, when_value

    def _build_bulk_update_script(self, todo_ids: List[str], kwargs: dict) -> str:
        """Build AppleScript for bulk update operation.

        Clear-field contract (mirrors TodoOperations._build_update_script):
        a field absent from kwargs leaves it unchanged; kwargs['notes'] == ''
        and kwargs['deadline'] == '' clear those fields; kwargs['tags'] == []
        (an explicit empty list, set by _validate_bulk_params for a tags=''
        request) clears all tags. title cannot be '' here - callers reject
        it upstream in ParameterValidator.validate_update_params.

        Args:
            todo_ids: List of todo IDs to update
            kwargs: Update parameters (without 'when')

        Returns:
            AppleScript code
        """
        script = 'tell application "Things3"\n'
        script += '    set successCount to 0\n'
        script += '    set errorMessages to {}\n'

        for todo_id in todo_ids:
            script += f'    try\n'
            script += f'        set targetTodo to to do id "{todo_id}"\n'

            # Handle status updates with proper precedence (mirrors
            # TodoOperations._build_update_script / update_project):
            # canceled=True always wins regardless of completed; otherwise
            # completed (True/False) sets completed/open; otherwise
            # canceled=False alone (with completed omitted/None) reopens the
            # todo rather than being a no-op.
            if kwargs.get('canceled'):
                script += f'        set status of targetTodo to canceled\n'
            elif 'completed' in kwargs and kwargs['completed'] is not None:
                if kwargs['completed']:
                    script += f'        set status of targetTodo to completed\n'
                else:
                    script += f'        set status of targetTodo to open\n'
            elif 'canceled' in kwargs and kwargs['canceled'] is False:
                script += f'        set status of targetTodo to open\n'

            if 'title' in kwargs and kwargs['title'] is not None:
                escaped_title = ToolsHelpers.escape_applescript_string(kwargs['title'])
                script += f'        set name of targetTodo to {escaped_title}\n'

            if 'notes' in kwargs and kwargs['notes'] is not None:
                escaped_notes = ToolsHelpers.escape_applescript_string(kwargs['notes'])
                script += f'        set notes of targetTodo to {escaped_notes}\n'

            if 'deadline' in kwargs:
                deadline = kwargs['deadline']
                if deadline == '':
                    # Things 3's AppleScript dictionary rejects
                    # `set due date of X to missing value` ("Can't make
                    # missing value into type date"); `delete` is the
                    # documented way to clear a date property.
                    script += '        delete due date of targetTodo\n'
                elif deadline:
                    date_components = locale_handler.normalize_date_input(deadline)
                    if date_components:
                        year, month, day = date_components
                        script += f'''        set deadlineDate to (current date)
        set time of deadlineDate to 0
        set day of deadlineDate to 1
        set year of deadlineDate to {year}
        set month of deadlineDate to {month}
        set day of deadlineDate to {day}
        set due date of targetTodo to deadlineDate
'''

            if 'tags' in kwargs and kwargs['tags'] is not None:
                tags_value = kwargs['tags']
                if isinstance(tags_value, str):
                    tags_value = [t.strip() for t in tags_value.split(",")] if tags_value else []
                # Filter out None and empty strings
                tags_value = [t for t in tags_value if t]
                if tags_value:
                    escaped_tags_string = ToolsHelpers.escape_applescript_string(', '.join(tags_value))
                    script += f'        set tag names of targetTodo to {escaped_tags_string}\n'
                else:
                    # Explicit clear request (kwargs['tags'] == [] before
                    # filtering) - clear all tags rather than leaving them
                    # unchanged.
                    script += '        set tag names of targetTodo to ""\n'

            script += '        set successCount to successCount + 1\n'
            script += '    on error errMsg\n'
            script += f'        set end of errorMessages to "ID {todo_id}: " & errMsg\n'
            script += '    end try\n'

        script += '    return {successCount:successCount, errors:errorMessages}\n'
        script += 'end tell'

        return script

    async def _parse_bulk_results(self, result: dict, todo_ids: List[str],
                                  when_value: Optional[str], tag_validation: Optional[dict]) -> Dict[str, Any]:
        """Parse results from bulk update operation.

        Args:
            result: AppleScript execution result
            todo_ids: List of todo IDs that were updated
            when_value: Optional scheduling value
            tag_validation: Optional tag validation results

        Returns:
            Formatted result dictionary
        """
        if not result.get('success'):
            return write_error(
                "APPLESCRIPT_ERROR", "Failed to perform bulk update",
                details=result.get('error', 'Unknown error'),
                updated_count=0,
                failed_count=len(todo_ids),
                total_requested=len(todo_ids)
            )

        output = result.get('output', '')

        # Parse success count
        success_count = len(todo_ids)  # Default
        error_messages = []

        if 'successCount' in output:
            try:
                match = re.search(r'successCount[:\s]+(\d+)', output)
                if match:
                    success_count = int(match.group(1))
            except Exception as e:
                logger.warning(f"Could not parse success count from: {output}, error: {e}")

        # Check for errors
        if 'errors' in output and success_count < len(todo_ids):
            error_messages.append(f"{len(todo_ids) - success_count} todos failed to update")

        # Handle scheduling
        scheduling_results = []
        when_is_evening = bool(when_value) and when_value.lower() == 'evening'
        if when_value and success_count > 0:
            logger.info(f"Scheduling {success_count} todos for: {when_value}")
            for todo_id in todo_ids:
                try:
                    if when_is_evening:
                        # AppleScript's 'schedule' command has no way to set
                        # "This Evening" - only the Things URL scheme's
                        # 'update' action accepts when=evening. The auth
                        # token is already verified present in
                        # bulk_update_todos before this method is reached.
                        url_result = await self.applescript.execute_url_scheme(
                            'update', {'id': todo_id, 'when': 'evening'}
                        )
                        schedule_result = {
                            "success": url_result.get('success', False),
                            "method": "url_scheme",
                            "date_set": "evening"
                        }
                    else:
                        schedule_result = await self.reliable_scheduler.schedule_todo_reliable(todo_id, when_value)
                    if schedule_result.get('success'):
                        scheduling_results.append(f"{todo_id}: scheduled")
                    else:
                        scheduling_results.append(f"{todo_id}: scheduling failed")
                        logger.warning(f"Failed to schedule todo {todo_id}: {schedule_result}")
                except Exception as e:
                    scheduling_results.append(f"{todo_id}: scheduling error")
                    logger.error(f"Error scheduling todo {todo_id}: {e}")

        # Build result message
        result_message = f"Bulk update completed: {success_count}/{len(todo_ids)} todos updated"
        if when_value:
            scheduled_count = len([r for r in scheduling_results if 'scheduled' in r and 'failed' not in r])
            result_message += f", {scheduled_count}/{success_count} scheduled"
        if error_messages:
            result_message += f" ({', '.join(error_messages)})"

        return {
            "success": success_count > 0,
            "message": result_message,
            "updated_count": success_count,
            "failed_count": len(todo_ids) - success_count,
            "total_requested": len(todo_ids),
            "scheduling_info": scheduling_results if when_value else None,
            "tag_info": tag_validation if tag_validation else None
        }

    async def bulk_update_todos(self, todo_ids: List[str], **kwargs) -> Dict[str, Any]:
        """Update multiple todos with the same changes in a single operation.

        Args:
            todo_ids: List of todo IDs to update
            **kwargs: Update parameters (completed, canceled, title, notes, when, deadline, tags)

        Returns:
            Dict with success status, count of updated items, and any errors

        when='evening' (alias 'tonight', normalized to 'evening' by
        ParameterValidator) is scheduled via the Things URL scheme's
        'update' action per todo (AppleScript's 'schedule' command cannot
        set "This Evening"), and therefore requires the Things auth token
        - checked once up front before any AppleScript write, so a missing
        token never results in a partially-applied bulk update. If the
        token IS configured, the AppleScript-only fields (title/notes/
        tags/deadline/etc.) are applied to every todo via the single bulk
        AppleScript script FIRST, then the per-todo URL-scheme evening
        schedule calls happen second - if a given todo's evening-schedule
        call fails, the AppleScript fields already applied to that todo
        are NOT rolled back.
        """
        try:
            # Validate parameters
            todo_ids, kwargs, tag_validation, when_value = await self._validate_bulk_params(todo_ids, kwargs)

            if not todo_ids:
                return write_error("NO_TODO_IDS", "No todo IDs provided", updated_count=0)

            # when='evening' is only honoured via the Things URL scheme's
            # 'update' action (AppleScript's 'schedule' command has no way to
            # set the "This Evening" flag), which requires the Things auth
            # token. Fail fast BEFORE any AppleScript write so nothing is
            # partially applied across the batch.
            if when_value and when_value.lower() == 'evening':
                if not self.applescript.auth_token:
                    from ..services.applescript_manager import AUTH_TOKEN_HINT
                    return write_error(
                        "AUTH_TOKEN_NOT_CONFIGURED",
                        "Things URL-scheme auth token not configured",
                        hint=AUTH_TOKEN_HINT,
                        updated_count=0,
                    )

            # Build and execute update script
            script = self._build_bulk_update_script(todo_ids, kwargs)
            result = await self.applescript.execute_applescript(script)

            # Parse and return results
            return await self._parse_bulk_results(result, todo_ids, when_value, tag_validation)

        except ValidationError as e:
            logger.error(f"Validation error in bulk_update_todos: {e}")
            return create_validation_error_response(e)
        except Exception as e:
            logger.error(f"Error in bulk update: {e}")
            return write_error(
                "APPLESCRIPT_ERROR", "Failed to perform bulk update",
                details=str(e), updated_count=0
            )

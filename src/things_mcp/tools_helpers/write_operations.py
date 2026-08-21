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
from ..things_import import LazyThingsProxy
from .helpers import ToolsHelpers
from .errors import write_error

# Lazily-importing proxy for things.py - avoids the module-level, unbounded
# glob.iglob() scan that a plain `import things` would perform at server
# boot time. See things_import.LazyThingsProxy docstring.
things = LazyThingsProxy()

logger = logging.getLogger(__name__)

# Sentinel distinguishing "things.py is unavailable / lookup itself failed
# for a reason unrelated to the id's existence" from "things.get()
# genuinely resolved and found nothing" (the latter is a real None return).
# delete_todo()'s type resolution only falls back to blind to-do/project
# delete attempts in the former case; the latter is a structured not_found.
_RESOLVE_UNAVAILABLE = object()


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
            error_response = write_error(
                "TAG_VALIDATION_FAILED",
                "Tag validation failed",
                errors=tag_validation['errors'],
                tag_info=tag_validation
            )
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
            return write_error("APPLESCRIPT_ERROR", "Failed to add todo", details=str(e))

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
            return write_error("APPLESCRIPT_ERROR", "Failed to update todo", details=str(e))

    async def delete_todo(self, todo_id: str) -> Dict[str, Any]:
        """Delete (trash) a to-do or project using AppleScript.

        Things' AppleScript dictionary does not treat a project as a to-do
        subtype for `delete`: `delete (to do id "<project-uuid>")` reliably
        errors with "Can't get to do id ..." even though reads on that same
        id resolve fine. Only `delete (project id "<project-uuid>")` works
        for projects (see hq-f0w.14/hq-f0w.40). This method resolves the
        item's type via things.get() first so it can pick the right script;
        when things.py is unavailable (import failure) or the lookup itself
        cannot be completed for a reason unrelated to the id's existence,
        it falls back to trying `to do id` then `project id` blind, and
        finally a `move ... to list "Trash"` as a last resort for cases
        where `delete` itself errors (e.g. a to-do whose parent project was
        already trashed in the same pass, per hq-f0w.14).

        Headings, areas, and tags cannot be deleted via AppleScript at all
        (Things' dictionary has no `delete` support for them) - those ids
        return a structured error explaining what to use instead, without
        attempting any AppleScript call. A genuinely nonexistent id (one
        things.get() resolves cleanly but finds nothing for) likewise
        returns a structured error without attempting any AppleScript call.
        """
        try:
            todo_id = ParameterValidator.validate_non_empty_string(todo_id, 'todo_id')

            item_type = self._resolve_delete_item_type(todo_id)

            if item_type in ('heading', 'area', 'tag'):
                kind_label = {
                    'heading': 'a heading',
                    'area': 'an area',
                    'tag': 'a tag',
                }[item_type]
                hint = {
                    'heading': "Headings cannot be deleted via the Things AppleScript API - delete it manually in the Things UI.",
                    'area': "Areas cannot be deleted via the Things AppleScript API (and deleting an area also deletes its projects) - delete it manually in the Things UI.",
                    'tag': "Tags cannot be deleted via delete_todo() - manage tags manually in the Things UI.",
                }[item_type]
                return {
                    "success": False,
                    "error": "not_deletable",
                    "message": f"Item {todo_id} is {kind_label}. {hint}"
                }

            if item_type is None:
                # things.get() resolved cleanly and found nothing - a
                # genuinely nonexistent id, not a things.py availability
                # problem. Fail fast with a structured error rather than
                # spending 2-3 AppleScript round-trips on an id that will
                # never resolve.
                return {
                    "success": False,
                    "error": "not_found",
                    "message": f"No to-do or project found with id {todo_id}"
                }

            if item_type == 'project':
                result = await self._try_delete_scripts(todo_id, ['project id'])
            elif item_type is not _RESOLVE_UNAVAILABLE:
                # 'to-do' (and any other resolvable non-project type)
                result = await self._try_delete_scripts(todo_id, ['to do id'])
            else:
                # things.get() unavailable - try both blind.
                result = await self._try_delete_scripts(todo_id, ['to do id', 'project id'])

            if result.get('success'):
                deleted_as_project = result.get('id_kind') == 'project id'
                return {
                    "success": True,
                    "message": "Project deleted successfully" if deleted_as_project else "Todo deleted successfully"
                }

            # Everything above failed to run `delete` successfully - last
            # resort is `move ... to list "Trash"`, which succeeds in cases
            # where `delete` itself errors (e.g. parent project already
            # trashed).
            move_result = await self._try_move_to_trash(todo_id)
            if move_result.get('success'):
                return {
                    "success": True,
                    "message": "Todo moved to Trash successfully"
                }

            return write_error(
                "APPLESCRIPT_ERROR", "Failed to delete todo",
                details=result.get('error', 'Failed to delete todo')
            )
        except ValidationError as e:
            logger.error(f"Validation error in delete_todo: {e}")
            return create_validation_error_response(e)
        except Exception as e:
            logger.error(f"Error deleting todo: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to delete todo", details=str(e))

    def _resolve_delete_item_type(self, todo_id: str) -> Any:
        """Resolve an id's type via things.get() for delete_todo's script selection.

        Returns the item's `type` string ('to-do', 'heading', 'project',
        'area', 'tag') if things.get() resolves the id, or `None` if
        things.get() resolves cleanly but finds nothing (a genuinely
        nonexistent id - the caller returns a structured not_found error
        for this case, not a blind fallback). Returns the module-level
        `_RESOLVE_UNAVAILABLE` sentinel only when the lookup itself could
        not be completed for a reason unrelated to the id's existence
        (things.py import failure, database unreadable, etc.) - callers
        fall back to trying both AppleScript delete forms blind only in
        that case.

        things.get(uuid, **kwargs) (things.py 1.0.1) forwards **kwargs to
        each lookup it tries in turn: tasks(uuid=..., **kwargs) first, and
        - only if that raises ValueError (id not a task) - areas(uuid=...,
        **kwargs) next. `trashed` is a kwarg tasks() accepts but
        Database.get_areas() does not, so `things.get(id, trashed=None)`
        raises TypeError (not caught by things.get()'s own `except
        ValueError`) for EVERY id that isn't a task - every area id, every
        tag id, and every nonexistent id - not just when things.py is
        genuinely unavailable. Passing `trashed=None` is necessary to see
        trashed to-dos/projects (matching tests/live/conftest.py's usage),
        so on that specific TypeError this retries once with a bare
        things.get(todo_id) (no kwargs) - tasks() has already ruled itself
        out by this point, so the retry only exercises areas()/tags(),
        which the plain call form supports, and returns None for a
        genuinely nonexistent id instead of raising again.
        """
        try:
            item = things.get(todo_id, trashed=None)
        except TypeError:
            try:
                item = things.get(todo_id)
            except Exception as e:
                logger.debug(f"delete_todo: things.get() unavailable for {todo_id}: {e}")
                return _RESOLVE_UNAVAILABLE
        except Exception as e:
            logger.debug(f"delete_todo: things.get() unavailable for {todo_id}: {e}")
            return _RESOLVE_UNAVAILABLE

        if item is None:
            return None

        return item.get('type', 'to-do')

    async def _try_delete_scripts(self, todo_id: str, id_kinds: List[str]) -> Dict[str, Any]:
        """Try `delete (<id_kind> id "...")` for each id_kind in order.

        Returns the first successful AppleScript result (with the winning
        `id_kind` recorded under `'id_kind'` so callers can report an
        accurate success message), or the last (failing) result if none
        succeed.
        """
        escaped_id = AppleScriptTemplates.escape_string_inner(todo_id)
        result: Dict[str, Any] = {"success": False, "error": "No delete attempts made"}

        for id_kind in id_kinds:
            var_name = "targetTodo" if id_kind == "to do id" else "targetProject"
            script = f'''
            tell application "Things3"
                set {var_name} to {id_kind} "{escaped_id}"
                delete {var_name}
                return "deleted"
            end tell
            '''
            result = await self.applescript.execute_applescript(script)
            if result.get('success'):
                result = dict(result)
                result['id_kind'] = id_kind
                return result

        return result

    async def _try_move_to_trash(self, todo_id: str) -> Dict[str, Any]:
        """Last-resort fallback: `move ... to list "Trash"`.

        Succeeds in cases where `delete` itself errors, e.g. a to-do whose
        parent project has already been trashed - `move` still resolves the
        id and trashes it even though `delete` errors with "Can't get to do
        id ...".
        """
        escaped_id = AppleScriptTemplates.escape_string_inner(todo_id)
        script = f'''
        tell application "Things3"
            set targetItem to to do id "{escaped_id}"
            move targetItem to list "Trash"
            return "trashed"
        end tell
        '''
        return await self.applescript.execute_applescript(script)

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
            return write_error("APPLESCRIPT_ERROR", "Failed to add project", details=str(e))

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
            return write_error("APPLESCRIPT_ERROR", "Failed to update project", details=str(e))

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
                return write_error("APPLESCRIPT_ERROR", "Failed to create area", details=output)
            return write_error(
                "APPLESCRIPT_ERROR", "Failed to create area",
                details=result.get("output", "AppleScript execution failed")
            )
        except Exception as e:
            logger.error(f"Error adding area: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to add area", details=str(e))

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
            return write_error("NO_FIELDS_PROVIDED", "Nothing to update")

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
                    return write_error("NOT_FOUND", f"Area not found: {area_id}")
                return write_error("APPLESCRIPT_ERROR", "Failed to update area", details=output)
            return write_error(
                "APPLESCRIPT_ERROR", "Failed to update area",
                details=result.get("output", "AppleScript execution failed")
            )
        except Exception as e:
            logger.error(f"Error updating area: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to update area", details=str(e))

    async def move_record(self, todo_id: str, destination_list: str) -> Dict[str, Any]:
        """Move a todo using AppleScript."""
        try:
            return await self.move_operations.move_record(todo_id, destination_list)
        except Exception as e:
            logger.error(f"Error moving record: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to move record", details=str(e))

    async def add_tags(self, todo_id: str, tags: List[str]) -> Dict[str, Any]:
        """Add tags to a todo using AppleScript."""
        try:
            todo_id = ParameterValidator.validate_non_empty_string(todo_id, 'todo_id')
        except ValidationError as e:
            logger.error(f"Validation error in add_tags: {e}")
            return create_validation_error_response(e)

        try:
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")] if tags else []

            error_response, valid_tags, tag_info = await self._prepare_tags(tags)

            if error_response:
                return error_response

            if valid_tags is None:
                valid_tags = tags

            if not valid_tags:
                return write_error("NO_VALID_TAGS", "No valid tags to add", tag_info=tag_info)

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
            if result.get('success'):
                return {
                    "success": True,
                    "message": f"Added {added_count} tags successfully",
                    "tag_info": tag_info
                }
            return write_error(
                "APPLESCRIPT_ERROR",
                result.get('error', 'Failed to add tags'),
                tag_info=tag_info
            )
        except Exception as e:
            logger.error(f"Error adding tags: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to add tags", details=str(e))

    async def add_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Add checklist items to an existing todo."""
        try:
            return await self.reliable_scheduler.add_checklist_items(todo_id, items)
        except Exception as e:
            logger.error(f"Error adding checklist items: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to add checklist items", details=str(e))

    async def prepend_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Prepend checklist items to an existing todo."""
        try:
            return await self.reliable_scheduler.prepend_checklist_items(todo_id, items)
        except Exception as e:
            logger.error(f"Error prepending checklist items: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to prepend checklist items", details=str(e))

    async def replace_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Replace all checklist items in a todo."""
        try:
            return await self.reliable_scheduler.replace_checklist_items(todo_id, items)
        except Exception as e:
            logger.error(f"Error replacing checklist items: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to replace checklist items", details=str(e))

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
            todo_id = ParameterValidator.validate_non_empty_string(todo_id, 'todo_id')
        except ValidationError as e:
            logger.error(f"Validation error in remove_tags: {e}")
            return create_validation_error_response(e)

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
            if write_succeeded:
                return {
                    "success": True,
                    "message": f"Removed {removed_count} tags successfully",
                    "removed_count": effective_removed_count,
                    "not_present": not_present
                }
            return write_error(
                "APPLESCRIPT_ERROR",
                result.get('error', 'Failed to remove tags'),
                removed_count=effective_removed_count,
                not_present=not_present
            )
        except Exception as e:
            logger.error(f"Error removing tags: {e}")
            return write_error("APPLESCRIPT_ERROR", "Failed to remove tags", details=str(e), removed_count=0)

"""Pre-check for Things URL-scheme update targets (hq-4w4).

Things shows a MODAL alert ("Things URL Scheme - Cannot update to-do with
ID ... because it does not exist.") whenever a ``things:///update`` or
``things:///update-project`` call targets an item Things considers gone -
notably a TRASHED one. ``things.get(id)`` still returns trashed items
(``trashed: True``), so the existing hq-wbm pre-checks let them through.
``check_url_scheme_target`` is the single shared gate every URL-scheme
update path calls BEFORE any write, so a trashed target is rejected as
``NOT_FOUND`` without ever contacting Things.
"""

import logging
from typing import Any, Callable, Dict, Optional

from .errors import write_error

logger = logging.getLogger(__name__)

_UNSET = object()


def _trashed_via_parent(record: Dict[str, Any], get: Callable[..., Any]) -> bool:
    """True if a to-do/heading's containing project is trashed.

    Mirrors get_todo_by_id's transitive resolution (hq-wsa.7): at most two
    get() calls (item's project, else item's heading -> heading's project).
    Any lookup failure is swallowed (treated as "not trashed").
    """
    try:
        project_id = record.get('project')
        if not project_id and record.get('heading'):
            heading_record = get(record['heading'])
            if heading_record:
                project_id = heading_record.get('project')
        if project_id:
            project_record = get(project_id)
            return bool(project_record and project_record.get('trashed'))
    except Exception as e:  # noqa: BLE001 - never fail the write on this
        logger.debug(f"Transitive trash check failed for {record.get('uuid')}: {e}")
    return False


def check_url_scheme_target(
    item_id: Any,
    expected_type: str,
    things_module: Any = None,
    record: Any = _UNSET,
) -> Optional[Dict[str, Any]]:
    """Validate a URL-scheme update target; return None if OK, else a write_error dict.

    Args:
        item_id: The id about to be sent to ``things:///update[-project]``.
        expected_type: ``'to-do'`` or ``'project'``.
        things_module: Object exposing ``get(id)`` (callers pass their
            module-level things proxy so test seams keep working).
        record: Optional already-fetched ``things.get(item_id)`` result, to
            avoid a second lookup.

    Rules: empty id -> VALIDATION_ERROR; unknown id -> NOT_FOUND; wrong type
    -> VALIDATION_ERROR; trashed (directly, or via a trashed parent project
    for to-dos) -> NOT_FOUND with ``trashed: true`` (+ ``trashedViaParent``).
    If the things.py lookup itself raises, returns None (documented
    proceed-unchecked fallback).
    """
    if not isinstance(item_id, str) or not item_id.strip():
        return write_error(
            "VALIDATION_ERROR", "id cannot be empty",
            field="id", invalid_value=item_id,
        )

    if things_module is None:
        from ..things_import import LazyThingsProxy
        things_module = LazyThingsProxy()

    if record is _UNSET:
        try:
            record = things_module.get(item_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"things.py lookup failed while pre-checking URL-scheme target "
                f"{item_id} (proceeding unchecked): {e}"
            )
            return None

    kind = 'project' if expected_type == 'project' else 'to-do'
    if record is None:
        return write_error("NOT_FOUND", f"No {kind} found with id '{item_id}'")

    actual = record.get('type')
    if actual != expected_type:
        if actual == 'project' and expected_type == 'to-do':
            msg = f"id '{item_id}' is a project, not a to-do; use update_project() instead"
        else:
            msg = f"id '{item_id}' refers to a '{actual}', not a {kind}"
        return write_error("VALIDATION_ERROR", msg, field="id", invalid_value=item_id)

    trash_msg = f"{kind} '{item_id}' is in the Trash; restore it in Things before updating it"
    if record.get('trashed'):
        return write_error("NOT_FOUND", trash_msg, trashed=True)
    if expected_type == 'to-do' and _trashed_via_parent(record, things_module.get):
        return write_error("NOT_FOUND", trash_msg, trashed=True, trashedViaParent=True)
    return None

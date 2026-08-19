# hq-gbl.1 spike: teardown de-risking findings

Live spike run 2026-08-19 against a real Things 3 database. All objects created
used the prefix `hq-gbl-spike <UTC-ts>` (area/project/todo) or
`hq-gbl-spike-tag[2]-<UTC-ts>` (tags) and were confirmed removed at the end
(see "Cleanup verification" below). No pre-existing Things data was touched.

## Step 1: create area/project/todo/tag (all succeeded)

```applescript
tell application "Things3"
    set newArea to make new area with properties {name:"hq-gbl-spike <ts>"}
    return id of newArea
end tell

tell application "Things3"
    set newProject to make new project with properties {name:"hq-gbl-spike <ts> project", area:area id "<area-id>"}
    return id of newProject
end tell

tell application "Things3"
    set newTodo to make new to do with properties {name:"hq-gbl-spike <ts> todo", project:project id "<project-id>"}
    return id of newTodo
end tell

tell application "Things3"
    set tag names of to do id "<todo-id>" to "hq-gbl-spike-tag-<ts>"
    return tag names of to do id "<todo-id>"
end tell
```

Setting `tag names of` on a to-do to a not-yet-existing tag name auto-creates
the tag and applies it in one step - no separate "create tag" verb is needed
for this path. A separate standalone tag (not applied to anything) can also be
created directly: `make new tag with properties {name:"..."}`.

## Step 2: delete verb results (exact scripts, all tried via `osascript`)

| Verb | Target | Result |
|---|---|---|
| `delete (tag id "<id>")` | tag applied to a to-do | **works** (rc 0, `"deleted"`) |
| `delete tag "<name>"` | standalone tag (name form) | **works** (rc 0, `"deleted"`) |
| `delete (area id "<id>")` | area containing 2 projects | **works** (rc 0, `"deleted"`) - see cascade below |
| `delete (project id "<id>")` | project already trashed (via area delete) | **fails**: `Can't get project id "<id>"` |
| `delete (to do id "<id>")` | to-do whose parent project was already trashed (orphaned) | **fails**: `Can't get to do id "<id>"` |
| `move targetItem to list "Trash"` | same orphaned to-do (fallback) | **works** (rc 0, `"moved"`), to-do ends up `trashed: True` |
| `move theTodo to project id "<id>"` (bare `move` verb) | moving a to-do between projects | **fails**: `Cannot move to-do (301)` |
| `set project of targetTodo to project id "<id>"` | same move, property-assignment form | **works** |

Working delete recipe (confirmed, exact text):

```applescript
tell application "Things3"
    try
        delete (tag id "<tag-id>")
        return "deleted"
    on error errMsg
        return "error: " & errMsg
    end try
end tell
```

```applescript
tell application "Things3"
    try
        delete (area id "<area-id>")
        return "deleted"
    on error errMsg
        return "error: " & errMsg
    end try
end tell
```

**Fallback recipe for a to-do orphaned by a just-deleted parent project**
(`delete (to do id ...)` errors in this specific case - this is the same
gap already documented in `tests/live/conftest.py`'s `_delete_via_applescript`
and `write_operations.py`'s `delete_todo` docstring, now confirmed live):

```applescript
tell application "Things3"
    try
        set targetItem to to do id "<todo-id>"
        move targetItem to list "Trash"
        return "moved"
    on error errMsg
        return "error: " & errMsg
    end try
end tell
```

## Cascade behavior: deleting an AREA (measured live)

Setup: area contained two projects (`project_id` empty, `project2_id`
containing one to-do). `delete (area id "<area-id>")` was run once.

- **The area itself**: fully purged. `things.get(area_id)` (bare call - see
  "things.py area/tag quirk" below) returns `None`, and the area no longer
  appears in `things.areas()`. Not "trashed" - genuinely gone.
- **The contained projects**: both are **trashed**, not purged and not
  merely orphaned. `things.get(project_id, trashed=None)['trashed']` is
  `True` for both, and `area` becomes `None` on each.
- **The to-do inside the (now-trashed) project**: **orphaned, not
  cascaded**. `things.get(todo_id, trashed=None)['trashed']` remained
  `None`/falsy (i.e. still an active, non-trashed to-do) even though its
  parent project was trashed by the area delete. Its `project` field still
  pointed at the now-trashed `project2_id` uuid - things.py does not null
  it out. This matches (and confirms live) the existing comment in
  `tests/live/conftest.py`'s `_trash_and_verify`: deleting a project does
  NOT cascade a trashed flag onto its to-do children.
- **Practical consequence for a teardown/harness**: deleting an area is
  NOT sufficient to clean up everything inside it. Any to-do that was
  filed directly under a project inside that area is left behind, active,
  and un-trashed, and subsequently fails a plain `delete (to do id ...)`
  (see table above - "Can't get to do id") because its parent project
  record is already gone/trashed. It must be swept up separately via the
  `move ... to list "Trash"` fallback (worked, confirmed above) before or
  after the area delete. A teardown routine must enumerate a session's
  child to-dos (as `tests/live/conftest.py`'s `_trash_and_verify` already
  does for projects) and trash them independently - area delete alone
  will silently leave to-dos behind, active and undetected unless
  specifically checked for.

## Tag delete: detach behavior + modificationDate

- `delete (tag id "<id>")` on a tag applied to one to-do: the to-do's
  `tags` list changes from `['hq-gbl-spike-tag-<ts>']` to absent - things.py
  drops the `tags` key entirely (`'tags' in row` is False; `row.get('tags')`
  is `None`) rather than reporting `[]`, after a tag it held is deleted out
  from under it. Any teardown/read-back assertion checking "tags empty"
  must use `.get('tags')` and accept `None` as well as `[]`.
- The to-do's `modified` field (`things.get(...)['modified']`) was
  **unchanged** by the tag deletion (`2026-08-19 21:24:07` before and
  after) - deleting a tag detaches it from the to-do silently, without
  bumping the to-do's modification timestamp.
- The tag itself: fully purged from `things.tags()` (both the `tag id`
  and `tag "<name>"` delete forms tested; `things.get()`-style existence
  check confirmed `False` after each).

## modificationDate (`modified` key) behavior - summary of all 4 measured operations

| Operation | Changed `modified`? |
|---|---|
| Adding a tag to a to-do (via `set tag names of`) | **yes** - bumps `modified` (measured in review: 21:29:01 -> 21:29:11 at the moment of the tag set) |
| Moving a to-do between projects (`set project of ... to project id ...`) | **yes** - `modified` advanced from `21:23:34` to `21:24:07` |
| Parent project being trashed (via area delete, cascading trash onto the project) | **no** - to-do's `modified` was unaffected (to-do wasn't itself touched at all - see orphaning note above) |
| Reading via `things.get()`/`get_todo_by_id`-equivalent (pure read) | **no** - two consecutive reads 1s apart returned identical `modified` values |
| Removing a tag via `delete (tag id ...)` | **no** - `modified` unchanged across the tag deletion |

Only an actual field write (the project move) advanced `modified`; the two
delete-adjacent operations (parent project trashed, tag detached) and a
pure read did not.

## things.py area/tag quirk (confirmed live, matches existing code comment)

`things.get(uuid, trashed=None)` raises `TypeError: Database.get_areas()
got an unexpected keyword argument 'trashed'` for any id that isn't a task
(area ids, tag ids, and any nonexistent id) - `trashed` is accepted by
`tasks()` but not `areas()`/`tags()`, and things.get() only catches
`ValueError` internally, not `TypeError`. This is the exact behavior
already documented in `write_operations.py`'s
`_resolve_delete_item_type` docstring; confirmed live here for area and
tag ids specifically. Callers needing to check an area/tag id must call
`things.get(uuid)` (no `trashed` kwarg) or catch `TypeError` and retry
bare, same pattern `_resolve_delete_item_type` already uses.

## Step 4: read-after-write lag for `things:///add` (checklist_items forces URL-scheme path)

Measured via `ThingsTools(AppleScriptManager()).add_todo(title=..., checklist_items=["a","b"])`,
timing `add_todo`'s own return (it already polls internally for the new id -
see CLAUDE.md's documented id-disambiguation polling, up to 3s / 250ms
interval) and then a `things.get(todo_id, trashed=None)` immediately after:

| Trial | `add_todo` wall time (its own internal poll included) | `things.get` time after `add_todo` returned |
|---|---|---|
| 0 | 2.06s | 0.006s |
| 1 | 2.14s | 0.003s |
| 2 | 2.65s | 0.002s |
| 3 | **18.65s** (outlier) | 0.014s |
| 4 | 3.20s | 0.014s |

- Once `add_todo` itself returns success, a `things.get()` read
  immediately afterward always found the record on the first try (max
  0.014s) across all 5 trials - `add_todo`'s internal polling reliably
  resolves the id before returning, so callers do not need their own
  extra read-after-write retry loop *after* `add_todo` returns
  successfully.
- `add_todo`'s own internal wall time is the real source of latency for
  checklist/URL-scheme creates: typically 2-3.2s, with one outlier of
  18.65s in this 5-trial run (Things was presumably slower to register the
  new to-do that one time; `add_todo` still eventually found it and
  returned success rather than timing out - CLAUDE.md documents a 3s poll
  window per attempt but does not document an outer retry count/ceiling,
  so this 18.65s outlier suggests either a longer effective ceiling in
  practice or multiple poll rounds - not further investigated here, out of
  scope for this spike).
- **Practical consequence for a harness**: a regression harness using
  `add_todo(..., checklist_items=...)` should budget a generous per-call
  timeout (at least ~20s to be safe based on this outlier, not just the
  documented 3s poll window) rather than assuming sub-3s completion, and
  does not need an additional read-after-write poll of its own once
  `add_todo` reports success.

## Cleanup verification

All spike objects were removed by the end of the run:

- Area (`JmWveVKwDCbZ1v7owZ7CWB`) and both tags (`hq-gbl-spike-tag-<ts>`,
  `hq-gbl-spike-tag2-<ts>`): fully purged - `things.get(id)` returns `None`
  and neither appears in `things.areas()`/`things.tags()`.
- Both projects (`project_id`, `project2_id`) and the original to-do
  (`todo_id`): `trashed: True` via `things.get(id, trashed=None)`.
- All 5 lag-trial to-dos from step 4: deleted via `delete (to do id
  "...")` (rc 0, `"deleted"` each) and confirmed `trashed: True`.
- Final sweep: iterated `things.tasks(status=None, trashed=None)`,
  `things.areas()`, `things.tags()` for any title containing
  `hq-gbl-spike` - **zero** non-trashed leftovers found; the only matches
  left in the database at all are the trashed projects/to-dos above
  (expected - not touching/emptying the Trash per the safety rule).

## Recipe for the harness (hq-gbl epic)

1. Track every created id by type (to-do/project/area/tag) as it's
   created, not just at teardown time.
2. Delete tags first (`delete (tag id "...")` or `delete tag "<name>"`) -
   cheap, no cascade risk, detaches without bumping to-do `modified`.
3. Delete areas next (`delete (area id "...")`) - fully purges the area
   and trashes any projects inside it, but does **not** cascade to
   trashing to-dos inside those projects. Do not rely on area delete
   alone to clean up child to-dos.
4. Sweep and trash any remaining to-dos (including ones orphaned by step
   3) via `delete (to do id "...")`, falling back to `move targetItem to
   list "Trash"` when the plain delete errors with `Can't get to do id`
   (this happens specifically when the to-do's parent project was already
   trashed in the same teardown pass).
5. Verify via `things.get(id, trashed=None)` (tasks) / bare `things.get(id)`
   (areas/tags, to avoid the `TypeError` quirk) that every tracked id is
   either `None` (purged) or `trashed: True` - never touch/empty the
   Trash itself.

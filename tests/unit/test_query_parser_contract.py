"""
Producer -> parser round-trip contract tests for AppleScript query builders.

Failure class 2 (producer/consumer format mismatch, GH#10): the query
builders in ``services/applescript/queries.py`` assemble AppleScript output
lines by raw string concatenation (``"id:" & id & ", name:" & ...``), *not*
by wrapping values in AppleScript string literal quotes. The parser tests in
``test_applescript_parser.py`` (``TestQuotedStrings``) feed the parser values
wrapped in ``"..."`` - a format the real scripts never emit. That mismatch
is how the GH#10 bugs 1-2 (comma/quote truncation) shipped undetected.

This module closes that gap with a small "AppleScript output simulator":
Python functions that reproduce, field-for-field, exactly what each real
query builder script would emit for a given set of input property values
(id, name, notes, tags, dates, ...), including the same
§COMMA§/§QUOTE§/§COLON§ ``replaceText`` protection (or lack thereof) applied
by that specific builder. Simulated output is then fed through the real
parser (``services/applescript/parser.AppleScriptParser``, via
``AppleScriptManager._parse_applescript_list`` - the same entry point
production code uses) and asserted to round-trip exactly.

Two pre-existing parser/builder bugs, found and confirmed while writing this
contract (NOT fixed here - out of scope for this bead), are pinned down as
``xfail(strict=True)`` cases so a future fix flips them green instead of
silently regressing:

1. The parser's list-detection enters ``LIST`` state on any ``{`` in a
   scalar value, so a literal ``{`` / ``}`` in a todo/project/area name is
   silently dropped (``'a {b} c'`` -> ``'a b c'``) even though queries.py
   does not protect braces in the name field.
2. ``build_get_projects_script`` emits ``tag_names`` as a raw, unquoted
   string with none of the §COMMA§/§QUOTE§/§COLON§ protection applied to
   name/notes. In real Things 3, ``tag names`` of a project is a TEXT
   property that already comes back comma-space-joined (e.g.
   ``"work, urgent"``), so the script's ``text item delimiters ","`` /
   ``tagList as string`` join is a no-op on it - the emitted line looks
   like ``tag_names:work, urgent`` (comma-SPACE), not a bare
   ``tag_names:work,urgent``. Either way, a tag_names value with more than
   one tag gets misparsed by the comma-splitting VALUE-state logic,
   producing a bogus extra field (e.g. ``tag_names:work, urgent`` yields a
   spurious ``"urgent creation_date"`` key instead of two tags). Because
   the projects script's date fields (creation_date, modification_date,
   due_date, start_date, completion_date, cancellation_date) are *also*
   emitted unprotected (unlike build_get_todos_script's dates), this
   corruption cascades into whichever field follows a multi-tag
   tag_names - pinned here with tag_names immediately followed by
   creation_date, exactly as queries.py emits them.

A known, already-documented (test_parser_comparison.py) legacy-parser gap -
completion_date/cancellation_date are not ISO-formatted by the legacy path
(they fall through the generic string branch, not the date branch) - is
tolerated in the legacy-path comparisons below rather than xfailed, per the
bead notes.
"""

from __future__ import annotations

import re
from typing import Optional

import pytest

from things_mcp.config import ThingsMCPConfig
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.services.applescript.queries import AppleScriptQueries


# ---------------------------------------------------------------------------
# AppleScript output simulator
#
# Each function below mirrors one query-builder script's per-record string
# assembly EXACTLY: same field order, same "field:" literals, same
# §COMMA§/§QUOTE§/§COLON§ protection (applied via the same replaceText
# semantics: naive global substring replace), same missing-value handling.
# ---------------------------------------------------------------------------


def _protect(value: str) -> str:
    """Mirror the "protect special characters" replaceText sequence that
    queries.py applies to name/notes fields: comma, then quote, then colon.

    This is a plain, order-dependent global substring replace - exactly what
    AppleScript's ``replaceText`` handler (text item delimiters split/join)
    does, and exactly the order queries.py calls it in for every protected
    field (see queries.py's repeated ``replaceText(x, ",", "§COMMA§")`` /
    ``replaceText(x, "\\"", "§QUOTE§")`` / ``replaceText(x, ":", "§COLON§")``
    sequence).
    """
    value = value.replace(",", "§COMMA§")
    value = value.replace('"', "§QUOTE§")
    value = value.replace(":", "§COLON§")
    return value


def _protect_date(value: str) -> str:
    """Mirror the date-field protection used in build_get_todos_script:
    colon first, then comma (see queries.py lines ~52-54, ~62-64, ~85-87,
    ~96-98: ``replaceText(x, ":", "§COLON§")`` then
    ``replaceText(x, ",", "§COMMA§")`` - the reverse order from name/notes).
    """
    value = value.replace(":", "§COLON§")
    value = value.replace(",", "§COMMA§")
    return value


def simulate_get_todos_record(
    *,
    id_: str,
    name: str,
    notes: Optional[str],
    status: str = "open",
    creation_date: Optional[str] = None,
    modification_date: Optional[str] = None,
    activation_date: Optional[str] = None,
    due_date: Optional[str] = None,
) -> str:
    """Mirror AppleScriptQueries.build_get_todos_script (both the
    project_uuid and non-project_uuid branches emit an identical per-record
    line - see queries.py lines 42-113 and 134-206, specifically the final
    concatenation on lines 109 and 202):

        "id:" & id & ", name:" & nameStr & ", notes:" & noteStr
            & ", status:" & status & ", creation_date:" & creationDateStr
            & ", modification_date:" & modificationDateStr
            & ", activation_date:" & activationDateStr
            & ", due_date:" & dueDateStr

    name and notes are protected with §COMMA§/§QUOTE§/§COLON§ (queries.py
    lines 69-79, 103-107). Date fields are protected with §COLON§/§COMMA§
    only, in that order (queries.py lines 48-101) - dates never carry raw
    quotes so §QUOTE§ protection is irrelevant there.
    """
    name_str = _protect(name)
    note_str = "missing value" if notes is None else _protect(notes)
    creation_str = "missing value" if creation_date is None else _protect_date(creation_date)
    mod_str = "missing value" if modification_date is None else _protect_date(modification_date)
    act_str = "missing value" if activation_date is None else _protect_date(activation_date)
    due_str = "missing value" if due_date is None else _protect_date(due_date)

    return (
        f"id:{id_}, name:{name_str}, notes:{note_str}, status:{status}, "
        f"creation_date:{creation_str}, modification_date:{mod_str}, "
        f"activation_date:{act_str}, due_date:{due_str}"
    )


def simulate_get_projects_record(
    *,
    id_: str,
    name: str,
    notes: Optional[str],
    status: str = "open",
    tags: Optional[list[str]] = None,
    creation_date: Optional[str] = None,
    modification_date: Optional[str] = None,
    due_date: Optional[str] = None,
    start_date: Optional[str] = None,
    completion_date: Optional[str] = None,
    cancellation_date: Optional[str] = None,
    contact: Optional[str] = None,
    area: Optional[str] = None,
    project: Optional[str] = None,
) -> str:
    """Mirror AppleScriptQueries.build_get_projects_script (queries.py
    lines 215-346), specifically the final concatenation on line 341:

        "id:" & id & ", name:" & nameStr & ", notes:" & noteStr
            & ", status:" & status & ", tag_names:" & tagNamesStr
            & ", creation_date:" & creationDateStr
            & ", modification_date:" & modificationDateStr
            & ", due_date:" & dueDateStr & ", start_date:" & startDateStr
            & ", completion_date:" & completionDateStr
            & ", cancellation_date:" & cancellationDateStr
            & ", contact:" & contactStr & ", area:" & areaStr
            & ", project:" & projectStr

    name and notes ARE protected (queries.py lines 322-338). tag_names is
    built via ``set AppleScript's text item delimiters to ","`` then
    ``tagList as string`` (queries.py lines 284-296) - but in real Things 3,
    ``tag names of <project>`` is a TEXT property, not a list (confirmed by
    reading it live: ``class of (tag names of p)`` -> ``text``, and a
    multi-tag project's value comes back already comma-SPACE-joined, e.g.
    ``"Colin, AndreasHolmen"``). Because AppleScript coerces a value that is
    already text via ``as string`` unchanged, the ``text item delimiters``
    join is a no-op here: it never gets the chance to re-join a *list* with
    "," because there is no list to join, only a moot re-stringification of
    already comma-space text. So the real emitted line looks like
    ``tag_names:work, urgent`` (comma-SPACE), not ``tag_names:work,urgent``
    (bare comma) - and either way there is NO §COMMA§/§QUOTE§/§COLON§
    protection applied to it - this is bug (2) documented in the module
    docstring. The date fields (creation_date, modification_date, due_date,
    start_date, completion_date, cancellation_date - queries.py lines
    240-281) are ALSO emitted with no protection whatsoever (unlike the
    todos script). contact/area/project (queries.py lines 298-320) are
    likewise unprotected raw ``as string`` coercions.
    """
    name_str = _protect(name)
    note_str = "missing value" if notes is None else _protect(notes)
    # Things 3's "tag names" is a text property already comma-space
    # joined (see docstring above) - the script's text item delimiters
    # join is a no-op on it, so the faithful simulated value uses ", "
    # (comma-SPACE), not a bare "," join.
    tag_names_str = "" if not tags else ", ".join(tags)
    creation_str = "missing value" if creation_date is None else creation_date
    mod_str = "missing value" if modification_date is None else modification_date
    due_str = "missing value" if due_date is None else due_date
    start_str = "missing value" if start_date is None else start_date
    completion_str = "missing value" if completion_date is None else completion_date
    cancellation_str = "missing value" if cancellation_date is None else cancellation_date
    contact_str = "missing value" if contact is None else contact
    area_str = "missing value" if area is None else area
    project_str = "missing value" if project is None else project

    return (
        f"id:{id_}, name:{name_str}, notes:{note_str}, status:{status}, "
        f"tag_names:{tag_names_str}, creation_date:{creation_str}, "
        f"modification_date:{mod_str}, due_date:{due_str}, "
        f"start_date:{start_str}, completion_date:{completion_str}, "
        f"cancellation_date:{cancellation_str}, contact:{contact_str}, "
        f"area:{area_str}, project:{project_str}"
    )


def simulate_get_areas_record(*, id_: str, name: str) -> str:
    """Mirror AppleScriptQueries.build_get_areas_script (queries.py lines
    354-391), specifically the final concatenation on line 386:

        "id:" & id & ", name:" & nameStr

    name is protected with §COMMA§/§QUOTE§/§COLON§ (queries.py lines
    380-384). Areas only ever have id and name (queries.py comment on line
    373: "Areas in Things 3 only have id and name properties").
    """
    name_str = _protect(name)
    return f"id:{id_}, name:{name_str}"


def join_records(records: list[str]) -> str:
    """Mirror the ``if outputText is not "" then outputText & ", "``
    record-separator logic every builder uses (e.g. queries.py lines 44-46):
    records are joined with ``", "`` exactly like fields are - there is no
    special record delimiter.
    """
    return ", ".join(records)


# ---------------------------------------------------------------------------
# Manager fixtures - same construction pattern as test_parser_comparison.py
# ---------------------------------------------------------------------------


@pytest.fixture
def new_manager() -> AppleScriptManager:
    config = ThingsMCPConfig()
    config.use_new_applescript_parser = True
    return AppleScriptManager(config=config)


@pytest.fixture
def legacy_manager() -> AppleScriptManager:
    config = ThingsMCPConfig()
    config.use_new_applescript_parser = False
    return AppleScriptManager(config=config)


# ---------------------------------------------------------------------------
# Adversarial input catalogue, reused across builders
# ---------------------------------------------------------------------------

def _expected_round_trip(raw: str) -> Optional[str]:
    """The parser's documented, pre-existing value normalization applied on
    top of the §COMMA§/§QUOTE§/§COLON§ unescape (see
    test_applescript_parser.py::TestQuotedStrings.test_empty_name and
    ::test_name_of_only_special_chars, both pre-dating this bead):

    - values are ``.strip()``-ped (AppleScriptParser._finalize_field), so
      leading/trailing whitespace never round-trips byte-for-byte.
    - an empty value normalizes to ``None`` ("missing value" semantics),
      not ``""``.

    This helper is NOT part of the simulator (which mirrors the AppleScript
    producer side only) - it captures the parser's already-documented
    consumer-side normalization so round-trip assertions reflect actual,
    accepted behaviour rather than an unrealistic byte-for-byte expectation.
    """
    stripped = raw.strip()
    return stripped if stripped != "" else None


ADVERSARIAL_NAMES = [
    pytest.param("Buy milk, eggs, bread", id="comma"),
    pytest.param('Say "hello" to Bob', id="straight-quote"),
    pytest.param("Curly “quotes” here", id="curly-quote"),
    pytest.param("Meeting at 3:00 PM", id="colon"),
    pytest.param("Line one\nLine two", id="newline"),
    pytest.param("  leading and trailing  ", id="leading-trailing-space"),
    pytest.param("", id="empty-string"),
    pytest.param("Party \U0001F389 emoji \U0001F600", id="emoji"),
    pytest.param("x" * 500, id="very-long-text"),
    pytest.param("a,b:c\"d", id="comma-colon-quote-combo"),
    pytest.param('Q1: "Growth," she said, "matters"', id="colon-comma-quote-combo"),
    pytest.param("trailing comma,", id="trailing-comma"),
    pytest.param(",leading comma", id="leading-comma"),
]

# Literal placeholder text is a separate, documented (not new) collision:
# AppleScriptParser._finalize_field unescapes §COMMA§/§QUOTE§/§COLON§
# unconditionally, so user text that happens to contain the literal
# placeholder string is indistinguishable from an escaped special character
# and gets unescaped too (test_applescript_parser.py
# ::test_name_of_only_special_chars documents this for a name of exactly
# '§COMMA§§QUOTE§§COLON§' -> ',":' pre-dating this bead). These cases assert
# the documented unescape, not byte-for-byte preservation.
LITERAL_PLACEHOLDER_CASES = [
    pytest.param("literal §COMMA§ text", "literal , text", id="literal-placeholder-comma"),
    pytest.param("literal §QUOTE§ text", 'literal " text', id="literal-placeholder-quote"),
    pytest.param("literal §COLON§ text", "literal : text", id="literal-placeholder-colon"),
]


# ---------------------------------------------------------------------------
# Step 2: round-trip tests through the production (new) parser
# ---------------------------------------------------------------------------


class TestGetTodosRoundTrip:
    """build_get_todos_script (both branches share one output format)."""

    @pytest.mark.parametrize("name", ADVERSARIAL_NAMES)
    def test_name_round_trips(self, new_manager, name):
        line = simulate_get_todos_record(
            id_="todo-1", name=name, notes="Some notes", status="open"
        )
        records = new_manager._parse_applescript_list(line)
        assert len(records) == 1
        assert records[0]["id"] == "todo-1"
        assert records[0]["name"] == _expected_round_trip(name)
        assert records[0]["notes"] == "Some notes"
        assert records[0]["status"] == "open"

    @pytest.mark.parametrize("notes", ADVERSARIAL_NAMES)
    def test_notes_round_trips(self, new_manager, notes):
        line = simulate_get_todos_record(
            id_="todo-2", name="A todo", notes=notes, status="open"
        )
        records = new_manager._parse_applescript_list(line)
        assert len(records) == 1
        assert records[0]["notes"] == _expected_round_trip(notes)

    @pytest.mark.parametrize("raw,expected", LITERAL_PLACEHOLDER_CASES)
    def test_name_with_literal_placeholder_text_unescapes(self, new_manager, raw, expected):
        line = simulate_get_todos_record(id_="todo-lit", name=raw, notes=None)
        records = new_manager._parse_applescript_list(line)
        assert records[0]["name"] == expected

    def test_notes_missing_value(self, new_manager):
        line = simulate_get_todos_record(id_="todo-3", name="No notes", notes=None)
        records = new_manager._parse_applescript_list(line)
        assert records[0]["notes"] is None

    def test_multiple_records_join_correctly(self, new_manager):
        line = join_records(
            [
                simulate_get_todos_record(id_="t1", name="One, with comma", notes="n1"),
                simulate_get_todos_record(id_="t2", name='Two "quoted"', notes="n2"),
                simulate_get_todos_record(id_="t3", name="Three: colon", notes="n3"),
            ]
        )
        records = new_manager._parse_applescript_list(line)
        assert len(records) == 3
        assert records[0]["name"] == "One, with comma"
        assert records[1]["name"] == 'Two "quoted"'
        assert records[2]["name"] == "Three: colon"

    def test_dates_round_trip_to_iso(self, new_manager):
        line = simulate_get_todos_record(
            id_="todo-4",
            name="Dated",
            notes=None,
            creation_date="Monday, January 15, 2024 at 2:30:00 PM",
            modification_date="Tuesday, February 20, 2024 at 9:05:00 AM",
            activation_date="Wednesday, March 6, 2024 at 12:00:00 AM",
            due_date="Thursday, April 4, 2024 at 11:59:00 PM",
        )
        records = new_manager._parse_applescript_list(line)
        rec = records[0]
        assert rec["creation_date"] == "2024-01-15T14:30:00"
        assert rec["modification_date"] == "2024-02-20T09:05:00"
        assert rec["activation_date"] == "2024-03-06T00:00:00"
        assert rec["due_date"] == "2024-04-04T23:59:00"

    def test_missing_dates_become_none(self, new_manager):
        line = simulate_get_todos_record(id_="todo-5", name="No dates", notes=None)
        records = new_manager._parse_applescript_list(line)
        rec = records[0]
        for field in (
            "creation_date",
            "modification_date",
            "activation_date",
            "due_date",
        ):
            assert rec[field] is None


class TestGetProjectsRoundTrip:
    """build_get_projects_script."""

    @pytest.mark.parametrize("name", ADVERSARIAL_NAMES)
    def test_name_round_trips(self, new_manager, name):
        line = simulate_get_projects_record(
            id_="proj-1", name=name, notes="Project notes", status="open"
        )
        records = new_manager._parse_applescript_list(line)
        assert len(records) == 1
        assert records[0]["id"] == "proj-1"
        assert records[0]["name"] == _expected_round_trip(name)
        assert records[0]["notes"] == "Project notes"

    @pytest.mark.parametrize("notes", ADVERSARIAL_NAMES)
    def test_notes_round_trips(self, new_manager, notes):
        line = simulate_get_projects_record(
            id_="proj-2", name="A project", notes=notes, status="open"
        )
        records = new_manager._parse_applescript_list(line)
        assert records[0]["notes"] == _expected_round_trip(notes)

    def test_single_tag_round_trips(self, new_manager):
        line = simulate_get_projects_record(
            id_="proj-3", name="Tagged", notes=None, tags=["work"]
        )
        records = new_manager._parse_applescript_list(line)
        assert records[0]["tags"] == ["work"]

    def test_no_tags_round_trips_to_empty_list(self, new_manager):
        line = simulate_get_projects_record(
            id_="proj-4", name="Untagged", notes=None, tags=None
        )
        records = new_manager._parse_applescript_list(line)
        assert records[0]["tags"] == []

    def test_contact_area_project_missing_value(self, new_manager):
        line = simulate_get_projects_record(
            id_="proj-5", name="Bare project", notes=None
        )
        records = new_manager._parse_applescript_list(line)
        rec = records[0]
        assert rec["contact"] is None
        assert rec["area"] is None
        assert rec["project"] is None

    def test_area_and_project_values_round_trip(self, new_manager):
        # NOTE (discovered while writing this contract, out of scope for
        # hq-f0w.8 - the orchestrator will file it as a separate bug):
        # reviewer-verified against real Things 3 that
        # ``(area of theProject) as string`` raises an AppleScript error
        # for a project that actually belongs to an area, so
        # build_get_projects_script's own ``on error`` handler always sets
        # areaStr to "missing value" in production - the script can never
        # actually emit a non-missing ``area:`` value. The non-missing-value
        # case exercised below is therefore synthetic coverage of the
        # *parser's* handling of an area/project/contact value, not a
        # reproduction of anything the real script can currently emit.
        line = simulate_get_projects_record(
            id_="proj-6",
            name="Nested project",
            notes=None,
            area="area-uuid-123",
            project="parent-project-uuid-456",
            contact="contact-uuid-789",
        )
        records = new_manager._parse_applescript_list(line)
        rec = records[0]
        assert rec["area"] == "area-uuid-123"
        assert rec["project"] == "parent-project-uuid-456"
        assert rec["contact"] == "contact-uuid-789"

    @pytest.mark.xfail(strict=True, reason=(
        "Pre-existing bug (out of scope for hq-f0w.8, found by hq-f0w.1's "
        "reviewer): Things 3's 'tag names' is a text property that comes "
        "back already comma-space-joined (e.g. 'work, urgent'), and "
        "build_get_projects_script applies NO §COMMA§/§QUOTE§/§COLON§ "
        "protection to it (queries.py build_get_projects_script, "
        "tagNamesStr assembly). The parser's VALUE-state comma-splitting "
        "therefore treats the second tag as the start of a brand new bogus "
        "field instead of a second list item, corrupting the record."
    ))
    def test_multiple_tags_round_trip_KNOWN_BUG(self, new_manager):
        line = simulate_get_projects_record(
            id_="proj-7", name="Multi-tagged", notes=None, tags=["work", "urgent"]
        )
        records = new_manager._parse_applescript_list(line)
        assert len(records) == 1
        assert records[0]["tags"] == ["work", "urgent"]

    @pytest.mark.xfail(strict=True, reason=(
        "Pre-existing bug (out of scope for hq-f0w.8, found by hq-f0w.1's "
        "reviewer): same root cause as test_multiple_tags_round_trip_KNOWN_BUG "
        "- build_get_projects_script's unprotected, unquoted multi-tag "
        "tag_names value corrupts the parser's field-boundary tracking, and "
        "because the projects script's date fields are ALSO emitted with no "
        "§COLON§/§COMMA§ protection (unlike build_get_todos_script), the "
        "very next field - creation_date - is swallowed by that same "
        "corruption instead of round-tripping to its ISO value. This pins "
        "the cascading failure exactly as queries.py would actually emit it "
        "(tag_names immediately followed by creation_date), confirming the "
        "date-field protection gap is not merely theoretical."
    ))
    def test_unprotected_dates_after_multitag_KNOWN_BUG(self, new_manager):
        line = simulate_get_projects_record(
            id_="proj-8",
            name="Dated project",
            notes=None,
            tags=["work", "urgent"],
            creation_date="Monday, January 15, 2024 at 2:30:00 PM",
        )
        records = new_manager._parse_applescript_list(line)
        assert len(records) == 1
        assert records[0]["tags"] == ["work", "urgent"]
        assert records[0]["creation_date"] == "2024-01-15T14:30:00"


class TestGetAreasRoundTrip:
    """build_get_areas_script."""

    @pytest.mark.parametrize("name", ADVERSARIAL_NAMES)
    def test_name_round_trips(self, new_manager, name):
        line = simulate_get_areas_record(id_="area-1", name=name)
        records = new_manager._parse_applescript_list(line)
        assert len(records) == 1
        assert records[0]["id"] == "area-1"
        assert records[0]["name"] == _expected_round_trip(name)

    def test_multiple_areas_join_correctly(self, new_manager):
        line = join_records(
            [
                simulate_get_areas_record(id_="a1", name="Work, Home"),
                simulate_get_areas_record(id_="a2", name='Side "Projects"'),
            ]
        )
        records = new_manager._parse_applescript_list(line)
        assert len(records) == 2
        assert records[0]["name"] == "Work, Home"
        assert records[1]["name"] == 'Side "Projects"'


class TestBracesKnownBug:
    """Pre-existing parser bug: braces in scalar text fields are dropped."""

    @pytest.mark.xfail(strict=True, reason=(
        "Pre-existing bug (out of scope for hq-f0w.8, found by hq-f0w.1's "
        "reviewer): AppleScriptParser._process_value_char() treats any '{' "
        "in a scalar VALUE as the start of a LIST, consuming (and dropping) "
        "the surrounding braces even for the 'name'/'notes' fields that "
        "queries.py deliberately never protects against literal braces. "
        "'a {b} c' comes back as 'a b c' - the braces vanish silently "
        "rather than raising or being preserved."
    ))
    def test_name_with_braces_round_trips_KNOWN_BUG(self, new_manager):
        line = simulate_get_todos_record(id_="todo-brace", name="a {b} c", notes=None)
        records = new_manager._parse_applescript_list(line)
        assert records[0]["name"] == "a {b} c"


# ---------------------------------------------------------------------------
# Step 3: same cases through the legacy parser path
# ---------------------------------------------------------------------------


# Legacy-parser placeholder-leak checks reuse the same adversarial catalogue
# used for the new-parser round-trip tests above (literal-placeholder cases
# are covered separately - see test_name_with_literal_placeholder_text_unescapes).
NO_PLACEHOLDER_LEAK_NAMES = ADVERSARIAL_NAMES


class TestLegacyParserNoPlaceholderLeak:
    """The legacy string-manipulation parser must never leak
    §COMMA§/§QUOTE§/§COLON§ placeholder text into tool output for
    already-supported field/value combinations.
    """

    @pytest.mark.parametrize("name", NO_PLACEHOLDER_LEAK_NAMES)
    def test_todos_name_no_placeholder_leak(self, legacy_manager, name):
        line = simulate_get_todos_record(id_="todo-legacy", name=name, notes="notes")
        records = legacy_manager._parse_applescript_list(line)
        assert len(records) == 1
        for placeholder in ("§COMMA§", "§QUOTE§", "§COLON§"):
            assert placeholder not in (records[0]["name"] or "")

    @pytest.mark.parametrize("notes", NO_PLACEHOLDER_LEAK_NAMES)
    def test_todos_notes_no_placeholder_leak(self, legacy_manager, notes):
        line = simulate_get_todos_record(id_="todo-legacy2", name="title", notes=notes)
        records = legacy_manager._parse_applescript_list(line)
        value = records[0]["notes"] or ""
        for placeholder in ("§COMMA§", "§QUOTE§", "§COLON§"):
            assert placeholder not in value

    @pytest.mark.parametrize("name", NO_PLACEHOLDER_LEAK_NAMES)
    def test_areas_name_no_placeholder_leak(self, legacy_manager, name):
        line = simulate_get_areas_record(id_="area-legacy", name=name)
        records = legacy_manager._parse_applescript_list(line)
        value = records[0]["name"] or ""
        for placeholder in ("§COMMA§", "§QUOTE§", "§COLON§"):
            assert placeholder not in value

    def test_todos_name_and_notes_match_new_parser(self, legacy_manager, new_manager):
        """Sanity cross-check: for a representative comma+quote+colon case,
        both parsers agree on the plain-text (non-date) fields.
        """
        line = simulate_get_todos_record(
            id_="todo-cmp", name='Q1: "Growth," she said', notes="Notes, with: stuff"
        )
        legacy = legacy_manager._parse_applescript_list(line)[0]
        new = new_manager._parse_applescript_list(line)[0]
        assert legacy["id"] == new["id"] == "todo-cmp"
        assert legacy["name"] == new["name"] == 'Q1: "Growth," she said'
        assert legacy["notes"] == new["notes"] == "Notes, with: stuff"

    def test_projects_completion_and_cancellation_date_known_gap(self, legacy_manager):
        """Documented pre-existing legacy gap (test_parser_comparison.py
        TestParserComparison.test_new_parser_fixes_completion_date_bug /
        ..._cancellation_date_bug): completion_date/cancellation_date are
        NOT in the legacy parser's date-field list, so they fall through to
        the generic string branch and are returned as raw (non-ISO)
        strings rather than being date-parsed. We tolerate that behaviour
        here (assert no placeholder leak + raw string is returned) rather
        than xfailing the whole case, per the bead notes - this is a known,
        already-documented gap, not a new finding.
        """
        line = simulate_get_projects_record(
            id_="proj-legacy-dates",
            name="Dated",
            notes=None,
            completion_date="Monday, January 15, 2024 at 2:30:00 PM",
            cancellation_date="Tuesday, February 20, 2024 at 9:05:00 AM",
        )
        records = legacy_manager._parse_applescript_list(line)
        rec = records[0]
        # Not ISO-formatted (known gap) - but no placeholder leak, and no
        # exception. completion_date/cancellation_date are not protected
        # by the projects script in the first place (see docstring above),
        # so nothing to unescape either way.
        assert rec["completion_date"] == "Monday, January 15, 2024 at 2:30:00 PM"
        assert rec["cancellation_date"] == "Tuesday, February 20, 2024 at 9:05:00 AM"
        for placeholder in ("§COMMA§", "§QUOTE§", "§COLON§"):
            assert placeholder not in rec["completion_date"]
            assert placeholder not in rec["cancellation_date"]


# ---------------------------------------------------------------------------
# Step 4: drift guard
# ---------------------------------------------------------------------------


def _extract_field_names_from_script(script: str) -> set[str]:
    """Extract every ``, <field>:`` (or leading ``"id:"``) literal field name
    that a query-builder script writes into its output line, via regex over
    the actual script source text - independent of the simulator.

    Matches both the record-leading ``"id:" & (id of theTodo)`` form and the
    ``, name:" & nameStr`` continuation form used throughout queries.py.
    """
    # Field names appear as literal text immediately following a '"' that is
    # itself immediately preceded by either the start of a concatenation
    # ('"id:"') or a ', ' separator ('", name:"' / ", name:"). We match the
    # literal string segments queries.py builds its output with, e.g.
    # '"id:"', '", name:"', '", notes:"', etc. The character class is
    # deliberately wide ([A-Za-z0-9_]+, not just [a-z_]+) so this stays
    # correct even if a future field name uses a digit or mixed case.
    pattern = re.compile(r'"(?:,\s*)?([A-Za-z0-9_]+):"')
    return set(pattern.findall(script))


def _extract_field_names_from_output(line: str) -> set[str]:
    """Extract every top-level ``<field>:`` key from a *simulated output
    line* (not script source), via the same regex-over-text approach as
    ``_extract_field_names_from_script`` - but applied to what a simulator
    function actually produced for a plain, non-adversarial dummy record.

    This makes the drift guard compare the real script's field set against
    what the simulator *actually emits*, not a hand-maintained literal set -
    so forgetting to update a simulator function after changing its return
    statement (not just forgetting to update queries.py) also fails the
    guard, closing the last manual-sync gap.
    """
    pattern = re.compile(r'(?:^|,\s*)([A-Za-z0-9_]+):')
    return set(pattern.findall(line))


class TestDriftGuard:
    """If someone adds/renames a field in queries.py without updating the
    simulator functions above, these tests fail with a clear message
    instead of the round-trip tests silently continuing to pass on a
    now-incomplete simulation.

    The expected field set for each builder is derived from the
    simulator's own output (a dummy record with plain, non-adversarial
    values, run through ``_extract_field_names_from_output``) rather than a
    hand-maintained literal set, so forgetting to update a simulator
    function's return statement - not just forgetting to update
    queries.py - also fails the guard.
    """

    def test_get_todos_script_fields_match_simulator(self):
        queries = AppleScriptQueries()
        script = queries.build_get_todos_script(project_uuid="proj-uuid")
        script_fields = _extract_field_names_from_script(script)
        dummy_line = simulate_get_todos_record(id_="x", name="n", notes="notes")
        simulator_fields = _extract_field_names_from_output(dummy_line)
        assert script_fields == simulator_fields, (
            "build_get_todos_script (project_uuid branch) field names "
            f"changed: script now emits {script_fields}, but "
            f"simulate_get_todos_record now emits {simulator_fields}. "
            "Update simulate_get_todos_record to match queries.py."
        )

    def test_get_todos_script_no_project_uuid_fields_match_simulator(self):
        queries = AppleScriptQueries()
        script = queries.build_get_todos_script(project_uuid=None)
        script_fields = _extract_field_names_from_script(script)
        dummy_line = simulate_get_todos_record(id_="x", name="n", notes="notes")
        simulator_fields = _extract_field_names_from_output(dummy_line)
        assert script_fields == simulator_fields, (
            "build_get_todos_script (no project_uuid branch) field names "
            f"changed: script now emits {script_fields}, but "
            f"simulate_get_todos_record now emits {simulator_fields}. "
            "Update simulate_get_todos_record to match queries.py."
        )

    def test_get_projects_script_fields_match_simulator(self):
        queries = AppleScriptQueries()
        script = queries.build_get_projects_script()
        script_fields = _extract_field_names_from_script(script)
        dummy_line = simulate_get_projects_record(id_="x", name="n", notes="notes")
        simulator_fields = _extract_field_names_from_output(dummy_line)
        assert script_fields == simulator_fields, (
            "build_get_projects_script field names changed: script now "
            f"emits {script_fields}, but simulate_get_projects_record now "
            f"emits {simulator_fields}. Update simulate_get_projects_record "
            "to match queries.py."
        )

    def test_get_areas_script_fields_match_simulator(self):
        queries = AppleScriptQueries()
        script = queries.build_get_areas_script()
        script_fields = _extract_field_names_from_script(script)
        dummy_line = simulate_get_areas_record(id_="x", name="n")
        simulator_fields = _extract_field_names_from_output(dummy_line)
        assert script_fields == simulator_fields, (
            "build_get_areas_script field names changed: script now emits "
            f"{script_fields}, but simulate_get_areas_record now emits "
            f"{simulator_fields}. Update simulate_get_areas_record to "
            "match queries.py."
        )

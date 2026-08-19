"""Tests for AppleScriptTemplates string escaping (utils/applescript_utils.py).

Covers hq-f0w.2: a single shared escaper that preserves newlines (instead of
collapsing them to spaces) and emits balanced-quote AppleScript literals.
"""

import re

import pytest

from things_mcp.utils.applescript_utils import AppleScriptTemplates
from things_mcp.tools import ThingsTools
from things_mcp.services.validation_service import ValidationService


def count_unescaped_quotes(script: str) -> int:
    """Count double quotes in `script` that are not preceded by a backslash.

    A cheap, generic balanced-quotes check: AppleScript string literals are
    delimited by unescaped double quotes, so a syntactically valid script
    must contain an even number of them. This catches the C1-class bug
    (escape().strip('"') leaving a dangling backslash that eats the closing
    quote) without needing a full AppleScript parser.
    """
    # Count '"' chars whose preceding backslash count is even (i.e. the
    # quote itself is not escaped).
    count = 0
    i = 0
    while i < len(script):
        if script[i] == '"':
            # Count immediately preceding backslashes.
            j = i - 1
            backslashes = 0
            while j >= 0 and script[j] == '\\':
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                count += 1
        i += 1
    return count


def assert_balanced_quotes(script: str) -> None:
    """Assert that `script` has an even number of unescaped double quotes."""
    n = count_unescaped_quotes(script)
    assert n % 2 == 0, f"Unbalanced quotes ({n} unescaped) in script:\n{script}"


class TestEscapeStringInner:
    """Tests for AppleScriptTemplates.escape_string_inner (unquoted payload)."""

    def test_empty_string(self):
        assert AppleScriptTemplates.escape_string_inner('') == ''

    def test_single_newline(self):
        assert AppleScriptTemplates.escape_string_inner('a\nb') == 'a\\nb'

    def test_double_newline(self):
        assert AppleScriptTemplates.escape_string_inner('a\n\nb') == 'a\\n\\nb'

    def test_crlf(self):
        assert AppleScriptTemplates.escape_string_inner('a\r\nb') == 'a\\r\\nb'

    def test_tab(self):
        assert AppleScriptTemplates.escape_string_inner('a\tb') == 'a\\tb'

    def test_mixed_quotes_and_newlines(self):
        result = AppleScriptTemplates.escape_string_inner('He said "hi"\nThen left')
        assert result == 'He said \\"hi\\"\\nThen left'

    def test_trailing_double_quote(self):
        """A value ending in a double quote must not leave a dangling backslash."""
        result = AppleScriptTemplates.escape_string_inner('Say "hi"')
        assert result == 'Say \\"hi\\"'
        # Wrapped in quotes, the literal must still be balanced.
        literal = f'"{result}"'
        assert_balanced_quotes(literal)

    def test_backslash_before_quote(self):
        result = AppleScriptTemplates.escape_string_inner('a"b\\c')
        assert result == 'a\\"b\\\\c'

    def test_injection_attempt_stays_plain_string(self):
        """A crafted value must not be able to close the string literal early."""
        payload = '" & do shell script "echo pwned" & "'
        escaped = AppleScriptTemplates.escape_string_inner(payload)
        literal = f'"{escaped}"'
        assert_balanced_quotes(literal)
        # The literal must contain no unescaped quote before its very end,
        # i.e. the payload cannot break out of the string context.
        inner = literal[1:-1]
        assert count_unescaped_quotes(inner) == 0

    def test_other_control_chars_stripped(self):
        result = AppleScriptTemplates.escape_string_inner('a\x01\x02b')
        assert result == 'ab'


class TestEscapeString:
    """Tests for AppleScriptTemplates.escape_string (quoted literal)."""

    def test_empty_string(self):
        assert AppleScriptTemplates.escape_string('') == '""'

    def test_none_like_falsy(self):
        assert AppleScriptTemplates.escape_string(None) == '""'

    def test_line_one_line_two(self):
        result = AppleScriptTemplates.escape_string('Line one.\n\nLine two.')
        assert result == '"Line one.\\n\\nLine two."'

    def test_quote_and_backslash(self):
        result = AppleScriptTemplates.escape_string('a"b\\c')
        assert result == '"a\\"b\\\\c"'

    def test_result_is_wrapped_in_quotes(self):
        result = AppleScriptTemplates.escape_string('plain text')
        assert result.startswith('"') and result.endswith('"')

    def test_no_raw_newline_in_output(self):
        result = AppleScriptTemplates.escape_string('a\nb\rc\td')
        assert '\n' not in result
        assert '\r' not in result
        assert '\t' not in result

    @pytest.mark.parametrize("text", [
        'Line one.\n\nLine two.\n\nLine three.',
        'a\r\nb\r\nc',
        'trailing quote"',
        'tab\there',
        'mix "quotes" and\nnewlines',
    ])
    def test_balanced_quotes_for_various_inputs(self, text):
        assert_balanced_quotes(AppleScriptTemplates.escape_string(text))


class TestScriptBuildersPreserveNewlinesAndBalance:
    """Builder-level tests: generated scripts carry escaped newlines and
    remain balanced-quote for every write path that touches notes/title/tags.
    """

    MULTI_LINE_NOTES = "Line one.\n\nLine two.\n\nLine three."
    ESCAPED_MULTI_LINE_NOTES = "Line one.\\n\\nLine two.\\n\\nLine three."

    @pytest.fixture
    def tools(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_add_todo_script_has_escaped_notes_and_balanced_quotes(self, tools, mock_applescript_manager):
        mock_applescript_manager.set_mock_response("default", {
            "success": True, "output": "todo-1", "error": None
        })
        result = await tools.add_todo(title="Test", notes=self.MULTI_LINE_NOTES)
        assert result["success"] is True

        script = mock_applescript_manager.execution_calls[0]["script"]
        assert self.ESCAPED_MULTI_LINE_NOTES in script
        assert_balanced_quotes(script)

    @pytest.mark.asyncio
    async def test_update_todo_script_has_escaped_notes_and_balanced_quotes(self, tools, mock_applescript_manager):
        mock_applescript_manager.set_mock_response("default", {
            "success": True, "output": "updated", "error": None
        })
        result = await tools.update_todo(todo_id="todo-1", notes=self.MULTI_LINE_NOTES)
        assert result["success"] is True

        script = mock_applescript_manager.execution_calls[-1]["script"]
        assert self.ESCAPED_MULTI_LINE_NOTES in script
        assert_balanced_quotes(script)

    @pytest.mark.asyncio
    async def test_add_project_script_has_escaped_notes_and_balanced_quotes(self, tools, mock_applescript_manager):
        mock_applescript_manager.set_mock_response("default", {
            "success": True, "output": "project-1", "error": None
        })
        result = await tools.add_project(title="Test Project", notes=self.MULTI_LINE_NOTES)
        assert result["success"] is True

        script = mock_applescript_manager.execution_calls[-1]["script"]
        assert self.ESCAPED_MULTI_LINE_NOTES in script
        assert_balanced_quotes(script)

    @pytest.mark.asyncio
    async def test_update_project_script_has_escaped_notes_and_balanced_quotes(self, tools, mock_applescript_manager):
        mock_applescript_manager.set_mock_response("default", {
            "success": True, "output": "updated", "error": None
        })
        result = await tools.update_project(project_id="project-1", notes=self.MULTI_LINE_NOTES)
        assert result["success"] is True

        script = mock_applescript_manager.execution_calls[-1]["script"]
        assert self.ESCAPED_MULTI_LINE_NOTES in script
        assert_balanced_quotes(script)

    @pytest.mark.asyncio
    async def test_bulk_update_todos_trailing_quote_title_and_multiline_notes(self, tools, mock_applescript_manager):
        """C1 regression: a title ending in a double quote must not leave a
        dangling backslash that eats the closing quote of the AppleScript
        string literal.
        """
        mock_applescript_manager.set_mock_response("default", {
            "success": True, "output": "successCount:1, errors:{}", "error": None
        })
        result = await tools.bulk_update_todos(
            todo_ids=["todo-1"],
            title='Say "hi"',
            notes="a\nb",
        )
        assert result["success"] is True

        script = mock_applescript_manager.execution_calls[-1]["script"]
        assert_balanced_quotes(script)
        # Title's embedded quotes must be escaped, not left dangling.
        assert 'Say \\"hi\\"' in script
        # Notes newline preserved as escape sequence.
        assert "a\\nb" in script

    @pytest.mark.asyncio
    async def test_add_tags_script_balanced_quotes(self, tools, mock_applescript_manager):
        mock_applescript_manager.set_mock_response("default", {
            "success": True, "output": "existing", "error": None
        })
        result = await tools.add_tags(todo_id="todo-1", tags=['Say "hi"'])
        assert result["success"] is True

        # The set-tag-names call is the final AppleScript execution.
        script = mock_applescript_manager.execution_calls[-1]["script"]
        assert_balanced_quotes(script)

    @pytest.mark.asyncio
    async def test_remove_tags_script_balanced_quotes(self, tools, mock_applescript_manager):
        mock_applescript_manager.set_mock_response("default", {
            "success": True, "output": 'existing, Say "hi"', "error": None
        })
        result = await tools.remove_tags(todo_id="todo-1", tags=["existing"])
        assert result["success"] is True

        script = mock_applescript_manager.execution_calls[-1]["script"]
        assert_balanced_quotes(script)


class TestValidationServiceEscapeIdUsesSharedEscaper:
    """hq-f0w.21: ValidationService._escape_id() used to build its own
    backslash/quote escaping inline. It now delegates to
    AppleScriptTemplates.escape_string_inner.
    """

    @pytest.fixture
    def service(self, mock_applescript_manager):
        return ValidationService(mock_applescript_manager)

    def test_escape_id_matches_shared_escaper(self, service):
        raw = 'a"b\\c\nd'
        assert service._escape_id(raw) == AppleScriptTemplates.escape_string_inner(raw)
        # Old inline escaper (`.replace('\\\\', ...).replace('"', ...)`) never
        # touched newlines - a newline is what actually distinguishes the
        # shared escaper's output from the old code's.
        assert '\\n' in service._escape_id(raw)

    def test_escape_id_empty_string(self, service):
        assert service._escape_id("") == ""

    @pytest.mark.asyncio
    async def test_validate_todo_id_script_balanced_quotes(self, service, mock_applescript_manager):
        mock_applescript_manager.set_mock_response("default", {
            "success": True, "output": "EXISTS", "error": None
        })
        result = await service.validate_todo_id('weird"id\\here\nx')
        assert result["valid"] is True

        script = mock_applescript_manager.execution_calls[-1]["script"]
        assert_balanced_quotes(script)
        assert 'weird\\"id\\\\here\\nx' in script
        # The newline must survive as the escape sequence \\n, not a raw
        # newline, inside the `to do id "..."` literal.
        literal = script.split('to do id "')[1].split('"')[0]
        assert '\n' not in literal

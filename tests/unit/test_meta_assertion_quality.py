"""Meta-test (hq-f0w.13): guard against 'success-only' write-path tests.

Why: tests/conftest.py MockAppleScriptManager returns {"success": True} for
any script it is handed - it does not validate the AppleScript/URL payload at
all. A test that mutates state (add_todo, update_todo, ...) and then only
asserts `result["success"] is True` (or bare truthiness of the result dict)
provides zero protection against bugs in what was actually sent to Things -
e.g. the newline-collapse regression that shipped with a "passing"
test_newlines_in_notes, because that test never inspected the emitted script.

This is a static (AST) scan of tests/unit/**/test_*.py: for every test
function that calls one of the known mutating tool/operation names, check
whether every assert statement in that function references only
success/result truthiness (see _is_success_only_assert). If ALL of a test's
asserts are success-only AND the function calls a mutating operation, the
test is flagged - unless it appears in ALLOWLIST with a reason.

This test intentionally does not know anything about *how* to fix a flagged
test (that's a per-test retrofit); it only detects the pattern.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Iterable

import pytest

TESTS_UNIT_DIR = pathlib.Path(__file__).resolve().parent

# Tool/operation names whose invocation marks a test as exercising a mutating
# (write) code path. Matched against the function name of any Call node in
# the test body (attribute calls like `tools.add_todo(...)` match on the
# trailing attribute name `add_todo`).
MUTATING_CALL_NAMES = {
    "add_todo",
    "update_todo",
    "add_project",
    "update_project",
    "add_area",
    "update_area",
    "add_tags",
    "remove_tags",
    "bulk_update_todos",
    "move_record",
    "bulk_move_records",
    "add_checklist_items",
    "prepend_checklist_items",
    "replace_checklist_items",
    "delete_todo",
    "create_tag",
}

# Names that, when referenced (Name or Attribute) inside an assert's test
# expression, count as "success/result truthiness" rather than a real
# assertion on emitted content.
SUCCESS_ONLY_NAMES = {"success", "result", "results", "response", "res"}

# (file, test_name) -> reason. Tests whose *entire purpose* is to check the
# success envelope shape (not the emitted script/URL) are legitimately
# success-only and are excluded from the failure list.
ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "test_tag_management_comprehensive.py",
        "test_empty_tag_string",
    ): "asserts add_tags(tags='') is rejected as NO_VALID_TAGS before any AppleScript is built - there is no emitted script to assert on for this error path",
    # test_with_token_succeeds is defined identically in three sibling
    # classes (TestAddChecklistItemsAuthGate, TestPrependChecklistItemsAuthGate,
    # TestReplaceChecklistItemsAuthGate) - each dict key matches all three
    # since the scanner is keyed by (file, function name) only.
    (
        "test_url_scheme_auth_gate.py",
        "test_with_token_succeeds",
    ): "hq-f0w.31: with a valid auth token, add/prepend/replace_checklist_items "
       "just proceeds to the (mocked) URL-scheme call and asserts only "
       "result['success'] is True - the point of the test is the auth-gate "
       "pass-through, not the checklist URL content (covered elsewhere by "
       "the checklist-item retrofits in test_edge_cases.py). Needs a "
       "follow-up bead to also assert on the URL scheme call if desired.",
}


def _dotted_or_attr_name(func_node: ast.AST) -> str | None:
    """Return the callable's simple name for ast.Name or ast.Attribute calls."""
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        return func_node.attr
    return None


def _calls_mutating_operation(func_def: ast.AST) -> bool:
    for node in ast.walk(func_def):
        if isinstance(node, ast.Call):
            name = _dotted_or_attr_name(node.func)
            if name in MUTATING_CALL_NAMES:
                return True
    return False


# Subscript/attribute keys that, together with a SUCCESS_ONLY_NAMES root,
# still count as "success-only" (they're part of the success/failure
# envelope shape itself, not a check on emitted script/URL content).
SUCCESS_ONLY_KEYS = {"success"}


def _is_success_only_compare_or_subscript(node: ast.AST) -> bool:
    """True if `node` is one of the specific success-only shapes:

    - bare `result` / `not result` (a Name whose id is in SUCCESS_ONLY_NAMES)
    - `result["success"]` / `result.get("success")` (Subscript/Call-of-.get
      on a SUCCESS_ONLY_NAMES root, keyed/argued by the literal "success")
    - `"success" in result` (Compare with an `in`/`not in` op)

    Any other string Constant subscript/key (e.g. "error", "tag_info",
    "updated_count") or any bare method call (mock.assert_called_once(),
    assert_balanced_quotes(...), etc.) is NOT success-only - it's a real
    assertion on something more specific than the success envelope.
    """
    # Bare `result` / `not result`
    if isinstance(node, ast.Name):
        return node.id in SUCCESS_ONLY_NAMES
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _is_success_only_compare_or_subscript(node.operand)

    # `result["success"]`
    if isinstance(node, ast.Subscript):
        root = node.value
        if isinstance(root, ast.Name) and root.id in SUCCESS_ONLY_NAMES:
            key_node = node.slice
            if isinstance(key_node, ast.Constant) and key_node.value in SUCCESS_ONLY_KEYS:
                return True
        return False

    # `result.get("success")`
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Name)
            and func.value.id in SUCCESS_ONLY_NAMES
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in SUCCESS_ONLY_KEYS
        ):
            return True
        return False

    # `"success" in result` / `"success" not in result`
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        op = node.ops[0]
        left = node.left
        right = node.comparators[0]

        if isinstance(op, (ast.In, ast.NotIn)):
            if (
                isinstance(left, ast.Constant)
                and left.value in SUCCESS_ONLY_KEYS
                and isinstance(right, ast.Name)
                and right.id in SUCCESS_ONLY_NAMES
            ):
                return True
            return False

        # `result["success"] is True` / `result["success"] == False` /
        # `result.get("success") is None` and the symmetric
        # `True == result["success"]` form - one side must itself be a
        # recognized success-only shape (bare name/subscript/.get), and the
        # other side must be a plain literal comparator (True/False/None),
        # not something that could carry script content.
        if isinstance(op, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)):
            def _is_plain_literal(n: ast.AST) -> bool:
                return isinstance(n, ast.Constant) and n.value in (True, False, None)

            left_is_success_shape = isinstance(
                left, (ast.Name, ast.Subscript, ast.Call)
            ) and _is_success_only_compare_or_subscript(left)
            right_is_success_shape = isinstance(
                right, (ast.Name, ast.Subscript, ast.Call)
            ) and _is_success_only_compare_or_subscript(right)

            if left_is_success_shape and _is_plain_literal(right):
                return True
            if right_is_success_shape and _is_plain_literal(left):
                return True
        return False

    return False


def _expr_references_only_success_names(expr: ast.AST) -> bool:
    """True if `expr` is a recognized success-only shape (see
    _is_success_only_compare_or_subscript), or a boolean combination
    (and/or) of such shapes, or a pure-literal expression with no Name
    references at all (e.g. `assert True`).

    Anything else - a reference to "error"/"tag_info"/"updated_count"/any
    other non-"success" key, a call to execution_calls/url_scheme_calls,
    a mock assert_* method, etc. - is NOT success-only.
    """
    if isinstance(expr, ast.BoolOp):
        return all(_expr_references_only_success_names(v) for v in expr.values)

    referenced_names = {n.id for n in ast.walk(expr) if isinstance(n, ast.Name)}
    if not referenced_names:
        # Pure literal assert (e.g. `assert True`) - not a script assertion,
        # but also not what we're hunting for; treat as non-flagging so it
        # doesn't force a false positive on unrelated sanity asserts.
        return True

    return _is_success_only_compare_or_subscript(expr)


def _is_success_only_assert(assert_node: ast.Assert) -> bool:
    return _expr_references_only_success_names(assert_node.test)


def _is_assert_style_call(node: ast.AST) -> bool:
    """True if `node` is a bare expression-statement Call whose callable
    name (Name or trailing Attribute) starts with 'assert' - e.g.
    `mock.assert_called_once()`, `mock.assert_not_awaited()`,
    `assert_balanced_quotes(script)`. These are real assertions (often the
    *only* assertion in a test that uses unittest.mock's assert_* API or a
    helper predicate function instead of a bare `assert` statement) and
    must never be treated as success-only, regardless of what they
    reference.
    """
    if not isinstance(node, ast.Expr):
        return False
    call = node.value
    if not isinstance(call, ast.Call):
        return False
    name = _dotted_or_attr_name(call.func)
    return bool(name) and name.startswith("assert")


def _find_test_functions(tree: ast.Module) -> Iterable[ast.AsyncFunctionDef | ast.FunctionDef]:
    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found: list[ast.AsyncFunctionDef | ast.FunctionDef] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name.startswith("test_"):
                self.found.append(node)
            # Do not recurse into nested defs for top-level scanning purposes
            # beyond what ast.walk would do anyway; NodeVisitor.generic_visit
            # still walks children, which is fine since nested test-shaped
            # helpers are rare and harmless to also catch.
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            if node.name.startswith("test_"):
                self.found.append(node)
            self.generic_visit(node)

    visitor = _Visitor()
    visitor.visit(tree)
    return visitor.found


def _asserts_in_function_body(func_def: ast.AST) -> list[ast.Assert | ast.Expr]:
    """Collect the "assertion statements" belonging to `func_def`, not to
    any nested function/class defined inside it (so a nested helper's
    asserts don't get attributed to the outer test). Two shapes count:

    - ast.Assert nodes (the `assert ...` statement)
    - ast.Expr statements whose value is a bare Call to something named
      'assert*' (unittest.mock's mock.assert_called_once() /
      assert_not_called() / assert_not_awaited() / etc., or a helper
      predicate like assert_balanced_quotes(script)) - these are real
      assertions even though they're not `assert` statements.
    """
    asserts: list[ast.Assert | ast.Expr] = []

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node is func_def:
                self.generic_visit(node)
            # else: nested def, skip descending

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            if node is func_def:
                self.generic_visit(node)

        def visit_Assert(self, node: ast.Assert) -> None:
            asserts.append(node)
            self.generic_visit(node)

        def visit_Expr(self, node: ast.Expr) -> None:
            if _is_assert_style_call(node):
                asserts.append(node)
            self.generic_visit(node)

    _Visitor().visit(func_def)
    return asserts


def _is_success_only_statement(stmt: ast.Assert | ast.Expr) -> bool:
    """True if `stmt` is success-only. An assert_*-style bare call
    expression (mock.assert_called_once(), assert_balanced_quotes(script),
    etc.) is never success-only - it is always a real, specific assertion."""
    if isinstance(stmt, ast.Expr):
        # By construction (see _asserts_in_function_body), any ast.Expr
        # collected here already passed _is_assert_style_call.
        return False
    return _is_success_only_assert(stmt)


def _scan_file(path: pathlib.Path) -> list[str]:
    """Return a list of flagged test names (not yet allowlist-filtered)."""
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    flagged: list[str] = []
    for func_def in _find_test_functions(tree):
        if not _calls_mutating_operation(func_def):
            continue
        asserts = _asserts_in_function_body(func_def)
        if not asserts:
            # No asserts at all is a different problem, not this one.
            continue
        if all(_is_success_only_statement(a) for a in asserts):
            flagged.append(func_def.name)
    return flagged


def _all_flagged() -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    for path in sorted(TESTS_UNIT_DIR.glob("test_*.py")):
        if path.name == "test_meta_assertion_quality.py":
            continue
        flagged = _scan_file(path)
        if flagged:
            results[path.name] = flagged
    return results


def test_no_success_only_write_tests_outside_allowlist():
    """Every mutating-operation test must assert on more than just success/
    result truthiness, unless explicitly allowlisted with a reason."""
    all_flagged = _all_flagged()

    violations = []
    for filename, test_names in all_flagged.items():
        for test_name in test_names:
            if (filename, test_name) in ALLOWLIST:
                continue
            violations.append(f"{filename}::{test_name}")

    assert not violations, (
        "The following tests call a mutating tool/operation but every assert "
        "references only success/result truthiness - they do not verify what "
        "was actually sent to Things (AppleScript script / URL scheme). "
        "Either add an assertion on mock_applescript_manager.execution_calls "
        "/ url_scheme_calls content, or add an ALLOWLIST entry with a reason "
        "if the test's purpose really is only the success envelope:\n  "
        + "\n  ".join(violations)
    )


def test_allowlist_entries_are_still_flagged():
    """Guard against a stale ALLOWLIST: every entry must correspond to a test
    that (a) exists and (b) is still detected as success-only by the scanner,
    otherwise the entry is dead weight (or worse, hiding that the test was
    retrofitted and the entry should be removed)."""
    all_flagged = _all_flagged()
    stale = []
    for (filename, test_name), _reason in ALLOWLIST.items():
        if test_name not in all_flagged.get(filename, []):
            stale.append(f"{filename}::{test_name}")

    assert not stale, (
        "The following ALLOWLIST entries no longer match a success-only test "
        "(the test may have been retrofitted, renamed, or removed) - remove "
        "the stale entry:\n  " + "\n  ".join(stale)
    )


def test_allowlist_entries_have_nonempty_reasons():
    empty = [f"{f}::{n}" for (f, n), reason in ALLOWLIST.items() if not reason or not reason.strip()]
    assert not empty, f"ALLOWLIST entries missing a reason: {empty}"


if __name__ == "__main__":
    import sys

    flagged = _all_flagged()
    total = sum(len(v) for v in flagged.values())
    print(f"Found {total} success-only write test(s) across {len(flagged)} file(s):")
    for filename, names in flagged.items():
        print(f"  {filename}:")
        for name in names:
            marker = " (allowlisted)" if (filename, name) in ALLOWLIST else ""
            print(f"    - {name}{marker}")
    sys.exit(0)

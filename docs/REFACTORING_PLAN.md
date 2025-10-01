# Things 3 MCP Server - Code Quality Refactoring Plan

**Created:** 2025-10-01
**Version:** 1.2.7
**Status:** Planning Phase
**Estimated Duration:** 10 weeks (99 hours)

## Executive Summary

This document provides a comprehensive SPARC-based plan for improving code quality in the Things 3 MCP Server while maintaining 100% backwards compatibility. The strategy focuses on incremental, low-risk improvements prioritized by value and safety.

**Current State:**
- 5 bare `except:` blocks hiding errors
- 19 functions >100 lines (largest: 214 lines)
- 4 files >1,300 lines (largest: 1,657 lines)
- 31 duplicate AppleScript invocations
- Complex 193-line string parser using placeholder substitution

**Target State:**
- Zero bare except blocks
- All functions <100 lines (target: 80)
- All files <1,000 lines (target: 500)
- Consolidated AppleScript patterns
- State machine-based parser
- 100% test coverage maintained (330+ tests)

---

## Specification - What "Good" Looks Like

### Code Quality Standards

**Function Complexity:**
- **Target:** Maximum 80 lines per function
- **Hard Limit:** 100 lines
- **Cyclomatic Complexity:** Maximum 10 branches per function
- **Rationale:** Functions >80 lines are difficult to understand and test

**Error Handling:**
- Zero bare `except:` blocks - Always specify exception types
- All exceptions must be logged with context
- User-facing errors must provide actionable messages
- System errors must include stack traces in logs

**File Organization:**
- **Target:** 500 lines per file
- **Warning:** 1,000 lines
- **Critical:** 1,500+ lines (must refactor)

**Code Duplication:**
- DRY Principle: Extract common AppleScript patterns
- Single source of truth for each AppleScript operation

### Testing Requirements

**Maintained Coverage:**
- All 330+ existing tests must pass
- No reduction in test coverage percentage
- New test categories for refactored code

**New Test Categories:**
- Error handling tests for each exception type
- Edge case tests for parser improvements
- Integration tests for refactored modules

**Test Execution Performance:**
- No more than 10% regression in test execution time

### Backwards Compatibility

**API Stability:**
- Zero breaking changes to public APIs
- All function signatures remain unchanged
- Return value formats preserved
- Error response formats maintained

---

## Architecture - Proposed System Design

### Module Reorganization

```
src/things_mcp/
├── services/
│   ├── applescript/
│   │   ├── __init__.py
│   │   ├── executor.py          # Core AppleScript execution (300 lines)
│   │   ├── parser.py             # Output parsing with state machine (400 lines)
│   │   ├── formatters.py         # Date/tag/string formatting (200 lines)
│   │   ├── queries.py            # Read operations (400 lines)
│   │   ├── commands.py           # Write operations (300 lines)
│   │   └── templates.py          # Reusable AppleScript patterns (200 lines)
│   ├── applescript_manager.py    # Public API facade (200 lines)
│   ├── validation_service.py     # (existing)
│   └── tag_service.py            # (existing)
├── tools/
│   ├── __init__.py
│   ├── read_operations.py        # (extracted from tools.py)
│   ├── write_operations.py       # (extracted from tools.py)
│   ├── bulk_operations.py        # (extracted from tools.py)
│   └── conversion.py             # Format converters
├── scheduling/
│   ├── __init__.py
│   ├── scheduler.py              # Core scheduling (400 lines)
│   ├── strategies.py             # Date scheduling strategies (300 lines)
│   ├── search.py                 # Advanced search (400 lines)
│   └── filters.py                # Search filters
├── exceptions.py                 # Structured exception hierarchy
├── server.py                     # Orchestration only (600 lines)
├── config.py                     # (existing, fix bare except)
└── context_manager.py            # (existing, fix bare excepts)
```

### AppleScript Parser Architecture

**Current:** String manipulation with §COMMA§ placeholders (193 lines)
**Proposed:** State machine parser

```python
class AppleScriptParser:
    """Parses AppleScript output using state machine."""

    class State(Enum):
        FIELD = "field"      # Reading field name
        VALUE = "value"      # Reading value
        QUOTED = "quoted"    # Inside quotes
        LIST = "list"        # Inside braces {}

    def parse(self, output: str) -> List[Dict[str, Any]]:
        """Parse AppleScript output into records."""
        state = State.FIELD
        current_field = ""
        current_value = ""
        current_record = {}
        records = []

        for char in output:
            state = self._transition(state, char)
            self._accumulate(char, state, ...)

        return records
```

### Exception Hierarchy

```python
class ThingsMCPError(Exception):
    """Base exception for Things MCP."""
    pass

class AppleScriptError(ThingsMCPError):
    """AppleScript execution errors."""
    pass

class ParseError(ThingsMCPError):
    """Data parsing errors."""
    pass

class ValidationError(ThingsMCPError):
    """Input validation errors."""
    pass
```

---

## Implementation Roadmap

### Phase 1: Quick Wins (Week 1, 7 hours) - LOW RISK

**Task 1.1: Fix bare except in config.py:283** (2 hours)
- Add specific exception: `json.JSONDecodeError`
- Log error with file path
- Add test for invalid JSON
- **Files:** `src/things_mcp/config.py`
- **Validation:** `pytest tests/unit/test_config.py`

**Task 1.2: Fix bare except in server.py:1388** (2 hours)
- Add specific exceptions: `AppleScriptError`, `KeyError`
- Log error with context
- Add test for tag counting failure
- **Files:** `src/things_mcp/server.py`
- **Validation:** `pytest tests/unit/test_server.py`

**Task 1.3: Fix bare excepts in context_manager.py:545,558** (3 hours)
- Add specific exceptions: `ValueError`, `TypeError`
- Log errors with date string context
- Add tests for invalid dates
- **Files:** `src/things_mcp/context_manager.py`
- **Validation:** `pytest tests/unit/test_context_manager.py`

**Deliverables:**
- [ ] All 5 bare except blocks fixed
- [ ] New unit tests for error paths
- [ ] All existing tests passing

---

### Phase 2: Parser Refactoring (Weeks 2-3, 15 hours) - HIGH RISK

**Task 2.1: Create new parser module** (8 hours)
- File: `src/things_mcp/services/applescript/parser.py`
- Implement state machine parser
- Add comprehensive tests (20+ test cases)
- **Complexity:** High
- **Dependencies:** None
- **Validation:** `pytest tests/unit/test_applescript_parser.py`

**Task 2.2: Add feature flag for new parser** (2 hours)
- Add config option: `USE_NEW_APPLESCRIPT_PARSER`
- Update `AppleScriptManager` to support both parsers
- **Files:** `src/things_mcp/config.py`, `src/things_mcp/services/applescript_manager.py`
- **Validation:** Tests pass with both parsers

**Task 2.3: Integration testing** (4 hours)
- Test with real Things 3 database
- Compare old vs new parser outputs
- Fix discrepancies
- **Validation:** Output byte-for-byte identical

**Task 2.4: Make new parser default** (1 hour)
- Update config default to new parser
- Add deprecation warning for old parser
- **Validation:** All tests pass

**Deliverables:**
- [ ] New state machine parser implemented
- [ ] Feature flag system in place
- [ ] Both parsers validated equivalent
- [ ] New parser is default

---

### Phase 3: Function Decomposition (Weeks 4-5, 20 hours) - MEDIUM RISK

**Task 3.1: Extract helpers from search_advanced()** (6 hours)
- Extract: `_build_search_filters()` (30 lines)
- Extract: `_apply_status_filter()` (25 lines)
- Extract: `_apply_tag_filter()` (30 lines)
- Extract: `_execute_search_script()` (40 lines)
- Add tests for each helper
- **Files:** `src/things_mcp/pure_applescript_scheduler.py`
- **Validation:** `pytest tests/unit/test_pure_applescript_scheduler.py`

**Task 3.2: Extract helpers from bulk_update_todos()** (6 hours)
- Extract: `_validate_bulk_params()` (30 lines)
- Extract: `_build_update_script()` (50 lines)
- Extract: `_parse_bulk_results()` (30 lines)
- Add tests for each helper
- **Files:** `src/things_mcp/tools.py`
- **Validation:** `pytest tests/unit/test_tools.py`

**Task 3.3: Extract helpers from other monster functions** (8 hours)
- Target: 17 remaining functions >100 lines
- Extract at least 3 more functions
- Focus on highest-value targets
- **Files:** Various
- **Validation:** Full test suite

**Deliverables:**
- [ ] At least 5 monster functions refactored
- [ ] Helper functions extracted and tested
- [ ] All existing tests passing
- [ ] Function count >100 lines reduced from 19 to <15

---

### Phase 4: File Organization (Week 6, 22 hours) - MEDIUM RISK

**Task 4.1: Split applescript_manager.py** (8 hours)
- Create `services/applescript/` directory
- Extract `executor.py` (300 lines)
- Extract `queries.py` (400 lines)
- Extract `formatters.py` (200 lines)
- Update imports in `applescript_manager.py`
- Keep public API unchanged
- **Files:** New directory structure
- **Validation:** All tests pass, imports resolve

**Task 4.2: Split tools.py** (8 hours)
- Create `tools/` directory
- Extract `read_operations.py` (500 lines)
- Extract `write_operations.py` (400 lines)
- Extract `bulk_operations.py` (300 lines)
- Keep `tools.py` as facade
- **Files:** New directory structure
- **Validation:** All tests pass

**Task 4.3: Split pure_applescript_scheduler.py** (6 hours)
- Create `scheduling/` directory
- Extract `strategies.py` (300 lines)
- Extract `search.py` (400 lines)
- Extract `filters.py` (200 lines)
- **Files:** New directory structure
- **Validation:** All tests pass

**Deliverables:**
- [ ] applescript_manager.py: 1,657 → ~600 lines
- [ ] tools.py: 1,604 → ~400 lines
- [ ] pure_applescript_scheduler.py: 1,379 → ~500 lines
- [ ] New directory structure created
- [ ] All imports updated
- [ ] All tests passing

---

### Phase 5: Consolidate AppleScript Patterns (Week 7, 8 hours) - LOW RISK

**Task 5.1: Create AppleScript template system** (8 hours)
- File: `services/applescript/templates.py`
- Extract common patterns
- Create reusable functions:
  - `build_tell_application_block()`
  - `build_error_handler()`
  - `build_date_formatter()`
- Update 31 call sites
- **Files:** Multiple files, new `templates.py`
- **Validation:** All tests pass

**Deliverables:**
- [ ] AppleScript template system created
- [ ] 31 duplicate invocations reduced to template calls
- [ ] All tests passing

---

### Phase 6: Error Handling Improvements (Week 8, 7 hours) - LOW RISK

**Task 6.1: Create exception hierarchy** (4 hours)
- File: `src/things_mcp/exceptions.py`
- Define structured exceptions
- Update all raise statements
- **Validation:** No bare excepts remain

**Task 6.2: Add error handling decorator** (3 hours)
- Implement `@handle_errors` decorator
- Apply to all public API functions
- **Validation:** Error logs are consistent

**Deliverables:**
- [ ] Exception hierarchy defined
- [ ] Error handling decorator implemented
- [ ] All public APIs use decorator
- [ ] Error logs are consistent

---

### Phase 7: Documentation (Week 9, 12 hours) - LOW RISK

**Task 7.1: Add missing docstrings** (8 hours)
- All public functions documented
- Complex algorithms explained
- Examples for non-obvious usage
- **Files:** All Python files
- **Validation:** `pydocstyle` checks pass

**Task 7.2: Create ADRs** (4 hours)
- Document parser refactoring decision
- Document file organization changes
- Document error handling patterns
- **Files:** `docs/adr/`

**Deliverables:**
- [ ] All public functions have docstrings
- [ ] Complex algorithms documented
- [ ] ADRs created for major changes

---

### Phase 8: Performance Testing (Week 10, 8 hours) - LOW RISK

**Task 8.1: Add performance benchmarks** (4 hours)
- Benchmark critical paths
- Establish baseline metrics
- **Files:** `tests/benchmarks/`
- **Validation:** No >10% regressions

**Task 8.2: Profile and optimize** (4 hours)
- Identify bottlenecks
- Optimize hot paths
- **Validation:** Performance improved or maintained

**Deliverables:**
- [ ] Performance benchmarks in place
- [ ] Baseline metrics established
- [ ] No performance regressions
- [ ] Hot paths optimized

---

## Progress Tracking

### Summary Metrics

| Metric | Current | Target | Progress |
|--------|---------|--------|----------|
| Bare except blocks | 5 | 0 | ⬜⬜⬜⬜⬜ |
| Functions >100 lines | 19 | 0 | ⬜⬜⬜⬜⬜ |
| Files >1,000 lines | 4 | 0 | ⬜⬜⬜⬜ |
| AppleScript duplicates | 31 | 0 | ⬜⬜⬜⬜⬜ |
| Test coverage | 80% | 80%+ | ✅ |
| Passing tests | 330+ | 330+ | ✅ |

### Phase Completion

- [ ] Phase 1: Quick Wins (Week 1)
- [ ] Phase 2: Parser Refactoring (Weeks 2-3)
- [ ] Phase 3: Function Decomposition (Weeks 4-5)
- [ ] Phase 4: File Organization (Week 6)
- [ ] Phase 5: Consolidate AppleScript (Week 7)
- [ ] Phase 6: Error Handling (Week 8)
- [ ] Phase 7: Documentation (Week 9)
- [ ] Phase 8: Performance Testing (Week 10)

---

## Risk Management

### Risk Mitigation Strategies

**For Each High-Risk Change:**

1. **Feature Flags:**
   ```python
   USE_NEW_PARSER = os.getenv('THINGS_MCP_USE_NEW_PARSER', 'false').lower() == 'true'
   ```

2. **Gradual Rollout:**
   - Enable for internal testing first
   - Beta release with opt-in
   - Default in next minor version

3. **Comprehensive Testing:**
   ```bash
   pytest tests/                    # Unit tests
   pytest tests/integration/        # Integration tests
   pytest --cov=src/things_mcp      # Coverage check
   ```

4. **Rollback Plan:**
   ```bash
   git tag pre-refactor-<phase>
   # If issues arise:
   git revert <commit-hash>
   ```

### Validation Checklist (After Each Task)

```bash
# 1. Run affected tests
pytest tests/unit/test_<module>.py

# 2. Run integration tests
pytest tests/integration/

# 3. Run full suite
pytest tests/

# 4. Check coverage
pytest --cov=src/things_mcp --cov-report=term-missing

# 5. Verify no new warnings
pytest -W error

# 6. Commit if all pass
git add .
git commit -m "refactor: <task description>"
git push
```

---

## Success Criteria

### Quantitative Metrics

- ✅ Zero bare except blocks remaining
- ✅ All functions <100 lines (target 80)
- ✅ All files <1,000 lines (target 500)
- ✅ Test coverage ≥80%
- ✅ All 330+ tests passing
- ✅ No performance regressions >10%
- ✅ AppleScript patterns consolidated

### Qualitative Metrics

- Code easier to navigate
- New contributors can understand codebase faster
- Bugs easier to diagnose and fix
- Maintenance burden reduced

---

## Notes for Swarm Implementation

### Swarm Coordination

**For parallel execution:**
- Phase 1 tasks (1.1, 1.2, 1.3) can run in parallel (independent files)
- Phase 3 tasks (3.1, 3.2) can run in parallel (different files)
- Phase 4 tasks (4.1, 4.2, 4.3) can run in parallel (different file splits)

**For sequential execution:**
- Phase 2 must complete before Phase 3
- Phase 4 depends on Phase 3 completion
- Phase 5 depends on Phase 4 completion

### Agent Recommendations

**Best agents for each phase:**

- **Phase 1 (Quick Wins):** `coder` agent - straightforward fixes
- **Phase 2 (Parser):** `base-template-generator` + `coder` + `tester` - complex new module
- **Phase 3 (Functions):** `code-analyzer` + `coder` - refactoring expertise
- **Phase 4 (Files):** `repo-architect` + `coder` - file organization
- **Phase 5 (Patterns):** `coder` - template creation
- **Phase 6 (Errors):** `coder` + `tester` - error handling
- **Phase 7 (Docs):** `coder` - documentation
- **Phase 8 (Performance):** `perf-analyzer` + `tester` - benchmarking

### Git Strategy

**Branch naming:**
```
refactor/phase-1-quick-wins
refactor/phase-2-parser
refactor/phase-3-functions
...
```

**Commit message format:**
```
refactor(module): description

- Detailed change 1
- Detailed change 2

Closes #<issue-number>
Relates to REFACTORING_PLAN.md Phase X Task Y
```

**Tags:**
```
git tag refactor-phase-1-complete
git tag refactor-phase-2-complete
...
```

---

## References

- **Project Documentation:** See `CLAUDE.md` for development guidelines
- **Testing:** See `tests/README.md` (if exists) for test organization
- **Architecture:** See `docs/ARCHITECTURE.md` (if exists)
- **Changelog:** See `CHANGELOG.md` for version history

---

## Appendix A: Detailed File List

### Files Requiring Refactoring

**Priority 1 (Bare Excepts):**
1. `src/things_mcp/config.py:283`
2. `src/things_mcp/server.py:1388`
3. `src/things_mcp/context_manager.py:545`
4. `src/things_mcp/context_manager.py:558`
5. `src/things_mcp/shared_cache.py:246`

**Priority 2 (Monster Functions):**
1. `src/things_mcp/pure_applescript_scheduler.py:1051` - search_advanced() - 214 lines
2. `src/things_mcp/tools.py:1111` - bulk_update_todos() - 197 lines
3. `src/things_mcp/services/applescript_manager.py:651` - _parse_applescript_list() - 193 lines
4. `src/things_mcp/services/applescript_manager.py:138` - get_todos() - 191 lines
5. (15 more functions 104-159 lines)

**Priority 3 (Large Files):**
1. `src/things_mcp/services/applescript_manager.py` - 1,657 lines
2. `src/things_mcp/tools.py` - 1,604 lines
3. `src/things_mcp/server.py` - 1,531 lines
4. `src/things_mcp/pure_applescript_scheduler.py` - 1,379 lines

---

## Appendix B: Test Commands Reference

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_config.py

# Run with coverage
pytest --cov=src/things_mcp --cov-report=html

# Run with verbose output
pytest -v

# Run only failed tests from last run
pytest --lf

# Run tests matching pattern
pytest -k "test_parse"

# Run benchmarks
pytest -m benchmark

# Run with warnings as errors
pytest -W error
```

---

**Last Updated:** 2025-10-01
**Next Review:** After Phase 1 completion

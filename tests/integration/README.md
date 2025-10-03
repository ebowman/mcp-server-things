# Integration Tests for Things 3 MCP Server

This directory contains integration tests that interact with a real Things 3 installation. These tests validate functionality end-to-end with actual AppleScript execution and database operations.

## ⚠️ Prerequisites

1. **Things 3 installed and running** on macOS
2. **Automation permissions granted** to your terminal/IDE
   - System Settings → Privacy & Security → Automation
   - Enable access for Terminal/VS Code/PyCharm
3. **Active Things 3 database** (does not need to be empty)

## 🧹 Cleanup Mechanism

**CRITICAL:** All integration tests use the `cleanup_test_todos` fixture to ensure NO test data remains in Things 3 after test runs.

### How It Works

1. Each test receives a `cleanup_test_todos` fixture with:
   - Unique timestamp-based tag
   - Lists to track created todo/project IDs

2. Tests create todos/projects and add IDs to tracking lists:
   ```python
   result = await tools.add_todo(title=f"Test {cleanup_test_todos['tag']}")
   cleanup_test_todos['ids'].append(result['todo_id'])
   ```

3. Fixture automatically deletes all tracked items after test completes

### Verify Cleanup

Before running tests for the first time:

```bash
# 1. Test the cleanup mechanism
pytest tests/integration/test_cleanup_mechanism.py -v

# 2. Verify no test data remains
python tests/integration/verify_cleanup.py
```

Expected output:
```
✅ CLEANUP VERIFICATION PASSED
No test data found in Things 3
```

## 🚀 Running Tests

### Test Cleanup First

```bash
# Verify cleanup mechanism works
pytest tests/integration/test_cleanup_mechanism.py -v
python tests/integration/verify_cleanup.py
```

### Run Date Scheduling Tests

```bash
# Run all date scheduling tests
pytest tests/integration/test_date_scheduling_integration.py -v

# Run specific test suite
pytest tests/integration/test_date_scheduling_integration.py::TestDateSchedulingBasics -v

# Run single test
pytest tests/integration/test_date_scheduling_integration.py::TestDateSchedulingBasics::test_schedule_todo_today -v
```

### Run All Integration Tests

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run with output
pytest tests/integration/ -v -s
```

### Cleanup Orphaned Test Data

If tests fail mid-execution, cleanup orphaned data:

```bash
# Find test data
python tests/integration/verify_cleanup.py

# Clean it up
python tests/integration/verify_cleanup.py --cleanup
```

## 📋 Test Suites

### test_cleanup_mechanism.py
**Purpose:** Verify cleanup fixture works correctly
**Tests:** 3
**Run First:** Yes

### test_date_scheduling_integration.py
**Purpose:** Validate date scheduling functionality
**Tests:** 17
**Suites:**
- `TestDateSchedulingBasics`: today, tomorrow, specific dates, someday, anytime (5 tests)
- `TestRelativeOffsets`: +7d, +1w, +1m, +3d, +14d (5 tests)
- `TestRescheduling`: reschedule, clear, move, deadline preservation (5 tests)
- `TestEdgeCases`: far future, multiple reschedules, complete after schedule (3 tests)

### test_bulk_operations_comprehensive.py
**Purpose:** Validate bulk operations and record movement
**Tests:** ~30+
**Suites:**
- Single field bulk updates
- Multi-field bulk updates
- Bulk move operations
- Tag management

### test_search_comprehensive.py
**Purpose:** Validate search functionality
**Tests:** ~20+

## 🔍 Troubleshooting

### Test Data Remains After Tests

```bash
# Check for orphaned data
python tests/integration/verify_cleanup.py

# Clean it up
python tests/integration/verify_cleanup.py --cleanup
```

### Permission Errors

Enable automation access:
1. System Settings → Privacy & Security → Automation
2. Find your terminal/IDE application
3. Enable "Things 3" checkbox

### Timeout Errors

Increase timeout in AppleScriptManager:
```python
manager = AppleScriptManager(timeout=60)  # Default: 45
```

### Tests Fail Intermittently

Things 3 may be busy with sync operations. Try:
1. Disable Things Cloud sync temporarily
2. Run tests one at a time
3. Add delays between operations

## 📊 Test Statistics

Total integration tests: **17+** (date scheduling) + 50+ (other suites)

**Coverage:**
- Date scheduling: 17 tests
- Bulk operations: 30+ tests
- Search operations: 20+ tests
- Cleanup mechanism: 3 tests

**Safety:**
- 100% of tests include cleanup
- 0% expected test data pollution
- Idempotent: can run multiple times

## 🛡️ Safety Features

1. **Unique Identifiers:** All test todos include timestamp-based tags
2. **Tracked IDs:** Every created item is tracked for cleanup
3. **Graceful Failure:** Cleanup handles already-deleted items
4. **Manual Verification:** Scripts available to verify cleanliness
5. **Isolated Projects:** Test projects are canceled, not deleted

## 📝 Writing New Integration Tests

Template for new integration tests:

```python
import pytest
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools


@pytest.fixture
def applescript_manager():
    return AppleScriptManager()


@pytest.fixture
def things_tools(applescript_manager):
    return ThingsTools(applescript_manager)


class TestMyFeature:
    @pytest.mark.asyncio
    async def test_my_feature(self, things_tools, cleanup_test_todos):
        # Create todo
        result = await things_tools.add_todo(
            title=f"My Test {cleanup_test_todos['tag']}"
        )

        # Track for cleanup
        cleanup_test_todos['ids'].append(result['todo_id'])

        # Test logic...
        assert result['success']

        # Cleanup happens automatically
```

**Always:**
- Use `cleanup_test_todos` fixture
- Add created IDs to tracking lists
- Use unique identifiers in titles
- Verify cleanup with verification script

## 🎯 Best Practices

1. **Test Cleanup First:** Run `test_cleanup_mechanism.py` before other tests
2. **Verify After:** Run `verify_cleanup.py` after test sessions
3. **Unique Names:** Use timestamp-based unique identifiers
4. **Track Everything:** Add all created IDs to cleanup lists
5. **Manual Cleanup:** Use `verify_cleanup.py --cleanup` for emergencies
6. **Isolation:** Don't depend on existing Things 3 data
7. **Idempotency:** Tests should work on empty or populated databases

## 📞 Support

If you encounter issues:
1. Check Things 3 is running
2. Verify automation permissions
3. Run cleanup verification script
4. Check test output for specific errors
5. Review cleanup fixture in `tests/conftest.py`

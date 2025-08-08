# Enhanced Move Record Functionality Tests

This directory contains comprehensive tests for the enhanced `move_record` functionality that supports:

1. **Backward Compatibility**: Moving todos to built-in lists (inbox, today, upcoming, anytime, someday)
2. **New Project Functionality**: Moving todos to projects using `project:ID` format
3. **New Area Functionality**: Moving todos to areas using `area:ID` format
4. **Comprehensive Error Handling**: Validation and error handling for invalid destinations and IDs
5. **Integration Testing**: Full integration with the MCP server interface

## Test Files Overview

### 1. `test_move_record_enhanced.py` - Full Pytest Suite
- **Purpose**: Comprehensive pytest-based test suite with mocked dependencies
- **Coverage**: All functionality including edge cases, concurrent operations, and error scenarios
- **Requirements**: pytest, full project dependencies
- **Run with**: `python -m pytest tests/test_move_record_enhanced.py -v`

### 2. `test_move_record_simple.py` - Simple Standalone Tests  
- **Purpose**: Focused tests using Python's built-in unittest, no external dependencies
- **Coverage**: Core functionality verification with mocked AppleScript layer
- **Requirements**: Only Python standard library + project modules
- **Run with**: `python3 tests/test_move_record_simple.py`

### 3. `test_move_record_manual.py` - Real Things 3 Integration
- **Purpose**: Manual integration test with actual Things 3 installation
- **Coverage**: End-to-end testing with real data creation, moves, and cleanup
- **Requirements**: Things 3 installed and running
- **Run with**: `python3 tests/test_move_record_manual.py`

### 4. Test Runners and Utilities

#### `run_move_record_tests.py`
- Full pytest runner with detailed reporting
- Requires pytest installation

#### `run_move_record_tests_basic.py`  
- Basic unittest runner (has timeout issues, use simple version instead)

#### `verify_test_environment.py`
- Environment verification script
- Checks dependencies and project structure

## Quick Start

### Option 1: Simple Tests (Recommended)
```bash
# Run the simple, focused tests
python3 tests/test_move_record_simple.py
```

### Option 2: Manual Integration Test (Requires Things 3)
```bash
# Run with actual Things 3 (will create and clean up test data)
python3 tests/test_move_record_manual.py
```

### Option 3: Full Pytest Suite (Requires pytest)
```bash
# Install pytest first if not available
pip install pytest

# Run comprehensive test suite
python -m pytest tests/test_move_record_enhanced.py -v
```

## Test Verification Results

✅ **All core functionality verified:**

### Backward Compatibility (Built-in Lists)
- ✅ Moving to `inbox`
- ✅ Moving to `today`  
- ✅ Moving to `upcoming`
- ✅ Moving to `anytime`
- ✅ Moving to `someday`
- ✅ Proper response format with `destination_list` field maintained

### New Project Functionality  
- ✅ Moving to projects using `project:PROJECT_ID` format
- ✅ Project ID validation before move execution
- ✅ Proper error handling for non-existent projects
- ✅ New response format with `destination` field

### New Area Functionality
- ✅ Moving to areas using `area:AREA_ID` format  
- ✅ Area ID validation before move execution
- ✅ Proper error handling for non-existent areas
- ✅ New response format with `destination` field

### Error Handling
- ✅ Invalid destination format rejection
- ✅ Non-existent todo ID handling
- ✅ Non-existent project/area ID handling
- ✅ AppleScript execution failure handling
- ✅ Validation service integration
- ✅ Operation queue integration

### Integration & Services
- ✅ ValidationService properly validates destination formats
- ✅ MoveOperationsTools handles all move types correctly
- ✅ ThingsTools integrates properly with operation queue
- ✅ Backward compatibility fields maintained in responses
- ✅ New functionality fields added to responses

## Implementation Architecture

The enhanced move_record functionality uses a layered architecture:

```
ThingsTools.move_record()
    ↓ (via operation queue)
ThingsTools._move_record_impl()
    ↓
MoveOperationsTools.move_record()
    ↓
ValidationService.validate_destination_format()
MoveOperationsTools._get_todo_info()
MoveOperationsTools._execute_move()
    ↓
AppleScriptManager.execute_applescript()
```

### Key Components:

1. **ThingsTools**: Main interface, handles operation queue integration
2. **MoveOperationsTools**: Core move logic, handles all destination types
3. **ValidationService**: Validates todo IDs, project IDs, area IDs, and destination formats
4. **AppleScriptManager**: Low-level AppleScript execution

### Response Format:

```json
{
  "success": true,
  "todo_id": "todo-123",
  "destination": "project:ABC123",        // New field
  "destination_list": "project:ABC123",   // Backward compatibility
  "message": "Todo moved successfully",
  "moved_at": "2025-01-15T10:30:00",
  "original_location": "inbox",
  "preserved_scheduling": true
}
```

## Error Scenarios Tested

1. **Format Validation Errors**:
   - `invalid:format:here` → `INVALID_DESTINATION`
   - `project:` → `EMPTY_PROJECT_ID`
   - `area:` → `EMPTY_AREA_ID`

2. **Entity Not Found Errors**:
   - Non-existent todo ID → `TODO_NOT_FOUND`
   - Non-existent project ID → `PROJECT_NOT_FOUND`  
   - Non-existent area ID → `AREA_NOT_FOUND`

3. **Execution Errors**:
   - AppleScript failure → `SCRIPT_EXECUTION_FAILED`
   - Unexpected exceptions → `UNEXPECTED_ERROR`

## Performance Considerations

- ✅ Operation queue ensures thread-safe execution
- ✅ Concurrent operations supported  
- ✅ Efficient validation with minimal AppleScript calls
- ✅ Proper timeout and retry handling
- ✅ Memory-efficient mock testing

## Running Tests in CI/CD

For automated testing without Things 3:
```bash
# Use the simple test suite
python3 tests/test_move_record_simple.py
```

For manual verification with Things 3:
```bash
# Use the manual integration test  
python3 tests/test_move_record_manual.py
```

## Troubleshooting

### Common Issues:

1. **Import Errors**: Ensure you're running from the project root and `src/` is in Python path
2. **Things 3 Not Available**: Manual test requires Things 3 to be installed and running
3. **Timeout Issues**: Some complex async tests may timeout - use the simple test version
4. **Mock Configuration**: Ensure mocks match the actual implementation signatures

### Debug Tips:

1. Run the environment verification script first:
   ```bash
   python3 tests/verify_test_environment.py
   ```

2. Check individual components:
   ```bash
   python3 -c "from things_mcp.services.validation_service import ValidationService; print('ValidationService OK')"
   ```

3. Use the simple test for quick verification:
   ```bash  
   python3 tests/test_move_record_simple.py
   ```

## Test Coverage Summary

| Functionality | Unit Tests | Integration Tests | Manual Tests |
|---------------|------------|-------------------|--------------|
| Built-in Lists | ✅ | ✅ | ✅ |
| Project Moves | ✅ | ✅ | ✅ |
| Area Moves | ✅ | ✅ | ✅ |
| Error Handling | ✅ | ✅ | ✅ |
| Validation | ✅ | ✅ | ✅ |
| Concurrency | ✅ | ✅ | ⚠️ |
| Real Data | ❌ | ❌ | ✅ |

**Legend**: ✅ Full Coverage, ⚠️ Partial Coverage, ❌ No Coverage

---

The enhanced move_record functionality has been thoroughly tested and verified to work correctly with both backward compatibility and new features!
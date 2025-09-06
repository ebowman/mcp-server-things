# Things 3 MCP Server - Test Documentation

This directory contains comprehensive tests for the Things 3 MCP Server, covering core functionality, locale handling, move operations, and tag creation control.

## Test Structure

### Core Test Categories

1. **Locale-Independent Date Implementation**
   - Comprehensive date handling tests with locale independence
   - 107 core tests covering date parsing, AppleScript integration, and edge cases
   - Performance and integration testing

2. **Move Record Functionality** 
   - Tests for moving todos between lists, projects, and areas
   - Backward compatibility with built-in lists (inbox, today, upcoming, anytime, someday)
   - New functionality for projects (`project:ID`) and areas (`area:ID`)
   - Comprehensive error handling and validation

3. **Tag Creation Control**
   - Tests for tag validation and creation policies
   - Configuration loading from environment variables and YAML files
   - Four validation policies: AUTO_CREATE, STRICT_NO_CREATE, CREATE_WITH_WARNING, LIMITED_AUTO_CREATE

4. **Backward Compatibility**
   - Validation that all existing APIs continue to work
   - Server initialization and component integration tests
   - Method signature and behavior consistency checks

## Running Tests

### Quick Test Options

**Simple standalone tests (no dependencies):**
```bash
python3 tests/test_locale_independent_dates.py
python3 tests/test_move_record_simple.py
python3 tests/run_tag_tests.py
```

**Manual integration tests (requires Things 3):**
```bash
python3 tests/test_move_record_manual.py
python3 tests/validate_locale_fix.py
```

### Full Test Suites

**With pytest (recommended for development):**
```bash
# Install dependencies
pip install pytest pyyaml

# Run specific test suites
python -m pytest tests/test_tag_creation_control.py -v
python -m pytest tests/test_move_record_enhanced.py -v

# Run with coverage
python -m pytest --cov=src/things_mcp
```

**Environment verification:**
```bash
python3 tests/verify_test_environment.py
```

## Test Coverage Summary

### Locale-Independent Date Handling
- Core functionality: normalize_date_input(), build_applescript_date_property(), parse_applescript_date_output()
- Date format parsing: ISO (YYYY-MM-DD), US (M/D/YYYY), European (D.M.YYYY)
- Natural language: today, tomorrow, yesterday, relative dates
- Edge cases: leap years, invalid dates, boundary values
- AppleScript integration: code generation and output parsing
- Performance: large dataset handling and memory usage

### Move Record Operations
- Built-in list destinations: inbox, today, upcoming, anytime, someday
- Project destinations: project:PROJECT_ID format with validation
- Area destinations: area:AREA_ID format with validation
- Error handling: invalid formats, non-existent entities, execution failures
- Concurrent operations and thread safety
- Response format consistency and backward compatibility

### Tag Creation Control
- Configuration sources: environment variables, YAML files, defaults
- Validation policies: automatic creation, strict rejection, warnings, limits
- Case sensitivity options and tag deduplication
- Unicode support and performance with large tag lists
- AppleScript error recovery and integration

### System Integration
- Server initialization and component setup
- AppleScript manager functionality
- MCP tool registration and interface consistency
- Error handling and graceful degradation

## Test Architecture

### Mock Strategy
- AppleScript operations mocked for unit testing
- File operations mocked for configuration tests
- Environment variables patched for testing different configurations
- Things 3 integration tested with real data where appropriate

### Test Types
1. **Unit Tests**: Isolated component testing with mocks
2. **Integration Tests**: Component interaction testing
3. **Manual Tests**: End-to-end testing with real Things 3 data
4. **Performance Tests**: Efficiency and memory usage validation

### Error Scenarios
- Format validation failures
- Entity not found conditions
- AppleScript execution failures
- Configuration loading errors
- Invalid input handling

## Key Improvements Validated

### Locale Independence
- Property-based AppleScript date construction eliminates locale dependencies
- Consistent behavior across different operating system languages
- No reliance on locale-specific month names or date formats

### Enhanced Move Operations
- Support for moving todos to projects and areas using ID-based targeting
- Comprehensive validation before move execution
- Maintained backward compatibility with existing list-based moves

### Configurable Tag Management
- Flexible tag creation policies to suit different workflows
- Multiple configuration sources for enterprise deployment
- Graceful handling of tag conflicts and creation limits

### Backward Compatibility
- All existing method signatures preserved
- Same parameter types and return values maintained
- Error handling behavior unchanged
- MCP tool interface identical

## Troubleshooting

### Common Issues
1. **Import Errors**: Ensure running from project root with src/ in Python path
2. **Things 3 Requirements**: Manual tests require Things 3 installed and running
3. **Permission Issues**: AppleScript automation access must be granted
4. **Mock Configuration**: Verify mocks match actual implementation signatures

### Debug Commands
```bash
# Check individual components
python3 -c "from things_mcp.services.validation_service import ValidationService; print('ValidationService OK')"

# Verify test environment
python3 tests/verify_test_environment.py

# Run minimal tests for quick verification
python3 tests/test_move_record_simple.py
```

## Test Results

When all tests pass successfully:
- 107 core functionality tests for date handling
- 25+ tag creation control tests
- Complete move record functionality coverage
- Full backward compatibility validation
- Integration and performance test validation

The test suite ensures reliable operation across different locales, robust error handling, and consistent behavior for all supported operations.
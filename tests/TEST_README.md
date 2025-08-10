# Tag Creation Control Test Suite

This directory contains comprehensive tests for the tag creation control feature in the Things 3 MCP Server.

## Test Files

### Core Test File
- **`test_tag_creation_control.py`** - Main test suite with 25+ test methods covering all aspects of tag creation control

### Test Configuration
- **`fixtures/test_config.yaml`** - Sample configuration files demonstrating different tag creation policies
- **`run_tag_tests.py`** - Standalone test runner for environments without pytest

## Test Coverage

### 1. TagConfig Class Tests
- Default configuration values
- Custom configuration creation
- Configuration from dictionary
- Invalid policy handling
- Partial configuration support

### 2. TagValidationService Tests
- Existing tag retrieval (case sensitive/insensitive)
- All four validation policies:
  - `AUTO_CREATE` - Creates all tags automatically
  - `STRICT_NO_CREATE` - Rejects non-existing tags
  - `CREATE_WITH_WARNING` - Creates with warning messages
  - `LIMITED_AUTO_CREATE` - Creates up to a limit
- Case sensitivity options
- Tag deduplication
- Empty list handling

### 3. Configuration Loading Tests
- Environment variable loading
- YAML file loading
- Default fallback behavior
- Invalid file handling
- Backward compatibility

### 4. Integration Tests
- Tag operations with validation enabled
- Response format validation
- Backward compatibility with existing code
- Multiple configuration sources

### 5. Edge Cases and Error Handling
- AppleScript error recovery
- Invalid tag names
- Large tag lists
- Unicode tag support
- Performance with extensive tag lists

## Running the Tests

### Option 1: Using pytest (Recommended)
```bash
# Install dependencies
pip install pytest pyyaml

# Run all tests with verbose output
python -m pytest tests/test_tag_creation_control.py -v

# Run specific test class
python -m pytest tests/test_tag_creation_control.py::TestTagConfig -v

# Run with coverage
python -m pytest tests/test_tag_creation_control.py --cov=src.simple_server
```

### Option 2: Using the standalone runner
```bash
# Run without pytest dependency
python3 tests/run_tag_tests.py

# Run with verbose error output
python3 tests/run_tag_tests.py --verbose
```

### Option 3: Manual execution
```bash
# Just check syntax
python3 -m py_compile tests/test_tag_creation_control.py

# Import and run specific tests
python3 -c "
from tests.test_tag_creation_control import TestTagConfig
test = TestTagConfig()
test.test_default_config()
print('Test passed!')
"
```

## Test Scenarios Covered

### Policy Testing
- ✅ Auto-create all tags
- ✅ Strict rejection of new tags
- ✅ Create with warnings
- ✅ Limited creation with quotas

### Configuration Sources
- ✅ Environment variables
- ✅ YAML configuration files
- ✅ Default values
- ✅ Mixed configuration sources

### Edge Cases
- ✅ Empty tag lists
- ✅ Duplicate tags
- ✅ Invalid tag names
- ✅ Unicode characters
- ✅ Large tag lists (performance)
- ✅ AppleScript failures

### Backward Compatibility
- ✅ No configuration provided
- ✅ Existing API compatibility
- ✅ Response format consistency

## Mock Strategy

The tests use `unittest.mock` to mock AppleScript operations:

- **`run_applescript`** - Mocked to return predefined tag lists
- **File operations** - Mocked for configuration loading tests
- **Environment variables** - Patched for testing different configs

## Configuration Examples

The `fixtures/test_config.yaml` file contains examples of:

- Different creation policies
- Case sensitivity options
- Auto-creation limits
- Predefined tag lists
- Unicode tag support
- Performance test configurations

## Expected Test Results

### With pytest (Full Test Suite)
When all tests pass with pytest, you should see:
- ✅ All 4 tag creation policies work correctly
- ✅ Configuration loading from all sources
- ✅ Proper error handling and edge cases
- ✅ Backward compatibility maintained
- ✅ Response formats are consistent

### With Standalone Runner (Basic Tests)
The standalone runner focuses on non-fixture tests:
- ✅ TagConfig class functionality (5/5 tests passing)
- ⚠️ Some tests require mocked dependencies and are skipped
- ℹ️ Run with pytest for complete coverage

### Current Status
As of this implementation:
- **5/25 tests passing** in standalone mode
- **All configuration tests working** ✅
- **Fixture-based tests require pytest** for proper mocking

## Adding New Tests

To add new test cases:

1. **Add to existing test class** for related functionality
2. **Create new test class** for new features
3. **Update fixtures** if new configuration options are needed
4. **Add to run_tag_tests.py** if creating new test methods

### Test Naming Convention
- `test_<functionality>_<specific_case>`
- Example: `test_validate_tags_auto_create`

### Test Structure
```python
def test_something_specific(self, mock_fixture):
    \"\"\"Test description explaining what is being tested.\"\"\"
    # Arrange
    config = TagConfig(creation_policy=TagCreationPolicy.AUTO_CREATE)
    
    # Act
    result = service.validate_tags(['tag1', 'tag2'], config)
    
    # Assert
    assert result.valid_tags == ['tag1', 'tag2']
    assert result.created_tags == ['tag1', 'tag2']
```

## Troubleshooting

### Import Errors
If you get import errors, ensure:
1. The `src/` directory is in your Python path
2. All required classes exist in `src/simple_server.py`
3. Dependencies are installed (`pytest`, `pyyaml`)

### Mock Issues
If mocks aren't working:
1. Check that the correct module path is being patched
2. Verify mock return values match expected format
3. Ensure patches are applied in the correct scope

### Configuration Loading
If config tests fail:
1. Check file permissions on test fixtures
2. Verify YAML syntax in test files
3. Ensure environment variables are properly cleared/set
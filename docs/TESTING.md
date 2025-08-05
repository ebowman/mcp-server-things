# Testing Guide for Things 3 MCP Server

This document provides comprehensive information about testing the Things 3 MCP server, including how to run tests, understand test coverage, and contribute new tests.

## Quick Start

```bash
# Install development dependencies
pip install -e ".[dev,test]"

# Run all tests
python tests/test_runner.py all

# Run tests with coverage
python tests/test_runner.py all --coverage

# Run specific test suite
python tests/test_runner.py unit
python tests/test_runner.py integration
```

## Test Structure

The test suite is organized into several categories:

```
tests/
├── conftest.py                 # Global fixtures and configuration
├── pytest.ini                 # Pytest configuration
├── test_runner.py             # Test runner script
├── unit/                      # Unit tests
│   ├── test_models.py         # Pydantic model tests
│   ├── test_applescript_manager.py  # AppleScript manager tests
│   └── test_tools.py          # MCP tools tests
└── integration/               # Integration tests
    ├── test_server_lifecycle.py    # Server startup/shutdown tests
    ├── test_error_handling.py      # Error handling tests
    └── test_cli_interface.py       # CLI interface tests
```

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual components in isolation with comprehensive mocking:

- **Models** (`test_models.py`): Pydantic model validation, serialization, edge cases
- **AppleScript Manager** (`test_applescript_manager.py`): Script execution, URL schemes, caching, retries
- **Tools** (`test_tools.py`): MCP tool operations, CRUD functionality, data transformation

### Integration Tests (`tests/integration/`)

Test components working together:

- **Server Lifecycle** (`test_server_lifecycle.py`): Startup, health checks, statistics, shutdown
- **Error Handling** (`test_error_handling.py`): Error propagation, recovery patterns, logging
- **CLI Interface** (`test_cli_interface.py`): Command-line argument parsing, configuration loading

## Test Framework Features

### Comprehensive Mocking

The test suite uses extensive mocking to avoid requiring Things 3 installation:

```python
# Mock AppleScript Manager with realistic responses
@pytest.fixture
def mock_applescript_manager_with_data(mock_applescript_manager, sample_todo_data):
    mock_applescript_manager.set_mock_response("get_todos", {
        "success": True,
        "data": [sample_todo_data],
        "error": None
    })
    return mock_applescript_manager
```

### Rich Test Fixtures

Pre-configured test data and mock objects:

```python
@pytest.fixture
def sample_todo_data():
    return {
        "id": "todo-123",
        "name": "Sample Todo",
        "notes": "This is a test todo item",
        "status": "open",
        "creation_date": datetime.now() - timedelta(days=1),
        # ... more fields
    }
```

### Test Markers

Organize and filter tests using markers:

```bash
# Run only unit tests
pytest -m unit

# Run only error handling tests
pytest -m error

# Skip slow tests
pytest -m "not slow"
```

Available markers:
- `unit`: Unit tests for individual components
- `integration`: Integration tests requiring multiple components
- `server`: Server-level tests
- `applescript`: Tests involving AppleScript operations
- `tools`: Tests for MCP tools
- `models`: Tests for data models
- `error`: Error handling tests
- `slow`: Slow tests that may take longer to execute

## Running Tests

### Using the Test Runner

The `tests/test_runner.py` script provides convenient commands:

```bash
# Run all unit tests
python tests/test_runner.py unit

# Run integration tests
python tests/test_runner.py integration

# Run all tests with coverage
python tests/test_runner.py all --coverage

# Run specific test file
python tests/test_runner.py specific tests/unit/test_models.py

# Run tests by marker
python tests/test_runner.py marker unit

# Run linting
python tests/test_runner.py lint

# Run type checking
python tests/test_runner.py typecheck

# Run full CI suite
python tests/test_runner.py ci

# List available tests
python tests/test_runner.py list

# Clean test artifacts
python tests/test_runner.py clean
```

### Using Pytest Directly

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_models.py

# Run specific test function
pytest tests/unit/test_models.py::TestTodoModel::test_todo_creation_minimal

# Run with coverage
pytest --cov=src/things_mcp --cov-report=html

# Run with markers
pytest -m "unit and not slow"
```

## Test Coverage

The test suite aims for comprehensive coverage:

- **Target Coverage**: 80%+ overall
- **Critical Paths**: 90%+ coverage for core functionality
- **Models**: 95%+ coverage for data validation
- **Error Handling**: 85%+ coverage for error paths

### Coverage Reports

```bash
# Generate HTML coverage report
python tests/test_runner.py coverage

# View report
open htmlcov/index.html
```

Coverage reports show:
- Line coverage percentages
- Missing line numbers
- Branch coverage
- Uncovered code paths

## Test Configuration

### pytest.ini

The test configuration includes:

```ini
[tool:pytest]
testpaths = tests
addopts = --strict-markers --verbose --tb=short --color=yes
markers = 
    unit: Unit tests for individual components
    integration: Integration tests requiring multiple components
    # ... more markers
asyncio_mode = auto
timeout = 300
```

### pyproject.toml

Additional configuration in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src/things_mcp"]
branch = true
omit = ["tests/*", "*/venv/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

## Writing New Tests

### Test Structure Guidelines

1. **Arrange-Act-Assert Pattern**:
   ```python
   def test_add_todo_success(self, tools_with_mock):
       # Arrange
       title = "New Todo"
       tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
       
       # Act
       result = tools_with_mock.add_todo(title)
       
       # Assert
       assert result["success"] is True
       assert result["todo"]["title"] == title
   ```

2. **Use Descriptive Test Names**:
   ```python
   def test_get_todos_with_project_filter_returns_filtered_results(self):
   def test_add_todo_with_invalid_date_raises_validation_error(self):
   def test_applescript_timeout_retries_with_exponential_backoff(self):
   ```

3. **Test Edge Cases**:
   ```python
   def test_unicode_content_in_todo_names(self):
   def test_very_long_todo_descriptions(self):
   def test_concurrent_applescript_execution_conflicts(self):
   ```

### Adding New Fixtures

Create reusable test fixtures in `conftest.py`:

```python
@pytest.fixture
def sample_project_with_todos(sample_project_data, multiple_todos_data):
    """Project with associated todos for testing relationships."""
    project = sample_project_data.copy()
    project["todos"] = multiple_todos_data
    return project
```

### Mock Patterns

Use consistent mock patterns:

```python
# Mock successful operations
mock_manager.set_mock_response("operation_name", {
    "success": True,
    "data": expected_data,
    "error": None
})

# Mock failures
mock_manager.set_failure_mode(True, "Error message")

# Mock specific behaviors
mock_manager.execute_applescript = AsyncMock(
    side_effect=Exception("Custom error")
)
```

### Testing Async Code

Use pytest-asyncio for async testing:

```python
@pytest.mark.asyncio
async def test_async_operation(self, mock_manager):
    result = await mock_manager.execute_applescript("test script")
    assert result["success"] is True
```

## Performance Testing

### Benchmarking

Use pytest-benchmark for performance tests:

```python
def test_todo_creation_performance(benchmark, tools):
    result = benchmark(tools.add_todo, "Performance Test Todo")
    assert result["success"] is True
```

### Memory Testing

Test memory usage patterns:

```python
def test_large_dataset_memory_usage(self):
    large_dataset = [create_todo_data() for _ in range(10000)]
    initial_memory = get_memory_usage()
    
    process_todos(large_dataset)
    
    final_memory = get_memory_usage()
    memory_increase = final_memory - initial_memory
    assert memory_increase < MAX_ACCEPTABLE_MEMORY_MB
```

## CI/CD Integration

### GitHub Actions

The test suite runs automatically on:
- Pull requests
- Pushes to main/develop branches
- Daily scheduled runs

### Test Matrix

Tests run across:
- Python versions: 3.8, 3.9, 3.10, 3.11, 3.12
- macOS versions: latest, 12
- Different configurations

### Artifacts

CI uploads test artifacts:
- Coverage reports
- Test results (JUnit XML)
- Performance benchmarks
- Security scan results

## Debugging Tests

### Running Individual Tests

```bash
# Run with maximum verbosity
pytest tests/unit/test_models.py::TestTodoModel::test_specific_case -vvv

# Drop into debugger on failure
pytest --pdb tests/unit/test_models.py

# Show local variables on failure
pytest --tb=long --showlocals tests/unit/test_models.py
```

### Debugging Mock Issues

```python
# Check mock calls
print(mock_manager.execution_calls)
print(mock_manager.url_scheme_calls)

# Verify mock configuration
assert mock_manager.should_fail == False
assert "test_key" in mock_manager.mock_responses
```

### Log Analysis

Enable debug logging in tests:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or use caplog fixture
def test_with_logging(caplog):
    with caplog.at_level(logging.INFO):
        perform_operation()
    
    assert "Expected log message" in caplog.text
```

## Best Practices

### Test Design

1. **Independent Tests**: Each test should be independent and not rely on others
2. **Fast Execution**: Unit tests should run quickly (<100ms each)
3. **Clear Assertions**: Use descriptive assertion messages
4. **Comprehensive Coverage**: Test both success and failure paths
5. **Realistic Mocks**: Mocks should behave like real components

### Code Organization

1. **Group Related Tests**: Use test classes to group related functionality
2. **Shared Setup**: Use fixtures for common test setup
3. **Helper Functions**: Extract common test logic into helper functions
4. **Clear Naming**: Use descriptive names for tests, fixtures, and helpers

### Maintenance

1. **Update Tests with Code Changes**: Keep tests in sync with code changes
2. **Remove Obsolete Tests**: Clean up tests for removed functionality
3. **Refactor Test Code**: Apply same quality standards to test code
4. **Document Complex Tests**: Add comments for complex test scenarios

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure PYTHONPATH includes src directory
2. **Async Test Failures**: Use `@pytest.mark.asyncio` for async tests
3. **Mock Configuration**: Verify mock responses match expected format
4. **Fixture Dependencies**: Check fixture dependency order

### Test Environment

```bash
# Verify test environment
python -c "import src.things_mcp; print('OK')"
pytest --version
python -m coverage --version

# Reset test environment
python tests/test_runner.py clean
pip install -e ".[dev,test]"
```

### Getting Help

1. Check test output for specific error messages
2. Run tests with increased verbosity (`-vvv`)
3. Use debugger to step through test execution
4. Review test logs and mock call history
5. Consult existing similar tests for patterns

This comprehensive testing framework ensures the Things 3 MCP server is reliable, maintainable, and ready for production use.
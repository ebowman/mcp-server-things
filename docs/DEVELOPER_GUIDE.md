# Things 3 MCP Server - Developer Guide

A comprehensive guide for developers who want to contribute to, extend, or understand the Things 3 MCP server codebase.

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Development Setup](#development-setup)
3. [Code Structure](#code-structure)
4. [Adding New Features](#adding-new-features)
5. [Testing Guidelines](#testing-guidelines)
6. [Contributing Instructions](#contributing-instructions)
7. [Release Process](#release-process)

## 🏗️ Architecture Overview

### System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MCP Client    │    │  FastMCP 2.0    │    │    Things 3     │
│   (Claude UI)   │◄──►│     Server      │◄──►│  Application    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  AppleScript    │
                    │    Manager      │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   URL Schemes   │
                    │   & Direct AS   │
                    └─────────────────┘
```

### Core Components

1. **MCP Server Layer** (`simple_server.py`)
   - FastMCP 2.0 server implementation
   - Tool registration and routing
   - Error handling and logging
   - Health monitoring

2. **Tools Layer** (`tools.py`)
   - Business logic implementation
   - Data transformation
   - Caching and optimization
   - Response formatting

3. **AppleScript Manager** (`applescript_manager.py`)
   - AppleScript execution
   - URL scheme handling
   - Retry logic and error recovery
   - Process management

4. **Models Layer** (`models.py`)
   - Pydantic data models
   - Type validation
   - Serialization/deserialization
   - API contracts

### Design Principles

- **Separation of Concerns**: Each layer has a single responsibility
- **Error Resilience**: Comprehensive error handling at every layer
- **Performance**: Caching, connection pooling, and async operations
- **Maintainability**: Clean code, type hints, and documentation
- **Testability**: Dependency injection and mocking support

## 🛠️ Development Setup

### Prerequisites

- **macOS**: 10.15+ (required for Things 3)
- **Things 3**: Latest version
- **Python**: 3.8+
- **Git**: For version control
- **IDE**: VS Code, PyCharm, or similar

### Local Development Environment

```bash
# Clone the repository
git clone https://github.com/your-repo/things-mcp-server.git
cd things-mcp-server

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install development dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify installation
python -m things_mcp.main --health-check
```

### Development Dependencies

The `[dev]` extra includes:

- **pytest**: Testing framework
- **pytest-asyncio**: Async test support
- **black**: Code formatting
- **isort**: Import sorting
- **mypy**: Type checking
- **pre-commit**: Git hooks
- **coverage**: Code coverage
- **flake8**: Linting

### IDE Setup

#### VS Code Configuration

Create `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.sortImports.args": ["--profile", "black"],
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
```

#### PyCharm Configuration

1. Set interpreter to `./venv/bin/python`
2. Enable Black formatter in preferences
3. Configure isort with Black profile
4. Enable mypy inspections

## 📁 Code Structure

### Project Layout

```
src/things_mcp/
├── __init__.py              # Package initialization
├── __main__.py              # Module entry point
├── main.py                  # CLI entry point and main server
├── simple_server.py         # FastMCP server with tool registration
├── applescript_manager.py   # AppleScript execution and caching
├── tools.py                 # Core tool implementations
├── models.py                # Pydantic data models
├── config.py                # Configuration management
├── models/
│   └── things_models.py     # Things-specific data models
├── services/
│   ├── applescript_manager.py  # Service layer
│   └── error_handler.py        # Error handling utilities
└── tools/
    └── core_operations.py      # Core tool operations
```

### Key Files Explained

#### `simple_server.py`
```python
class ThingsMCPServer:
    """Main MCP server class with tool registration."""
    
    def __init__(self):
        self.mcp = FastMCP("things-mcp")
        self.applescript_manager = AppleScriptManager()
        self.tools = ThingsTools(self.applescript_manager)
        self._register_tools()
    
    def _register_tools(self):
        """Register all MCP tools with FastMCP decorators."""
        
        @self.mcp.tool()
        def get_todos(project_uuid: Optional[str] = None) -> List[Dict]:
            return self.tools.get_todos(project_uuid)
```

#### `applescript_manager.py`
```python
class AppleScriptManager:
    """Manages AppleScript execution with caching and retry logic."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.cache = TTLCache(maxsize=100, ttl=300)
        self.retry_count = 3
    
    def execute_applescript(self, script: str, cache_key: str = None) -> Dict:
        """Execute AppleScript with caching and retry logic."""
```

#### `tools.py`
```python
class ThingsTools:
    """Core business logic for Things 3 operations."""
    
    def __init__(self, applescript_manager: AppleScriptManager):
        self.applescript = applescript_manager
    
    def get_todos(self, project_uuid: Optional[str] = None) -> List[Dict]:
        """Get todos with data transformation and error handling."""
```

### Data Flow

1. **Request**: MCP client calls tool
2. **Validation**: FastMCP validates parameters using Pydantic
3. **Routing**: Server routes to appropriate tool method
4. **Business Logic**: Tool method processes request
5. **AppleScript**: Manager executes AppleScript or URL scheme
6. **Caching**: Results cached if appropriate
7. **Response**: Data transformed and returned

## 🔧 Adding New Features

### Adding a New MCP Tool

#### Step 1: Define the Tool Interface

Add to `simple_server.py`:

```python
@self.mcp.tool()
def new_tool_name(
    param1: str = Field(..., description="Required parameter"),
    param2: Optional[int] = Field(None, description="Optional parameter")
) -> Dict[str, Any]:
    """Tool description for MCP client."""
    try:
        return self.tools.new_tool_implementation(param1, param2)
    except Exception as e:
        logger.error(f"Error in new tool: {e}")
        raise
```

#### Step 2: Implement Business Logic

Add to `tools.py`:

```python
def new_tool_implementation(self, param1: str, param2: Optional[int] = None) -> Dict[str, Any]:
    """Implement the actual tool logic."""
    try:
        # Validate inputs
        if not param1:
            raise ValueError("param1 cannot be empty")
        
        # Execute AppleScript or URL scheme
        result = self.applescript.execute_applescript(
            script=self._build_applescript(param1, param2),
            cache_key=f"new_tool_{param1}"
        )
        
        # Transform and return data
        return self._transform_result(result)
        
    except Exception as e:
        logger.error(f"Error in tool implementation: {e}")
        raise

def _build_applescript(self, param1: str, param2: Optional[int]) -> str:
    """Build AppleScript for the operation."""
    return f'''
    tell application "Things3"
        -- AppleScript implementation
        return "result"
    end tell
    '''

def _transform_result(self, raw_result: Dict) -> Dict[str, Any]:
    """Transform AppleScript result to standardized format."""
    return {
        "success": raw_result.get("success", False),
        "data": raw_result.get("output"),
        "timestamp": datetime.now().isoformat()
    }
```

#### Step 3: Add Data Models

Add to `models.py` if needed:

```python
class NewToolRequest(BaseModel):
    """Request model for new tool."""
    param1: str = Field(..., description="Required parameter")
    param2: Optional[int] = Field(None, description="Optional parameter")

class NewToolResponse(BaseModel):
    """Response model for new tool."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str
```

#### Step 4: Add Tests

Create `tests/test_new_tool.py`:

```python
import pytest
from unittest.mock import Mock, patch
from things_mcp.tools import ThingsTools

class TestNewTool:
    @pytest.fixture
    def mock_applescript_manager(self):
        return Mock()
    
    @pytest.fixture
    def tools(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)
    
    def test_new_tool_success(self, tools, mock_applescript_manager):
        # Mock the AppleScript response
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "expected_result"
        }
        
        # Call the tool
        result = tools.new_tool_implementation("test_param", 42)
        
        # Verify results
        assert result["success"] is True
        assert result["data"] == "expected_result"
        
        # Verify AppleScript was called correctly
        mock_applescript_manager.execute_applescript.assert_called_once()
    
    def test_new_tool_validation_error(self, tools):
        with pytest.raises(ValueError, match="param1 cannot be empty"):
            tools.new_tool_implementation("", None)
```

### Adding AppleScript Operations

#### Direct AppleScript

```python
def execute_direct_applescript(self, operation_params: Dict) -> Dict:
    """Execute AppleScript directly."""
    script = f'''
    tell application "Things3"
        set theTodo to to do id "{operation_params['todo_id']}"
        set name of theTodo to "{operation_params['new_title']}"
        return {{id: id of theTodo, name: name of theTodo}}
    end tell
    '''
    
    return self.applescript.execute_applescript(script)
```

#### URL Scheme Operations

```python
def execute_url_scheme(self, action: str, params: Dict) -> Dict:
    """Execute Things URL scheme."""
    url_params = urllib.parse.urlencode(params)
    url = f"things:///{action}?{url_params}"
    
    return self.applescript.execute_url_scheme(action, params)
```

### Extending the AppleScript Manager

#### Adding Custom Caching

```python
class CustomCacheManager:
    def __init__(self):
        self.memory_cache = TTLCache(maxsize=100, ttl=300)
        self.disk_cache = DiskCache("./cache")
    
    def get_cached(self, key: str) -> Optional[Dict]:
        # Try memory cache first
        if key in self.memory_cache:
            return self.memory_cache[key]
        
        # Try disk cache
        if key in self.disk_cache:
            result = self.disk_cache[key]
            self.memory_cache[key] = result  # Promote to memory
            return result
        
        return None
```

#### Adding Retry Strategies

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class AppleScriptManager:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def execute_with_retry(self, script: str) -> Dict:
        """Execute AppleScript with exponential backoff retry."""
        return self._execute_raw_applescript(script)
```

## 🧪 Testing Guidelines

### Test Structure

```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── unit/                    # Unit tests
│   ├── test_applescript_manager.py
│   ├── test_tools.py
│   └── test_models.py
├── integration/             # Integration tests
│   ├── test_server_lifecycle.py
│   ├── test_things_integration.py
│   └── test_error_handling.py
├── fixtures/                # Test data and fixtures
│   ├── applescript_responses.json
│   └── sample_data.py
└── test_runner.py          # Custom test runner
```

### Unit Testing

#### Testing Tools

```python
# tests/unit/test_tools.py
import pytest
from unittest.mock import Mock, patch
from things_mcp.tools import ThingsTools

class TestThingsTools:
    @pytest.fixture
    def mock_applescript_manager(self):
        manager = Mock()
        manager.execute_applescript.return_value = {
            "success": True,
            "output": [{"id": "123", "name": "Test Todo"}]
        }
        return manager
    
    @pytest.fixture
    def tools(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)
    
    def test_get_todos_success(self, tools, mock_applescript_manager):
        result = tools.get_todos()
        
        assert len(result) == 1
        assert result[0]["title"] == "Test Todo"
        mock_applescript_manager.execute_applescript.assert_called_once()
    
    def test_get_todos_with_project_filter(self, tools, mock_applescript_manager):
        project_uuid = "project-123"
        tools.get_todos(project_uuid=project_uuid)
        
        # Verify AppleScript was called with project filter
        call_args = mock_applescript_manager.execute_applescript.call_args
        assert project_uuid in str(call_args)
```

#### Testing AppleScript Manager

```python
# tests/unit/test_applescript_manager.py
import pytest
from unittest.mock import patch, Mock
from things_mcp.applescript_manager import AppleScriptManager

class TestAppleScriptManager:
    @pytest.fixture
    def manager(self):
        return AppleScriptManager(timeout=10)
    
    @patch('subprocess.run')
    def test_execute_applescript_success(self, mock_subprocess, manager):
        # Mock successful subprocess response
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="success",
            stderr=""
        )
        
        result = manager.execute_applescript("test script")
        
        assert result["success"] is True
        assert result["output"] == "success"
    
    @patch('subprocess.run')
    def test_execute_applescript_failure(self, mock_subprocess, manager):
        # Mock failed subprocess response
        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="AppleScript error"
        )
        
        result = manager.execute_applescript("test script")
        
        assert result["success"] is False
        assert "AppleScript error" in result["error"]
```

### Integration Testing

#### Testing Server Lifecycle

```python
# tests/integration/test_server_lifecycle.py
import pytest
import asyncio
from mcp import ClientSession
from things_mcp.simple_server import ThingsMCPServer

class TestServerLifecycle:
    @pytest.fixture
    async def server(self):
        server = ThingsMCPServer()
        # Start server in test mode
        await server.start_test_mode()
        yield server
        await server.stop()
    
    @pytest.mark.asyncio
    async def test_server_startup_and_health(self, server):
        # Test health check
        health = await server.tools.health_check()
        assert health["server_status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_tool_registration(self, server):
        # Verify all tools are registered
        tools = server.mcp.list_tools()
        expected_tools = [
            "get_todos", "add_todo", "update_todo",
            "get_projects", "add_project",
            "health_check"
        ]
        
        for tool_name in expected_tools:
            assert tool_name in [tool.name for tool in tools]
```

#### Testing Things 3 Integration

```python
# tests/integration/test_things_integration.py
import pytest
from things_mcp.applescript_manager import AppleScriptManager

class TestThingsIntegration:
    @pytest.fixture
    def manager(self):
        return AppleScriptManager()
    
    @pytest.mark.skipif(not_things_available(), reason="Things 3 not available")
    def test_things_connectivity(self, manager):
        # Test if Things 3 is accessible
        is_running = manager.is_things_running()
        assert is_running is True
    
    @pytest.mark.skipif(not_things_available(), reason="Things 3 not available")
    def test_get_version(self, manager):
        # Test getting Things 3 version
        script = 'tell application "Things3" to get version'
        result = manager.execute_applescript(script)
        
        assert result["success"] is True
        assert result["output"]  # Should have version string

def not_things_available():
    """Check if Things 3 is available for testing."""
    try:
        manager = AppleScriptManager()
        return not manager.is_things_running()
    except:
        return True
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/things_mcp --cov-report=html

# Run specific test file
pytest tests/unit/test_tools.py

# Run with verbose output
pytest -v

# Run integration tests only
pytest tests/integration/

# Run with specific markers
pytest -m "not integration"
```

### Test Configuration

```python
# conftest.py
import pytest
from unittest.mock import Mock
from things_mcp.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools

@pytest.fixture
def mock_applescript_manager():
    """Mock AppleScript manager for unit tests."""
    manager = Mock(spec=AppleScriptManager)
    manager.execute_applescript.return_value = {"success": True, "output": []}
    manager.execute_url_scheme.return_value = {"success": True}
    manager.is_things_running.return_value = True
    return manager

@pytest.fixture
def things_tools(mock_applescript_manager):
    """Things tools with mocked AppleScript manager."""
    return ThingsTools(mock_applescript_manager)

@pytest.fixture
def sample_todo_data():
    """Sample todo data for testing."""
    return {
        "id": "todo-123",
        "title": "Test Todo",
        "notes": "Test notes",
        "status": "open",
        "tags": ["test", "sample"],
        "creation_date": "2024-01-01T10:00:00Z"
    }
```

## 🤝 Contributing Instructions

### Getting Started

1. **Fork the Repository**
   ```bash
   # Fork on GitHub, then clone your fork
   git clone https://github.com/YOUR_USERNAME/things-mcp-server.git
   cd things-mcp-server
   ```

2. **Set Up Development Environment**
   ```bash
   # Follow development setup instructions
   python -m venv venv
   source venv/bin/activate
   pip install -e ".[dev]"
   pre-commit install
   ```

3. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

### Code Standards

#### Python Style Guide

We follow PEP 8 with these specific guidelines:

- **Line Length**: 88 characters (Black default)
- **Imports**: Use isort with Black profile
- **Type Hints**: Required for all public functions
- **Docstrings**: Google style docstrings

#### Example Code Style

```python
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ExampleClass:
    """Example class following our style guidelines.
    
    This class demonstrates proper formatting, type hints,
    and documentation standards.
    
    Args:
        param1: Description of parameter 1
        param2: Optional parameter with default
    """
    
    def __init__(self, param1: str, param2: Optional[int] = None) -> None:
        self.param1 = param1
        self.param2 = param2 or 0
    
    def process_data(self, input_data: List[Dict[str, str]]) -> Dict[str, int]:
        """Process input data and return summary.
        
        Args:
            input_data: List of dictionaries to process
            
        Returns:
            Dictionary with processing results
            
        Raises:
            ValueError: If input_data is empty
        """
        if not input_data:
            raise ValueError("input_data cannot be empty")
        
        try:
            # Processing logic here
            result = {"processed": len(input_data)}
            logger.info(f"Processed {len(input_data)} items")
            return result
            
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            raise
```

#### Pre-commit Hooks

Our pre-commit configuration runs:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3
        
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: ["--profile", "black"]
        
  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        additional_dependencies: [flake8-docstrings]
        
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

### Pull Request Process

#### 1. Before Submitting

```bash
# Run all checks
pre-commit run --all-files

# Run tests
pytest --cov=src/things_mcp

# Update documentation if needed
# Check that all tests pass
```

#### 2. Pull Request Template

```markdown
## Description
Brief description of changes made.

## Type of Change
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests pass locally
- [ ] Added appropriate type hints
```

#### 3. Review Process

1. **Automated Checks**: CI/CD runs tests and style checks
2. **Code Review**: Maintainers review code quality and design
3. **Testing**: Changes tested in development environment
4. **Documentation**: Verify documentation is updated
5. **Merge**: Changes merged after approval

### Issue Guidelines

#### Bug Reports

```markdown
**Bug Description**
Clear description of the bug.

**Steps to Reproduce**
1. Step 1
2. Step 2
3. Step 3

**Expected Behavior**
What should happen.

**Actual Behavior**
What actually happened.

**Environment**
- OS: macOS 13.0
- Python: 3.11
- Things 3: 3.19.1
- Server Version: 1.0.0

**Logs**
Include relevant log output.
```

#### Feature Requests

```markdown
**Feature Description**
Clear description of the requested feature.

**Use Case**
Why is this feature needed?

**Proposed Solution**
How should this feature work?

**Alternatives Considered**
Other approaches that were considered.

**Additional Context**
Any other relevant information.
```

## 🚀 Release Process

### Version Management

We use semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Steps

#### 1. Prepare Release

```bash
# Create release branch
git checkout -b release/v1.2.0

# Update version in setup.py and __init__.py
# Update CHANGELOG.md
# Update documentation
```

#### 2. Testing

```bash
# Run full test suite
pytest --cov=src/things_mcp --cov-report=html

# Test installation
pip install -e .
python -m things_mcp.main --health-check

# Manual testing on clean environment
```

#### 3. Documentation Update

```bash
# Update API documentation
# Update user guide with new features
# Update developer guide if needed
# Generate API reference docs
```

#### 4. Create Release

```bash
# Commit changes
git add .
git commit -m "Prepare release v1.2.0"

# Create tag
git tag -a v1.2.0 -m "Release v1.2.0"

# Push to GitHub
git push origin release/v1.2.0
git push origin v1.2.0
```

#### 5. GitHub Release

1. Create release on GitHub
2. Upload distribution files
3. Write release notes
4. Publish release

### Continuous Integration

Our CI/CD pipeline includes:

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: macos-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, "3.10", "3.11"]
        
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
          
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
          
      - name: Run tests
        run: |
          pytest --cov=src/things_mcp --cov-report=xml
          
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

This developer guide provides comprehensive information for contributing to the Things 3 MCP server. For usage information, see the [User Guide](USER_GUIDE.md) and [API Reference](API_REFERENCE.md).# Testing Guide for Things 3 MCP Server

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
# Contributing to Things 3 MCP Server

Thank you for your interest in contributing to the Things 3 MCP Server! This guide will help you get started with contributing to our open-source project.

## 🌟 Ways to Contribute

We welcome all types of contributions:

- 🐛 **Bug Reports** - Help us identify and fix issues
- 💡 **Feature Requests** - Suggest new functionality
- 📖 **Documentation** - Improve guides, examples, and API docs
- 🧪 **Tests** - Add test coverage for better reliability
- ✨ **Code Contributions** - Implement features and fix bugs
- 🎨 **Examples** - Create usage examples and tutorials
- 💬 **Community Support** - Help others in discussions

## 🚀 Quick Start for Contributors

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/things-mcp-server.git
cd things-mcp-server

# Add upstream remote
git remote add upstream https://github.com/yourusername/things-mcp-server.git
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### 3. Create a Feature Branch

```bash
# Always create a new branch for your work
git checkout -b feature/your-feature-name
```

### 4. Make Your Changes

Follow our [coding standards](#coding-standards) and add tests for your changes.

### 5. Test Your Changes

```bash
# Run the full test suite
pytest

# Run with coverage
pytest --cov=src/things_mcp --cov-report=html

# Run linting
flake8 src/ tests/
black --check src/ tests/
isort --check src/ tests/
mypy src/
```

### 6. Submit a Pull Request

```bash
# Push your branch
git push origin feature/your-feature-name
```

Then open a Pull Request on GitHub.

## 📝 Development Setup

### Prerequisites

- macOS 12.0 or later
- Python 3.8+
- Things 3 installed
- Git
- IDE with Python support (VS Code, PyCharm, etc.)

### Detailed Setup

```bash
# 1. Clone and setup
git clone https://github.com/YOUR_USERNAME/things-mcp-server.git
cd things-mcp-server

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install all dependencies
pip install -e ".[dev,test,docs]"

# 4. Setup pre-commit hooks
pre-commit install

# 5. Copy configuration files
cp config/example.yaml config/development.yaml

# 6. Run tests to verify setup
pytest
```

### IDE Configuration

#### VS Code

Install recommended extensions:
- Python
- Pylance  
- Black Formatter
- isort
- Python Test Explorer

Add to your `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "editor.formatOnSave": true,
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"]
}
```

#### PyCharm

1. Open project in PyCharm
2. Configure Python interpreter to use `./venv/bin/python`
3. Enable Black as code formatter
4. Configure pytest as test runner
5. Enable type checking with mypy

## 🧪 Testing Guidelines

### Test Structure

```
tests/
├── unit/                   # Unit tests
│   ├── test_tools.py
│   ├── test_models.py
│   └── test_applescript_manager.py
├── integration/           # Integration tests
│   ├── test_server_lifecycle.py
│   ├── test_error_handling.py
│   └── test_cli_interface.py
├── fixtures/              # Test data and fixtures
│   ├── sample_todos.json
│   └── mock_responses.py
└── conftest.py           # Pytest configuration
```

### Writing Tests

#### Unit Tests

```python
# tests/unit/test_example.py
import pytest
from unittest.mock import Mock, patch
from things_mcp.tools import ThingsTools

class TestThingsTools:
    
    def test_add_todo_basic(self):
        """Test basic todo creation."""
        applescript_manager = Mock()
        tools = ThingsTools(applescript_manager)
        
        # Test implementation
        result = tools.add_todo(title="Test Todo")
        
        # Assertions
        assert result["success"] is True
        applescript_manager.execute_script.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_todo_async(self):
        """Test async todo creation."""
        # Async test implementation
        pass
```

#### Integration Tests

```python
# tests/integration/test_server.py
import pytest
from things_mcp.server import ThingsMCPServer

@pytest.mark.integration
class TestServerIntegration:
    
    @pytest.fixture
    def server(self):
        return ThingsMCPServer()
    
    async def test_health_check_integration(self, server):
        """Test actual health check against Things 3."""
        health = await server.health_check()
        assert health["server_status"] == "healthy"
```

### Test Categories

Use pytest markers to categorize tests:

```python
@pytest.mark.unit          # Fast unit tests
@pytest.mark.integration   # Slower integration tests  
@pytest.mark.applescript   # Tests requiring Things 3
@pytest.mark.slow          # Tests that take >5 seconds
@pytest.mark.skip_ci       # Skip in CI environment
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific categories
pytest -m "unit"                    # Only unit tests
pytest -m "not slow"                # Skip slow tests
pytest -m "integration"             # Only integration tests

# Run with coverage
pytest --cov=src/things_mcp --cov-report=html

# Run specific test file
pytest tests/unit/test_tools.py

# Run specific test
pytest tests/unit/test_tools.py::TestThingsTools::test_add_todo_basic

# Run with verbose output
pytest -v

# Run tests in parallel (faster)
pytest -n auto
```

## 🎯 Coding Standards

### Code Style

We use these tools to maintain consistent code style:

- **Black**: Code formatting
- **isort**: Import sorting  
- **Flake8**: Linting
- **mypy**: Type checking

```bash
# Format code
black src/ tests/
isort src/ tests/

# Check formatting
black --check src/ tests/
isort --check src/ tests/

# Lint code
flake8 src/ tests/

# Type check
mypy src/
```

### Python Guidelines

#### Function Documentation

```python
def add_todo(
    self,
    title: str,
    notes: Optional[str] = None,
    tags: Optional[List[str]] = None,
    when: Optional[str] = None,
    deadline: Optional[str] = None
) -> Dict[str, Any]:
    """Add a new todo to Things 3.
    
    Args:
        title: The todo title (required)
        notes: Optional notes for the todo
        tags: List of tag names to apply
        when: When to schedule (today, tomorrow, YYYY-MM-DD, etc.)
        deadline: Deadline date in YYYY-MM-DD format
        
    Returns:
        Dict containing creation result with success status and todo data
        
    Raises:
        AppleScriptError: If Things 3 is not accessible
        ValidationError: If parameters are invalid
        
    Example:
        >>> result = await tools.add_todo(
        ...     title="Review proposal",
        ...     notes="Check budget section",
        ...     tags=["work", "urgent"],
        ...     when="tomorrow",
        ...     deadline="2024-01-30"
        ... )
        >>> assert result["success"] is True
    """
```

#### Type Hints

Use type hints throughout:

```python
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

class ThingsTools:
    def __init__(self, applescript_manager: AppleScriptManager) -> None:
        self.applescript = applescript_manager
    
    async def get_todos(
        self, 
        project_uuid: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        # Implementation
        pass
```

#### Error Handling

```python
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

async def risky_operation() -> Dict[str, Any]:
    """Example of proper error handling."""
    try:
        result = await some_operation()
        return {"success": True, "data": result}
    
    except SpecificError as e:
        logger.error(f"Specific error occurred: {e}")
        return {
            "success": False, 
            "error": f"Operation failed: {e}",
            "error_code": "SPECIFIC_ERROR"
        }
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {
            "success": False,
            "error": "An unexpected error occurred",
            "error_code": "UNKNOWN_ERROR"
        }
```

### File Organization

```python
# Standard library imports first
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# Third-party imports
import pytest
from fastmcp import FastMCP

# Local imports
from .applescript_manager import AppleScriptManager
from .models import Todo, Project
```

## 📖 Documentation Standards

### Docstring Format

We use Google-style docstrings:

```python
def example_function(param1: str, param2: int = 0) -> bool:
    """Brief description of what the function does.
    
    Longer description if needed. This can span multiple lines
    and include examples, implementation notes, etc.
    
    Args:
        param1: Description of first parameter
        param2: Description of second parameter (default: 0)
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When param1 is empty
        TypeError: When param2 is not an integer
        
    Example:
        >>> result = example_function("test", 5)
        >>> assert result is True
        
    Note:
        Any important implementation details or caveats
    """
```

### README and Documentation

- Keep language clear and accessible
- Use examples for all concepts
- Include troubleshooting sections
- Update documentation when changing APIs
- Test all code examples

## 🐛 Bug Reports

### Before Reporting

1. Check existing issues
2. Update to latest version
3. Test with minimal reproduction case

### Bug Report Template

Use our issue template or include:

```markdown
## Bug Description
Brief description of the issue

## Steps to Reproduce
1. First step
2. Second step
3. Third step

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- OS: macOS 13.2
- Python: 3.11.1
- Things 3: 3.19.1
- Server Version: 1.0.0

## Additional Context
Any other relevant information, error messages, logs
```

## 💡 Feature Requests

### Before Requesting

1. Check existing feature requests
2. Consider if it fits project scope
3. Think about implementation approach

### Feature Request Template

```markdown
## Feature Description
Clear description of the proposed feature

## Use Case
Why is this needed? What problem does it solve?

## Proposed Solution
How should this feature work?

## Alternatives Considered
What other approaches did you consider?

## Additional Context
Any other relevant information, mockups, examples
```

## 🔄 Pull Request Process

### Before Submitting

- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation is updated
- [ ] CHANGELOG.md is updated
- [ ] Commits are well-formatted

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix (non-breaking change)
- [ ] New feature (non-breaking change)
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added for new functionality
```

### Review Process

1. **Automated Checks**: CI must pass
2. **Code Review**: At least one maintainer review
3. **Testing**: Feature testing by reviewers
4. **Documentation**: Docs review if applicable
5. **Merge**: Squash and merge when approved

## 🎉 Recognition

Contributors are recognized in:

- CHANGELOG.md for each release
- README.md contributors section  
- GitHub repository insights
- Release notes for major contributions

## 📞 Getting Help

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and general discussion
- **Discord**: Real-time chat (link in README)
- **Email**: maintainer@yourdomain.com

### Development Questions

For development help:

1. Check existing documentation
2. Search closed issues/PRs
3. Ask in GitHub Discussions
4. Join our Discord community

## 📜 Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

### Quick Summary

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Respect different viewpoints
- Report unacceptable behavior

## 🏆 Contributor Levels

### First-Time Contributors

- Start with "good first issue" labels
- Documentation improvements
- Test additions
- Bug reports with reproduction steps

### Regular Contributors  

- Feature implementations
- Code reviews
- Issue triage
- Community support

### Core Contributors

- Architecture decisions
- Release management
- Mentoring new contributors
- Project direction

## 📋 Development Checklist

For major contributions, ensure:

- [ ] **Design Discussion**: For large features, discuss approach first
- [ ] **Tests**: Comprehensive test coverage
- [ ] **Documentation**: All public APIs documented
- [ ] **Performance**: No significant performance regressions
- [ ] **Backward Compatibility**: Changes don't break existing users
- [ ] **Security**: No security vulnerabilities introduced
- [ ] **Accessibility**: Features work for all users

Thank you for contributing to Things 3 MCP Server! 🚀
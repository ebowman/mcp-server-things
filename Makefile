# Makefile for Things 3 MCP Server

.PHONY: help install test test-unit test-integration test-live lint clean coverage docs

# Default target
help:
	@echo "Things 3 MCP Server Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  install        Install dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  test           Run all tests"
	@echo "  test-unit      Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-live      Run the opt-in live Things 3 smoke suite (writes to a real Things 3)"
	@echo "  coverage       Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint           Run linting checks"
	@echo "  format         Format code with black"
	@echo ""
	@echo "Utilities:"
	@echo "  clean          Clean build artifacts"
	@echo "  docs           Generate documentation"

# Installation
install:
	pip install -e .
	pip install -r requirements-dev.txt

# Testing targets
test:
	python -m pytest

test-unit:
	python -m pytest tests/unit -v

test-integration:
	python -m pytest tests/integration -v

# Opt-in live Things 3 smoke suite (hq-f0w.14): requires a real, running
# Things 3 and writes to (then cleans up after itself in) that live
# database. Skipped entirely unless THINGS_MCP_LIVE_TESTS=1 is set - see
# tests/live/conftest.py and docs/TESTING.md.
test-live:
	THINGS_MCP_LIVE_TESTS=1 python -m pytest tests/live -v

coverage:
	python -m pytest --cov=src/things_mcp --cov-report=html --cov-report=term-missing

# Code quality
lint:
	python -m flake8 src tests
	python -m mypy src

format:
	python -m black src tests
	python -m isort src tests

# Utilities
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docs:
	@echo "Documentation generation not yet implemented"
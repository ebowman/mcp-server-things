# Makefile for Things 3 MCP Server

# Interpreter: default to the project venv so pytest/flake8/mypy/black are the
# pinned dev tools (a bare `python` can resolve to an unrelated interpreter,
# e.g. miniconda, without them). Override per call: `make PYTHON=python3 test`.
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: help install test test-unit test-integration test-live test-regression lint clean coverage coverage-regression docs

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
	@echo "  test-regression Run the opt-in MCP-boundary regression suite (writes to a real Things 3)"
	@echo "  coverage       Run tests with coverage report"
	@echo "  coverage-regression Run unit+regression+live branch coverage and write coverage-unit.json/coverage-all.json (see docs/testing/COVERAGE_REPORT.md)"
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
	$(PYTHON) -m pip install -e .
	$(PYTHON) -m pip install -r requirements-dev.txt

# Testing targets
test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest tests/unit -v

test-integration:
	$(PYTHON) -m pytest tests/integration -v

# Opt-in live Things 3 smoke suite (hq-f0w.14): requires a real, running
# Things 3 and writes to (then cleans up after itself in) that live
# database. Skipped entirely unless THINGS_MCP_LIVE_TESTS=1 is set - see
# tests/live/conftest.py and docs/TESTING.md.
test-live:
	THINGS_MCP_LIVE_TESTS=1 $(PYTHON) -m pytest tests/live -v

# Opt-in MCP-boundary regression suite (hq-gbl epic): drives the real
# fastmcp Client against a real ThingsMCPServer().mcp, against a real,
# running Things 3. See tests/regression/README.md. Skipped entirely
# unless THINGS_MCP_LIVE_TESTS=1 is set.
test-regression:
	THINGS_MCP_LIVE_TESTS=1 $(PYTHON) -m pytest tests/regression -v

coverage:
	$(PYTHON) -m pytest --cov=src/things_mcp --cov-report=html --cov-report=term-missing

# Branch coverage across unit + regression + live suites (hq-gbl.17): unit
# coverage is written first, then regression+live coverage is appended onto
# the same data file so coverage-all.json reflects the combined total. See
# docs/testing/COVERAGE_REPORT.md for the last published numbers and how to
# interpret them. Requires a running Things 3 (regression/live write to it).
# --cov-fail-under=0 overrides pyproject's [tool.coverage.report] fail_under=80,
# which would otherwise abort the recipe after the unit line (current combined
# coverage is below 80) and the live line would never run.
coverage-regression:
	$(PYTHON) -m pytest tests/unit --cov=src/things_mcp --cov-branch --cov-report=term-missing --cov-report=json:coverage-unit.json --cov-fail-under=0 -q
	THINGS_MCP_LIVE_TESTS=1 $(PYTHON) -m pytest tests/regression tests/live --cov=src/things_mcp --cov-branch --cov-append --cov-report=json:coverage-all.json --cov-fail-under=0 -q

# Code quality
lint:
	$(PYTHON) -m flake8 src tests
	$(PYTHON) -m mypy src

format:
	$(PYTHON) -m black src tests
	$(PYTHON) -m isort src tests

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
"""
Test runner script for Things 3 MCP server tests.

Provides convenient commands for running different test suites,
generating coverage reports, and managing test execution.
"""

import subprocess
import sys
import argparse
from pathlib import Path
from typing import List, Optional


def run_command(cmd: List[str], description: str) -> int:
    """Run a command and return exit code."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
        else:
            print(f"❌ {description} failed with exit code {result.returncode}")
        return result.returncode
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        return 1


def run_unit_tests(verbose: bool = False, coverage: bool = False) -> int:
    """Run unit tests."""
    cmd = ["python", "-m", "pytest", "tests/unit/"]
    
    if verbose:
        cmd.append("-v")
    
    if coverage:
        cmd.extend([
            "--cov=src/things_mcp",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml"
        ])
    
    cmd.extend([
        "--tb=short",
        "--strict-markers",
        "--strict-config"
    ])
    
    return run_command(cmd, "Unit Tests")


def run_integration_tests(verbose: bool = False) -> int:
    """Run integration tests."""
    cmd = ["python", "-m", "pytest", "tests/integration/"]
    
    if verbose:
        cmd.append("-v")
    
    cmd.extend([
        "--tb=short",
        "--strict-markers",
        "--strict-config"
    ])
    
    return run_command(cmd, "Integration Tests")


def run_all_tests(verbose: bool = False, coverage: bool = False) -> int:
    """Run all tests."""
    cmd = ["python", "-m", "pytest", "tests/"]
    
    if verbose:
        cmd.append("-v")
    
    if coverage:
        cmd.extend([
            "--cov=src/things_mcp",
            "--cov-report=html:htmlcov", 
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml",
            "--cov-fail-under=80"
        ])
    
    cmd.extend([
        "--tb=short",
        "--strict-markers",
        "--strict-config"
    ])
    
    return run_command(cmd, "All Tests")


def run_specific_test(test_path: str, verbose: bool = False) -> int:
    """Run a specific test file or test function."""
    cmd = ["python", "-m", "pytest", test_path]
    
    if verbose:
        cmd.append("-v")
    
    cmd.extend([
        "--tb=long",
        "--strict-markers",
        "--strict-config"
    ])
    
    return run_command(cmd, f"Specific Test: {test_path}")


def run_tests_by_marker(marker: str, verbose: bool = False) -> int:
    """Run tests by marker."""
    cmd = ["python", "-m", "pytest", "-m", marker, "tests/"]
    
    if verbose:
        cmd.append("-v")
    
    cmd.extend([
        "--tb=short",
        "--strict-markers",
        "--strict-config"
    ])
    
    return run_command(cmd, f"Tests with marker: {marker}")


def run_linting() -> int:
    """Run code linting."""
    commands = [
        (["python", "-m", "black", "--check", "src/", "tests/"], "Black Code Formatting Check"),
        (["python", "-m", "isort", "--check-only", "src/", "tests/"], "Import Sorting Check"),
        (["python", "-m", "flake8", "src/", "tests/"], "Flake8 Linting"),
    ]
    
    total_failures = 0
    for cmd, desc in commands:
        try:
            result = run_command(cmd, desc)
            if result != 0:
                total_failures += 1
        except FileNotFoundError:
            print(f"⚠️  Skipping {desc} - tool not installed")
    
    return total_failures


def run_type_checking() -> int:
    """Run type checking with mypy."""
    cmd = ["python", "-m", "mypy", "src/things_mcp", "--ignore-missing-imports"]
    
    try:
        return run_command(cmd, "Type Checking with MyPy")
    except FileNotFoundError:
        print("⚠️  Skipping type checking - mypy not installed")
        return 0


def generate_coverage_report() -> int:
    """Generate coverage report."""
    print("\n" + "="*60)
    print("Generating Coverage Report")
    print("="*60)
    
    # Run tests with coverage
    result = run_all_tests(coverage=True)
    
    if result == 0:
        print("\n📊 Coverage reports generated:")
        print("  - HTML: htmlcov/index.html")
        print("  - XML: coverage.xml")
        print("  - Terminal output above")
    
    return result


def run_performance_tests() -> int:
    """Run performance-focused tests."""
    cmd = [
        "python", "-m", "pytest", 
        "-m", "not slow",  # Skip slow tests for performance testing
        "tests/",
        "--benchmark-only",  # If pytest-benchmark is installed
        "-v"
    ]
    
    try:
        return run_command(cmd, "Performance Tests")
    except Exception:
        # Fallback to regular fast tests
        cmd = [
            "python", "-m", "pytest",
            "-m", "not slow",
            "tests/",
            "-v"
        ]
        return run_command(cmd, "Fast Tests (Performance)")


def run_ci_tests() -> int:
    """Run tests suitable for CI environment."""
    print("\n🚀 Running CI Test Suite")
    
    total_failures = 0
    
    # Run linting
    if run_linting() != 0:
        total_failures += 1
    
    # Run type checking
    if run_type_checking() != 0:
        total_failures += 1
    
    # Run all tests with coverage
    if run_all_tests(verbose=True, coverage=True) != 0:
        total_failures += 1
    
    print(f"\n{'='*60}")
    if total_failures == 0:
        print("✅ All CI checks passed!")
    else:
        print(f"❌ {total_failures} CI checks failed")
    print('='*60)
    
    return total_failures


def list_test_files() -> None:
    """List all test files."""
    print("\n📋 Available Test Files:")
    print("="*40)
    
    test_dir = Path("tests")
    if not test_dir.exists():
        print("  No test directory found")
        return
    
    for test_file in sorted(test_dir.rglob("test_*.py")):
        try:
            relative_path = test_file.relative_to(Path.cwd())
            print(f"  {relative_path}")
        except ValueError:
            # Fallback to just the filename if relative_to fails
            print(f"  {test_file}")
    
    print("\n📋 Available Test Markers:")
    print("="*40)
    
    markers = [
        "unit - Unit tests for individual components",
        "integration - Integration tests requiring multiple components", 
        "server - Server-level tests",
        "applescript - Tests involving AppleScript operations",
        "tools - Tests for MCP tools",
        "models - Tests for data models",
        "error - Error handling tests",
        "slow - Slow tests that may take longer to execute"
    ]
    
    for marker in markers:
        print(f"  {marker}")


def clean_test_artifacts() -> None:
    """Clean test artifacts and cache files."""
    import shutil
    
    print("\n🧹 Cleaning test artifacts...")
    
    artifacts = [
        ".pytest_cache",
        "__pycache__",
        "htmlcov",
        "coverage.xml",
        ".coverage",
        "tests/__pycache__",
        "src/__pycache__",
    ]
    
    for artifact in artifacts:
        path = Path(artifact)
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
                print(f"  Removed directory: {artifact}")
            else:
                path.unlink()
                print(f"  Removed file: {artifact}")
    
    # Clean Python cache recursively
    for cache_dir in Path(".").rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"  Removed cache: {cache_dir}")
    
    print("✅ Test artifacts cleaned")


def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(
        description="Test runner for Things 3 MCP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/test_runner.py unit                    # Run unit tests
  python tests/test_runner.py integration             # Run integration tests  
  python tests/test_runner.py all --coverage          # Run all tests with coverage
  python tests/test_runner.py specific tests/unit/test_models.py  # Run specific test
  python tests/test_runner.py marker unit             # Run tests with 'unit' marker
  python tests/test_runner.py ci                      # Run full CI test suite
  python tests/test_runner.py list                    # List available tests
  python tests/test_runner.py clean                   # Clean test artifacts
        """
    )
    
    parser.add_argument(
        "command",
        choices=[
            "unit", "integration", "all", "specific", "marker", 
            "lint", "typecheck", "coverage", "performance", "ci",
            "list", "clean"
        ],
        help="Test command to run"
    )
    
    parser.add_argument(
        "target",
        nargs="?",
        help="Target for specific/marker commands (test file path or marker name)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--coverage",
        action="store_true", 
        help="Generate coverage report"
    )
    
    args = parser.parse_args()
    
    # Change to project root directory
    project_root = Path(__file__).parent.parent
    import os
    os.chdir(project_root)
    
    # Execute command
    exit_code = 0
    
    if args.command == "unit":
        exit_code = run_unit_tests(args.verbose, args.coverage)
    elif args.command == "integration":
        exit_code = run_integration_tests(args.verbose)
    elif args.command == "all":
        exit_code = run_all_tests(args.verbose, args.coverage)
    elif args.command == "specific":
        if not args.target:
            print("❌ Error: specific command requires a target test file")
            exit_code = 1
        else:
            exit_code = run_specific_test(args.target, args.verbose)
    elif args.command == "marker":
        if not args.target:
            print("❌ Error: marker command requires a marker name")
            exit_code = 1
        else:
            exit_code = run_tests_by_marker(args.target, args.verbose)
    elif args.command == "lint":
        exit_code = run_linting()
    elif args.command == "typecheck":
        exit_code = run_type_checking()
    elif args.command == "coverage":
        exit_code = generate_coverage_report()
    elif args.command == "performance":
        exit_code = run_performance_tests()
    elif args.command == "ci":
        exit_code = run_ci_tests()
    elif args.command == "list":
        list_test_files()
        exit_code = 0
    elif args.command == "clean":
        clean_test_artifacts()
        exit_code = 0
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
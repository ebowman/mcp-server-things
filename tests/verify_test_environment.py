#!/usr/bin/env python3
"""
Verification script to ensure the test environment is properly set up
for running the enhanced move_record functionality tests.

This script checks:
1. Required Python modules are importable
2. Test dependencies are available
3. Mock objects can be created successfully
4. Basic test infrastructure is working
"""

import sys
import os
from pathlib import Path

def check_import(module_name, description):
    """Check if a module can be imported."""
    try:
        __import__(module_name)
        print(f"✅ {description}")
        return True
    except ImportError as e:
        print(f"❌ {description} - Error: {e}")
        return False

def check_project_structure():
    """Check if the project structure is correct."""
    project_root = Path(__file__).parent.parent
    
    required_paths = [
        "src/things_mcp/tools.py",
        "src/things_mcp/applescript_manager.py", 
        "src/things_mcp/move_operations.py",
        "src/things_mcp/services/validation_service.py",
        "tests/test_move_record_enhanced.py"
    ]
    
    all_good = True
    print("\n📁 Checking project structure:")
    
    for path in required_paths:
        full_path = project_root / path
        if full_path.exists():
            print(f"✅ {path}")
        else:
            print(f"❌ {path} - File not found")
            all_good = False
    
    return all_good

def test_mock_creation():
    """Test that mock objects can be created successfully."""
    try:
        from unittest.mock import Mock, AsyncMock
        
        # Test basic mock creation
        mock_manager = Mock()
        mock_manager.execute_applescript = AsyncMock()
        
        print("\n🧪 Mock object creation test:")
        print("✅ Mock objects can be created successfully")
        return True
        
    except Exception as e:
        print(f"\n🧪 Mock object creation test:")
        print(f"❌ Failed to create mock objects: {e}")
        return False

def test_pytest_availability():
    """Test that pytest is available and can discover tests."""
    try:
        import pytest
        
        # Try to collect tests from our test file
        project_root = Path(__file__).parent.parent
        test_file = project_root / "tests" / "test_move_record_enhanced.py"
        
        if test_file.exists():
            print("\n🧪 Pytest availability test:")
            print("✅ pytest is available and test file exists")
            return True
        else:
            print("\n🧪 Pytest availability test:")
            print("❌ Test file not found")
            return False
            
    except ImportError:
        print("\n🧪 Pytest availability test:")
        print("❌ pytest is not available - run: pip install pytest")
        return False

def main():
    """Run all verification checks."""
    print("🔍 Verifying Enhanced Move Record Test Environment")
    print("=" * 60)
    
    # Check Python version
    python_version = sys.version_info
    print(f"🐍 Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 7):
        print("⚠️  Python 3.7+ is recommended")
    
    # Check core dependencies
    print("\n📦 Checking core dependencies:")
    all_checks = []
    
    all_checks.append(check_import("asyncio", "asyncio (async/await support)"))
    all_checks.append(check_import("unittest.mock", "unittest.mock (mocking support)"))
    all_checks.append(check_import("pytest", "pytest (test framework)"))
    all_checks.append(check_import("datetime", "datetime (date/time support)"))
    all_checks.append(check_import("typing", "typing (type hints support)"))
    
    # Check project structure
    all_checks.append(check_project_structure())
    
    # Test mock creation
    all_checks.append(test_mock_creation())
    
    # Test pytest
    all_checks.append(test_pytest_availability())
    
    # Check if we can add project to path
    print("\n🛣️  Python path configuration:")
    project_root = Path(__file__).parent.parent
    src_path = str(project_root / "src")
    
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
        print(f"✅ Added {src_path} to Python path")
    else:
        print(f"✅ {src_path} already in Python path")
    
    # Try to import our modules
    print("\n📋 Checking Things MCP modules:")
    module_checks = [
        ("src.things_mcp.tools", "ThingsTools class"),
        ("src.things_mcp.applescript_manager", "AppleScriptManager class"),
        ("src.things_mcp.move_operations", "MoveOperationsTools class"),
        ("src.things_mcp.services.validation_service", "ValidationService class"),
    ]
    
    for module_name, description in module_checks:
        all_checks.append(check_import(module_name, description))
    
    # Summary
    print("\n" + "=" * 60)
    
    if all(all_checks):
        print("🎉 All verification checks passed!")
        print("\nYou can now run the enhanced move_record tests:")
        print("  python tests/run_move_record_tests.py")
        print("  # OR")
        print("  python -m pytest tests/test_move_record_enhanced.py -v")
        return 0
    else:
        print("❌ Some verification checks failed.")
        print("\nPlease resolve the issues above before running the tests.")
        failed_count = sum(1 for check in all_checks if not check)
        print(f"Failed checks: {failed_count}/{len(all_checks)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
#!/usr/bin/env python3
"""
Test runner specifically for the enhanced move_record functionality tests.

This script runs the comprehensive move_record tests and provides detailed output
about the test results, including specific information about what functionality
was tested.

Usage:
    python tests/run_move_record_tests.py
    
Or from the project root:
    python -m pytest tests/test_move_record_enhanced.py -v
"""

import sys
import subprocess
import os
from pathlib import Path

def main():
    """Run the move_record enhanced tests."""
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    test_file = project_root / "tests" / "test_move_record_enhanced.py"
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return 1
    
    print("🧪 Running Enhanced Move Record Functionality Tests")
    print("=" * 60)
    print()
    print("This test suite verifies:")
    print("✅ Backward compatibility with built-in lists (inbox, today, etc.)")
    print("✅ New project move functionality (project:ID format)")
    print("✅ New area move functionality (area:ID format)")
    print("✅ Comprehensive error handling")
    print("✅ Integration with ValidationService and MoveOperationsTools")
    print("✅ Operation queue integration")
    print("✅ Concurrent operations support")
    print()
    print("-" * 60)
    
    # Change to project root directory
    os.chdir(project_root)
    
    # Run pytest with verbose output
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_file),
        "-v",                          # Verbose output
        "--tb=short",                  # Short traceback format
        "--no-header",                 # Skip pytest header
        "--show-capture=no",          # Don't show captured output unless failure
        "-x",                         # Stop at first failure
        "--color=yes"                 # Force colored output
    ]
    
    try:
        result = subprocess.run(cmd, check=False, text=True)
        
        print()
        print("-" * 60)
        
        if result.returncode == 0:
            print("✅ All move_record enhanced functionality tests passed!")
            print()
            print("The following functionality has been verified:")
            print("  • Built-in list moves (inbox, today, upcoming, anytime, someday)")
            print("  • Project moves using 'project:ID' format")
            print("  • Area moves using 'area:ID' format")
            print("  • Validation of todo IDs, project IDs, and area IDs")
            print("  • Error handling for invalid destinations and IDs")
            print("  • Integration with operation queue and concurrency support")
            print("  • Proper backward compatibility maintenance")
            print()
            print("🎉 The enhanced move_record functionality is working correctly!")
        else:
            print("❌ Some tests failed. Please review the output above.")
            print()
            print("Common issues to check:")
            print("  • Ensure all required dependencies are installed")
            print("  • Verify that src/things_mcp modules are importable")
            print("  • Check that mock configurations match the actual implementation")
        
        return result.returncode
        
    except FileNotFoundError:
        print("❌ Python or pytest not found. Please ensure they are installed.")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error running tests: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
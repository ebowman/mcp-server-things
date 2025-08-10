#!/usr/bin/env python3
"""
Simple test runner for tag creation control tests.
Run this file to execute the tests manually if pytest is not available.
"""

import sys
import os
import traceback

# Add src directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def run_test_method(test_instance, method_name):
    """Run a single test method and report results."""
    try:
        method = getattr(test_instance, method_name)
        method()
        print(f"✓ {method_name}")
        return True
    except Exception as e:
        print(f"✗ {method_name}: {str(e)}")
        if "--verbose" in sys.argv:
            traceback.print_exc()
        return False

def run_tests():
    """Run all tag creation control tests manually."""
    try:
        from test_tag_creation_control import (
            TestTagConfig,
            TestTagValidationService,
            TestTagCreationIntegration,
            TestTagOperationsWithValidation,
            TestEdgeCasesAndErrorHandling
        )
        
        test_classes = [
            (TestTagConfig, [
                'test_default_config',
                'test_custom_config', 
                'test_config_from_dict',
                'test_invalid_policy_string',
                'test_config_from_partial_dict'
            ]),
            (TestTagValidationService, [
                'test_get_existing_tags_case_insensitive',
                'test_get_existing_tags_case_sensitive', 
                'test_get_existing_tags_with_predefined',
                'test_validate_tags_auto_create',
                'test_validate_tags_strict_no_create',
                'test_validate_tags_create_with_warning',
                'test_validate_tags_limited_auto_create_within_limit',
                'test_validate_tags_limited_auto_create_exceeds_limit',
                'test_validate_tags_case_sensitivity',
                'test_validate_tags_empty_list',
                'test_validate_tags_duplicate_tags'
            ]),
            (TestTagCreationIntegration, [
                'test_load_config_from_env_vars',
                'test_load_config_defaults',
                'test_load_config_invalid_file'
            ]),
            (TestTagOperationsWithValidation, [
                'test_add_tags_backward_compatibility',
                'test_remove_tags_no_validation'
            ]),
            (TestEdgeCasesAndErrorHandling, [
                'test_applescript_error_handling',
                'test_invalid_tag_names',
                'test_large_tag_list',
                'test_unicode_tag_names'
            ])
        ]
        
        total_tests = 0
        passed_tests = 0
        
        print("Running Tag Creation Control Tests")
        print("=" * 50)
        
        for test_class, test_methods in test_classes:
            print(f"\nRunning {test_class.__name__}:")
            print("-" * 30)
            
            for method_name in test_methods:
                # Skip methods that require fixtures for manual testing
                if method_name in ['test_load_config_from_file', 
                                  'test_add_tags_with_validation_success',
                                  'test_add_tags_with_validation_failure',
                                  'test_get_tagged_items_no_validation']:
                    print(f"~ {method_name} (requires fixtures - skipped)")
                    continue
                    
                test_instance = test_class()
                total_tests += 1
                if run_test_method(test_instance, method_name):
                    passed_tests += 1
        
        print(f"\n{'='*50}")
        print(f"Test Results: {passed_tests}/{total_tests} passed")
        
        if passed_tests == total_tests:
            print("✓ All tests passed!")
            return 0
        else:
            print(f"✗ {total_tests - passed_tests} tests failed")
            return 1
            
    except ImportError as e:
        print(f"Error importing test modules: {e}")
        print("Make sure src/simple_server.py contains the required classes:")
        print("- TagConfig")
        print("- TagCreationPolicy") 
        print("- TagValidationService")
        return 1

if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
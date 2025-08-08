#!/usr/bin/env python3
"""
Manual integration test for the enhanced move_record functionality.

This script can be run with an actual Things 3 installation to verify
that the move_record functionality works end-to-end with real data.

IMPORTANT: This script requires Things 3 to be installed and running.
It will create test todos and then move them around to verify functionality.

Usage:
    python tests/test_move_record_manual.py

The script will:
1. Create test todos in Things 3
2. Test moving them to various destinations
3. Clean up test data
4. Report results
"""

import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add the src directory to the Python path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Import required modules
try:
    from things_mcp.server import ThingsMCPServer
    from things_mcp.config import ThingsMCPConfig
    print("✅ Successfully imported MCP server modules")
except ImportError as e:
    print(f"❌ Failed to import MCP server modules: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


class ManualMoveRecordTester:
    """Manual tester for move_record functionality with real Things 3 data."""
    
    def __init__(self):
        self.server = None
        self.test_todos = []  # Track created test todos for cleanup
        self.test_results = []
    
    async def setup(self):
        """Set up the MCP server and test environment."""
        print("🔧 Setting up test environment...")
        
        # Create server config
        config = ThingsMCPConfig(
            applescript_timeout=10,
            applescript_retry_count=2,
            enable_detailed_logging=True
        )
        
        # Initialize server
        self.server = ThingsMCPServer(config)
        
        # Check Things 3 availability
        try:
            # Test basic connectivity
            result = await self.server.tools.get_inbox()
            if not result.get("success"):
                raise Exception("Failed to connect to Things 3")
            print("✅ Successfully connected to Things 3")
        except Exception as e:
            print(f"❌ Failed to connect to Things 3: {e}")
            print("Make sure Things 3 is installed and running")
            raise
    
    async def create_test_todos(self) -> List[str]:
        """Create test todos for move testing."""
        print("\n📝 Creating test todos...")
        
        test_todo_data = [
            {
                "title": f"Move Test Todo 1 - {datetime.now().strftime('%H:%M:%S')}",
                "notes": "Test todo for move_record testing (inbox to today)"
            },
            {
                "title": f"Move Test Todo 2 - {datetime.now().strftime('%H:%M:%S')}",
                "notes": "Test todo for move_record testing (project moves)"
            },
            {
                "title": f"Move Test Todo 3 - {datetime.now().strftime('%H:%M:%S')}",
                "notes": "Test todo for move_record testing (area moves)"
            }
        ]
        
        created_todo_ids = []
        
        for todo_data in test_todo_data:
            try:
                result = await self.server.tools.add_todo(
                    title=todo_data["title"],
                    notes=todo_data["notes"]
                )
                
                if result.get("success") and "id" in result:
                    todo_id = result["id"]
                    created_todo_ids.append(todo_id)
                    self.test_todos.append(todo_id)
                    print(f"✅ Created test todo: {todo_id}")
                else:
                    print(f"❌ Failed to create test todo: {todo_data['title']}")
                    
            except Exception as e:
                print(f"❌ Exception creating todo: {e}")
        
        print(f"📝 Created {len(created_todo_ids)} test todos")
        return created_todo_ids
    
    async def test_backward_compatibility_moves(self, todo_ids: List[str]):
        """Test backward compatibility moves to built-in lists."""
        print("\n🧪 Testing backward compatibility: built-in list moves")
        
        built_in_lists = ["inbox", "today", "anytime", "someday"]
        
        if not todo_ids:
            print("❌ No test todos available")
            return
        
        todo_id = todo_ids[0]
        
        for list_name in built_in_lists:
            print(f"  Moving todo to {list_name}...")
            
            try:
                result = await self.server.tools.move_record(todo_id, list_name)
                
                if result.get("success"):
                    print(f"✅ Successfully moved to {list_name}")
                    self.test_results.append({
                        "test": f"move_to_{list_name}",
                        "success": True,
                        "message": result.get("message", ""),
                        "backward_compatible": result.get("destination_list") == list_name
                    })
                else:
                    print(f"❌ Failed to move to {list_name}: {result.get('message', 'Unknown error')}")
                    self.test_results.append({
                        "test": f"move_to_{list_name}",
                        "success": False,
                        "error": result.get("error", "Unknown error")
                    })
                
                # Small delay between moves
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Exception moving to {list_name}: {e}")
                self.test_results.append({
                    "test": f"move_to_{list_name}",
                    "success": False,
                    "error": str(e)
                })
    
    async def test_project_moves(self, todo_ids: List[str]):
        """Test moves to projects using project:ID format."""
        print("\n🧪 Testing new functionality: project moves")
        
        if len(todo_ids) < 2:
            print("❌ Not enough test todos for project moves")
            return
        
        todo_id = todo_ids[1]
        
        # First get available projects
        try:
            projects_result = await self.server.tools.get_projects()
            
            if projects_result.get("success") and projects_result.get("projects"):
                projects = projects_result["projects"]
                
                if projects:
                    # Use the first project for testing
                    project = projects[0]
                    project_id = project["id"]
                    project_name = project["title"]
                    
                    print(f"  Moving todo to project: {project_name} ({project_id})")
                    
                    result = await self.server.tools.move_record(todo_id, f"project:{project_id}")
                    
                    if result.get("success"):
                        print(f"✅ Successfully moved to project {project_name}")
                        self.test_results.append({
                            "test": "move_to_project",
                            "success": True,
                            "message": result.get("message", ""),
                            "project_id": project_id,
                            "new_functionality": result.get("destination") == f"project:{project_id}"
                        })
                    else:
                        print(f"❌ Failed to move to project: {result.get('message', 'Unknown error')}")
                        self.test_results.append({
                            "test": "move_to_project",
                            "success": False,
                            "error": result.get("error", "Unknown error")
                        })
                else:
                    print("⚠️  No projects found - creating a test project")
                    await self.create_test_project_and_move(todo_id)
            else:
                print("⚠️  Could not retrieve projects - creating a test project")
                await self.create_test_project_and_move(todo_id)
                
        except Exception as e:
            print(f"❌ Exception during project move test: {e}")
            self.test_results.append({
                "test": "move_to_project",
                "success": False,
                "error": str(e)
            })
    
    async def create_test_project_and_move(self, todo_id: str):
        """Create a test project and move todo to it."""
        project_title = f"Test Project for Move Testing - {datetime.now().strftime('%H:%M:%S')}"
        
        try:
            # Create test project
            project_result = await self.server.tools.add_project(title=project_title)
            
            if project_result.get("success") and "id" in project_result:
                project_id = project_result["id"]
                print(f"✅ Created test project: {project_id}")
                
                # Move todo to the new project
                result = await self.server.tools.move_record(todo_id, f"project:{project_id}")
                
                if result.get("success"):
                    print(f"✅ Successfully moved to test project")
                    self.test_results.append({
                        "test": "move_to_test_project",
                        "success": True,
                        "message": result.get("message", ""),
                        "project_id": project_id
                    })
                else:
                    print(f"❌ Failed to move to test project: {result.get('message')}")
                    self.test_results.append({
                        "test": "move_to_test_project",
                        "success": False,
                        "error": result.get("error", "Unknown error")
                    })
            else:
                print(f"❌ Failed to create test project")
                
        except Exception as e:
            print(f"❌ Exception creating test project: {e}")
    
    async def test_area_moves(self, todo_ids: List[str]):
        """Test moves to areas using area:ID format."""
        print("\n🧪 Testing new functionality: area moves")
        
        if len(todo_ids) < 3:
            print("❌ Not enough test todos for area moves")
            return
        
        todo_id = todo_ids[2]
        
        # Get available areas
        try:
            areas_result = await self.server.tools.get_areas()
            
            if areas_result.get("success") and areas_result.get("areas"):
                areas = areas_result["areas"]
                
                if areas:
                    # Use the first area for testing
                    area = areas[0]
                    area_id = area["id"]
                    area_name = area["title"]
                    
                    print(f"  Moving todo to area: {area_name} ({area_id})")
                    
                    result = await self.server.tools.move_record(todo_id, f"area:{area_id}")
                    
                    if result.get("success"):
                        print(f"✅ Successfully moved to area {area_name}")
                        self.test_results.append({
                            "test": "move_to_area",
                            "success": True,
                            "message": result.get("message", ""),
                            "area_id": area_id,
                            "new_functionality": result.get("destination") == f"area:{area_id}"
                        })
                    else:
                        print(f"❌ Failed to move to area: {result.get('message', 'Unknown error')}")
                        self.test_results.append({
                            "test": "move_to_area",
                            "success": False,
                            "error": result.get("error", "Unknown error")
                        })
                else:
                    print("⚠️  No areas found - skipping area move test")
                    self.test_results.append({
                        "test": "move_to_area",
                        "success": False,
                        "error": "No areas available for testing"
                    })
            else:
                print("⚠️  Could not retrieve areas - skipping area move test")
                self.test_results.append({
                    "test": "move_to_area",
                    "success": False,
                    "error": "Could not retrieve areas"
                })
                
        except Exception as e:
            print(f"❌ Exception during area move test: {e}")
            self.test_results.append({
                "test": "move_to_area",
                "success": False,
                "error": str(e)
            })
    
    async def test_error_handling(self):
        """Test error handling scenarios."""
        print("\n🧪 Testing error handling scenarios")
        
        # Test 1: Invalid destination format
        print("  Testing invalid destination format...")
        try:
            result = await self.server.tools.move_record("dummy-id", "invalid:format:here")
            
            if not result.get("success") and "error" in result:
                print("✅ Invalid destination format properly rejected")
                self.test_results.append({
                    "test": "invalid_destination_format",
                    "success": True,
                    "error_handled": True
                })
            else:
                print("❌ Invalid destination format should have been rejected")
                self.test_results.append({
                    "test": "invalid_destination_format",
                    "success": False,
                    "error": "Invalid format not properly rejected"
                })
        except Exception as e:
            print(f"❌ Exception testing invalid destination: {e}")
            self.test_results.append({
                "test": "invalid_destination_format",
                "success": False,
                "error": str(e)
            })
        
        # Test 2: Nonexistent todo ID
        print("  Testing nonexistent todo ID...")
        try:
            result = await self.server.tools.move_record("nonexistent-todo-id-12345", "inbox")
            
            if not result.get("success") and "error" in result:
                print("✅ Nonexistent todo ID properly handled")
                self.test_results.append({
                    "test": "nonexistent_todo_id",
                    "success": True,
                    "error_handled": True
                })
            else:
                print("❌ Nonexistent todo ID should have been handled as error")
                self.test_results.append({
                    "test": "nonexistent_todo_id",
                    "success": False,
                    "error": "Nonexistent todo not properly handled"
                })
        except Exception as e:
            print(f"❌ Exception testing nonexistent todo: {e}")
            self.test_results.append({
                "test": "nonexistent_todo_id",
                "success": False,
                "error": str(e)
            })
        
        # Test 3: Nonexistent project ID
        print("  Testing nonexistent project ID...")
        if self.test_todos:
            try:
                result = await self.server.tools.move_record(self.test_todos[0], "project:nonexistent-project-12345")
                
                if not result.get("success") and "error" in result:
                    print("✅ Nonexistent project ID properly handled")
                    self.test_results.append({
                        "test": "nonexistent_project_id",
                        "success": True,
                        "error_handled": True
                    })
                else:
                    print("❌ Nonexistent project ID should have been handled as error")
                    self.test_results.append({
                        "test": "nonexistent_project_id",
                        "success": False,
                        "error": "Nonexistent project not properly handled"
                    })
            except Exception as e:
                print(f"❌ Exception testing nonexistent project: {e}")
                self.test_results.append({
                    "test": "nonexistent_project_id",
                    "success": False,
                    "error": str(e)
                })
    
    async def cleanup(self):
        """Clean up test todos."""
        print("\n🧹 Cleaning up test todos...")
        
        for todo_id in self.test_todos:
            try:
                # Move to trash (delete)
                result = await self.server.tools.delete_todo(todo_id)
                if result.get("success"):
                    print(f"✅ Cleaned up test todo: {todo_id}")
                else:
                    print(f"⚠️  Could not clean up todo {todo_id}: {result.get('message', 'Unknown error')}")
            except Exception as e:
                print(f"⚠️  Exception cleaning up todo {todo_id}: {e}")
        
        print(f"🧹 Cleanup completed for {len(self.test_todos)} test todos")
    
    def print_results(self):
        """Print comprehensive test results."""
        print("\n" + "=" * 60)
        print("📊 COMPREHENSIVE TEST RESULTS")
        print("=" * 60)
        
        successful_tests = [r for r in self.test_results if r.get("success")]
        failed_tests = [r for r in self.test_results if not r.get("success")]
        
        print(f"Total tests: {len(self.test_results)}")
        print(f"Successful: {len(successful_tests)}")
        print(f"Failed: {len(failed_tests)}")
        print(f"Success rate: {len(successful_tests)/len(self.test_results)*100:.1f}%")
        
        if successful_tests:
            print("\n✅ PASSED TESTS:")
            for test in successful_tests:
                print(f"  • {test['test']}")
                if test.get("backward_compatible"):
                    print("    - Backward compatibility maintained")
                if test.get("new_functionality"):
                    print("    - New functionality working")
                if test.get("error_handled"):
                    print("    - Error properly handled")
        
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"  • {test['test']}: {test.get('error', 'Unknown error')}")
        
        print("\n" + "=" * 60)
        
        if len(failed_tests) == 0:
            print("🎉 ALL TESTS PASSED!")
            print()
            print("The enhanced move_record functionality is working correctly with Things 3:")
            print("✅ Backward compatibility with built-in lists maintained")
            print("✅ New project move functionality (project:ID) working")
            print("✅ New area move functionality (area:ID) working") 
            print("✅ Error handling working for invalid inputs")
            print("✅ Integration with actual Things 3 data successful")
            return True
        else:
            print(f"❌ {len(failed_tests)} tests failed. Review the errors above.")
            return False


async def main():
    """Run the manual integration test."""
    print("🧪 Manual Integration Test for Enhanced Move Record Functionality")
    print("=" * 60)
    print()
    print("⚠️  IMPORTANT: This test requires Things 3 to be installed and running!")
    print("   It will create temporary test todos and clean them up afterward.")
    print()
    
    # Ask for confirmation
    response = input("Do you want to proceed with the manual test? (y/N): ")
    if response.lower() != 'y':
        print("Test cancelled.")
        return 1
    
    tester = ManualMoveRecordTester()
    
    try:
        # Setup
        await tester.setup()
        
        # Create test todos
        test_todo_ids = await tester.create_test_todos()
        
        if not test_todo_ids:
            print("❌ No test todos were created. Cannot proceed with tests.")
            return 1
        
        # Run tests
        await tester.test_backward_compatibility_moves(test_todo_ids)
        await tester.test_project_moves(test_todo_ids)
        await tester.test_area_moves(test_todo_ids)
        await tester.test_error_handling()
        
        # Print results
        success = tester.print_results()
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return 1
    
    finally:
        # Always try to clean up
        try:
            await tester.cleanup()
        except Exception as e:
            print(f"⚠️  Error during cleanup: {e}")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
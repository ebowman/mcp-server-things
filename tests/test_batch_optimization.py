#!/usr/bin/env python3
"""
Test script to verify batch optimization performance improvements.

This script tests the optimized get_todos(), get_projects(), and get_areas() methods
to ensure they maintain the same output format while providing better performance.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from things_mcp.applescript_manager import AppleScriptManager


async def test_batch_optimization():
    """Test the batch optimization improvements."""
    print("🚀 Testing batch optimization improvements...")
    
    # Initialize the manager
    manager = AppleScriptManager()
    
    # Test each method
    test_results = {}
    
    # Test todos
    print("\n📝 Testing get_todos()...")
    start_time = time.time()
    try:
        todos = await manager.get_todos()
        todos_time = time.time() - start_time
        print(f"✅ Retrieved {len(todos)} todos in {todos_time:.3f}s")
        
        # Display sample todo structure
        if todos:
            sample_todo = todos[0]
            print(f"📋 Sample todo structure: {list(sample_todo.keys())}")
            test_results['todos'] = {
                'count': len(todos),
                'time': todos_time,
                'success': True,
                'sample_keys': list(sample_todo.keys())
            }
        else:
            print("📋 No todos found")
            test_results['todos'] = {
                'count': 0,
                'time': todos_time,
                'success': True,
                'sample_keys': []
            }
            
    except Exception as e:
        print(f"❌ Error testing todos: {e}")
        test_results['todos'] = {'success': False, 'error': str(e)}
    
    # Test projects
    print("\n📂 Testing get_projects()...")
    start_time = time.time()
    try:
        projects = await manager.get_projects()
        projects_time = time.time() - start_time
        print(f"✅ Retrieved {len(projects)} projects in {projects_time:.3f}s")
        
        # Display sample project structure
        if projects:
            sample_project = projects[0]
            print(f"📂 Sample project structure: {list(sample_project.keys())}")
            test_results['projects'] = {
                'count': len(projects),
                'time': projects_time,
                'success': True,
                'sample_keys': list(sample_project.keys())
            }
        else:
            print("📂 No projects found")
            test_results['projects'] = {
                'count': 0,
                'time': projects_time,
                'success': True,
                'sample_keys': []
            }
            
    except Exception as e:
        print(f"❌ Error testing projects: {e}")
        test_results['projects'] = {'success': False, 'error': str(e)}
    
    # Test areas
    print("\n🏷️ Testing get_areas()...")
    start_time = time.time()
    try:
        areas = await manager.get_areas()
        areas_time = time.time() - start_time
        print(f"✅ Retrieved {len(areas)} areas in {areas_time:.3f}s")
        
        # Display sample area structure
        if areas:
            sample_area = areas[0]
            print(f"🏷️ Sample area structure: {list(sample_area.keys())}")
            print(f"🏷️ Sample area data: {sample_area}")
            test_results['areas'] = {
                'count': len(areas),
                'time': areas_time,
                'success': True,
                'sample_keys': list(sample_area.keys())
            }
        else:
            print("🏷️ No areas found")
            test_results['areas'] = {
                'count': 0,
                'time': areas_time,
                'success': True,
                'sample_keys': []
            }
            
    except Exception as e:
        print(f"❌ Error testing areas: {e}")
        test_results['areas'] = {'success': False, 'error': str(e)}
    
    # Test project-specific todos
    if test_results.get('projects', {}).get('success') and test_results['projects']['count'] > 0:
        print("\n📝 Testing get_todos() with project filter...")
        try:
            # Get first project ID
            projects = await manager.get_projects()
            if projects:
                first_project_id = projects[0]['id']
                start_time = time.time()
                project_todos = await manager.get_todos(project_uuid=first_project_id)
                project_todos_time = time.time() - start_time
                print(f"✅ Retrieved {len(project_todos)} todos for project '{projects[0]['name']}' in {project_todos_time:.3f}s")
                test_results['project_todos'] = {
                    'count': len(project_todos),
                    'time': project_todos_time,
                    'success': True
                }
        except Exception as e:
            print(f"❌ Error testing project todos: {e}")
            test_results['project_todos'] = {'success': False, 'error': str(e)}
    
    # Print summary
    print("\n" + "="*60)
    print("📊 BATCH OPTIMIZATION TEST SUMMARY")
    print("="*60)
    
    total_time = sum(result.get('time', 0) for result in test_results.values() if result.get('success'))
    total_items = sum(result.get('count', 0) for result in test_results.values() if result.get('success'))
    
    print(f"⏱️  Total execution time: {total_time:.3f}s")
    print(f"📊 Total items retrieved: {total_items}")
    if total_time > 0:
        print(f"🚀 Average throughput: {total_items/total_time:.1f} items/second")
    
    print("\nMethod performance breakdown:")
    for method, result in test_results.items():
        if result.get('success'):
            count = result.get('count', 0)
            time_taken = result.get('time', 0)
            throughput = count / time_taken if time_taken > 0 else 0
            print(f"  {method:15s}: {count:4d} items in {time_taken:.3f}s ({throughput:6.1f} items/s)")
        else:
            print(f"  {method:15s}: ❌ {result.get('error', 'Unknown error')}")
    
    print("\n✅ Data structure verification:")
    expected_keys = {
        'todos': ['id', 'name', 'notes', 'status', 'creation_date', 'modification_date'],
        'projects': ['id', 'name', 'notes', 'status', 'creation_date', 'modification_date'],
        'areas': ['id', 'name']  # Areas only have id and name in Things 3
    }
    
    for method, result in test_results.items():
        if method in expected_keys and result.get('success') and result.get('sample_keys'):
            actual_keys = set(result['sample_keys'])
            expected = set(expected_keys[method])
            if actual_keys >= expected:  # Allow extra keys
                print(f"  {method:15s}: ✅ All expected keys present")
            else:
                missing = expected - actual_keys
                print(f"  {method:15s}: ❌ Missing keys: {missing}")
    
    print("\n🎉 Batch optimization test completed!")
    return test_results


if __name__ == "__main__":
    asyncio.run(test_batch_optimization())
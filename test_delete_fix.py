#!/usr/bin/env python3
"""Test the delete_todo fix to ensure it returns proper response format."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.tools import ThingsTools
from things_mcp.applescript_manager import AppleScriptManager

async def test_delete_response_format():
    """Test that delete_todo returns the correct response format."""
    
    print("Testing delete_todo response format fix...")
    print("=" * 50)
    
    # Initialize the tools
    applescript_manager = AppleScriptManager()
    tools = ThingsTools(applescript_manager)
    
    # 1. Create a test todo
    print("\n1. Creating test todo...")
    todo_result = await tools.add_todo(
        title="Test Delete Response Format",
        notes="This todo will be deleted to test response format"
    )
    
    if not todo_result.get("success"):
        print(f"❌ Failed to create todo: {todo_result.get('error')}")
        return False
    
    todo_data = todo_result.get("todo", {})
    todo_id = todo_data.get("id") or todo_data.get("uuid")
    print(f"✅ Created todo with ID: {todo_id}")
    
    # 2. Delete the todo and check response format
    print(f"\n2. Deleting todo and checking response format...")
    try:
        delete_result = await tools.delete_todo(todo_id)
        
        # Check the response structure
        print(f"   Response type: {type(delete_result)}")
        print(f"   Response keys: {delete_result.keys()}")
        
        # Verify expected fields
        if not isinstance(delete_result, dict):
            print(f"❌ Response is not a dictionary: {type(delete_result)}")
            return False
            
        if "success" not in delete_result:
            print(f"❌ Missing 'success' field in response")
            return False
            
        if not isinstance(delete_result.get("success"), bool):
            print(f"❌ 'success' field is not boolean: {type(delete_result.get('success'))}")
            return False
            
        if delete_result.get("success"):
            # Successful deletion should have message
            if "message" not in delete_result:
                print(f"❌ Missing 'message' field in successful response")
                return False
            if not isinstance(delete_result.get("message"), str):
                print(f"❌ 'message' field is not string: {type(delete_result.get('message'))}")
                return False
            print(f"✅ Successful deletion with proper response format:")
            print(f"   - success: {delete_result.get('success')} (boolean)")
            print(f"   - message: {delete_result.get('message')} (string)")
            print(f"   - todo_id: {delete_result.get('todo_id')} (string)")
            print(f"   - deleted_at: {delete_result.get('deleted_at')} (string)")
        else:
            # Failed deletion should have error
            if "error" not in delete_result:
                print(f"❌ Missing 'error' field in error response")
                return False
            print(f"⚠️ Deletion failed with proper error format:")
            print(f"   - success: {delete_result.get('success')} (boolean)")
            print(f"   - error: {delete_result.get('error')} (string)")
            
    except Exception as e:
        print(f"❌ Exception during delete: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. Test deletion of non-existent todo
    print(f"\n3. Testing deletion of non-existent todo...")
    fake_id = "NONEXISTENT123"
    try:
        delete_result = await tools.delete_todo(fake_id)
        
        if not isinstance(delete_result, dict):
            print(f"❌ Response is not a dictionary for error case")
            return False
            
        if delete_result.get("success"):
            print(f"⚠️ Unexpected success for non-existent todo")
        else:
            print(f"✅ Proper error response for non-existent todo:")
            print(f"   - success: {delete_result.get('success')} (boolean)")
            print(f"   - error: {delete_result.get('error')} (string)")
            
    except Exception as e:
        print(f"❌ Exception during invalid delete: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("✅ TEST SUCCESSFUL: delete_todo returns proper response format!")
    print("   - Returns Dict[str, Any] not boolean")
    print("   - Contains success (bool) and message/error (str) fields")
    print("   - Compatible with MCP protocol expectations")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_delete_response_format())
    sys.exit(0 if success else 1)
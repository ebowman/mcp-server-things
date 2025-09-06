#!/usr/bin/env python3
"""Complete MCP client example for Things 3.

This example demonstrates comprehensive usage of the Things 3 MCP server,
including error handling, batch operations, and practical workflows.

Usage:
    python mcp_client_example.py
    python mcp_client_example.py --demo-mode
    python mcp_client_example.py --cleanup
"""

import asyncio
import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ThingsMCPClient:
    """Comprehensive Things 3 MCP client."""
    
    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.created_items = []  # Track items for cleanup
        self.session = None
    
    async def connect(self):
        """Connect to the Things MCP server."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "things_mcp.main"],
            env={"THINGS_MCP_LOG_LEVEL": "ERROR"}  # Quiet mode for demo
        )
        
        self.client_manager = stdio_client(server_params)
        read, write = await self.client_manager.__aenter__()
        
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()
        
        print("Connected to Things MCP Server")
    
    async def disconnect(self):
        """Disconnect from the server."""
        if self.session:
            await self.session.__aexit__(None, None, None)
        if hasattr(self, 'client_manager'):
            await self.client_manager.__aexit__(None, None, None)
        print("Disconnected from server")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        print("Running health check...")
        
        try:
            health = await self.session.call_tool("health_check")
            
            if health.get("things_running"):
                print("Things 3 is running and accessible")
                print(f"Server status: {health.get('server_status')}")
                if "cache_stats" in health:
                    cache_stats = health["cache_stats"]
                print(f"Cache hit rate: {cache_stats.get('hit_rate', 0):.1%}")
            else:
                print("Things 3 is not accessible")
                return health
            
            return health
            
        except Exception as e:
            print(f"Health check failed: {e}")
            return {"error": str(e)}
    
    async def demo_basic_operations(self):
        """Demonstrate basic CRUD operations."""
        print("\nDemo: Basic Todo Operations")
        print("-" * 40)
        
        # Create a simple todo
        print("Creating a simple todo...")
        todo_result = await self.session.call_tool(
            "add_todo",
            title="MCP Demo - Simple Todo",
            notes="This todo was created via MCP client",
            tags=["demo", "mcp"]
        )
        
        if todo_result.get("success"):
            print("Simple todo created successfully")
            if self.demo_mode:
                self.created_items.append(("todo", "MCP Demo - Simple Todo"))
        else:
            print(f"Failed to create todo: {todo_result.get('error')}")
            return
        
        # Create a todo with scheduling
        print("Creating a scheduled todo...")
        scheduled_result = await self.session.call_tool(
            "add_todo",
            title="MCP Demo - Scheduled Task",
            notes="This task is scheduled for today",
            tags=["demo", "scheduled"],
            when="today",
            deadline=(datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        )
        
        if scheduled_result.get("success"):
            print("Scheduled todo created successfully")
            if self.demo_mode:
                self.created_items.append(("todo", "MCP Demo - Scheduled Task"))
        
        # Get today's todos
        print("Retrieving today's todos...")
        today_todos = await self.session.call_tool("get_today")
        demo_todos = [t for t in today_todos if "MCP Demo" in t.get("title", "")]
        print(f"Found {len(demo_todos)} demo todos in today's list")
        
        # Search for our todos
        print("Searching for demo todos...")
        search_results = await self.session.call_tool("search_todos", query="MCP Demo")
        print(f"Search found {len(search_results)} matching todos")
    
    async def demo_project_management(self):
        """Demonstrate project creation and management."""
        print("\nDemo: Project Management")
        print("-" * 40)
        
        # Create a project with initial tasks
        print("Creating a project with initial tasks...")
        project_result = await self.session.call_tool(
            "add_project",
            title="MCP Demo Project",
            notes="This project demonstrates MCP capabilities",
            tags=["demo", "project", "mcp"],
            area_title="Personal",  # Assuming Personal area exists
            todos=[
                "Set up MCP server",
                "Test basic operations",
                "Create comprehensive examples",
                "Document best practices",
                "Share with team"
            ]
        )
        
        if project_result.get("success"):
            print("Project created with 5 initial tasks")
            if self.demo_mode:
                self.created_items.append(("project", "MCP Demo Project"))
        else:
            print(f"Failed to create project: {project_result.get('error')}")
            return
        
        # Add an additional task to the project
        print("Adding additional task to project...")
        additional_task = await self.session.call_tool(
            "add_todo",
            title="Celebrate successful implementation",
            notes="Pat yourself on the back for learning MCP!",
            list_title="MCP Demo Project",
            tags=["demo", "celebration"]
        )
        
        if additional_task.get("success"):
            print("Additional task added to project")
            if self.demo_mode:
                self.created_items.append(("todo", "Celebrate successful implementation"))
        
        # Get all projects to verify
        print("Retrieving all projects...")
        projects = await self.session.call_tool("get_projects", include_items=True)
        demo_projects = [p for p in projects if "MCP Demo" in p.get("title", "")]
        
        if demo_projects:
            project = demo_projects[0]
            task_count = len(project.get("todos", []))
            print(f"Project verification: Found project with {task_count} tasks")
    
    async def demo_advanced_search(self):
        """Demonstrate advanced search capabilities."""
        print("\nDemo: Advanced Search")
        print("-" * 40)
        
        # Search by status
        print("Searching for incomplete tasks...")
        incomplete_tasks = await self.session.call_tool(
            "search_advanced",
            status="incomplete",
            tag="demo"
        )
        print(f"Found {len(incomplete_tasks)} incomplete demo tasks")
        
        # Search by date range
        print("Searching for recently created items...")
        recent_items = await self.session.call_tool(
            "get_recent",
            period="1d"
        )
        demo_recent = [item for item in recent_items if "MCP Demo" in item.get("title", "")]
        print(f"Found {len(demo_recent)} demo items created in last 24 hours")
        
        # Search by tag
        print("Searching for items with 'demo' tag...")
        tagged_items = await self.session.call_tool(
            "get_tagged_items",
            tag="demo"
        )
        print(f"Found {len(tagged_items)} items tagged with 'demo'")
    
    async def demo_list_access(self):
        """Demonstrate access to various Things lists."""
        print("\nDemo: List Access")
        print("-" * 40)
        
        lists_to_check = [
            ("inbox", "get_inbox"),
            ("today", "get_today"),
            ("upcoming", "get_upcoming"),
            ("anytime", "get_anytime"),
            ("someday", "get_someday")
        ]
        
        for list_name, tool_name in lists_to_check:
            try:
                items = await self.session.call_tool(tool_name)
                print(f"{list_name.capitalize()}: {len(items)} items")
            except Exception as e:
                print(f"Error accessing {list_name}: {e}")
        
        # Check logbook (completed items)
        try:
            completed = await self.session.call_tool("get_logbook", period="7d", limit=10)
            print(f"Logbook: {len(completed)} items completed in last 7 days")
        except Exception as e:
            print(f"Error accessing logbook: {e}")
    
    async def demo_navigation(self):
        """Demonstrate navigation features."""
        print("\nDemo: Navigation")
        print("-" * 40)
        
        # Show today's list in Things
        print("Opening today's list in Things...")
        show_result = await self.session.call_tool(
            "show_item",
            id="today"
        )
        
        if show_result.get("success"):
            print("Today's list opened in Things 3")
        else:
            print(f"Failed to show today's list: {show_result.get('error')}")
        
        # Search and show results
        print("Performing search in Things...")
        search_result = await self.session.call_tool(
            "search_items",
            query="MCP Demo"
        )
        
        if search_result.get("success"):
            print("Search results shown in Things 3")
        else:
            print(f"Search failed: {search_result.get('error')}")
    
    async def demo_batch_operations(self):
        """Demonstrate efficient batch operations."""
        print("\nDemo: Batch Operations")
        print("-" * 40)
        
        # Create multiple related todos efficiently
        print("Creating multiple related todos...")
        
        meeting_tasks = [
            "Prepare meeting agenda",
            "Book conference room", 
            "Send calendar invites",
            "Prepare presentation materials",
            "Set up video conferencing"
        ]
        
        # Method 1: Create project with initial todos (most efficient)
        batch_project = await self.session.call_tool(
            "add_project",
            title="MCP Demo - Team Meeting",
            notes="Batch creation demo for team meeting preparation",
            tags=["demo", "meeting", "batch"],
            todos=meeting_tasks
        )
        
        if batch_project.get("success"):
            print(f"Efficiently created project with {len(meeting_tasks)} tasks")
            if self.demo_mode:
                self.created_items.append(("project", "MCP Demo - Team Meeting"))
        
        # Demonstrate tag management
        print("Retrieving all tags...")
        tags = await self.session.call_tool("get_tags")
        demo_tags = [tag for tag in tags if tag.get("name") in ["demo", "mcp", "batch"]]
        print(f"Found {len(demo_tags)} demo-related tags")
    
    async def demo_error_handling(self):
        """Demonstrate error handling patterns."""
        print("\nDemo: Error Handling")
        print("-" * 40)
        
        # Try to get a non-existent todo
        print("Testing error handling with invalid todo ID...")
        try:
            invalid_todo = await self.session.call_tool(
                "get_todo_by_id",
                todo_id="non-existent-id"
            )
            print("Expected error but got success")
        except Exception as e:
            print(f"Properly caught error: {type(e).__name__}")
        
        # Try to create todo with invalid date
        print("Testing validation with invalid date...")
        invalid_date_result = await self.session.call_tool(
            "add_todo",
            title="Invalid Date Test",
            deadline="invalid-date-format"
        )
        
        if not invalid_date_result.get("success"):
            print("Date validation working properly")
        else:
            print("Date validation may need improvement")
    
    async def cleanup_demo_items(self):
        """Clean up items created during demo."""
        if not self.demo_mode or not self.created_items:
            return
        
        print("\nCleaning up demo items...")
        print("-" * 40)
        
        # Search for demo items to get their IDs
        demo_todos = await self.session.call_tool("search_todos", query="MCP Demo")
        
        cleaned_count = 0
        for todo in demo_todos:
            try:
                delete_result = await self.session.call_tool(
                    "delete_todo",
                    todo_id=todo["id"]
                )
                if delete_result.get("success"):
                    cleaned_count += 1
                    print(f"Deleted: {todo['title']}")
            except Exception as e:
                print(f"Failed to delete {todo['title']}: {e}")
        
        print(f"Cleaned up {cleaned_count} demo items")
    
    async def run_comprehensive_demo(self):
        """Run all demo sections."""
        print("Starting comprehensive Things 3 MCP demo")
        print("=" * 50)
        
        # Health check first
        health = await self.health_check()
        if not health.get("things_running"):
            print("Cannot continue - Things 3 is not accessible")
            return
        
        # Run all demo sections
        await self.demo_basic_operations()
        await self.demo_project_management()
        await self.demo_advanced_search()
        await self.demo_list_access()
        await self.demo_navigation()
        await self.demo_batch_operations()
        await self.demo_error_handling()
        
        print("\nDemo completed successfully!")
        print("=" * 50)
        
        if self.demo_mode:
            cleanup = input("\nClean up demo items? (y/N): ")
            if cleanup.lower().startswith('y'):
                await self.cleanup_demo_items()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Things 3 MCP Client Demo")
    parser.add_argument("--demo-mode", action="store_true", 
                       help="Run in demo mode (creates and optionally cleans up test items)")
    parser.add_argument("--cleanup", action="store_true",
                       help="Clean up existing demo items and exit")
    
    args = parser.parse_args()
    
    client = ThingsMCPClient(demo_mode=args.demo_mode)
    
    try:
        await client.connect()
        
        if args.cleanup:
            # Clean up mode
            print("Cleanup mode - removing demo items...")
            demo_todos = await client.session.call_tool("search_todos", query="MCP Demo")
            
            cleaned = 0
            for todo in demo_todos:
                try:
                    result = await client.session.call_tool("delete_todo", todo_id=todo["id"])
                    if result.get("success"):
                        cleaned += 1
                        print(f"Deleted: {todo['title']}")
                except Exception as e:
                    print(f"Failed to delete {todo['title']}: {e}")
            
            print(f"Cleaned up {cleaned} items")
        else:
            # Normal demo mode
            await client.run_comprehensive_demo()
    
    except KeyboardInterrupt:
        print("\nDemo cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nDemo failed: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
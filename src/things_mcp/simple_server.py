"""Simple FastMCP 2.0 server implementation for Things 3 integration."""

import logging
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .applescript_manager import AppleScriptManager
from .tools import ThingsTools

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ThingsMCPServer:
    """Simple MCP server for Things 3 integration."""
    
    def __init__(self):
        """Initialize the Things MCP server."""
        self.mcp = FastMCP("things-mcp")
        self.applescript_manager = AppleScriptManager()
        self.tools = ThingsTools(self.applescript_manager)
        self._register_tools()
        logger.info("Things MCP Server initialized")
    
    def _register_tools(self) -> None:
        """Register all MCP tools with the server."""
        
        # Todo management tools
        @self.mcp.tool()
        def get_todos(
            project_uuid: Optional[str] = Field(None, description="Optional UUID of a specific project to get todos from"),
            include_items: bool = Field(True, description="Include checklist items")
        ) -> List[Dict[str, Any]]:
            """Get todos from Things, optionally filtered by project."""
            try:
                return self.tools.get_todos(project_uuid=project_uuid, include_items=include_items)
            except Exception as e:
                logger.error(f"Error getting todos: {e}")
                raise
        
        @self.mcp.tool()
        def add_todo(
            title: str = Field(..., description="Title of the todo"),
            notes: Optional[str] = Field(None, description="Notes for the todo"),
            tags: Optional[List[str]] = Field(None, description="Tags to apply to the todo"),
            when: Optional[str] = Field(None, description="When to schedule the todo (today, tomorrow, evening, anytime, someday, or YYYY-MM-DD)"),
            deadline: Optional[str] = Field(None, description="Deadline for the todo (YYYY-MM-DD)"),
            list_id: Optional[str] = Field(None, description="ID of project/area to add to"),
            list_title: Optional[str] = Field(None, description="Title of project/area to add to"),
            heading: Optional[str] = Field(None, description="Heading to add under"),
            checklist_items: Optional[List[str]] = Field(None, description="Checklist items to add")
        ) -> Dict[str, Any]:
            """Create a new todo in Things."""
            try:
                return self.tools.add_todo(
                    title=title,
                    notes=notes,
                    tags=tags,
                    when=when,
                    deadline=deadline,
                    list_id=list_id,
                    list_title=list_title,
                    heading=heading,
                    checklist_items=checklist_items
                )
            except Exception as e:
                logger.error(f"Error adding todo: {e}")
                raise
        
        @self.mcp.tool()
        def update_todo(
            id: str = Field(..., description="ID of the todo to update"),
            title: Optional[str] = Field(None, description="New title"),
            notes: Optional[str] = Field(None, description="New notes"),
            tags: Optional[List[str]] = Field(None, description="New tags"),
            when: Optional[str] = Field(None, description="New schedule"),
            deadline: Optional[str] = Field(None, description="New deadline"),
            completed: Optional[bool] = Field(None, description="Mark as completed"),
            canceled: Optional[bool] = Field(None, description="Mark as canceled")
        ) -> Dict[str, Any]:
            """Update an existing todo in Things."""
            try:
                return self.tools.update_todo(
                    todo_id=id,
                    title=title,
                    notes=notes,
                    tags=tags,
                    when=when,
                    deadline=deadline,
                    completed=completed,
                    canceled=canceled
                )
            except Exception as e:
                logger.error(f"Error updating todo: {e}")
                raise
        
        @self.mcp.tool()
        def get_todo_by_id(
            todo_id: str = Field(..., description="ID of the todo to retrieve")
        ) -> Dict[str, Any]:
            """Get a specific todo by its ID."""
            try:
                return self.tools.get_todo_by_id(todo_id)
            except Exception as e:
                logger.error(f"Error getting todo by ID: {e}")
                raise
        
        @self.mcp.tool()
        def delete_todo(
            todo_id: str = Field(..., description="ID of the todo to delete")
        ) -> Dict[str, str]:
            """Delete a todo from Things."""
            try:
                return self.tools.delete_todo(todo_id)
            except Exception as e:
                logger.error(f"Error deleting todo: {e}")
                raise
        
        # Project management tools
        @self.mcp.tool()
        def get_projects(
            include_items: bool = Field(False, description="Include tasks within projects")
        ) -> List[Dict[str, Any]]:
            """Get all projects from Things."""
            try:
                return self.tools.get_projects(include_items=include_items)
            except Exception as e:
                logger.error(f"Error getting projects: {e}")
                raise
        
        @self.mcp.tool()
        def add_project(
            title: str = Field(..., description="Title of the project"),
            notes: Optional[str] = Field(None, description="Notes for the project"),
            tags: Optional[List[str]] = Field(None, description="Tags to apply to the project"),
            when: Optional[str] = Field(None, description="When to schedule the project"),
            deadline: Optional[str] = Field(None, description="Deadline for the project"),
            area_id: Optional[str] = Field(None, description="ID of area to add to"),
            area_title: Optional[str] = Field(None, description="Title of area to add to"),
            todos: Optional[List[str]] = Field(None, description="Initial todos to create in the project")
        ) -> Dict[str, Any]:
            """Create a new project in Things."""
            try:
                return self.tools.add_project(
                    title=title,
                    notes=notes,
                    tags=tags,
                    when=when,
                    deadline=deadline,
                    area_id=area_id,
                    area_title=area_title,
                    todos=todos
                )
            except Exception as e:
                logger.error(f"Error adding project: {e}")
                raise
        
        @self.mcp.tool()
        def update_project(
            id: str = Field(..., description="ID of the project to update"),
            title: Optional[str] = Field(None, description="New title"),
            notes: Optional[str] = Field(None, description="New notes"),
            tags: Optional[List[str]] = Field(None, description="New tags"),
            when: Optional[str] = Field(None, description="New schedule"),
            deadline: Optional[str] = Field(None, description="New deadline"),
            completed: Optional[bool] = Field(None, description="Mark as completed"),
            canceled: Optional[bool] = Field(None, description="Mark as canceled")
        ) -> Dict[str, Any]:
            """Update an existing project in Things."""
            try:
                return self.tools.update_project(
                    project_id=id,
                    title=title,
                    notes=notes,
                    tags=tags,
                    when=when,
                    deadline=deadline,
                    completed=completed,
                    canceled=canceled
                )
            except Exception as e:
                logger.error(f"Error updating project: {e}")
                raise
        
        # Area management tools
        @self.mcp.tool()
        def get_areas(
            include_items: bool = Field(False, description="Include projects and tasks within areas")
        ) -> List[Dict[str, Any]]:
            """Get all areas from Things."""
            try:
                return self.tools.get_areas(include_items=include_items)
            except Exception as e:
                logger.error(f"Error getting areas: {e}")
                raise
        
        # List-based tools
        @self.mcp.tool()
        def get_inbox() -> List[Dict[str, Any]]:
            """Get todos from Inbox."""
            try:
                return self.tools.get_inbox()
            except Exception as e:
                logger.error(f"Error getting inbox: {e}")
                raise
        
        @self.mcp.tool()
        def get_today() -> List[Dict[str, Any]]:
            """Get todos due today."""
            try:
                return self.tools.get_today()
            except Exception as e:
                logger.error(f"Error getting today's todos: {e}")
                raise
        
        @self.mcp.tool()
        def get_upcoming() -> List[Dict[str, Any]]:
            """Get upcoming todos."""
            try:
                return self.tools.get_upcoming()
            except Exception as e:
                logger.error(f"Error getting upcoming todos: {e}")
                raise
        
        @self.mcp.tool()
        def get_anytime() -> List[Dict[str, Any]]:
            """Get todos from Anytime list."""
            try:
                return self.tools.get_anytime()
            except Exception as e:
                logger.error(f"Error getting anytime todos: {e}")
                raise
        
        @self.mcp.tool()
        def get_someday() -> List[Dict[str, Any]]:
            """Get todos from Someday list."""
            try:
                return self.tools.get_someday()
            except Exception as e:
                logger.error(f"Error getting someday todos: {e}")
                raise
        
        @self.mcp.tool()
        def get_logbook(
            limit: int = Field(50, description="Maximum number of entries to return. Defaults to 50", ge=1, le=100),
            period: str = Field("7d", description="Time period to look back (e.g., '3d', '1w', '2m', '1y'). Defaults to '7d'", pattern=r"^\d+[dwmy]$")
        ) -> List[Dict[str, Any]]:
            """Get completed todos from Logbook, defaults to last 7 days."""
            try:
                return self.tools.get_logbook(limit=limit, period=period)
            except Exception as e:
                logger.error(f"Error getting logbook: {e}")
                raise
        
        @self.mcp.tool()
        def get_trash() -> List[Dict[str, Any]]:
            """Get trashed todos."""
            try:
                return self.tools.get_trash()
            except Exception as e:
                logger.error(f"Error getting trash: {e}")
                raise
        
        # Tag management tools
        @self.mcp.tool()
        def get_tags(
            include_items: bool = Field(False, description="Include items tagged with each tag")
        ) -> List[Dict[str, Any]]:
            """Get all tags."""
            try:
                return self.tools.get_tags(include_items=include_items)
            except Exception as e:
                logger.error(f"Error getting tags: {e}")
                raise
        
        @self.mcp.tool()
        def get_tagged_items(
            tag: str = Field(..., description="Tag title to filter by")
        ) -> List[Dict[str, Any]]:
            """Get items with a specific tag."""
            try:
                return self.tools.get_tagged_items(tag=tag)
            except Exception as e:
                logger.error(f"Error getting tagged items: {e}")
                raise
        
        # Search tools
        @self.mcp.tool()
        def search_todos(
            query: str = Field(..., description="Search term to look for in todo titles and notes")
        ) -> List[Dict[str, Any]]:
            """Search todos by title or notes."""
            try:
                return self.tools.search_todos(query=query)
            except Exception as e:
                logger.error(f"Error searching todos: {e}")
                raise
        
        @self.mcp.tool()
        def search_advanced(
            status: Optional[str] = Field(None, description="Filter by todo status", pattern="^(incomplete|completed|canceled)$"),
            type: Optional[str] = Field(None, description="Filter by item type", pattern="^(to-do|project|heading)$"),
            tag: Optional[str] = Field(None, description="Filter by tag"),
            area: Optional[str] = Field(None, description="Filter by area UUID"),
            start_date: Optional[str] = Field(None, description="Filter by start date (YYYY-MM-DD)"),
            deadline: Optional[str] = Field(None, description="Filter by deadline (YYYY-MM-DD)")
        ) -> List[Dict[str, Any]]:
            """Advanced todo search with multiple filters."""
            try:
                return self.tools.search_advanced(
                    status=status,
                    type=type,
                    tag=tag,
                    area=area,
                    start_date=start_date,
                    deadline=deadline
                )
            except Exception as e:
                logger.error(f"Error in advanced search: {e}")
                raise
        
        @self.mcp.tool()
        def get_recent(
            period: str = Field(..., description="Time period (e.g., '3d', '1w', '2m', '1y')", pattern=r"^\d+[dwmy]$")
        ) -> List[Dict[str, Any]]:
            """Get recently created items."""
            try:
                return self.tools.get_recent(period=period)
            except Exception as e:
                logger.error(f"Error getting recent items: {e}")
                raise
        
        # Navigation tools
        @self.mcp.tool()
        def show_item(
            id: str = Field(..., description="ID of item to show, or one of: inbox, today, upcoming, anytime, someday, logbook"),
            query: Optional[str] = Field(None, description="Optional query to filter by"),
            filter_tags: Optional[List[str]] = Field(None, description="Optional tags to filter by")
        ) -> Dict[str, str]:
            """Show a specific item or list in Things."""
            try:
                return self.tools.show_item(id=id, query=query, filter_tags=filter_tags)
            except Exception as e:
                logger.error(f"Error showing item: {e}")
                raise
        
        @self.mcp.tool()
        def search_items(
            query: str = Field(..., description="Search query")
        ) -> Dict[str, str]:
            """Search for items in Things."""
            try:
                return self.tools.search_items(query=query)
            except Exception as e:
                logger.error(f"Error searching items: {e}")
                raise
        
        # Health check tool
        @self.mcp.tool()
        def health_check() -> Dict[str, Any]:
            """Check server health and Things 3 connectivity."""
            try:
                is_running = self.applescript_manager.is_things_running()
                return {
                    "server_status": "healthy",
                    "things_running": is_running,
                    "applescript_available": True,
                    "timestamp": self.applescript_manager._get_current_timestamp()
                }
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return {
                    "server_status": "unhealthy",
                    "error": str(e),
                    "timestamp": self.applescript_manager._get_current_timestamp()
                }
        
        logger.info("All MCP tools registered successfully")
    
    def run(self) -> None:
        """Run the MCP server."""
        try:
            logger.info("Starting Things MCP Server...")
            self.mcp.run()
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
    
    def stop(self) -> None:
        """Stop the MCP server gracefully."""
        logger.info("Stopping Things MCP Server...")
        # Add any cleanup logic here if needed


def main():
    """Main entry point for the simple server."""
    server = ThingsMCPServer()
    server.run()


if __name__ == "__main__":
    main()
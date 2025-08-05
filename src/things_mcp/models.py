"""Data models for Things 3 objects."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator


class BaseThingsModel(BaseModel):
    """Base model for all Things objects."""
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class Todo(BaseThingsModel):
    """Represents a Things 3 todo item."""
    
    id: Optional[str] = Field(None, description="Unique identifier")
    name: str = Field(..., description="Todo title")
    notes: Optional[str] = Field(None, description="Todo notes")
    due_date: Optional[datetime] = Field(None, description="Due date")
    activation_date: Optional[datetime] = Field(None, description="Start date")
    completion_date: Optional[datetime] = Field(None, description="Completion date")
    cancellation_date: Optional[datetime] = Field(None, description="Cancellation date")
    creation_date: Optional[datetime] = Field(None, description="Creation date")
    modification_date: Optional[datetime] = Field(None, description="Last modified")
    status: str = Field("open", description="Status: open, completed, canceled")
    tag_names: Optional[str] = Field(None, description="Comma-separated tag names")
    area_name: Optional[str] = Field(None, description="Area name")
    project_name: Optional[str] = Field(None, description="Project name")
    contact_name: Optional[str] = Field(None, description="Contact name")


class Project(Todo):
    """Represents a Things 3 project."""
    pass


class Area(BaseThingsModel):
    """Represents a Things 3 area."""
    
    id: Optional[str] = Field(None, description="Unique identifier")
    name: str = Field(..., description="Area name")
    collapsed: bool = Field(False, description="Is area collapsed")
    tag_names: Optional[str] = Field(None, description="Comma-separated tag names")


class Tag(BaseThingsModel):
    """Represents a Things 3 tag."""
    
    id: Optional[str] = Field(None, description="Unique identifier")
    name: str = Field(..., description="Tag name")
    keyboard_shortcut: Optional[str] = Field(None, description="Keyboard shortcut")
    parent_tag_name: Optional[str] = Field(None, description="Parent tag name")


class Contact(BaseThingsModel):
    """Represents a Things 3 contact."""
    
    id: Optional[str] = Field(None, description="Unique identifier")
    name: str = Field(..., description="Contact name")


class TodoResult(BaseModel):
    """Result of a todo operation."""
    
    success: bool
    message: str
    todo: Optional[Todo] = None
    todos: Optional[List[Todo]] = None
    error: Optional[str] = None


class ServerStats(BaseModel):
    """Server statistics."""
    
    uptime_seconds: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    applescript_executions: int
    cache_hits: int
    cache_size: int
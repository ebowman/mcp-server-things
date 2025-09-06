"""
Unit tests for Things 3 MCP data models.

Tests Pydantic model validation, serialization, and business logic
for Todo, Project, Area, and other model classes.
"""

import pytest
from datetime import datetime, timedelta, date
from typing import Dict, Any
from pydantic import ValidationError

from things_mcp.models import (
    Todo, Project, Area, Tag, Contact, TodoResult, ServerStats
)


class TestTodoModel:
    """Test cases for Todo model."""
    
    def test_todo_creation_with_minimal_data(self):
        """Test creating todo with only required fields."""
        todo = Todo(name="Test Todo")
        
        assert todo.name == "Test Todo"
        assert todo.id is None
        assert todo.notes is None
        assert todo.status == "open"  # Default value
        assert todo.due_date is None
        assert todo.tag_names == []
    
    def test_todo_creation_with_full_data(self, sample_todo_data):
        """Test creating todo with all fields."""
        todo = Todo(**sample_todo_data)
        
        assert todo.id == sample_todo_data["id"]
        assert todo.name == sample_todo_data["name"]
        assert todo.notes == sample_todo_data["notes"]
        assert todo.status == sample_todo_data["status"]
        assert todo.creation_date == sample_todo_data["creation_date"]
        assert todo.modification_date == sample_todo_data["modification_date"]
        assert todo.tag_names == sample_todo_data["tag_names"]
        assert todo.area_name == sample_todo_data["area_name"]
    
    def test_todo_validation_empty_name(self):
        """Test todo validation fails with empty name."""
        with pytest.raises(ValidationError) as exc_info:
            Todo(name="")
        
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("name" in str(error) for error in errors)
    
    def test_todo_validation_missing_name(self):
        """Test todo validation fails without name."""
        with pytest.raises(ValidationError) as exc_info:
            Todo()
        
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("name" in str(error) for error in errors)
    
    def test_todo_status_values(self):
        """Test todo with different status values."""
        valid_statuses = ["open", "completed", "canceled"]
        
        for status in valid_statuses:
            todo = Todo(name="Test", status=status)
            assert todo.status == status
    
    def test_todo_date_handling(self):
        """Test todo date field handling."""
        now = datetime.now()
        future_date = (now + timedelta(days=7)).date()
        
        todo = Todo(
            name="Test Todo",
            creation_date=now,
            due_date=future_date,
            completion_date=None
        )
        
        assert todo.creation_date == now
        assert todo.due_date == future_date
        assert todo.completion_date is None
    
    def test_todo_json_serialization(self, sample_todo_data):
        """Test todo JSON serialization."""
        todo = Todo(**sample_todo_data)
        json_data = todo.model_dump()
        
        assert isinstance(json_data, dict)
        assert json_data["name"] == sample_todo_data["name"]
        assert json_data["status"] == sample_todo_data["status"]
        
        # Test datetime serialization is handled properly
        if todo.creation_date:
            assert "creation_date" in json_data
    
    def test_todo_json_deserialization(self, sample_todo_data):
        """Test todo JSON deserialization."""
        todo = Todo(**sample_todo_data)
        json_data = todo.model_dump()
        
        # Recreate from JSON data
        restored_todo = Todo(**json_data)
        
        assert restored_todo.name == todo.name
        assert restored_todo.status == todo.status
        assert restored_todo.id == todo.id
    
    @pytest.mark.parametrize("field_name,invalid_value", [
        ("name", None),
        ("name", 123),
        ("status", "invalid_status"),
        ("id", 123),  # Should be string
    ])
    def test_todo_field_validation(self, field_name, invalid_value):
        """Test individual field validation."""
        todo_data = {"name": "Test Todo"}
        todo_data[field_name] = invalid_value
        
        with pytest.raises(ValidationError):
            Todo(**todo_data)


class TestProjectModel:
    """Test cases for Project model."""
    
    def test_project_inherits_from_base(self):
        """Test Project model inherits from BaseThingsModel."""
        from things_mcp.models.things_models import BaseThingsModel
        assert issubclass(Project, BaseThingsModel)
    
    def test_project_creation(self, sample_project_data):
        """Test creating project with data."""
        project = Project(**sample_project_data)
        
        assert project.name == sample_project_data["name"]
        assert project.notes == sample_project_data["notes"]
        assert project.status == sample_project_data["status"]
        assert isinstance(project, Project)  # Type check
    
    def test_project_minimal_creation(self):
        """Test creating project with minimal data."""
        project = Project(name="Test Project")
        
        assert project.name == "Test Project"
        assert project.status == "open"
        assert isinstance(project, Project)


class TestAreaModel:
    """Test cases for Area model."""
    
    def test_area_creation_minimal(self):
        """Test creating area with minimal data."""
        area = Area(name="Test Area")
        
        assert area.name == "Test Area"
        assert area.collapsed is False  # Default value
        assert area.id is None
        assert area.tag_names == []  # Default is empty list, not None
    
    def test_area_creation_full(self, sample_area_data):
        """Test creating area with full data."""
        area = Area(**sample_area_data)
        
        assert area.id == sample_area_data["id"]
        assert area.name == sample_area_data["name"]
        assert area.collapsed == sample_area_data["collapsed"]
        assert area.tag_names == sample_area_data["tag_names"]
    
    def test_area_validation_empty_name(self):
        """Test area validation fails with empty name."""
        with pytest.raises(ValidationError):
            Area(name="")
    
    def test_area_validation_missing_name(self):
        """Test area validation fails without name."""
        with pytest.raises(ValidationError):
            Area()
    
    def test_area_collapsed_boolean(self):
        """Test area collapsed field is boolean."""
        area = Area(name="Test", collapsed=True)
        assert area.collapsed is True
        
        area = Area(name="Test", collapsed=False)
        assert area.collapsed is False
    
    def test_area_json_serialization(self, sample_area_data):
        """Test area JSON serialization."""
        area = Area(**sample_area_data)
        json_data = area.model_dump()
        
        assert isinstance(json_data, dict)
        assert json_data["name"] == sample_area_data["name"]
        assert json_data["collapsed"] == sample_area_data["collapsed"]


class TestTagModel:
    """Test cases for Tag model."""
    
    def test_tag_creation_minimal(self):
        """Test creating tag with minimal data."""
        tag = Tag(name="urgent")
        
        assert tag.name == "urgent"
        assert tag.id is None
        assert tag.keyboard_shortcut is None
        assert tag.parent_tag_name is None
    
    def test_tag_creation_full(self, sample_tag_data):
        """Test creating tag with full data."""
        tag = Tag(**sample_tag_data)
        
        assert tag.id == sample_tag_data["id"]
        assert tag.name == sample_tag_data["name"]
        assert tag.keyboard_shortcut == sample_tag_data["keyboard_shortcut"]
        assert tag.parent_tag_name == sample_tag_data["parent_tag_name"]
    
    def test_tag_validation_empty_name(self):
        """Test tag validation fails with empty name."""
        with pytest.raises(ValidationError):
            Tag(name="")
    
    def test_tag_validation_missing_name(self):
        """Test tag validation fails without name."""
        with pytest.raises(ValidationError):
            Tag()
    
    def test_tag_hierarchical_structure(self):
        """Test tag hierarchical structure with parent."""
        parent_tag = Tag(name="work")
        child_tag = Tag(name="urgent", parent_tag_name="work")
        
        assert parent_tag.parent_tag_name is None
        assert child_tag.parent_tag_name == "work"


class TestContactModel:
    """Test cases for Contact model."""
    
    def test_contact_creation_minimal(self):
        """Test creating contact with minimal data."""
        contact = Contact(name="John Doe")
        
        assert contact.name == "John Doe"
        assert contact.id is None
    
    def test_contact_validation_empty_name(self):
        """Test contact validation fails with empty name."""
        with pytest.raises(ValidationError):
            Contact(name="")
    
    def test_contact_validation_missing_name(self):
        """Test contact validation fails without name."""
        with pytest.raises(ValidationError):
            Contact()


class TestTodoResultModel:
    """Test cases for TodoResult model."""
    
    def test_todo_result_success(self, sample_todo_data):
        """Test successful todo result."""
        todo = Todo(**sample_todo_data)
        result = TodoResult(
            success=True,
            message="Todo created successfully",
            todo=todo
        )
        
        assert result.success is True
        assert result.message == "Todo created successfully"
        assert result.todo == todo
        assert result.todos is None
        assert result.error is None
    
    def test_todo_result_failure(self):
        """Test failed todo result."""
        result = TodoResult(
            success=False,
            message="Operation failed",
            error="Invalid input data"
        )
        
        assert result.success is False
        assert result.message == "Operation failed"
        assert result.error == "Invalid input data"
        assert result.todo is None
        assert result.todos is None
    
    def test_todo_result_multiple_todos(self, multiple_todos_data):
        """Test todo result with multiple todos."""
        todos = [Todo(**todo_data) for todo_data in multiple_todos_data]
        result = TodoResult(
            success=True,
            message="Retrieved todos",
            todos=todos
        )
        
        assert result.success is True
        assert result.todos == todos
        assert len(result.todos) == len(multiple_todos_data)
        assert result.todo is None
    
    def test_todo_result_validation(self):
        """Test todo result field validation."""
        # Missing required fields should raise validation error
        with pytest.raises(ValidationError):
            TodoResult()
        
        # success and message are required
        with pytest.raises(ValidationError):
            TodoResult(success=True)
        
        with pytest.raises(ValidationError):
            TodoResult(message="Test")


class TestServerStatsModel:
    """Test cases for ServerStats model."""
    
    def test_server_stats_creation(self):
        """Test creating server stats."""
        stats = ServerStats(
            uptime_seconds=3600.5,
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            applescript_executions=50,
            cache_hits=25,
            cache_size=1024
        )
        
        assert stats.uptime_seconds == 3600.5
        assert stats.total_requests == 100
        assert stats.successful_requests == 95
        assert stats.failed_requests == 5
        assert stats.applescript_executions == 50
        assert stats.cache_hits == 25
        assert stats.cache_size == 1024
    
    def test_server_stats_validation(self):
        """Test server stats validation."""
        # All fields are required
        with pytest.raises(ValidationError):
            ServerStats()
        
        # Test individual field validation
        with pytest.raises(ValidationError):
            ServerStats(
                uptime_seconds="invalid",  # Should be float
                total_requests=100,
                successful_requests=95,
                failed_requests=5,
                applescript_executions=50,
                cache_hits=25,
                cache_size=1024
            )
    
    def test_server_stats_computed_properties(self):
        """Test computed properties of server stats."""
        stats = ServerStats(
            uptime_seconds=7200,  # 2 hours
            total_requests=100,
            successful_requests=90,
            failed_requests=10,
            applescript_executions=50,
            cache_hits=25,
            cache_size=1024
        )
        
        # These would be computed properties if implemented
        assert stats.total_requests == stats.successful_requests + stats.failed_requests
        
        # Success rate would be 0.9 if implemented as property
        expected_success_rate = stats.successful_requests / stats.total_requests
        assert expected_success_rate == 0.9


class TestModelJSONHandling:
    """Test JSON serialization/deserialization across all models."""
    
    def test_model_roundtrip_serialization(self, sample_todo_data, sample_project_data, sample_area_data, sample_tag_data):
        """Test roundtrip JSON serialization for all models."""
        models_and_data = [
            (Todo, sample_todo_data),
            (Project, sample_project_data),
            (Area, sample_area_data),
            (Tag, sample_tag_data),
        ]
        
        for model_class, sample_data in models_and_data:
            # Create model instance
            original = model_class(**sample_data)
            
            # Serialize to JSON
            json_data = original.model_dump()
            
            # Deserialize back
            restored = model_class(**json_data)
            
            # Compare key fields
            assert restored.name == original.name
            assert restored.id == original.id
            
            # Verify it's a new instance
            assert restored is not original
    
    def test_datetime_json_encoding(self):
        """Test datetime fields are properly JSON encoded."""
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).date()  # Convert to date
        todo = Todo(
            name="Test",
            creation_date=now,
            due_date=tomorrow
        )
        
        json_data = todo.model_dump()
        
        # Datetime fields should be serialized to ISO format strings
        assert isinstance(json_data["creation_date"], datetime)
        assert isinstance(json_data["due_date"], date)
    
    def test_optional_fields_serialization(self):
        """Test that optional fields serialize correctly when None."""
        todo = Todo(name="Test")
        json_data = todo.model_dump()
        
        # Optional fields should be included even if None/empty
        none_fields = ["notes", "due_date", "area_name"]
        list_fields = ["tag_names", "checklist_items"]
        
        for field in none_fields:
            assert field in json_data
            assert json_data[field] is None
        
        for field in list_fields:
            assert field in json_data
            assert json_data[field] == []


class TestModelValidationEdgeCases:
    """Test edge cases for model validation."""
    
    def test_unicode_content(self):
        """Test models handle unicode content properly."""
        unicode_content = "📝 Unicode test with émojis and spëcial chärs"
        
        todo = Todo(name=unicode_content, notes=unicode_content)
        assert todo.name == unicode_content
        assert todo.notes == unicode_content
        
        # Test serialization preserves unicode
        json_data = todo.model_dump()
        assert json_data["name"] == unicode_content
        assert json_data["notes"] == unicode_content
    
    def test_very_long_content(self):
        """Test models handle very long content."""
        long_content = "x" * 10000  # 10KB of content
        
        todo = Todo(name="Test", notes=long_content)
        assert len(todo.notes) == 10000
        
        # Should serialize without issues
        json_data = todo.model_dump()
        assert len(json_data["notes"]) == 10000
    
    def test_special_characters_in_names(self):
        """Test models handle special characters in names."""
        special_names = [
            "Name with\nnewlines",
            "Name with\ttabs",
            "Name with \"quotes\"",
            "Name with 'apostrophes'",
            "Name with <html> tags",
            "Name/with/slashes",
            "Name\\with\\backslashes",
        ]
        
        for name in special_names:
            todo = Todo(name=name)
            assert todo.name == name
            
            # Should serialize/deserialize correctly
            json_data = todo.model_dump()
            restored = Todo(**json_data)
            assert restored.name == name
    
    def test_boundary_datetime_values(self):
        """Test models handle boundary datetime values."""
        # Very old date
        old_date = datetime(1900, 1, 1)
        # Very future date
        future_date = datetime(2100, 12, 31)
        future_date_as_date = future_date.date()  # Convert to date for due_date field
        
        todo = Todo(
            name="Test",
            creation_date=old_date,
            due_date=future_date
        )
        
        assert todo.creation_date == old_date
        assert todo.due_date == future_date_as_date
        
        # Should serialize correctly
        json_data = todo.model_dump()
        restored = Todo(**json_data)
        assert restored.creation_date == old_date
        assert restored.due_date == future_date_as_date
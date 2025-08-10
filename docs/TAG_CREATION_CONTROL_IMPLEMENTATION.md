# Tag Creation Control Implementation Guide

## Overview

This document provides implementation details for integrating the Tag Creation Control feature into the existing Things 3 MCP Server codebase. It shows how the feature builds upon the current tag handling system while maintaining backward compatibility.

## Configuration Integration

### Extended Configuration Model

Add to `src/things_mcp/config.py`:

```python
from enum import Enum
from typing import List, Optional, Pattern
import re

class TagCreationPolicy(str, Enum):
    """Tag creation behavior policies"""
    CREATE = "create"
    ERROR = "error" 
    WARN = "warn"
    IGNORE = "ignore"

class TagCreationConfig(BaseModel):
    """Tag creation control configuration"""
    
    policy: TagCreationPolicy = Field(
        default=TagCreationPolicy.CREATE,
        description="Tag creation policy for non-existing tags"
    )
    
    max_auto_created_per_operation: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum tags that can be auto-created in single operation"
    )
    
    enable_audit_logging: bool = Field(
        default=False,
        description="Enable detailed audit logging for tag creation"
    )
    
    allowed_patterns: List[str] = Field(
        default_factory=lambda: ["^[a-zA-Z0-9_-]+$"],
        description="Regex patterns for allowed tag names"
    )
    
    restricted_prefixes: List[str] = Field(
        default_factory=list,
        description="Tag prefixes that cannot be auto-created"
    )
    
    max_tag_length: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum length for auto-created tags"
    )
    
    case_sensitivity: bool = Field(
        default=False,
        description="Whether tag matching is case-sensitive"
    )

# Add to main ThingsMCPConfig class
class ThingsMCPConfig(BaseSettings):
    # ... existing fields ...
    
    tag_creation: TagCreationConfig = Field(
        default_factory=TagCreationConfig,
        description="Tag creation control settings"
    )
```

## Enhanced Tag Management

### Updated Tools Implementation

Modify `src/things_mcp/tools.py` to support the new policies:

```python
from typing import Dict, List, Tuple, Optional, Union
from .config import TagCreationPolicy, TagCreationConfig
from .models import TagOperationResult, TagValidationError

class ThingsTools:
    def __init__(self, applescript_manager: AppleScriptManager, config: ThingsMCPConfig):
        self.applescript = applescript_manager
        self.config = config
        self.tag_config = config.tag_creation
        self.logger = logging.getLogger(__name__)
        
        # Compile regex patterns for performance
        self._compiled_patterns = [
            re.compile(pattern) for pattern in self.tag_config.allowed_patterns
        ]
    
    async def _validate_tag_names(self, tags: List[str]) -> Tuple[List[str], List[str]]:
        """Validate tag names against configured patterns.
        
        Returns:
            Tuple of (valid_tags, invalid_tags)
        """
        valid_tags = []
        invalid_tags = []
        
        for tag in tags:
            if not tag or len(tag) > self.tag_config.max_tag_length:
                invalid_tags.append(tag)
                continue
                
            # Check restricted prefixes
            if any(tag.lower().startswith(prefix.lower()) 
                   for prefix in self.tag_config.restricted_prefixes):
                invalid_tags.append(tag)
                continue
                
            # Check against allowed patterns
            if any(pattern.match(tag) for pattern in self._compiled_patterns):
                valid_tags.append(tag)
            else:
                invalid_tags.append(tag)
                
        return valid_tags, invalid_tags
    
    async def _handle_tag_creation_by_policy(
        self, 
        existing_tags: List[str], 
        requested_tags: List[str]
    ) -> TagOperationResult:
        """Handle tag creation based on configured policy.
        
        Args:
            existing_tags: Tags that already exist in Things
            requested_tags: Tags that were requested for the operation
            
        Returns:
            TagOperationResult with policy-specific behavior
        """
        # Normalize case if needed
        if not self.tag_config.case_sensitivity:
            existing_lower = [tag.lower() for tag in existing_tags]
            existing_tags_map = {tag.lower(): tag for tag in existing_tags}
        else:
            existing_lower = existing_tags
            existing_tags_map = {tag: tag for tag in existing_tags}
        
        # Separate existing and missing tags
        found_tags = []
        missing_tags = []
        
        for requested_tag in requested_tags:
            search_tag = requested_tag.lower() if not self.tag_config.case_sensitivity else requested_tag
            if search_tag in existing_lower:
                found_tags.append(existing_tags_map[search_tag])
            else:
                missing_tags.append(requested_tag)
        
        # Validate missing tags
        valid_missing, invalid_missing = await self._validate_tag_names(missing_tags)
        
        if invalid_missing:
            raise TagValidationError(f"Invalid tag names: {invalid_missing}")
        
        # Check auto-creation limit
        if len(valid_missing) > self.tag_config.max_auto_created_per_operation:
            raise TagValidationError(
                f"Too many tags to create: {len(valid_missing)} "
                f"(limit: {self.tag_config.max_auto_created_per_operation})"
            )
        
        # Handle based on policy
        if self.tag_config.policy == TagCreationPolicy.CREATE:
            return await self._handle_create_policy(found_tags, valid_missing)
            
        elif self.tag_config.policy == TagCreationPolicy.ERROR:
            return await self._handle_error_policy(found_tags, valid_missing)
            
        elif self.tag_config.policy == TagCreationPolicy.WARN:
            return await self._handle_warn_policy(found_tags, valid_missing)
            
        elif self.tag_config.policy == TagCreationPolicy.IGNORE:
            return await self._handle_ignore_policy(found_tags, valid_missing)
        
        else:
            raise ValueError(f"Unknown tag creation policy: {self.tag_config.policy}")
    
    async def _handle_create_policy(
        self, 
        existing_tags: List[str], 
        missing_tags: List[str]
    ) -> TagOperationResult:
        """Handle CREATE policy - auto-create missing tags."""
        created_tags = []
        
        if missing_tags:
            creation_result = await self._create_tags_batch(missing_tags)
            created_tags = creation_result['created']
            
            if self.tag_config.enable_audit_logging:
                self.logger.info(
                    f"Auto-created tags (CREATE policy): {created_tags}",
                    extra={'audit': True, 'policy': 'CREATE'}
                )
        
        return TagOperationResult(
            policy=TagCreationPolicy.CREATE,
            success=True,
            applied_tags=existing_tags + created_tags,
            existing_tags=existing_tags,
            created_tags=created_tags,
            ignored_tags=[],
            warnings=[]
        )
    
    async def _handle_error_policy(
        self, 
        existing_tags: List[str], 
        missing_tags: List[str]
    ) -> TagOperationResult:
        """Handle ERROR policy - fail if any tags are missing."""
        if missing_tags:
            # Find similar tags for suggestions
            suggestions = await self._find_similar_tags(missing_tags)
            
            raise TagNotFoundError(
                message=f"Tags do not exist: {missing_tags}",
                missing_tags=missing_tags,
                existing_tags=existing_tags,
                suggestions=suggestions,
                policy=TagCreationPolicy.ERROR
            )
        
        return TagOperationResult(
            policy=TagCreationPolicy.ERROR,
            success=True,
            applied_tags=existing_tags,
            existing_tags=existing_tags,
            created_tags=[],
            ignored_tags=[],
            warnings=[]
        )
    
    async def _handle_warn_policy(
        self, 
        existing_tags: List[str], 
        missing_tags: List[str]
    ) -> TagOperationResult:
        """Handle WARN policy - create tags but log warnings."""
        created_tags = []
        warnings = []
        
        if missing_tags:
            creation_result = await self._create_tags_batch(missing_tags)
            created_tags = creation_result['created']
            
            # Log warnings for each created tag
            for tag in created_tags:
                warning_msg = f"Auto-created tag '{tag}' - consider using existing tags"
                warnings.append({
                    'type': 'TAG_CREATED',
                    'message': warning_msg,
                    'tag': tag,
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                })
                
                if self.tag_config.enable_audit_logging:
                    self.logger.warning(
                        warning_msg,
                        extra={'audit': True, 'policy': 'WARN', 'tag': tag}
                    )
        
        return TagOperationResult(
            policy=TagCreationPolicy.WARN,
            success=True,
            applied_tags=existing_tags + created_tags,
            existing_tags=existing_tags,
            created_tags=created_tags,
            ignored_tags=[],
            warnings=warnings
        )
    
    async def _handle_ignore_policy(
        self, 
        existing_tags: List[str], 
        missing_tags: List[str]
    ) -> TagOperationResult:
        """Handle IGNORE policy - skip missing tags silently."""
        if missing_tags and self.tag_config.enable_audit_logging:
            self.logger.info(
                f"Ignored missing tags (IGNORE policy): {missing_tags}",
                extra={'audit': True, 'policy': 'IGNORE'}
            )
        
        return TagOperationResult(
            policy=TagCreationPolicy.IGNORE,
            success=True,
            applied_tags=existing_tags,
            existing_tags=existing_tags,
            created_tags=[],
            ignored_tags=missing_tags,
            warnings=[]
        )
    
    async def _create_tags_batch(self, tag_names: List[str]) -> Dict[str, List[str]]:
        """Create multiple tags in a single operation."""
        # This extends the existing _ensure_tags_exist method
        return await self._ensure_tags_exist(tag_names)
    
    async def _find_similar_tags(self, missing_tags: List[str], limit: int = 3) -> Dict[str, List[str]]:
        """Find similar existing tags for suggestions."""
        suggestions = {}
        
        try:
            all_tags = await self.get_tags(include_items=False)
            tag_names = [tag.get('name', '') for tag in all_tags]
            
            from difflib import get_close_matches
            
            for missing_tag in missing_tags:
                similar = get_close_matches(
                    missing_tag, 
                    tag_names, 
                    n=limit, 
                    cutoff=0.6
                )
                suggestions[missing_tag] = similar
                
        except Exception as e:
            self.logger.warning(f"Could not find similar tags: {e}")
            
        return suggestions
```

## Data Models

Create `src/things_mcp/models/tag_models.py`:

```python
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

@dataclass
class TagOperationResult:
    """Result of a tag operation with policy-specific behavior."""
    
    policy: 'TagCreationPolicy'
    success: bool
    applied_tags: List[str]
    existing_tags: List[str]
    created_tags: List[str]
    ignored_tags: List[str]
    warnings: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'policy': self.policy.value,
            'success': self.success,
            'applied_tags': self.applied_tags,
            'tag_operations': {
                'existing_tags': self.existing_tags,
                'created_tags': self.created_tags,
                'ignored_tags': self.ignored_tags,
                'total_applied': len(self.applied_tags),
                'total_created': len(self.created_tags),
                'total_ignored': len(self.ignored_tags)
            },
            'warnings': self.warnings if self.warnings else None
        }

class TagValidationError(ValueError):
    """Error raised when tag validation fails."""
    pass

class TagNotFoundError(Exception):
    """Error raised when tags are not found and policy is ERROR."""
    
    def __init__(
        self, 
        message: str,
        missing_tags: List[str],
        existing_tags: List[str],
        suggestions: Dict[str, List[str]],
        policy: 'TagCreationPolicy'
    ):
        super().__init__(message)
        self.missing_tags = missing_tags
        self.existing_tags = existing_tags
        self.suggestions = suggestions
        self.policy = policy
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for error responses."""
        return {
            'error': 'TAG_NOT_FOUND',
            'message': str(self),
            'details': {
                'non_existing_tags': self.missing_tags,
                'existing_tags': self.existing_tags,
                'policy': self.policy.value
            },
            'suggestions': {
                'available_similar_tags': self.suggestions,
                'create_tags_first': [
                    "Use add_tag endpoint to create tags first",
                    f"Or change policy from {self.policy.value.upper()} to CREATE mode"
                ]
            }
        }
```

## Server Integration

Update `src/things_mcp/simple_server.py` to use the new tag handling:

```python
class ThingsMCPServer:
    def __init__(self):
        # Load configuration with tag creation settings
        self.config = ThingsMCPConfig()
        self.applescript_manager = AppleScriptManager()
        self.tools = ThingsTools(self.applescript_manager, self.config)
        # ... rest of initialization
    
    def _register_tools(self) -> None:
        @self.mcp.tool()
        async def add_todo(
            title: str = Field(..., description="Title of the todo"),
            # ... other parameters ...
            tags: Optional[str] = Field(None, description="Comma-separated tags to apply to the todo")
        ) -> Dict[str, Any]:
            """Create a new todo in Things with tag creation control."""
            try:
                tag_list = [t.strip() for t in tags.split(",")] if tags else []
                
                # Handle tag creation based on policy
                if tag_list:
                    all_existing_tags = await self.tools.get_tags(include_items=False)
                    existing_tag_names = [tag.get('name', '') for tag in all_existing_tags]
                    
                    tag_result = await self.tools._handle_tag_creation_by_policy(
                        existing_tags=existing_tag_names,
                        requested_tags=tag_list
                    )
                    
                    # Use only the tags that were approved by the policy
                    approved_tags = tag_result.applied_tags
                else:
                    tag_result = None
                    approved_tags = []
                
                # Create the todo with approved tags
                result = await self.tools.add_todo(
                    title=title,
                    notes=notes,
                    tags=approved_tags,
                    when=when,
                    deadline=deadline,
                    list_id=list_id,
                    list_title=list_title,
                    heading=heading,
                    checklist_items=[item.strip() for item in checklist_items.split("\n")] if checklist_items else None
                )
                
                # Enhance response with tag operation details
                if tag_result:
                    result.update(tag_result.to_dict())
                    
                    # Add policy-specific messages
                    if tag_result.created_tags:
                        if tag_result.policy == TagCreationPolicy.WARN:
                            result['message'] = f"Todo created successfully. Warning: Created new tag(s): {', '.join(tag_result.created_tags)}"
                        else:
                            result['message'] = f"Todo created successfully. Created new tag(s): {', '.join(tag_result.created_tags)}"
                    
                    if tag_result.ignored_tags:
                        result['message'] = f"Todo created successfully. Ignored {len(tag_result.ignored_tags)} non-existing tag(s)"
                
                return result
                
            except TagNotFoundError as e:
                # Return structured error response for ERROR policy
                error_response = e.to_dict()
                error_response['success'] = False
                raise HTTPException(status_code=400, detail=error_response)
                
            except TagValidationError as e:
                raise HTTPException(status_code=400, detail={
                    'success': False,
                    'error': 'TAG_VALIDATION_FAILED',
                    'message': str(e)
                })
                
            except Exception as e:
                logger.error(f"Error adding todo: {e}")
                raise
        
        # Similar updates for add_tags, update_todo, add_project, etc.
        @self.mcp.tool()
        async def add_tags(
            todo_id: str = Field(..., description="ID of the todo"),
            tags: str = Field(..., description="Comma-separated tags to add")
        ) -> Dict[str, Any]:
            """Add tags to a todo with tag creation control."""
            try:
                tag_list = [t.strip() for t in tags.split(",")] if tags else []
                
                if not tag_list:
                    return {
                        'success': False,
                        'error': 'NO_TAGS_PROVIDED',
                        'message': 'No tags provided to add'
                    }
                
                # Get existing tags
                all_existing_tags = await self.tools.get_tags(include_items=False)
                existing_tag_names = [tag.get('name', '') for tag in all_existing_tags]
                
                # Handle tag creation by policy
                tag_result = await self.tools._handle_tag_creation_by_policy(
                    existing_tags=existing_tag_names,
                    requested_tags=tag_list
                )
                
                # Add approved tags to the todo
                if tag_result.applied_tags:
                    result = await self.tools.add_tags(
                        todo_id=todo_id, 
                        tags=tag_result.applied_tags
                    )
                    
                    # Enhance response with tag operation details
                    result.update(tag_result.to_dict())
                    
                    return result
                else:
                    return {
                        'success': True,
                        'message': 'No tags were applied',
                        **tag_result.to_dict()
                    }
                    
            except TagNotFoundError as e:
                error_response = e.to_dict()
                error_response['success'] = False
                raise HTTPException(status_code=400, detail=error_response)
                
            except Exception as e:
                logger.error(f"Error adding tags: {e}")
                raise
```

## Testing Integration

Create `tests/test_tag_creation_control.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.things_mcp.config import TagCreationPolicy, TagCreationConfig
from src.things_mcp.models.tag_models import TagNotFoundError, TagValidationError
from src.things_mcp.tools import ThingsTools

@pytest.fixture
def create_policy_config():
    config = TagCreationConfig(policy=TagCreationPolicy.CREATE)
    return config

@pytest.fixture
def error_policy_config():
    config = TagCreationConfig(policy=TagCreationPolicy.ERROR)
    return config

@pytest.fixture
def warn_policy_config():
    config = TagCreationConfig(
        policy=TagCreationPolicy.WARN,
        enable_audit_logging=True
    )
    return config

@pytest.fixture
def ignore_policy_config():
    config = TagCreationConfig(policy=TagCreationPolicy.IGNORE)
    return config

class TestTagCreationPolicies:
    
    @pytest.mark.asyncio
    async def test_create_policy_auto_creates_tags(self, create_policy_config):
        """Test that CREATE policy automatically creates missing tags."""
        # Mock setup
        mock_applescript = AsyncMock()
        tools = ThingsTools(mock_applescript, create_policy_config)
        
        existing_tags = ['work', 'review']
        requested_tags = ['work', 'urgent', 'review', 'new-tag']
        
        with patch.object(tools, '_create_tags_batch') as mock_create:
            mock_create.return_value = {'created': ['urgent', 'new-tag']}
            
            result = await tools._handle_tag_creation_by_policy(
                existing_tags, requested_tags
            )
        
        assert result.success is True
        assert result.policy == TagCreationPolicy.CREATE
        assert set(result.applied_tags) == {'work', 'review', 'urgent', 'new-tag'}
        assert set(result.created_tags) == {'urgent', 'new-tag'}
        assert result.ignored_tags == []
        assert result.warnings == []
    
    @pytest.mark.asyncio
    async def test_error_policy_raises_exception(self, error_policy_config):
        """Test that ERROR policy raises exception for missing tags."""
        mock_applescript = AsyncMock()
        tools = ThingsTools(mock_applescript, error_policy_config)
        
        existing_tags = ['work', 'review']
        requested_tags = ['work', 'urgent', 'new-tag']
        
        with pytest.raises(TagNotFoundError) as exc_info:
            await tools._handle_tag_creation_by_policy(
                existing_tags, requested_tags
            )
        
        error = exc_info.value
        assert set(error.missing_tags) == {'urgent', 'new-tag'}
        assert set(error.existing_tags) == {'work', 'review'}
        assert error.policy == TagCreationPolicy.ERROR
    
    @pytest.mark.asyncio
    async def test_warn_policy_creates_with_warnings(self, warn_policy_config):
        """Test that WARN policy creates tags but includes warnings."""
        mock_applescript = AsyncMock()
        tools = ThingsTools(mock_applescript, warn_policy_config)
        
        existing_tags = ['work']
        requested_tags = ['work', 'urgent']
        
        with patch.object(tools, '_create_tags_batch') as mock_create:
            mock_create.return_value = {'created': ['urgent']}
            
            result = await tools._handle_tag_creation_by_policy(
                existing_tags, requested_tags
            )
        
        assert result.success is True
        assert result.policy == TagCreationPolicy.WARN
        assert 'urgent' in result.applied_tags
        assert 'urgent' in result.created_tags
        assert len(result.warnings) == 1
        assert result.warnings[0]['type'] == 'TAG_CREATED'
        assert 'urgent' in result.warnings[0]['message']
    
    @pytest.mark.asyncio
    async def test_ignore_policy_skips_missing_tags(self, ignore_policy_config):
        """Test that IGNORE policy skips missing tags."""
        mock_applescript = AsyncMock()
        tools = ThingsTools(mock_applescript, ignore_policy_config)
        
        existing_tags = ['work', 'review']
        requested_tags = ['work', 'urgent', 'review', 'new-tag']
        
        result = await tools._handle_tag_creation_by_policy(
            existing_tags, requested_tags
        )
        
        assert result.success is True
        assert result.policy == TagCreationPolicy.IGNORE
        assert set(result.applied_tags) == {'work', 'review'}
        assert result.created_tags == []
        assert set(result.ignored_tags) == {'urgent', 'new-tag'}
        assert result.warnings == []
    
    @pytest.mark.asyncio
    async def test_tag_validation_fails_invalid_names(self, create_policy_config):
        """Test tag name validation."""
        mock_applescript = AsyncMock()
        config = create_policy_config
        config.allowed_patterns = ['^[a-zA-Z0-9_-]+$']
        config.max_tag_length = 10
        
        tools = ThingsTools(mock_applescript, config)
        
        # Test invalid characters and length
        valid, invalid = await tools._validate_tag_names([
            'valid-tag',     # valid
            'invalid tag',   # space not allowed
            'way-too-long-tag-name',  # too long
            'valid_2'        # valid
        ])
        
        assert set(valid) == {'valid-tag', 'valid_2'}
        assert set(invalid) == {'invalid tag', 'way-too-long-tag-name'}
    
    @pytest.mark.asyncio 
    async def test_auto_creation_limit(self, create_policy_config):
        """Test that auto-creation respects limits."""
        mock_applescript = AsyncMock()
        config = create_policy_config
        config.max_auto_created_per_operation = 2
        
        tools = ThingsTools(mock_applescript, config)
        
        existing_tags = []
        requested_tags = ['tag1', 'tag2', 'tag3', 'tag4']  # 4 > limit of 2
        
        with pytest.raises(TagValidationError) as exc_info:
            await tools._handle_tag_creation_by_policy(
                existing_tags, requested_tags
            )
        
        assert "Too many tags to create" in str(exc_info.value)
```

## Environment Variable Support

Update the configuration loading to support environment variables:

```python
# In config.py
class TagCreationConfig(BaseModel):
    # ... existing fields ...
    
    class Config:
        env_prefix = "THINGS_MCP_TAG_"
        
        # Environment variable mapping:
        # THINGS_MCP_TAG_CREATION_POLICY=warn
        # THINGS_MCP_TAG_MAX_AUTO_CREATED_PER_OPERATION=5
        # THINGS_MCP_TAG_ENABLE_AUDIT_LOGGING=true
        # THINGS_MCP_TAG_ALLOWED_PATTERNS="^[a-zA-Z0-9_-]+$,^[a-zA-Z0-9_.]+$"
        # THINGS_MCP_TAG_RESTRICTED_PREFIXES="admin,system,internal"
```

## Backward Compatibility

The implementation maintains backward compatibility by:

1. **Default Policy**: Uses CREATE as default, matching current behavior
2. **Existing APIs**: All existing endpoints work without changes
3. **Response Structure**: Adds optional fields, doesn't remove existing ones
4. **Configuration**: Tag creation settings are optional in config files

## Migration Path

For existing installations:

1. **Phase 1**: Deploy with CREATE policy (no behavior change)
2. **Phase 2**: Enable WARN policy and audit logging to understand usage
3. **Phase 3**: Optionally switch to stricter policies based on analysis

This implementation provides a comprehensive, configurable solution for tag creation control while maintaining compatibility with the existing codebase.
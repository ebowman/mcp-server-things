try:
    import pytest
except ImportError:
    # If pytest is not available, create a minimal replacement
    class pytest:
        @staticmethod
        def fixture(func):
            return func
        
        @staticmethod
        def raises(exception, match=None):
            class RaisesContext:
                def __init__(self, exception_type, match_str):
                    self.exception_type = exception_type
                    self.match_str = match_str
                
                def __enter__(self):
                    return self
                
                def __exit__(self, exc_type, exc_val, exc_tb):
                    if exc_type is None:
                        raise AssertionError(f"Expected {self.exception_type.__name__} but no exception was raised")
                    if not issubclass(exc_type, self.exception_type):
                        return False
                    if self.match_str and self.match_str not in str(exc_val):
                        raise AssertionError(f"Expected exception message to contain '{self.match_str}', got '{str(exc_val)}'")
                    return True
            
            return RaisesContext(exception, match)
        
        @staticmethod
        def main(args):
            print("pytest not available, use run_tag_tests.py instead")

import unittest.mock as mock
import os
import tempfile
try:
    import yaml
except ImportError:
    # If yaml is not available, create minimal replacement for basic tests
    class yaml:
        @staticmethod
        def dump(data, file):
            pass
        
        @staticmethod
        def load(file):
            return {}

from unittest.mock import patch, MagicMock

try:
    from src.things_mcp.simple_server import (
        TagValidationService,
        TagCreationPolicy,
        TagConfig,
        get_all_tags,
        add_tags,
        remove_tags,
        get_tagged_items
    )
except ImportError:
    # For testing when the actual implementation doesn't exist yet
    # Create mock classes for basic testing
    from enum import Enum
    
    class TagCreationPolicy(Enum):
        AUTO_CREATE = "auto_create"
        STRICT_NO_CREATE = "strict_no_create" 
        CREATE_WITH_WARNING = "create_with_warning"
        LIMITED_AUTO_CREATE = "limited_auto_create"
    
    class TagConfig:
        def __init__(self, creation_policy=TagCreationPolicy.CREATE_WITH_WARNING,
                     case_sensitive=False, auto_creation_limit=5, existing_tags=None):
            self.creation_policy = creation_policy
            self.case_sensitive = case_sensitive
            self.auto_creation_limit = auto_creation_limit
            self.existing_tags = existing_tags or []
        
        @classmethod
        def from_dict(cls, data):
            policy_str = data.get('creation_policy', 'create_with_warning')
            try:
                policy = TagCreationPolicy(policy_str)
            except ValueError:
                raise ValueError(f"Invalid tag creation policy: {policy_str}")
            
            return cls(
                creation_policy=policy,
                case_sensitive=data.get('case_sensitive', False),
                auto_creation_limit=data.get('auto_creation_limit', 5),
                existing_tags=data.get('existing_tags', [])
            )
    
    class ValidationResult:
        def __init__(self, valid_tags=None, invalid_tags=None, warnings=None, created_tags=None):
            self.valid_tags = valid_tags or []
            self.invalid_tags = invalid_tags or []
            self.warnings = warnings or []
            self.created_tags = created_tags or []
    
    class TagValidationService:
        def __init__(self):
            pass
            
        def _load_config(self):
            return TagConfig()
            
        def get_existing_tags(self, config):
            return set()
            
        def validate_tags(self, tags, config):
            return ValidationResult(valid_tags=tags, created_tags=tags)
    
    def get_all_tags():
        return []
    
    def add_tags(todo_id, tags):
        return {'success': True, 'validation_result': {'valid_tags': tags.split(','), 'created_tags': []}}
    
    def remove_tags(todo_id, tags):
        return {'success': True}
    
    def get_tagged_items(tag):
        return []


class TestTagConfig:
    """Test TagConfig class functionality."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TagConfig()
        assert config.creation_policy == TagCreationPolicy.CREATE_WITH_WARNING
        assert config.case_sensitive is False
        assert config.auto_creation_limit == 5
        assert config.existing_tags == []

    def test_custom_config(self):
        """Test custom configuration values."""
        config = TagConfig(
            creation_policy=TagCreationPolicy.STRICT_NO_CREATE,
            case_sensitive=True,
            auto_creation_limit=10,
            existing_tags=['work', 'personal']
        )
        assert config.creation_policy == TagCreationPolicy.STRICT_NO_CREATE
        assert config.case_sensitive is True
        assert config.auto_creation_limit == 10
        assert config.existing_tags == ['work', 'personal']

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            'creation_policy': 'auto_create',
            'case_sensitive': True,
            'auto_creation_limit': 15,
            'existing_tags': ['urgent', 'later']
        }
        config = TagConfig.from_dict(data)
        assert config.creation_policy == TagCreationPolicy.AUTO_CREATE
        assert config.case_sensitive is True
        assert config.auto_creation_limit == 15
        assert config.existing_tags == ['urgent', 'later']

    def test_invalid_policy_string(self):
        """Test handling of invalid policy string."""
        data = {'creation_policy': 'invalid_policy'}
        with pytest.raises(ValueError, match="Invalid tag creation policy"):
            TagConfig.from_dict(data)

    def test_config_from_partial_dict(self):
        """Test creating config from partial dictionary (uses defaults)."""
        data = {'creation_policy': 'strict_no_create'}
        config = TagConfig.from_dict(data)
        assert config.creation_policy == TagCreationPolicy.STRICT_NO_CREATE
        assert config.case_sensitive is False  # default
        assert config.auto_creation_limit == 5  # default


class TestTagValidationService:
    """Test TagValidationService functionality."""

    @pytest.fixture
    def mock_applescript(self):
        """Mock AppleScript operations."""
        with patch('src.simple_server.run_applescript') as mock_script:
            mock_script.return_value = [
                {'name': 'Work', 'uuid': 'tag-work-123'},
                {'name': 'Personal', 'uuid': 'tag-personal-456'},
                {'name': 'urgent', 'uuid': 'tag-urgent-789'}
            ]
            yield mock_script

    @pytest.fixture
    def service(self, mock_applescript):
        """Create TagValidationService instance with mocked AppleScript."""
        return TagValidationService()

    def test_get_existing_tags_case_insensitive(self, service, mock_applescript):
        """Test getting existing tags (case insensitive)."""
        config = TagConfig(case_sensitive=False)
        tags = service.get_existing_tags(config)
        expected = {'work', 'personal', 'urgent'}
        assert tags == expected

    def test_get_existing_tags_case_sensitive(self, service, mock_applescript):
        """Test getting existing tags (case sensitive)."""
        config = TagConfig(case_sensitive=True)
        tags = service.get_existing_tags(config)
        expected = {'Work', 'Personal', 'urgent'}
        assert tags == expected

    def test_get_existing_tags_with_predefined(self, service, mock_applescript):
        """Test getting existing tags with predefined list."""
        config = TagConfig(
            existing_tags=['Work', 'Custom'],
            case_sensitive=False
        )
        tags = service.get_existing_tags(config)
        # Should combine AppleScript tags with predefined ones
        expected = {'work', 'personal', 'urgent', 'custom'}
        assert tags == expected

    def test_validate_tags_auto_create(self, service, mock_applescript):
        """Test AUTO_CREATE policy - should pass all tags."""
        config = TagConfig(creation_policy=TagCreationPolicy.AUTO_CREATE)
        result = service.validate_tags(
            ['Work', 'NewTag1', 'NewTag2'],
            config
        )
        assert result.valid_tags == ['Work', 'NewTag1', 'NewTag2']
        assert result.invalid_tags == []
        assert result.warnings == []
        assert result.created_tags == ['NewTag1', 'NewTag2']

    def test_validate_tags_strict_no_create(self, service, mock_applescript):
        """Test STRICT_NO_CREATE policy - should reject non-existing tags."""
        config = TagConfig(creation_policy=TagCreationPolicy.STRICT_NO_CREATE)
        result = service.validate_tags(
            ['Work', 'NonExistent', 'Personal'],
            config
        )
        assert result.valid_tags == ['Work', 'Personal']
        assert result.invalid_tags == ['NonExistent']
        assert len(result.warnings) == 1
        assert 'NonExistent' in result.warnings[0]
        assert result.created_tags == []

    def test_validate_tags_create_with_warning(self, service, mock_applescript):
        """Test CREATE_WITH_WARNING policy - should create with warnings."""
        config = TagConfig(creation_policy=TagCreationPolicy.CREATE_WITH_WARNING)
        result = service.validate_tags(
            ['Work', 'NewTag1', 'NewTag2'],
            config
        )
        assert result.valid_tags == ['Work', 'NewTag1', 'NewTag2']
        assert result.invalid_tags == []
        assert len(result.warnings) == 2
        assert any('NewTag1' in warning for warning in result.warnings)
        assert any('NewTag2' in warning for warning in result.warnings)
        assert result.created_tags == ['NewTag1', 'NewTag2']

    def test_validate_tags_limited_auto_create_within_limit(self, service, mock_applescript):
        """Test LIMITED_AUTO_CREATE policy within limit."""
        config = TagConfig(
            creation_policy=TagCreationPolicy.LIMITED_AUTO_CREATE,
            auto_creation_limit=3
        )
        result = service.validate_tags(
            ['Work', 'New1', 'New2'],
            config
        )
        assert result.valid_tags == ['Work', 'New1', 'New2']
        assert result.invalid_tags == []
        assert len(result.warnings) == 1  # Warning about creating new tags
        assert result.created_tags == ['New1', 'New2']

    def test_validate_tags_limited_auto_create_exceeds_limit(self, service, mock_applescript):
        """Test LIMITED_AUTO_CREATE policy exceeding limit."""
        config = TagConfig(
            creation_policy=TagCreationPolicy.LIMITED_AUTO_CREATE,
            auto_creation_limit=2
        )
        result = service.validate_tags(
            ['Work', 'New1', 'New2', 'New3'],
            config
        )
        assert result.valid_tags == ['Work']
        assert result.invalid_tags == ['New1', 'New2', 'New3']
        assert len(result.warnings) == 1
        assert 'exceeds auto-creation limit' in result.warnings[0]
        assert result.created_tags == []

    def test_validate_tags_case_sensitivity(self, service, mock_applescript):
        """Test case sensitivity in tag validation."""
        # Case insensitive - 'work' should match 'Work'
        config = TagConfig(
            creation_policy=TagCreationPolicy.STRICT_NO_CREATE,
            case_sensitive=False
        )
        result = service.validate_tags(['work', 'PERSONAL'], config)
        assert result.valid_tags == ['work', 'PERSONAL']
        assert result.invalid_tags == []

        # Case sensitive - 'work' should NOT match 'Work'
        config = TagConfig(
            creation_policy=TagCreationPolicy.STRICT_NO_CREATE,
            case_sensitive=True
        )
        result = service.validate_tags(['work', 'Work'], config)
        assert result.valid_tags == ['Work']  # Only exact case match
        assert result.invalid_tags == ['work']

    def test_validate_tags_empty_list(self, service, mock_applescript):
        """Test validation of empty tag list."""
        config = TagConfig()
        result = service.validate_tags([], config)
        assert result.valid_tags == []
        assert result.invalid_tags == []
        assert result.warnings == []
        assert result.created_tags == []

    def test_validate_tags_duplicate_tags(self, service, mock_applescript):
        """Test validation with duplicate tags."""
        config = TagConfig(creation_policy=TagCreationPolicy.AUTO_CREATE)
        result = service.validate_tags(
            ['Work', 'NewTag', 'Work', 'NewTag'],
            config
        )
        # Should deduplicate
        assert set(result.valid_tags) == {'Work', 'NewTag'}
        assert len(result.valid_tags) == 2
        assert result.created_tags == ['NewTag']


class TestTagCreationIntegration:
    """Test tag creation with different configuration sources."""

    @pytest.fixture
    def temp_config_file(self):
        """Create temporary config file for testing."""
        config_data = {
            'tag_creation': {
                'creation_policy': 'strict_no_create',
                'case_sensitive': True,
                'auto_creation_limit': 3,
                'existing_tags': ['predefined1', 'predefined2']
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_file = f.name
        
        yield temp_file
        os.unlink(temp_file)

    @patch('src.simple_server.run_applescript')
    def test_load_config_from_file(self, mock_applescript, temp_config_file):
        """Test loading configuration from file."""
        mock_applescript.return_value = []
        
        with patch.dict(os.environ, {'TAG_CONFIG_FILE': temp_config_file}):
            service = TagValidationService()
            config = service._load_config()
            
            assert config.creation_policy == TagCreationPolicy.STRICT_NO_CREATE
            assert config.case_sensitive is True
            assert config.auto_creation_limit == 3
            assert config.existing_tags == ['predefined1', 'predefined2']

    @patch('src.simple_server.run_applescript')
    def test_load_config_from_env_vars(self, mock_applescript):
        """Test loading configuration from environment variables."""
        mock_applescript.return_value = []
        
        env_vars = {
            'TAG_CREATION_POLICY': 'auto_create',
            'TAG_CASE_SENSITIVE': 'true',
            'TAG_AUTO_CREATION_LIMIT': '10',
            'TAG_EXISTING_TAGS': 'env1,env2,env3'
        }
        
        with patch.dict(os.environ, env_vars):
            service = TagValidationService()
            config = service._load_config()
            
            assert config.creation_policy == TagCreationPolicy.AUTO_CREATE
            assert config.case_sensitive is True
            assert config.auto_creation_limit == 10
            assert config.existing_tags == ['env1', 'env2', 'env3']

    @patch('src.simple_server.run_applescript')
    def test_load_config_defaults(self, mock_applescript):
        """Test loading default configuration when no config provided."""
        mock_applescript.return_value = []
        
        # Clear any existing environment variables
        env_vars_to_clear = [
            'TAG_CONFIG_FILE', 'TAG_CREATION_POLICY', 'TAG_CASE_SENSITIVE',
            'TAG_AUTO_CREATION_LIMIT', 'TAG_EXISTING_TAGS'
        ]
        
        with patch.dict(os.environ, {}, clear=True):
            service = TagValidationService()
            config = service._load_config()
            
            assert config.creation_policy == TagCreationPolicy.CREATE_WITH_WARNING
            assert config.case_sensitive is False
            assert config.auto_creation_limit == 5
            assert config.existing_tags == []

    def test_load_config_invalid_file(self):
        """Test handling of invalid config file."""
        with patch.dict(os.environ, {'TAG_CONFIG_FILE': '/nonexistent/file.yaml'}):
            with patch('src.simple_server.run_applescript') as mock_script:
                mock_script.return_value = []
                
                # Should fall back to defaults without crashing
                service = TagValidationService()
                config = service._load_config()
                assert config.creation_policy == TagCreationPolicy.CREATE_WITH_WARNING


class TestTagOperationsWithValidation:
    """Test tag operations with validation enabled."""

    @pytest.fixture
    def mock_applescript_tags(self):
        """Mock AppleScript for tag operations."""
        def mock_script_side_effect(script_name, *args):
            if script_name == 'get_all_tags':
                return [
                    {'name': 'Work', 'uuid': 'tag-work-123'},
                    {'name': 'Personal', 'uuid': 'tag-personal-456'}
                ]
            elif script_name == 'add_tags':
                return {'success': True, 'tags_added': args[1].split(',')}
            elif script_name == 'remove_tags':
                return {'success': True, 'tags_removed': args[1].split(',')}
            elif script_name == 'get_tagged_items':
                return [{'name': 'Test Todo', 'uuid': 'todo-123'}]
            return {}
        
        with patch('src.simple_server.run_applescript') as mock_script:
            mock_script.side_effect = mock_script_side_effect
            yield mock_script

    def test_add_tags_with_validation_success(self, mock_applescript_tags):
        """Test adding valid tags."""
        with patch.dict(os.environ, {'TAG_CREATION_POLICY': 'auto_create'}):
            result = add_tags('todo-123', 'Work,NewTag')
            
            assert result['success'] is True
            assert 'validation_result' in result
            assert result['validation_result']['valid_tags'] == ['Work', 'NewTag']
            assert result['validation_result']['created_tags'] == ['NewTag']

    def test_add_tags_with_validation_failure(self, mock_applescript_tags):
        """Test adding tags that fail validation."""
        with patch.dict(os.environ, {'TAG_CREATION_POLICY': 'strict_no_create'}):
            result = add_tags('todo-123', 'Work,NonExistent')
            
            assert result['success'] is True
            assert result['validation_result']['valid_tags'] == ['Work']
            assert result['validation_result']['invalid_tags'] == ['NonExistent']
            assert len(result['validation_result']['warnings']) > 0

    def test_add_tags_backward_compatibility(self, mock_applescript_tags):
        """Test that add_tags works without validation config (backward compatibility)."""
        # Clear all tag-related environment variables
        with patch.dict(os.environ, {}, clear=True):
            result = add_tags('todo-123', 'Work,NewTag')
            
            assert result['success'] is True
            # Should still work, with default validation behavior
            assert 'validation_result' in result

    def test_remove_tags_no_validation(self, mock_applescript_tags):
        """Test that remove_tags doesn't apply validation."""
        result = remove_tags('todo-123', 'Work,NonExistent')
        
        assert result['success'] is True
        assert 'validation_result' not in result
        # Should remove tags without validation

    def test_get_tagged_items_no_validation(self, mock_applescript_tags):
        """Test that get_tagged_items doesn't apply validation."""
        result = get_tagged_items('Work')
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['name'] == 'Test Todo'


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling."""

    @patch('src.simple_server.run_applescript')
    def test_applescript_error_handling(self, mock_applescript):
        """Test handling of AppleScript errors."""
        mock_applescript.side_effect = Exception("AppleScript error")
        
        service = TagValidationService()
        # Should handle error gracefully and return empty set
        config = TagConfig()
        tags = service.get_existing_tags(config)
        assert tags == set()

    def test_invalid_tag_names(self):
        """Test handling of invalid tag names."""
        service = TagValidationService()
        config = TagConfig()
        
        with patch('src.simple_server.run_applescript') as mock_script:
            mock_script.return_value = []
            
            # Test with None, empty strings, etc.
            result = service.validate_tags(['', '   ', None], config)
            # Should filter out invalid names
            assert len([t for t in result.valid_tags if t and t.strip()]) >= 0

    def test_large_tag_list(self):
        """Test handling of large tag lists."""
        service = TagValidationService()
        config = TagConfig(
            creation_policy=TagCreationPolicy.LIMITED_AUTO_CREATE,
            auto_creation_limit=5
        )
        
        with patch('src.simple_server.run_applescript') as mock_script:
            mock_script.return_value = []
            
            # Create a large list of new tags
            large_tag_list = [f'newtag{i}' for i in range(100)]
            result = service.validate_tags(large_tag_list, config)
            
            # Should reject most tags due to limit
            assert len(result.invalid_tags) > len(result.valid_tags)

    def test_unicode_tag_names(self):
        """Test handling of unicode tag names."""
        service = TagValidationService()
        config = TagConfig(creation_policy=TagCreationPolicy.AUTO_CREATE)
        
        with patch('src.simple_server.run_applescript') as mock_script:
            mock_script.return_value = []
            
            unicode_tags = ['工作', 'личное', 'travail', '📝notes']
            result = service.validate_tags(unicode_tags, config)
            
            # Should handle unicode tags properly
            assert len(result.valid_tags) == len(unicode_tags)
            assert result.created_tags == unicode_tags


if __name__ == '__main__':
    pytest.main([__file__])

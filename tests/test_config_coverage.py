"""
Comprehensive configuration tests for maximum coverage.

Tests all aspects of the ThingsMCPConfig class including:
- Default values
- Custom initialization
- Environment variable support
- Validation
- Enum types
- Edge cases
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.things_mcp.config import (
    ThingsMCPConfig, 
    ExecutionMethod,
    LogLevel,
    TagCreationPolicy
)


class TestThingsMCPConfigDefaults:
    """Test default configuration values and initialization."""
    
    def test_default_config_creation(self):
        """Test creating config with all defaults."""
        config = ThingsMCPConfig()
        
        # Server configuration defaults
        assert config.server_name == "things3-mcp-server"
        assert config.server_version == "1.0.0"
        assert config.server_description == "MCP server for Things 3 task management integration"
        
        # AppleScript execution defaults
        assert config.applescript_timeout == 30.0
        assert config.applescript_retry_count == 3
        assert config.preferred_execution_method == ExecutionMethod.HYBRID
        
        # Cache configuration defaults
        assert config.enable_caching is True
        assert config.cache_max_size == 1000
    
    def test_custom_config_creation(self):
        """Test creating config with custom values."""
        config = ThingsMCPConfig(
            server_name="custom-server",
            server_version="2.0.0",
            applescript_timeout=45.0,
            applescript_retry_count=5,
            enable_caching=False,
            cache_max_size=500,
            preferred_execution_method=ExecutionMethod.URL_SCHEME
        )
        
        assert config.server_name == "custom-server"
        assert config.server_version == "2.0.0"
        assert config.applescript_timeout == 45.0
        assert config.applescript_retry_count == 5
        assert config.enable_caching is False
        assert config.cache_max_size == 500
        assert config.preferred_execution_method == ExecutionMethod.URL_SCHEME


class TestExecutionMethodEnum:
    """Test ExecutionMethod enum values."""
    
    def test_execution_method_values(self):
        """Test all ExecutionMethod enum values."""
        assert ExecutionMethod.URL_SCHEME == "url_scheme"
        assert ExecutionMethod.APPLESCRIPT == "applescript"
        assert ExecutionMethod.HYBRID == "hybrid"
    
    def test_execution_method_usage_in_config(self):
        """Test using ExecutionMethod in config."""
        for method in ExecutionMethod:
            config = ThingsMCPConfig(preferred_execution_method=method)
            assert config.preferred_execution_method == method


class TestLogLevelEnum:
    """Test LogLevel enum values."""
    
    def test_log_level_values(self):
        """Test all LogLevel enum values."""
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.CRITICAL == "CRITICAL"


class TestTagCreationPolicyEnum:
    """Test TagCreationPolicy enum values."""
    
    def test_tag_creation_policy_values(self):
        """Test all TagCreationPolicy enum values."""
        assert TagCreationPolicy.ALLOW_ALL == "allow_all"
        assert TagCreationPolicy.FILTER_SILENT == "filter_silent"
        assert TagCreationPolicy.FILTER_WARN == "filter_warn"
        assert TagCreationPolicy.FAIL_ON_UNKNOWN == "fail_on_unknown"


class TestConfigValidation:
    """Test configuration validation constraints."""
    
    def test_applescript_timeout_validation(self):
        """Test AppleScript timeout validation."""
        # Valid values
        config = ThingsMCPConfig(applescript_timeout=1.0)
        assert config.applescript_timeout == 1.0
        
        config = ThingsMCPConfig(applescript_timeout=300.0)
        assert config.applescript_timeout == 300.0
        
        # Test boundary values
        with pytest.raises(Exception):
            ThingsMCPConfig(applescript_timeout=0.5)  # Below minimum
            
        with pytest.raises(Exception):
            ThingsMCPConfig(applescript_timeout=301.0)  # Above maximum
    
    def test_retry_count_validation(self):
        """Test retry count validation."""
        # Valid values
        config = ThingsMCPConfig(applescript_retry_count=0)
        assert config.applescript_retry_count == 0
        
        config = ThingsMCPConfig(applescript_retry_count=10)
        assert config.applescript_retry_count == 10
        
        # Test boundary values
        with pytest.raises(Exception):
            ThingsMCPConfig(applescript_retry_count=-1)  # Below minimum
            
        with pytest.raises(Exception):
            ThingsMCPConfig(applescript_retry_count=11)  # Above maximum
    
    def test_cache_max_size_validation(self):
        """Test cache max size validation."""
        # Valid values
        config = ThingsMCPConfig(cache_max_size=10)
        assert config.cache_max_size == 10
        
        config = ThingsMCPConfig(cache_max_size=10000)
        assert config.cache_max_size == 10000
        
        # Test boundary values
        with pytest.raises(Exception):
            ThingsMCPConfig(cache_max_size=9)  # Below minimum


class TestEnvironmentVariables:
    """Test environment variable support."""
    
    @patch.dict(os.environ, {
        'THINGS_MCP_SERVER_NAME': 'env-server',
        'THINGS_MCP_APPLESCRIPT_TIMEOUT': '60.0',
        'THINGS_MCP_ENABLE_CACHING': 'false'
    })
    def test_env_var_support(self):
        """Test configuration from environment variables."""
        config = ThingsMCPConfig()
        
        # These should come from environment variables
        assert config.server_name == 'env-server'
        assert config.applescript_timeout == 60.0
        assert config.enable_caching is False
    
    @patch.dict(os.environ, {
        'THINGS_MCP_PREFERRED_EXECUTION_METHOD': 'applescript'
    })
    def test_enum_env_var_support(self):
        """Test enum values from environment variables."""
        config = ThingsMCPConfig()
        assert config.preferred_execution_method == ExecutionMethod.APPLESCRIPT


class TestConfigParsing:
    """Test configuration parsing and loading."""
    
    def test_config_dict_conversion(self):
        """Test converting config to dict."""
        config = ThingsMCPConfig(
            server_name="test-server",
            applescript_timeout=45.0
        )
        
        config_dict = config.model_dump()
        assert isinstance(config_dict, dict)
        assert config_dict['server_name'] == "test-server"
        assert config_dict['applescript_timeout'] == 45.0
    
    def test_config_json_serialization(self):
        """Test JSON serialization."""
        config = ThingsMCPConfig(server_name="test-server")
        
        json_str = config.model_dump_json()
        assert isinstance(json_str, str)
        assert '"server_name":"test-server"' in json_str or '"server_name": "test-server"' in json_str


class TestConfigEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_string_to_number_coercion(self):
        """Test automatic type coercion."""
        config = ThingsMCPConfig(
            applescript_timeout="45.0",
            applescript_retry_count="5"
        )
        
        assert config.applescript_timeout == 45.0
        assert config.applescript_retry_count == 5
    
    def test_boolean_coercion(self):
        """Test boolean value coercion."""
        # Test various boolean representations
        config = ThingsMCPConfig(enable_caching="false")
        assert config.enable_caching is False
        
        config = ThingsMCPConfig(enable_caching="true")  
        assert config.enable_caching is True
        
        config = ThingsMCPConfig(enable_caching=0)
        assert config.enable_caching is False
        
        config = ThingsMCPConfig(enable_caching=1)
        assert config.enable_caching is True


class TestConfigCompleteFields:
    """Test accessing all config fields for complete coverage."""
    
    def test_all_config_fields_accessible(self):
        """Test that all config fields are accessible and have expected types."""
        config = ThingsMCPConfig()
        
        # Test all fields exist and have proper types
        assert isinstance(config.server_name, str)
        assert isinstance(config.server_version, str)  
        assert isinstance(config.server_description, str)
        assert isinstance(config.applescript_timeout, float)
        assert isinstance(config.applescript_retry_count, int)
        assert isinstance(config.preferred_execution_method, ExecutionMethod)
        assert isinstance(config.enable_caching, bool)
        assert isinstance(config.cache_max_size, int)
    
    def test_config_field_descriptions(self):
        """Test config field descriptions exist."""
        config = ThingsMCPConfig()
        schema = config.model_json_schema()
        
        # Check that key fields have descriptions
        properties = schema.get('properties', {})
        
        assert 'description' in properties.get('server_name', {})
        assert 'description' in properties.get('applescript_timeout', {})
        assert 'description' in properties.get('enable_caching', {})
    
    def test_config_repr_and_str(self):
        """Test config string representations."""
        config = ThingsMCPConfig(server_name="test")
        
        # These should not raise exceptions
        str_repr = str(config)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0
        
        repr_str = repr(config)
        assert isinstance(repr_str, str)
        assert len(repr_str) > 0
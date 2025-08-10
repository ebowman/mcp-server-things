"""
Configuration Management for Things 3 MCP Server

Centralized configuration handling with environment variables,
file-based configuration, and sensible defaults.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import json
import yaml
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings
from pydantic import Field, validator


class ExecutionMethod(str, Enum):
    """Preferred execution method for AppleScript operations"""
    URL_SCHEME = "url_scheme"
    APPLESCRIPT = "applescript"
    HYBRID = "hybrid"


class LogLevel(str, Enum):
    """Logging levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class TagCreationPolicy(str, Enum):
    """Tag creation policy for handling unknown tags"""
    ALLOW_ALL = "allow_all"
    FILTER_UNKNOWN = "filter_unknown"
    WARN_UNKNOWN = "warn_unknown"
    REJECT_UNKNOWN = "reject_unknown"


class ThingsMCPConfig(BaseSettings):
    """
    Configuration model for Things 3 MCP Server.
    
    Supports configuration via:
    - Environment variables (prefixed with THINGS_MCP_)
    - Configuration files (JSON/YAML)
    - Default values
    """
    
    # Server configuration
    server_name: str = Field(
        default="things3-mcp-server",
        description="Name of the MCP server"
    )
    
    server_version: str = Field(
        default="1.0.0",
        description="Version of the MCP server"
    )
    
    server_description: str = Field(
        default="MCP server for Things 3 task management integration",
        description="Description of the MCP server"
    )
    
    # AppleScript execution configuration
    applescript_timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Timeout for AppleScript execution in seconds"
    )
    
    applescript_retry_count: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of retries for failed AppleScript operations"
    )
    
    preferred_execution_method: ExecutionMethod = Field(
        default=ExecutionMethod.HYBRID,
        description="Preferred method for executing Things 3 operations"
    )
    
    # Cache configuration
    enable_caching: bool = Field(
        default=True,
        description="Enable response caching"
    )
    
    cache_max_size: int = Field(
        default=1000,
        ge=10,
        le=10000,
        description="Maximum number of items in cache"
    )
    
    cache_default_ttl: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Default TTL for cached items in seconds"
    )
    
    cache_memory_limit: int = Field(
        default=100,  # MB
        ge=10,
        le=1000,
        description="Maximum memory usage for cache in MB"
    )
    
    # Logging configuration
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Logging level"
    )
    
    enable_detailed_logging: bool = Field(
        default=False,
        description="Enable detailed logging including stack traces"
    )
    
    enable_debug_logging: bool = Field(
        default=False,
        description="Enable debug logging"
    )
    
    log_file_path: Optional[Path] = Field(
        default=None,
        description="Path to log file (if None, logs to stdout)"
    )
    
    # Validation configuration
    max_title_length: int = Field(
        default=500,
        ge=50,
        le=1000,
        description="Maximum length for todo/project titles"
    )
    
    max_notes_length: int = Field(
        default=10000,
        ge=100,
        le=50000,
        description="Maximum length for notes"
    )
    
    max_tags_per_item: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Maximum number of tags per item"
    )
    
    max_checklist_items: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of checklist items"
    )
    
    # Performance configuration
    max_concurrent_operations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum concurrent AppleScript operations"
    )
    
    batch_operation_max_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum items in batch operations"
    )
    
    search_results_limit: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Default maximum search results"
    )
    
    # Security configuration
    enable_input_sanitization: bool = Field(
        default=True,
        description="Enable input sanitization for AppleScript"
    )
    
    allowed_hosts: List[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Allowed hosts for server access (JSON array or comma-separated string)"
    )
    
    # Tag management configuration
    tag_creation_policy: TagCreationPolicy = Field(
        default=TagCreationPolicy.ALLOW_ALL,
        description="Policy for handling unknown tags during operations"
    )
    
    tag_policy_strict_mode: bool = Field(
        default=False,
        description="Enable strict mode for tag policy enforcement"
    )
    
    tag_validation_case_sensitive: bool = Field(
        default=False,
        description="Enable case-sensitive tag validation"
    )
    
    max_auto_created_tags_per_operation: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of tags that can be auto-created per operation"
    )
    
    # Feature flags
    enable_experimental_features: bool = Field(
        default=False,
        description="Enable experimental features"
    )
    
    enable_analytics: bool = Field(
        default=True,
        description="Enable analytics and statistics collection"
    )
    
    enable_health_checks: bool = Field(
        default=True,
        description="Enable health check endpoints"
    )
    
    # Things 3 specific configuration
    things_app_name: str = Field(
        default="Things3",
        description="Name of the Things 3 application"
    )
    
    things_url_scheme_base: str = Field(
        default="things:///",
        description="Base URL for Things 3 URL schemes"
    )
    
    verify_things_availability: bool = Field(
        default=True,
        description="Verify Things 3 is available on startup"
    )
    
    # Development configuration
    enable_mock_mode: bool = Field(
        default=False,
        description="Enable mock mode for testing without Things 3"
    )
    
    mock_data_path: Optional[Path] = Field(
        default=None,
        description="Path to mock data file for testing"
    )
    
    @validator('log_file_path', pre=True)
    def validate_log_file_path(cls, v):
        if v is not None:
            return Path(v)
        return v
    
    @validator('mock_data_path', pre=True)
    def validate_mock_data_path(cls, v):
        if v is not None:
            return Path(v)
        return v
    
    @validator('allowed_hosts', pre=True)
    def validate_allowed_hosts(cls, v):
        """Parse allowed_hosts from various formats."""
        if v is None:
            return ["localhost", "127.0.0.1"]
        if isinstance(v, str):
            # Try to parse as JSON array first (for pydantic-settings v2)
            if v.startswith('['):
                try:
                    import json
                    return json.loads(v)
                except:
                    pass
            # Otherwise, split comma-separated string
            return [host.strip() for host in v.split(',') if host.strip()]
        if isinstance(v, list):
            return v
        return ["localhost", "127.0.0.1"]
    
    @validator('preferred_execution_method', pre=True)
    def validate_execution_method(cls, v):
        if isinstance(v, str):
            return ExecutionMethod(v.lower())
        return v
    
    @validator('log_level', pre=True)
    def validate_log_level(cls, v):
        if isinstance(v, str):
            return LogLevel(v.upper())
        return v
    
    @validator('tag_creation_policy', pre=True)
    def validate_tag_creation_policy(cls, v):
        if isinstance(v, str):
            return TagCreationPolicy(v.lower())
        return v
    
    class Config:
        env_prefix = "THINGS_MCP_"
        case_sensitive = False
        
        # Example environment variables:
        # THINGS_MCP_APPLESCRIPT_TIMEOUT=60.0
        # THINGS_MCP_CACHE_MAX_SIZE=2000
        # THINGS_MCP_ENABLE_DEBUG_LOGGING=true
        # THINGS_MCP_ALLOWED_HOSTS=["localhost","127.0.0.1"]  # JSON array format
        # THINGS_MCP_TAG_CREATION_POLICY=allow_all
        # THINGS_MCP_TAG_POLICY_STRICT_MODE=false
        # THINGS_MCP_MAX_AUTO_CREATED_TAGS_PER_OPERATION=10
    
    @classmethod
    def from_file(cls, config_path: Path) -> 'ThingsMCPConfig':
        """
        Load configuration from file.
        
        Args:
            config_path: Path to configuration file (JSON or YAML)
            
        Returns:
            ThingsMCPConfig instance
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file format is invalid
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    config_data = yaml.safe_load(f)
                elif config_path.suffix.lower() == '.json':
                    config_data = json.load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {config_path.suffix}")
            
            return cls(**config_data)
            
        except Exception as e:
            raise ValueError(f"Error loading configuration from {config_path}: {e}")
    
    def to_file(self, config_path: Path, format: str = "yaml"):
        """
        Save configuration to file.
        
        Args:
            config_path: Path to save configuration file
            format: File format ('yaml' or 'json')
        """
        config_data = self.dict()
        
        # Convert Path objects to strings for serialization
        for key, value in config_data.items():
            if isinstance(value, Path):
                config_data[key] = str(value)
        
        with open(config_path, 'w') as f:
            if format.lower() == 'yaml':
                yaml.dump(config_data, f, default_flow_style=False)
            elif format.lower() == 'json':
                json.dump(config_data, f, indent=2)
            else:
                raise ValueError(f"Unsupported format: {format}")
    
    def get_applescript_config(self) -> Dict[str, Any]:
        """Get AppleScript-specific configuration"""
        return {
            "timeout": self.applescript_timeout,
            "retry_count": self.applescript_retry_count,
            "preferred_method": self.preferred_execution_method,
            "app_name": self.things_app_name,
            "enable_sanitization": self.enable_input_sanitization
        }
    
    def get_cache_config(self) -> Dict[str, Any]:
        """Get cache-specific configuration"""
        return {
            "enabled": self.enable_caching,
            "max_size": self.cache_max_size,
            "default_ttl": self.cache_default_ttl,
            "memory_limit": self.cache_memory_limit
        }
    
    def get_validation_config(self) -> Dict[str, Any]:
        """Get validation-specific configuration"""
        return {
            "max_title_length": self.max_title_length,
            "max_notes_length": self.max_notes_length,
            "max_tags_per_item": self.max_tags_per_item,
            "max_checklist_items": self.max_checklist_items
        }
    
    def get_tag_config(self) -> Dict[str, Any]:
        """Get tag management configuration"""
        return {
            "creation_policy": self.tag_creation_policy,
            "strict_mode": self.tag_policy_strict_mode,
            "case_sensitive": self.tag_validation_case_sensitive,
            "max_auto_created_per_operation": self.max_auto_created_tags_per_operation
        }
    
    def is_development_mode(self) -> bool:
        """Check if running in development mode"""
        return (
            self.enable_debug_logging or 
            self.enable_mock_mode or 
            self.enable_experimental_features
        )
    
    def validate_environment(self) -> List[str]:
        """
        Validate the current environment and configuration.
        
        Returns:
            List of validation warnings/errors
        """
        issues = []
        
        # Check Things 3 availability if not in mock mode
        if not self.enable_mock_mode and self.verify_things_availability:
            try:
                import subprocess
                result = subprocess.run(
                    ['osascript', '-e', f'tell application "{self.things_app_name}" to return version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode != 0:
                    issues.append(f"Things 3 not accessible: {result.stderr}")
            except Exception as e:
                issues.append(f"Could not verify Things 3 availability: {e}")
        
        # Check log file path
        if self.log_file_path:
            log_dir = self.log_file_path.parent
            if not log_dir.exists():
                issues.append(f"Log directory does not exist: {log_dir}")
            elif not os.access(log_dir, os.W_OK):
                issues.append(f"Log directory is not writable: {log_dir}")
        
        # Check mock data path
        if self.enable_mock_mode and self.mock_data_path:
            if not self.mock_data_path.exists():
                issues.append(f"Mock data file not found: {self.mock_data_path}")
        
        # Performance warnings
        if self.cache_max_size > 5000:
            issues.append("Large cache size may impact memory usage")
        
        if self.max_concurrent_operations > 20:
            issues.append("High concurrent operation limit may overwhelm system")
        
        return issues


# Environment-specific configurations
class DevelopmentConfig(ThingsMCPConfig):
    """Development environment configuration"""
    
    enable_debug_logging: bool = True
    enable_detailed_logging: bool = True
    cache_default_ttl: int = 60  # Shorter TTL for development
    enable_experimental_features: bool = True
    log_level: LogLevel = LogLevel.DEBUG


class ProductionConfig(ThingsMCPConfig):
    """Production environment configuration"""
    
    enable_debug_logging: bool = False
    enable_detailed_logging: bool = False
    applescript_timeout: float = 60.0  # Longer timeout for production
    cache_max_size: int = 2000  # Larger cache for production
    log_level: LogLevel = LogLevel.INFO


class TestingConfig(ThingsMCPConfig):
    """Testing environment configuration"""
    
    enable_mock_mode: bool = True
    enable_caching: bool = False  # Disable caching for consistent tests
    applescript_timeout: float = 5.0  # Short timeout for tests
    verify_things_availability: bool = False
    log_level: LogLevel = LogLevel.WARNING


# Configuration factory
def get_config(environment: str = "development") -> ThingsMCPConfig:
    """
    Get configuration for specific environment.
    
    Args:
        environment: Environment name (development, production, testing)
        
    Returns:
        Appropriate configuration instance
    """
    env_configs = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig
    }
    
    config_class = env_configs.get(environment.lower(), ThingsMCPConfig)
    return config_class()


# Configuration utilities
def load_config_from_env() -> ThingsMCPConfig:
    """Load configuration from environment variables"""
    return ThingsMCPConfig()


def create_default_config_file(config_path: Path, environment: str = "development"):
    """
    Create a default configuration file.
    
    Args:
        config_path: Path where to create the config file
        environment: Environment type for defaults
    """
    config = get_config(environment)
    config.to_file(config_path, format="yaml")


# Configuration validation
def validate_config(config: ThingsMCPConfig) -> bool:
    """
    Validate configuration and environment.
    
    Args:
        config: Configuration to validate
        
    Returns:
        True if valid, False otherwise
    """
    issues = config.validate_environment()
    
    if issues:
        print("Configuration issues found:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    
    return True
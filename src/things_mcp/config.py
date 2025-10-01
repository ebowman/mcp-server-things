"""
Configuration Management for Things 3 MCP Server

Centralized configuration handling with environment variables,
file-based configuration, and sensible defaults.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings
from pydantic import Field, field_validator, ConfigDict


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
    """Tag creation policy for handling unknown tags - clear, self-contained behaviors"""
    ALLOW_ALL = "allow_all"              # Create any new tags automatically
    FILTER_SILENT = "filter_silent"      # Remove unknown tags silently, continue operation
    FILTER_WARN = "filter_warn"          # Remove unknown tags with warnings, continue operation
    FAIL_ON_UNKNOWN = "fail_on_unknown"  # Reject entire operation if any unknown tags


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
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    
    log_file_path: Optional[Path] = Field(
        default=None,
        description="Path to log file (if None, logs to console only)"
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
    ai_can_create_tags: bool = Field(
        default=False,
        description="Whether AI assistants can create new tags (false = human-only tag creation)"
    )
    
    # Keep legacy field for backward compatibility but map to new simplified model
    tag_creation_policy: TagCreationPolicy = Field(
        default=TagCreationPolicy.FAIL_ON_UNKNOWN,
        description="[DEPRECATED - use ai_can_create_tags] Policy for handling unknown tags"
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

    use_new_applescript_parser: bool = Field(
        default=False,
        description="Use new state machine parser for AppleScript output (experimental)"
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
    
    @field_validator('log_file_path', mode='before')
    @classmethod
    def validate_log_file_path(cls, v):
        if v is not None:
            return Path(v)
        return v
    
    @field_validator('mock_data_path', mode='before')
    @classmethod
    def validate_mock_data_path(cls, v):
        if v is not None:
            return Path(v)
        return v
    
    @field_validator('allowed_hosts', mode='before')
    @classmethod
    def validate_allowed_hosts(cls, v):
        """Parse allowed_hosts from various formats."""
        if v is None:
            return ["localhost", "127.0.0.1"]
        if isinstance(v, str):
            # Try to parse as JSON array first
            if v.startswith('['):
                try:
                    import json
                    return json.loads(v)
                except json.JSONDecodeError as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to parse JSON value for allowed_hosts: {v[:100]}... Error: {e}")
                    pass  # Fall through to comma-separated parsing
            # Otherwise, split comma-separated string
            return [host.strip() for host in v.split(',') if host.strip()]
        if isinstance(v, list):
            return v
        return ["localhost", "127.0.0.1"]
    
    @field_validator('preferred_execution_method', mode='before')
    @classmethod
    def validate_execution_method(cls, v):
        if isinstance(v, str):
            return ExecutionMethod(v.lower())
        return v
    
    @field_validator('log_level', mode='before')
    @classmethod
    def validate_log_level(cls, v):
        if isinstance(v, str):
            return LogLevel(v.upper())
        return v
    
    @field_validator('tag_creation_policy', mode='before')
    @classmethod
    def validate_tag_creation_policy(cls, v, info):
        """Sync tag policy with ai_can_create_tags setting."""
        # If ai_can_create_tags is explicitly set, use it to determine policy
        if info.data and 'ai_can_create_tags' in info.data:
            if info.data['ai_can_create_tags']:
                return TagCreationPolicy.ALLOW_ALL
            else:
                # Use FILTER_WARN for better AI guidance
                return TagCreationPolicy.FILTER_WARN
        
        # Otherwise parse from string with backward compatibility
        if isinstance(v, str):
            v_lower = v.lower()
            # Map old names to new ones for backward compatibility
            compatibility_map = {
                'filter_unknown': 'filter_warn',     # Old filter_unknown becomes filter_warn
                'reject_unknown': 'fail_on_unknown', # Old reject_unknown becomes fail_on_unknown
                'warn_unknown': 'allow_all',         # Old warn_unknown actually created tags
            }
            v_lower = compatibility_map.get(v_lower, v_lower)
            return TagCreationPolicy(v_lower)
        return v
    
    @field_validator('ai_can_create_tags', mode='before')
    @classmethod
    def set_ai_can_create_tags_from_policy(cls, v, info):
        """Set ai_can_create_tags based on policy if not explicitly set."""
        # If explicitly set, use that value
        if v is not None:
            return v
        
        # Otherwise derive from tag_creation_policy if present
        if info.data and 'tag_creation_policy' in info.data:
            policy = info.data['tag_creation_policy']
            if isinstance(policy, str):
                policy = policy.lower()
            # Only ALLOW_ALL means AI can create tags
            return policy == TagCreationPolicy.ALLOW_ALL or policy == 'allow_all'
        
        # Default to False (human-only)
        return False
    
    model_config = ConfigDict(
        env_prefix="THINGS_MCP_",
        case_sensitive=False,
        # Example environment variables (in .env file or system):
        # THINGS_MCP_APPLESCRIPT_TIMEOUT=60.0
        # THINGS_MCP_CACHE_MAX_SIZE=2000
        # THINGS_MCP_LOG_LEVEL=DEBUG
    )
        # THINGS_MCP_LOG_FILE_PATH=/var/log/things-mcp.log
        # THINGS_MCP_AI_CAN_CREATE_TAGS=true
        # THINGS_MCP_MAX_AUTO_CREATED_TAGS_PER_OPERATION=10
    
    @classmethod
    def from_env_file(cls, env_path: Optional[Path] = None) -> 'ThingsMCPConfig':
        """
        Load configuration from environment variables and optional .env file.
        
        Args:
            env_path: Optional path to .env file. If not provided, looks for .env in current directory.
            
        Returns:
            ThingsMCPConfig instance
        """
        # Load from .env file if specified or if default .env exists
        if env_path:
            if not env_path.exists():
                raise FileNotFoundError(f".env file not found: {env_path}")
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path, override=True)
            except ImportError:
                import logging
                logging.getLogger(__name__).warning(
                    "python-dotenv not installed. Install it to use .env files: pip install python-dotenv"
                )
        else:
            # Look for default .env file in current directory
            default_env = Path(".env")
            if default_env.exists():
                try:
                    from dotenv import load_dotenv
                    load_dotenv(default_env, override=True)
                    import logging
                    logging.getLogger(__name__).info(f"Loaded default .env file from {default_env.absolute()}")
                except ImportError:
                    import logging
                    logging.getLogger(__name__).warning(
                        "python-dotenv not installed. Install it to use .env files: pip install python-dotenv"
                    )
        
        # Create config from environment variables
        return cls()
    
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
            "case_sensitive": self.tag_validation_case_sensitive,
            "max_auto_created_per_operation": self.max_auto_created_tags_per_operation
        }
    
    def is_development_mode(self) -> bool:
        """Check if running in development mode"""
        return (
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
    
    cache_default_ttl: int = 60  # Shorter TTL for development
    enable_experimental_features: bool = True
    log_level: LogLevel = LogLevel.DEBUG


class ProductionConfig(ThingsMCPConfig):
    """Production environment configuration"""
    
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
def load_config_from_env(env_file: Optional[Path] = None) -> ThingsMCPConfig:
    """
    Load configuration from environment variables and optional .env file.
    
    Args:
        env_file: Optional path to .env file
        
    Returns:
        ThingsMCPConfig instance
    """
    return ThingsMCPConfig.from_env_file(env_file)


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
"""
Comprehensive Error Handling Service

Provides centralized error handling for AppleScript operations, system errors,
and business logic errors with categorization, logging, and user-friendly messages.
"""

import logging
import traceback
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

from ..models.response_models import AppleScriptResult, ErrorDetails, OperationResult


class ErrorCategory(str, Enum):
    """Categories of errors that can occur"""
    APPLESCRIPT_ERROR = "applescript_error"
    PERMISSION_ERROR = "permission_error"
    VALIDATION_ERROR = "validation_error"
    SYSTEM_ERROR = "system_error"
    TIMEOUT_ERROR = "timeout_error"
    NETWORK_ERROR = "network_error"
    THINGS_ERROR = "things_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """Context information for error handling"""
    operation: str
    parameters: Dict[str, Any]
    timestamp: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    retry_count: int = 0


class ErrorHandler:
    """
    Centralized error handling service for Things 3 MCP operations.
    
    Provides:
    - Error categorization and severity assessment
    - User-friendly error messages
    - Logging and monitoring integration
    - Recovery suggestions
    - Error statistics and reporting
    """
    
    def __init__(self, enable_detailed_logging: bool = True):
        self.logger = logging.getLogger(__name__)
        self.enable_detailed_logging = enable_detailed_logging
        
        # Error statistics
        self.error_stats = {
            category.value: 0 for category in ErrorCategory
        }
        
        # Common error patterns and their mappings
        self.applescript_error_patterns = {
            "execution error": ErrorCategory.APPLESCRIPT_ERROR,
            "access denied": ErrorCategory.PERMISSION_ERROR,
            "timeout": ErrorCategory.TIMEOUT_ERROR,
            "application not found": ErrorCategory.SYSTEM_ERROR,
            "file not found": ErrorCategory.SYSTEM_ERROR,
            "network": ErrorCategory.NETWORK_ERROR,
        }
        
        # User-friendly error messages
        self.error_messages = {
            ErrorCategory.APPLESCRIPT_ERROR: {
                "title": "AppleScript Execution Failed",
                "message": "There was an error executing the AppleScript command.",
                "suggestions": [
                    "Ensure Things 3 is running and accessible",
                    "Check if the requested item exists",
                    "Verify the operation parameters are correct"
                ]
            },
            ErrorCategory.PERMISSION_ERROR: {
                "title": "Permission Denied",
                "message": "The application doesn't have permission to control Things 3.",
                "suggestions": [
                    "Go to System Preferences > Security & Privacy > Privacy",
                    "Select 'Accessibility' from the list",
                    "Add this application and enable access",
                    "Restart the application after granting permissions"
                ]
            },
            ErrorCategory.VALIDATION_ERROR: {
                "title": "Invalid Input",
                "message": "The provided input parameters are invalid.",
                "suggestions": [
                    "Check that all required fields are provided",
                    "Verify date formats are correct (YYYY-MM-DD)",
                    "Ensure text fields don't exceed maximum length",
                    "Check that referenced projects/areas exist"
                ]
            },
            ErrorCategory.SYSTEM_ERROR: {
                "title": "System Error",
                "message": "A system-level error occurred.",
                "suggestions": [
                    "Ensure Things 3 is installed and running",
                    "Check system resources (memory, disk space)",
                    "Restart Things 3 if the problem persists",
                    "Contact support if the error continues"
                ]
            },
            ErrorCategory.TIMEOUT_ERROR: {
                "title": "Operation Timeout",
                "message": "The operation took too long to complete.",
                "suggestions": [
                    "Try the operation again",
                    "Check if Things 3 is responding",
                    "Reduce the scope of the operation if possible",
                    "Ensure system is not under heavy load"
                ]
            },
            ErrorCategory.THINGS_ERROR: {
                "title": "Things 3 Error",
                "message": "Things 3 reported an error during the operation.",
                "suggestions": [
                    "Check if the item you're trying to access exists",
                    "Verify Things 3 database is not corrupted",
                    "Try restarting Things 3",
                    "Check Things 3 logs for more details"
                ]
            }
        }
    
    async def handle_execution_error(
        self,
        error: Exception,
        operation: str,
        context: Dict[str, Any],
        retry_count: int = 0
    ) -> AppleScriptResult:
        """
        Handle AppleScript execution errors with comprehensive analysis.
        
        Args:
            error: The exception that occurred
            operation: Name of the operation that failed
            context: Context information about the operation
            retry_count: Number of retries attempted
            
        Returns:
            AppleScriptResult with error details and recovery information
        """
        error_context = ErrorContext(
            operation=operation,
            parameters=context,
            timestamp=datetime.now(),
            retry_count=retry_count
        )
        
        # Categorize the error
        category = self._categorize_error(error)
        severity = self._assess_severity(error, category)
        
        # Generate error details
        error_details = await self._generate_error_details(
            error, category, severity, error_context
        )
        
        # Log the error
        await self._log_error(error, error_details, error_context)
        
        # Update statistics
        self.error_stats[category.value] += 1
        
        # Create result with recovery information
        result = AppleScriptResult(
            success=False,
            error=str(error),
            error_category=category.value,
            error_severity=severity.value,
            error_details=error_details,
            recovery_suggestions=self._get_recovery_suggestions(category),
            timestamp=error_context.timestamp,
            context=context
        )
        
        return result
    
    async def handle_validation_error(
        self,
        validation_errors: List[str],
        operation: str,
        parameters: Dict[str, Any]
    ) -> OperationResult:
        """
        Handle validation errors with detailed field-level information.
        
        Args:
            validation_errors: List of validation error messages
            operation: Operation that failed validation
            parameters: Parameters that failed validation
            
        Returns:
            OperationResult with validation error details
        """
        error_details = ErrorDetails(
            category=ErrorCategory.VALIDATION_ERROR.value,
            severity=ErrorSeverity.MEDIUM.value,
            message="Input validation failed",
            field_errors=validation_errors,
            timestamp=datetime.now(),
            operation=operation
        )
        
        # Log validation error
        self.logger.warning(
            f"Validation failed for operation '{operation}': {validation_errors}",
            extra={
                "operation": operation,
                "parameters": parameters,
                "errors": validation_errors
            }
        )
        
        self.error_stats[ErrorCategory.VALIDATION_ERROR.value] += 1
        
        return OperationResult(
            success=False,
            error=ErrorCategory.VALIDATION_ERROR.value,
            message="Input validation failed",
            details={
                "validation_errors": validation_errors,
                "parameters": parameters,
                "suggestions": self._get_recovery_suggestions(ErrorCategory.VALIDATION_ERROR)
            }
        )
    
    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """
        Categorize an error based on its type and message.
        
        Args:
            error: The exception to categorize
            
        Returns:
            ErrorCategory enum value
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Check for specific error types
        if "permission" in error_str or "access denied" in error_str:
            return ErrorCategory.PERMISSION_ERROR
        elif "timeout" in error_str or "timed out" in error_str:
            return ErrorCategory.TIMEOUT_ERROR
        elif "validation" in error_str or "invalid" in error_str:
            return ErrorCategory.VALIDATION_ERROR
        elif "network" in error_str or "connection" in error_str:
            return ErrorCategory.NETWORK_ERROR
        elif "applescript" in error_str or "osascript" in error_str:
            return ErrorCategory.APPLESCRIPT_ERROR
        elif "things" in error_str:
            return ErrorCategory.THINGS_ERROR
        elif "system" in error_str or "os" in error_str:
            return ErrorCategory.SYSTEM_ERROR
        
        # Check error patterns
        for pattern, category in self.applescript_error_patterns.items():
            if pattern in error_str:
                return category
        
        # Default to unknown error
        return ErrorCategory.UNKNOWN_ERROR
    
    def _assess_severity(self, error: Exception, category: ErrorCategory) -> ErrorSeverity:
        """
        Assess the severity of an error.
        
        Args:
            error: The exception
            category: Categorized error type
            
        Returns:
            ErrorSeverity enum value
        """
        # High severity errors
        if category in [ErrorCategory.PERMISSION_ERROR, ErrorCategory.SYSTEM_ERROR]:
            return ErrorSeverity.HIGH
        
        # Medium severity errors
        if category in [ErrorCategory.APPLESCRIPT_ERROR, ErrorCategory.THINGS_ERROR]:
            return ErrorSeverity.MEDIUM
        
        # Low severity errors
        if category in [ErrorCategory.VALIDATION_ERROR, ErrorCategory.TIMEOUT_ERROR]:
            return ErrorSeverity.LOW
        
        # Critical errors (data corruption, etc.)
        if "corrupt" in str(error).lower() or "critical" in str(error).lower():
            return ErrorSeverity.CRITICAL
        
        return ErrorSeverity.MEDIUM
    
    async def _generate_error_details(
        self,
        error: Exception,
        category: ErrorCategory,
        severity: ErrorSeverity,
        context: ErrorContext
    ) -> ErrorDetails:
        """
        Generate comprehensive error details.
        
        Args:
            error: The original exception
            category: Error category
            severity: Error severity
            context: Error context
            
        Returns:
            ErrorDetails object with comprehensive information
        """
        error_info = self.error_messages.get(category, {
            "title": "Unknown Error",
            "message": "An unexpected error occurred.",
            "suggestions": ["Try the operation again", "Contact support if the problem persists"]
        })
        
        return ErrorDetails(
            category=category.value,
            severity=severity.value,
            title=error_info["title"],
            message=error_info["message"],
            technical_details=str(error),
            suggestions=error_info["suggestions"],
            timestamp=context.timestamp,
            operation=context.operation,
            parameters=context.parameters,
            retry_count=context.retry_count,
            stack_trace=traceback.format_exc() if self.enable_detailed_logging else None
        )
    
    async def _log_error(
        self,
        error: Exception,
        error_details: ErrorDetails,
        context: ErrorContext
    ):
        """
        Log error with appropriate level and context.
        
        Args:
            error: Original exception
            error_details: Processed error details
            context: Error context
        """
        log_data = {
            "operation": context.operation,
            "category": error_details.category,
            "severity": error_details.severity,
            "parameters": context.parameters,
            "retry_count": context.retry_count
        }
        
        if error_details.severity == ErrorSeverity.CRITICAL.value:
            self.logger.critical(f"Critical error in {context.operation}: {error}", extra=log_data)
        elif error_details.severity == ErrorSeverity.HIGH.value:
            self.logger.error(f"High severity error in {context.operation}: {error}", extra=log_data)
        elif error_details.severity == ErrorSeverity.MEDIUM.value:
            self.logger.warning(f"Error in {context.operation}: {error}", extra=log_data)
        else:
            self.logger.info(f"Low severity error in {context.operation}: {error}", extra=log_data)
    
    def _get_recovery_suggestions(self, category: ErrorCategory) -> List[str]:
        """
        Get recovery suggestions for a specific error category.
        
        Args:
            category: Error category
            
        Returns:
            List of recovery suggestions
        """
        return self.error_messages.get(category, {}).get("suggestions", [
            "Try the operation again",
            "Contact support if the problem persists"
        ])
    
    async def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get error statistics for monitoring and debugging.
        
        Returns:
            Dictionary with error statistics
        """
        total_errors = sum(self.error_stats.values())
        
        return {
            "total_errors": total_errors,
            "error_breakdown": self.error_stats.copy(),
            "error_rates": {
                category: (count / max(1, total_errors)) * 100
                for category, count in self.error_stats.items()
            },
            "most_common_error": max(self.error_stats.items(), key=lambda x: x[1])[0] if total_errors > 0 else None
        }
    
    async def reset_statistics(self):
        """Reset error statistics."""
        self.error_stats = {category.value: 0 for category in ErrorCategory}
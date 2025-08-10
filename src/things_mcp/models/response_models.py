"""Response models for AppleScript operations."""

from typing import Any, Dict, Optional, List
from dataclasses import dataclass


@dataclass
class ErrorDetails:
    """Details about an error that occurred."""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class AppleScriptResult:
    """Result from an AppleScript operation."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_details: Optional[ErrorDetails] = None
    execution_time: Optional[float] = None


@dataclass
class OperationResult:
    """Result from a complex operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    warnings: List[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.metadata is None:
            self.metadata = {}
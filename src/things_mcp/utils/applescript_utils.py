"""AppleScript utilities and templates."""

from typing import Dict, Any


class AppleScriptTemplates:
    """Templates and utilities for AppleScript generation."""
    
    @staticmethod
    def escape_string(text: str) -> str:
        """Escape a string for safe use in AppleScript.
        
        Args:
            text: Text to escape
            
        Returns:
            Escaped text safe for AppleScript
        """
        if not text:
            return '""'
        
        # Escape quotes and backslashes
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    
    @staticmethod
    def build_property_dict(properties: Dict[str, Any]) -> str:
        """Build AppleScript properties dictionary.
        
        Args:
            properties: Dictionary of properties
            
        Returns:
            AppleScript properties string
        """
        if not properties:
            return "{}"
        
        props = []
        for key, value in properties.items():
            if isinstance(value, str):
                value = AppleScriptTemplates.escape_string(value)
            elif isinstance(value, bool):
                value = "true" if value else "false"
            elif value is None:
                continue  # Skip null values
            
            props.append(f"{key}:{value}")
        
        return "{" + ", ".join(props) + "}"
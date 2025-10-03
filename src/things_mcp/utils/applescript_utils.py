"""AppleScript utilities and templates."""

from typing import Dict, Any


class AppleScriptTemplates:
    """Templates and utilities for AppleScript generation."""

    @staticmethod
    def escape_string(text: str) -> str:
        """Escape a string for safe use in AppleScript.

        Protects against injection attacks by:
        - Escaping backslashes and quotes (order matters!)
        - Replacing newlines/carriage returns (main injection vector)
        - Removing other control characters

        Args:
            text: Text to escape

        Returns:
            Safely escaped text wrapped in quotes
        """
        if not text:
            return '""'

        # CRITICAL: Escape backslashes FIRST, then quotes
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')

        # Replace control characters that could break string context
        # Newlines (\n) and carriage returns (\r) are the primary injection vectors
        escaped = (escaped
                   .replace('\n', ' ')     # newline → space
                   .replace('\r', ' ')     # carriage return → space
                   .replace('\t', '    '))  # tab → 4 spaces

        # Remove any remaining control characters (ASCII 0-31)
        escaped = ''.join(c for c in escaped if ord(c) >= 32)

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
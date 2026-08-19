"""AppleScript utilities and templates."""

from typing import Dict, Any


class AppleScriptTemplates:
    """Templates and utilities for AppleScript generation."""

    @staticmethod
    def escape_string_inner(text: str) -> str:
        """Escape a string for safe embedding inside an AppleScript string literal.

        This is the single source of truth for AppleScript string escaping.
        It does NOT add the surrounding quotes - callers that need a full
        string literal should use `escape_string()` instead; callers that
        need to embed the escaped text inside a larger literal (e.g.
        `"...text contains " & escaped & "..."`, or building a value that
        will itself be wrapped in quotes later) should use this method
        directly so they never need to re-process (e.g. `.strip('"')`) an
        already-quoted result.

        Protects against injection attacks by:
        - Escaping backslashes and quotes (order matters!)
        - Escaping newlines/carriage returns/tabs to their AppleScript
          literal escape sequences (\\n, \\r, \\t) so they survive inside a
          double-quoted literal instead of being collapsed to spaces
        - Removing other control characters

        Args:
            text: Text to escape

        Returns:
            Escaped text, NOT wrapped in quotes
        """
        if not text:
            return ''

        # CRITICAL: Escape backslashes FIRST, then quotes
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')

        # Map newlines/carriage returns/tabs to their AppleScript escape
        # sequences so a double-quoted literal can carry them verbatim
        # (AppleScript interprets \n, \r, \t inside a quoted string).
        escaped = (escaped
                   .replace('\n', '\\n')
                   .replace('\r', '\\r')
                   .replace('\t', '\\t'))

        # Remove any remaining control characters (ASCII 0-31)
        escaped = ''.join(c for c in escaped if ord(c) >= 32)

        return escaped

    @staticmethod
    def escape_string(text: str) -> str:
        """Escape a string for safe use in AppleScript.

        Delegates to `escape_string_inner()` for the escaping logic and
        wraps the result in double quotes, producing a complete AppleScript
        string literal.

        Args:
            text: Text to escape

        Returns:
            Safely escaped text wrapped in quotes
        """
        if not text:
            return '""'

        return f'"{AppleScriptTemplates.escape_string_inner(text)}"'
    
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
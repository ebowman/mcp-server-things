"""
Tag Validation Service for Things 3 MCP Server

Provides advanced tag validation and policy enforcement capabilities,
including filtering, creation policies, and tag management operations.
"""

import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass

from .applescript_manager import AppleScriptManager
from ..config import ThingsMCPConfig, TagCreationPolicy

logger = logging.getLogger(__name__)


@dataclass
class TagValidationResult:
    """Result of tag validation operation."""
    valid_tags: List[str]
    filtered_tags: List[str]
    created_tags: List[str]
    warnings: List[str]
    errors: List[str]


class TagValidationService:
    """Service for tag validation and policy enforcement."""
    
    def __init__(self, applescript_manager: AppleScriptManager, config: ThingsMCPConfig):
        """Initialize tag validation service.
        
        Args:
            applescript_manager: AppleScript manager instance
            config: MCP configuration with tag policy settings
        """
        self.applescript = applescript_manager
        self.config = config
        self._existing_tags_cache: Optional[Set[str]] = None
        
    async def validate_and_filter_tags(self, tags: List[str]) -> TagValidationResult:
        """Main validation method that applies configured tag policies.
        
        Args:
            tags: List of tag names to validate
            
        Returns:
            TagValidationResult with processed tags and metadata
        """
        if not tags:
            return TagValidationResult(
                valid_tags=[],
                filtered_tags=[],
                created_tags=[],
                warnings=[],
                errors=[]
            )
        
        # Remove duplicates while preserving order
        unique_tags = list(dict.fromkeys(tags))
        
        # Check limits
        max_tags = self.config.max_tags_per_item
        if len(unique_tags) > max_tags:
            return TagValidationResult(
                valid_tags=[],
                filtered_tags=unique_tags,
                created_tags=[],
                warnings=[],
                errors=[f"Too many tags provided ({len(unique_tags)}). Maximum allowed: {max_tags}"]
            )
        
        # Get existing tags
        try:
            existing_tags = await self._get_existing_tags()
        except Exception as e:
            logger.error(f"Failed to get existing tags: {e}")
            # Continue with empty set if we can't fetch existing tags
            existing_tags = set()
        
        # Apply policy
        return await self._apply_policy(unique_tags, existing_tags)
    
    async def _get_existing_tags(self) -> Set[str]:
        """Get current tags from Things 3.
        
        Returns:
            Set of existing tag names (preserving original case)
        """
        try:
            script = '''
            tell application "Things3"
                set AppleScript's text item delimiters to "|DELIMITER|"
                set tagList to {}
                repeat with theTag in tags
                    set end of tagList to name of theTag
                end repeat
                set tagString to tagList as text
                set AppleScript's text item delimiters to ""
                return tagString
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, cache_key="all_tags")
            
            if result.get("success"):
                output = result.get("output", "")
                
                # Parse the delimited string
                if isinstance(output, str) and output:
                    # Split by our delimiter
                    if "|DELIMITER|" in output:
                        tag_names = output.split("|DELIMITER|")
                    else:
                        # Fallback: might be a single tag
                        tag_names = [output] if output else []
                elif isinstance(output, list):
                    # Already a list (shouldn't happen with our script but handle it)
                    tag_names = output
                else:
                    logger.warning(f"Unexpected tag format from AppleScript: {type(output)}")
                    tag_names = []
                
                # Clean up any empty strings
                tag_names = [tag.strip() for tag in tag_names if tag.strip()]
                
                logger.info(f"Found {len(tag_names)} existing tags in Things 3")
                if tag_names:
                    logger.debug(f"Sample tags: {tag_names[:5]}")
                
                # Always return original tag names, case handling will be done during comparison
                return set(tag_names)
            else:
                logger.error(f"Failed to get existing tags: {result.get('error')}")
                return set()
                
        except Exception as e:
            logger.error(f"Error getting existing tags: {e}")
            return set()
    
    async def _apply_policy(self, tags: List[str], existing_tags: Set[str]) -> TagValidationResult:
        """Apply the configured policy to tag validation.
        
        Args:
            tags: List of tags to process
            existing_tags: Set of existing tag names
            
        Returns:
            TagValidationResult with policy-applied results
        """
        result = TagValidationResult(
            valid_tags=[],
            filtered_tags=[],
            created_tags=[],
            warnings=[],
            errors=[]
        )
        
        policy = self.config.tag_creation_policy
        case_sensitive = self.config.tag_validation_case_sensitive
        max_auto_created = self.config.max_auto_created_tags_per_operation
        
        unknown_tags = []
        known_tags = []
        
        # Create a lookup map for case-insensitive matching if needed
        if not case_sensitive:
            # Map lowercase tag names to original names for case-insensitive comparison
            existing_tags_lower = {tag.lower() for tag in existing_tags}
        
        # Categorize tags
        for tag in tags:
            found = False
            if case_sensitive:
                # Case-sensitive: exact match required
                if tag in existing_tags:
                    known_tags.append(tag)
                    found = True
            else:
                # Case-insensitive: check lowercase version
                if tag.lower() in existing_tags_lower:
                    known_tags.append(tag)
                    found = True
            
            if not found:
                unknown_tags.append(tag)
        
        # Always include known tags
        result.valid_tags.extend(known_tags)
        
        # Handle unknown tags based on policy
        if policy == TagCreationPolicy.ALLOW_ALL:
            # Create all unknown tags up to limit
            tags_to_create = unknown_tags[:max_auto_created]
            result.valid_tags.extend(tags_to_create)
            result.created_tags.extend(tags_to_create)
            
            if len(unknown_tags) > max_auto_created:
                excess_tags = unknown_tags[max_auto_created:]
                result.filtered_tags.extend(excess_tags)
                result.warnings.append(
                    f"Auto-creation limit reached. Created {max_auto_created} tags, "
                    f"filtered {len(excess_tags)} additional unknown tags: {', '.join(excess_tags)}"
                )
            elif tags_to_create:
                result.warnings.append(f"Created new tags: {', '.join(tags_to_create)}")
        
        elif policy == TagCreationPolicy.FILTER_SILENT:
            # Filter out unknown tags silently (no warnings)
            result.filtered_tags.extend(unknown_tags)
            # Silent means no warnings
        
        elif policy == TagCreationPolicy.FILTER_WARN:
            # Filter out unknown tags with warnings
            result.filtered_tags.extend(unknown_tags)
            if unknown_tags:
                result.warnings.append(
                    f"Filtered unknown tags: {', '.join(unknown_tags)}. "
                    f"Only existing tags will be applied."
                )
        
        elif policy == TagCreationPolicy.FAIL_ON_UNKNOWN:
            # Fail the entire operation if any unknown tags
            if unknown_tags:
                error_msg = (
                    f"Operation rejected due to unknown tags: {', '.join(unknown_tags)}. "
                    f"Please create these tags first or change tag policy to allow/filter."
                )
                result.errors.append(error_msg)
                result.filtered_tags.extend(unknown_tags)
        
        return result
    
    async def create_tags(self, tag_names: List[str]) -> Dict[str, Any]:
        """Create new tags in Things 3.
        
        Args:
            tag_names: List of tag names to create
            
        Returns:
            Dict with creation results and any errors
        """
        if not tag_names:
            return {"created": [], "errors": []}
        
        created_tags = []
        errors = []
        
        try:
            # Create tags one by one as Things 3 doesn't support batch tag creation
            for tag_name in tag_names:
                try:
                    escaped_name = self._escape_applescript_string(tag_name)
                    script = f'''
                    tell application "Things3"
                        try
                            make new tag with properties {{name:{escaped_name}}}
                            return "CREATED"
                        on error errorMsg
                            return "ERROR: " & errorMsg
                        end try
                    end tell
                    '''
                    
                    result = await self.applescript.execute_applescript(script, cache_key=None)
                    
                    if result.get("success") and result.get("output") == "CREATED":
                        created_tags.append(tag_name)
                        logger.info(f"Created tag: {tag_name}")
                    else:
                        error_msg = result.get("output", "Unknown error")
                        if "ERROR:" in error_msg:
                            error_msg = error_msg.replace("ERROR: ", "")
                        errors.append(f"Failed to create tag '{tag_name}': {error_msg}")
                        logger.error(f"Failed to create tag '{tag_name}': {error_msg}")
                
                except Exception as e:
                    errors.append(f"Exception creating tag '{tag_name}': {str(e)}")
                    logger.error(f"Exception creating tag '{tag_name}': {e}")
            
            # Clear cache if we created any tags
            if created_tags:
                self._existing_tags_cache = None
                # Clear AppleScript manager cache for tag-related queries
                if hasattr(self.applescript, 'clear_cache_pattern'):
                    await self.applescript.clear_cache_pattern("*tags*")
            
            return {"created": created_tags, "errors": errors}
        
        except Exception as e:
            logger.error(f"Error in tag creation batch: {e}")
            return {"created": created_tags, "errors": errors + [f"Batch creation error: {str(e)}"]}
    
    def _escape_applescript_string(self, text: str) -> str:
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
    
    def clear_cache(self):
        """Clear the existing tags cache."""
        self._existing_tags_cache = None
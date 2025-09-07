"""
Response optimization utilities for Things MCP Server.

This module provides field standardization, deduplication, and optimization
to reduce response sizes by 30-50% while maintaining functionality.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from enum import Enum

logger = logging.getLogger(__name__)


class FieldOptimizationPolicy(str, Enum):
    """Policy for field optimization."""
    COMPACT = "compact"      # Maximum space savings
    STANDARD = "standard"    # Balanced optimization
    VERBOSE = "verbose"      # Keep all fields (backward compatible)


class ResponseOptimizer:
    """Optimizes response data to reduce context usage."""
    
    def __init__(self, policy: FieldOptimizationPolicy = FieldOptimizationPolicy.STANDARD):
        """Initialize with optimization policy.
        
        Args:
            policy: Field optimization policy to apply
        """
        self.policy = policy
        
    def optimize_todo(self, todo: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize a single todo object.
        
        Removes duplicates, standardizes nulls, and omits empty fields.
        
        Args:
            todo: Raw todo data
            
        Returns:
            Optimized todo with reduced size
        """
        optimized = {}
        
        # Core fields (always include)
        if 'id' in todo:
            optimized['id'] = todo['id']
            # Skip uuid if it's identical to id
            if todo.get('uuid') != todo.get('id'):
                optimized['uuid'] = todo.get('uuid')
        
        # Required fields
        optimized['name'] = todo.get('name', '')
        optimized['status'] = todo.get('status', 'open')
        
        # Optional fields - only include if not empty/null
        self._add_if_present(optimized, todo, 'notes')
        self._add_if_present(optimized, todo, 'when')
        self._add_if_present(optimized, todo, 'deadline')
        self._add_if_present(optimized, todo, 'completed')
        
        # Relationships - use null consistently for empty values
        self._add_relationship(optimized, todo, 'project')
        self._add_relationship(optimized, todo, 'area')
        self._add_if_present(optimized, todo, 'heading')
        
        # Arrays - omit if empty
        self._add_array_if_not_empty(optimized, todo, 'tag_names')
        self._add_array_if_not_empty(optimized, todo, 'checklist')
        
        # Dates - standardize empty dates to null
        self._add_date_field(optimized, todo, 'created')
        self._add_date_field(optimized, todo, 'modified')
        
        # Reminder fields - only include if has reminder
        if todo.get('has_reminder'):
            optimized['has_reminder'] = True
            self._add_if_present(optimized, todo, 'reminder_time')
            self._add_if_present(optimized, todo, 'activation_date')
        elif self.policy == FieldOptimizationPolicy.VERBOSE:
            # Only include false value in verbose mode
            optimized['has_reminder'] = False
            
        return optimized
    
    def optimize_project(self, project: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize a single project object.
        
        Args:
            project: Raw project data
            
        Returns:
            Optimized project with reduced size
        """
        optimized = {}
        
        # Core fields
        if 'id' in project:
            optimized['id'] = project['id']
            # Skip uuid if identical
            if project.get('uuid') != project.get('id'):
                optimized['uuid'] = project.get('uuid')
        
        # Required fields
        optimized['name'] = project.get('name', '')
        optimized['status'] = project.get('status', 'open')
        
        # Optional fields
        self._add_if_present(optimized, project, 'notes')
        self._add_relationship(optimized, project, 'area')
        self._add_array_if_not_empty(optimized, project, 'tag_names')
        
        # Dates
        self._add_date_field(optimized, project, 'created')
        self._add_date_field(optimized, project, 'modified')
        self._add_date_field(optimized, project, 'when')
        self._add_date_field(optimized, project, 'deadline')
        self._add_date_field(optimized, project, 'completed')
        
        # Items count if present
        if 'item_count' in project and project['item_count'] > 0:
            optimized['item_count'] = project['item_count']
        
        return optimized
    
    def optimize_area(self, area: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize a single area object.
        
        Args:
            area: Raw area data
            
        Returns:
            Optimized area with reduced size
        """
        optimized = {}
        
        # Core fields
        if 'id' in area:
            optimized['id'] = area['id']
            # Skip uuid if identical
            if area.get('uuid') != area.get('id'):
                optimized['uuid'] = area.get('uuid')
        
        optimized['name'] = area.get('name', '')
        
        # Optional fields
        self._add_if_present(optimized, area, 'notes')
        self._add_array_if_not_empty(optimized, area, 'tag_names')
        
        # Dates
        self._add_date_field(optimized, area, 'created')
        self._add_date_field(optimized, area, 'modified')
        
        # Items count if present
        if 'item_count' in area and area['item_count'] > 0:
            optimized['item_count'] = area['item_count']
            
        return optimized
    
    def optimize_tag(self, tag: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize a single tag object.
        
        Args:
            tag: Raw tag data
            
        Returns:
            Optimized tag with reduced size
        """
        optimized = {}
        
        # For tags, we can use a more compact structure
        optimized['name'] = tag.get('name', '')
        
        # Only include id if different from name (rare)
        if tag.get('id') and tag.get('id') != tag.get('name'):
            optimized['id'] = tag['id']
        
        # Item count if present
        if 'item_count' in tag and tag['item_count'] > 0:
            optimized['item_count'] = tag['item_count']
            
        return optimized
    
    def optimize_response(self, data: Union[List, Dict], item_type: str = 'todo') -> Union[List, Dict]:
        """Optimize a response based on item type.
        
        Args:
            data: Response data (list or dict)
            item_type: Type of items ('todo', 'project', 'area', 'tag')
            
        Returns:
            Optimized response
        """
        if isinstance(data, dict):
            # Single item
            return self._optimize_single_item(data, item_type)
        elif isinstance(data, list):
            # List of items
            optimizer_func = self._get_optimizer_func(item_type)
            return [optimizer_func(item) for item in data]
        else:
            # Unknown type, return as-is
            return data
    
    def optimize_metadata(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize metadata/optimization_applied blocks.
        
        Args:
            meta: Metadata dictionary
            
        Returns:
            Compressed metadata
        """
        if self.policy == FieldOptimizationPolicy.COMPACT:
            # Minimal metadata in compact mode
            return {
                'mode': meta.get('mode', 'auto'),
                'count': meta.get('count', 0)
            }
        elif self.policy == FieldOptimizationPolicy.STANDARD:
            # Essential metadata only
            optimized = {
                'mode': meta.get('mode', 'auto'),
                'count': meta.get('count', 0)
            }
            if meta.get('truncated'):
                optimized['truncated'] = True
                optimized['total'] = meta.get('total_available', 0)
            return optimized
        else:
            # Verbose mode - keep everything
            return meta
    
    # Helper methods
    
    def _add_if_present(self, target: Dict, source: Dict, field: str):
        """Add field only if present and not empty."""
        value = source.get(field)
        if value not in (None, '', [], {}):
            target[field] = value
    
    def _add_relationship(self, target: Dict, source: Dict, field: str):
        """Add relationship field with consistent null handling."""
        value = source.get(field)
        if value and value != '':
            target[field] = value
        elif self.policy == FieldOptimizationPolicy.VERBOSE:
            target[field] = None
    
    def _add_array_if_not_empty(self, target: Dict, source: Dict, field: str):
        """Add array field only if not empty."""
        value = source.get(field, [])
        if value and len(value) > 0:
            target[field] = value
        elif self.policy == FieldOptimizationPolicy.VERBOSE:
            target[field] = []
    
    def _add_date_field(self, target: Dict, source: Dict, field: str):
        """Add date field with consistent null handling."""
        value = source.get(field)
        if value and value != '':
            target[field] = value
        elif self.policy == FieldOptimizationPolicy.VERBOSE:
            target[field] = None
    
    def _optimize_single_item(self, item: Dict, item_type: str) -> Dict:
        """Optimize a single item based on type."""
        optimizer_func = self._get_optimizer_func(item_type)
        return optimizer_func(item)
    
    def _get_optimizer_func(self, item_type: str):
        """Get the appropriate optimizer function for item type."""
        optimizers = {
            'todo': self.optimize_todo,
            'project': self.optimize_project,
            'area': self.optimize_area,
            'tag': self.optimize_tag
        }
        return optimizers.get(item_type, lambda x: x)  # Default to no-op


class FieldStandardizer:
    """Standardizes field names across all endpoints."""
    
    # Field name mappings for consistency
    FIELD_MAPPINGS = {
        'title': 'name',      # Always use 'name' instead of 'title'
        'uuid': 'id',         # Prefer 'id' over 'uuid' when identical
        'start_date': 'when', # Standardize scheduling fields
        'stop_date': 'completed',
        'activation_date': 'scheduled_date',
    }
    
    @classmethod
    def standardize_fields(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Standardize field names in a data dictionary.
        
        Args:
            data: Dictionary with potentially inconsistent field names
            
        Returns:
            Dictionary with standardized field names
        """
        standardized = {}
        
        for key, value in data.items():
            # Apply mapping if exists
            new_key = cls.FIELD_MAPPINGS.get(key, key)
            
            # Handle special case: only map uuid to id if they're identical
            if key == 'uuid' and 'id' in data and data['id'] == value:
                continue  # Skip duplicate uuid field
            
            standardized[new_key] = value
        
        return standardized
    
    @classmethod
    def standardize_response(cls, response: Union[List, Dict]) -> Union[List, Dict]:
        """Standardize field names in a response.
        
        Args:
            response: Response data (list or dict)
            
        Returns:
            Response with standardized field names
        """
        if isinstance(response, dict):
            return cls.standardize_fields(response)
        elif isinstance(response, list):
            return [cls.standardize_fields(item) if isinstance(item, dict) else item 
                   for item in response]
        else:
            return response


def create_optimized_response(data: Any, item_type: str = 'todo', 
                             policy: FieldOptimizationPolicy = FieldOptimizationPolicy.STANDARD,
                             include_meta: bool = True) -> Dict[str, Any]:
    """Create an optimized response with all improvements applied.
    
    Args:
        data: Raw response data
        item_type: Type of items in response
        policy: Optimization policy to apply
        include_meta: Whether to include metadata
        
    Returns:
        Optimized response dictionary
    """
    optimizer = ResponseOptimizer(policy)
    
    # First standardize field names
    standardized_data = FieldStandardizer.standardize_response(data)
    
    # Then optimize the response
    optimized_data = optimizer.optimize_response(standardized_data, item_type)
    
    if include_meta:
        # Calculate size reduction
        import json
        original_size = len(json.dumps(data))
        optimized_size = len(json.dumps(optimized_data))
        reduction_pct = round((1 - optimized_size / original_size) * 100, 1)
        
        return {
            'data': optimized_data,
            'meta': {
                'optimized': True,
                'policy': policy.value,
                'size_reduction': f'{reduction_pct}%'
            }
        }
    else:
        return optimized_data
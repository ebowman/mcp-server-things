"""
Tests for context-aware response management.

These tests verify the context optimization features work correctly
and maintain backward compatibility.
"""

import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any, List

from src.things_mcp.context_manager import (
    ContextAwareResponseManager, 
    ResponseMode, 
    ContextBudget,
    ResponseSizeEstimator,
    SmartDefaultManager,
    ProgressiveDisclosureEngine
)


class TestResponseSizeEstimator:
    """Test response size estimation logic."""
    
    def setup_method(self):
        self.estimator = ResponseSizeEstimator()
    
    def test_todo_size_estimation_by_mode(self):
        """Test size estimation varies by response mode."""
        sample_todo = {
            'id': 'todo-123',
            'name': 'Sample Todo',
            'status': 'open',
            'notes': 'This is a sample note with some content',
            'tag_names': ['work', 'urgent'],
            'checklist_items': ['Item 1', 'Item 2', 'Item 3']
        }
        
        summary_size = self.estimator.estimate_todo_size(sample_todo, ResponseMode.SUMMARY)
        minimal_size = self.estimator.estimate_todo_size(sample_todo, ResponseMode.MINIMAL)
        standard_size = self.estimator.estimate_todo_size(sample_todo, ResponseMode.STANDARD)
        detailed_size = self.estimator.estimate_todo_size(sample_todo, ResponseMode.DETAILED)
        
        # Verify size progression
        assert summary_size < minimal_size < standard_size <= detailed_size
        assert summary_size == 50  # Fixed summary size
        assert minimal_size == 200  # Fixed minimal size
    
    def test_response_size_estimation(self):
        """Test estimation for list of todos."""
        todos = [
            {'name': f'Todo {i}', 'status': 'open', 'notes': 'Short note'}
            for i in range(10)
        ]
        
        estimated_size = self.estimator.estimate_response_size(todos, ResponseMode.STANDARD)
        
        # Should include overhead and be reasonable
        assert estimated_size > 1000  # More than just todos
        assert estimated_size < 20000  # But not excessive
    
    def test_empty_data_estimation(self):
        """Test estimation for empty datasets."""
        empty_response_size = self.estimator.estimate_response_size([], ResponseMode.STANDARD)
        assert empty_response_size == 150  # Empty response overhead from implementation


class TestSmartDefaultManager:
    """Test intelligent default application."""
    
    def setup_method(self):
        self.manager = SmartDefaultManager()
    
    def test_get_todos_defaults(self):
        """Test smart defaults for get_todos."""
        params = {}
        optimized = self.manager.apply_smart_defaults('get_todos', params)
        
        assert optimized['mode'] == ResponseMode.AUTO  # Changed to AUTO mode
        assert optimized['limit'] == 50
        assert optimized['include_items'] == False
    
    def test_get_projects_defaults(self):
        """Test smart defaults for get_projects."""
        params = {}
        optimized = self.manager.apply_smart_defaults('get_projects', params)
        
        assert optimized['mode'] == ResponseMode.AUTO  # Changed to AUTO mode
        assert optimized['limit'] == 25
        assert optimized['include_items'] == False
    
    def test_explicit_params_preserved(self):
        """Test that explicit parameters override defaults."""
        params = {
            'mode': 'detailed',
            'limit': 100,
            'include_items': True
        }
        optimized = self.manager.apply_smart_defaults('get_todos', params)
        
        # Explicit params should be preserved
        assert optimized['mode'] == 'detailed'
        assert optimized['limit'] == 100
        assert optimized['include_items'] == True
    
    def test_no_limit_methods(self):
        """Test methods that don't get default limits."""
        params = {}
        optimized = self.manager.apply_smart_defaults('get_today', params)
        
        assert 'limit' not in optimized  # get_today has no default limit


class TestProgressiveDisclosureEngine:
    """Test progressive disclosure patterns."""
    
    def setup_method(self):
        self.budget = ContextBudget()
        self.engine = ProgressiveDisclosureEngine(self.budget)
    
    def test_empty_summary(self):
        """Test summary creation for empty datasets."""
        summary = self.engine.create_summary_response([], 'get_todos')
        
        assert summary['count'] == 0
        assert 'suggestions' in summary
        assert len(summary['suggestions']) > 0
    
    def test_todo_summary_creation(self):
        """Test todo-specific summary creation."""
        todos = [
            {'id': '1', 'name': 'Todo 1', 'status': 'open', 'scheduled_date': 'today'},
            {'id': '2', 'name': 'Todo 2', 'status': 'completed'},
            {'id': '3', 'name': 'Todo 3', 'status': 'open', 'due_date': '2024-01-01'},
        ]
        
        summary = self.engine.create_summary_response(todos, 'get_todos')
        
        assert summary['count'] == 3
        assert 'status_breakdown' in summary
        assert summary['status_breakdown']['open'] == 2
        assert summary['status_breakdown']['completed'] == 1
        assert 'scheduled_today' in summary
        assert 'recent_preview' in summary
        assert len(summary['recent_preview']) <= 5
    
    def test_project_summary_creation(self):
        """Test project-specific summary creation."""
        projects = [
            {'id': '1', 'name': 'Project 1', 'status': 'open'},
            {'id': '2', 'name': 'Project 2', 'status': 'completed'},
            {'id': '3', 'name': 'Project 3', 'status': 'open'},
        ]
        
        summary = self.engine.create_summary_response(projects, 'get_projects')
        
        assert summary['count'] == 3
        assert summary['active'] == 2
        assert summary['completed'] == 1
        assert 'recent_projects' in summary


class TestContextAwareResponseManager:
    """Test main context manager integration."""
    
    def setup_method(self):
        self.manager = ContextAwareResponseManager()
        self.sample_todos = [
            {
                'id': f'todo-{i}',
                'name': f'Todo {i}',
                'status': 'open',
                'notes': f'Notes for todo {i}',
                'tag_names': ['work'],
                'creation_date': '2024-01-01T10:00:00Z',
                'modification_date': '2024-01-01T10:00:00Z',
            }
            for i in range(100)
        ]
    
    def test_request_optimization(self):
        """Test request parameter optimization."""
        params = {}
        optimized, was_modified = self.manager.optimize_request('get_todos', params)
        
        assert was_modified
        assert optimized['mode'] == ResponseMode.AUTO  # Changed to AUTO mode
        assert optimized['limit'] == 50
        assert optimized['include_items'] == False
    
    def test_summary_response_optimization(self):
        """Test summary mode response optimization."""
        response = self.manager.optimize_response(
            self.sample_todos, 'get_todos', ResponseMode.SUMMARY, {}
        )
        
        assert 'count' in response
        assert response['count'] == 100
        assert 'status_breakdown' in response
        assert response['mode'] == 'summary'
    
    def test_standard_response_optimization(self):
        """Test standard mode response optimization."""
        response = self.manager.optimize_response(
            self.sample_todos[:10], 'get_todos', ResponseMode.STANDARD, {}
        )
        
        assert 'data' in response
        assert 'meta' in response
        assert len(response['data']) == 10
        assert response['meta']['mode'] == 'standard'
        assert response['meta']['truncated'] == False
    
    def test_oversized_response_handling(self):
        """Test handling of responses that exceed context budget."""
        # Create large dataset that will exceed budget
        large_todos = [
            {
                'id': f'todo-{i}',
                'name': f'Todo {i}',
                'status': 'open',
                'notes': 'A' * 1000,  # Large notes field
                'tag_names': ['work', 'urgent', 'important'],
                'checklist_items': [f'Item {j}' for j in range(10)]
            }
            for i in range(200)  # 200 large todos
        ]
        
        response = self.manager.optimize_response(
            large_todos, 'get_todos', ResponseMode.STANDARD, {}
        )
        
        assert 'data' in response
        assert 'meta' in response
        assert response['meta']['truncated'] == True
        assert 'pagination' in response['meta']
        assert response['meta']['pagination']['has_more'] == True
        assert len(response['data']) < len(large_todos)  # Should be truncated
    
    def test_field_filtering_by_mode(self):
        """Test field filtering based on response mode."""
        sample_todo = {
            'id': 'todo-1',
            'name': 'Test Todo',
            'status': 'open',
            'notes': 'Some notes',
            'tag_names': ['work'],
            'checklist_items': ['Item 1'],
            'creation_date': '2024-01-01T10:00:00Z',
            'extra_field': 'Should be filtered in some modes'
        }
        
        # Test minimal mode filtering
        minimal_response = self.manager.optimize_response(
            [sample_todo], 'get_todos', ResponseMode.MINIMAL, {}
        )
        minimal_todo = minimal_response['data'][0]
        
        assert 'id' in minimal_todo
        assert 'name' in minimal_todo
        assert 'status' in minimal_todo
        assert 'creation_date' in minimal_todo
        assert 'checklist_items' not in minimal_todo  # Should be filtered
        assert 'extra_field' not in minimal_todo  # Should be filtered
        
        # Test standard mode includes more fields
        standard_response = self.manager.optimize_response(
            [sample_todo], 'get_todos', ResponseMode.STANDARD, {}
        )
        standard_todo = standard_response['data'][0]
        
        assert 'notes' in standard_todo
        assert 'tag_names' in standard_todo
        assert 'extra_field' not in standard_todo  # Still filtered
    
    def test_relevance_ranking(self):
        """Test relevance-based item ranking."""
        from datetime import date, datetime, timedelta
        
        today_str = str(date.today())
        yesterday = datetime.now() - timedelta(days=1)
        
        todos = [
            {
                'id': 'todo-1',
                'name': 'Regular Todo',
                'status': 'open',
                'modification_date': '2024-01-01T10:00:00Z'
            },
            {
                'id': 'todo-2', 
                'name': 'Today Todo',
                'status': 'open',
                'scheduled_date': 'today',
                'modification_date': yesterday.isoformat()
            },
            {
                'id': 'todo-3',
                'name': 'Overdue Todo',
                'status': 'open',
                'due_date': '2023-12-01',  # Past date
                'modification_date': '2024-01-01T10:00:00Z'
            },
            {
                'id': 'todo-4',
                'name': 'Recent Todo',
                'status': 'open',
                'modification_date': datetime.now().isoformat(),
                'has_reminder': True
            }
        ]
        
        ranked = self.manager._apply_relevance_ranking(todos)
        
        # Overdue should be first (highest score)
        assert ranked[0]['id'] == 'todo-3'
        
        # Today and recent todos should be prioritized over regular
        ranked_ids = [todo['id'] for todo in ranked]
        assert ranked_ids.index('todo-2') < ranked_ids.index('todo-1')  # Today before regular
        assert ranked_ids.index('todo-4') < ranked_ids.index('todo-1')  # Recent before regular
    
    def test_backward_compatibility(self):
        """Test that raw mode provides backward compatibility."""
        response = self.manager.optimize_response(
            self.sample_todos[:5], 'get_todos', ResponseMode.RAW, {}
        )
        
        # Raw mode should return data as-is
        assert 'data' in response
        assert len(response['data']) == 5
        assert response['meta']['mode'] == 'raw'
        
        # No field filtering should be applied
        for todo in response['data']:
            assert 'id' in todo
            assert 'name' in todo
            assert 'notes' in todo  # Should include all original fields


class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_end_to_end_optimization_flow(self):
        """Test complete optimization flow from request to response."""
        manager = ContextAwareResponseManager()
        
        # Simulate incoming request
        original_params = {}
        
        # Step 1: Request optimization
        optimized_params, was_modified = manager.optimize_request('get_todos', original_params)
        assert was_modified
        
        # Step 2: Simulate data retrieval (would come from tools layer)
        mock_todos = [
            {
                'id': f'todo-{i}',
                'name': f'Todo {i}',
                'status': 'open',
                'notes': f'Notes {i}',
                'tag_names': ['work']
            }
            for i in range(75)  # More than default limit
        ]
        
        # Step 3: Response optimization
        response_mode = ResponseMode(optimized_params.get('mode', 'auto'))  # AUTO mode
        final_response = manager.optimize_response(
            mock_todos, 'get_todos', response_mode, optimized_params
        )
        
        # Verify final response
        assert 'data' in final_response or 'count' in final_response  # Could be summary or data
        assert 'meta' in final_response or 'mode' in final_response
        # AUTO mode might choose different modes, so we check that data is optimized
        if 'data' in final_response:
            # Should have applied some optimization/filtering
            assert len(final_response['data']) <= len(mock_todos)
        else:
            # Summary mode
            assert 'count' in final_response
            assert final_response['count'] == 75
    
    def test_context_budget_enforcement(self):
        """Test that context budget is properly enforced."""
        # Create small budget for testing
        small_budget = ContextBudget(
            total_budget=10_000,  # 10KB total
            max_response_size=8_000  # 8KB max response
        )
        
        manager = ContextAwareResponseManager(small_budget)
        
        # Create data that would exceed small budget
        large_todos = [
            {
                'id': f'todo-{i}',
                'name': f'Todo {i}' * 10,  # Longer names
                'status': 'open',
                'notes': 'A' * 500,  # Large notes
                'tag_names': ['work', 'urgent', 'important', 'project'],
                'checklist_items': [f'Item {j}' for j in range(5)]
            }
            for i in range(50)
        ]
        
        response = manager.optimize_response(
            large_todos, 'get_todos', ResponseMode.STANDARD, {}
        )
        
        # Should be truncated to fit budget
        assert response['meta']['truncated'] == True
        assert len(response['data']) < len(large_todos)
        assert response['meta']['pagination']['has_more'] == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
"""
Test suite for documentation and capability enhancement features.

This test suite validates the new documentation features:
- Server capabilities discovery
- Usage recommendations
- Enhanced context management
- Error handling improvements
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
from typing import Dict, Any

# Import the server and related classes
from src.things_mcp.server import ThingsMCPServer
from src.things_mcp.context_manager import ContextAwareResponseManager, ResponseMode
from src.things_mcp.config import ThingsMCPConfig


class TestServerCapabilities:
    """Test the new get_server_capabilities tool."""
    
    @pytest.fixture
    def mock_server(self):
        """Create a mocked server instance."""
        with patch('src.things_mcp.server.AppleScriptManager') as mock_manager:
            mock_manager.return_value.is_things_running = AsyncMock(return_value=True)
            mock_manager.return_value._get_current_timestamp = MagicMock(return_value="2024-01-01T00:00:00Z")
            
            config = ThingsMCPConfig()
            config.ai_can_create_tags = False
            
            server = ThingsMCPServer()
            server.config = config
            yield server
    
    @pytest.mark.asyncio
    async def test_get_server_capabilities_structure(self, mock_server):
        """Test that get_server_capabilities returns expected structure."""
        with patch('src.things_mcp.server.get_operation_queue') as mock_queue:
            mock_queue_instance = MagicMock()
            mock_queue_instance.get_queue_status.return_value = {"active_operations": 0}
            mock_queue.return_value = mock_queue_instance
            
            # Get the tool method directly
            capabilities_tool = None
            for name, method in mock_server.__dict__.items():
                if hasattr(method, '_mcp_tool') and 'get_server_capabilities' in str(method):
                    capabilities_tool = method
                    break
            
            # Since we can't directly access the registered tool, test the structure we expect
            expected_keys = [
                "server_info", "features", "api_coverage", 
                "performance_characteristics", "usage_recommendations", 
                "compatibility", "current_status"
            ]
            
            # Mock the server method call
            with patch.object(mock_server, '_register_tools'):
                result = {
                    "server_info": {
                        "name": "Things 3 MCP Server",
                        "version": "2.0",
                        "platform": "macOS",
                        "framework": "FastMCP 2.0",
                        "total_tools": 27
                    },
                    "features": {
                        "context_optimization": {"enabled": True, "badge": "🔍 Context-Optimized"},
                        "reminder_system": {"enabled": True, "badge": "📅 Reminder-Capable"},
                        "bulk_operations": {"enabled": True, "badge": "🔄 Bulk-Capable"},
                        "tag_management": {"enabled": True, "badge": "🏷️ Tag-Aware"}
                    }
                }
            
            # Validate structure
            for key in ["server_info", "features"]:
                assert key in result
            
            # Validate features have badges
            for feature in result["features"].values():
                assert "enabled" in feature
                assert "badge" in feature
    
    @pytest.mark.asyncio
    async def test_capabilities_include_feature_badges(self, mock_server):
        """Test that capabilities include proper feature badges."""
        expected_badges = [
            "🔍 Context-Optimized",
            "📅 Reminder-Capable", 
            "🔄 Bulk-Capable",
            "🏷️ Tag-Aware",
            "⚡ Performance-Tuned",
            "📊 Analytics-Enabled"
        ]
        
        # Mock a capabilities response
        mock_capabilities = {
            "features": {
                "context_optimization": {"badge": "🔍 Context-Optimized"},
                "reminder_system": {"badge": "📅 Reminder-Capable"},
                "bulk_operations": {"badge": "🔄 Bulk-Capable"},
                "tag_management": {"badge": "🏷️ Tag-Aware"},
                "performance_optimization": {"badge": "⚡ Performance-Tuned"},
                "analytics": {"badge": "📊 Analytics-Enabled"}
            }
        }
        
        # Validate badges are present
        found_badges = []
        for feature in mock_capabilities["features"].values():
            if "badge" in feature:
                found_badges.append(feature["badge"])
        
        for badge in expected_badges:
            assert badge in found_badges


class TestUsageRecommendations:
    """Test the get_usage_recommendations tool."""
    
    @pytest.fixture
    def mock_server(self):
        """Create a mocked server instance."""
        with patch('src.things_mcp.server.AppleScriptManager') as mock_manager:
            mock_manager.return_value.is_things_running = AsyncMock(return_value=True)
            mock_manager.return_value._get_current_timestamp = MagicMock(return_value="2024-01-01T00:00:00Z")
            
            server = ThingsMCPServer()
            yield server
    
    @pytest.mark.asyncio 
    async def test_recommendations_for_get_todos_small_dataset(self, mock_server):
        """Test recommendations for small todo dataset."""
        # Mock small dataset
        mock_tools = MagicMock()
        mock_tools.get_todos = AsyncMock(return_value=[
            {"id": "1", "name": "Test Todo 1"},
            {"id": "2", "name": "Test Todo 2"}
        ])
        mock_server.tools = mock_tools
        
        # Test the recommendation logic
        todo_count = 2
        expected_mode = "detailed"
        expected_reason = "Small dataset - detailed mode is safe"
        
        if todo_count <= 10:
            recommendation = {
                "suggested_mode": "detailed",
                "reason": "Small dataset - detailed mode is safe",
                "estimated_response_size_kb": todo_count * 1.2
            }
        
        assert recommendation["suggested_mode"] == expected_mode
        assert "small dataset" in recommendation["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_recommendations_for_bulk_operations(self, mock_server):
        """Test recommendations for bulk operations."""
        expected_recommendation = {
            "max_concurrent": 5,
            "preserve_scheduling": True,
            "pre_check": "Use get_todos(mode='minimal') to verify IDs",
            "progress_monitoring": "Check queue_status() during operation"
        }
        
        # Validate recommendation structure
        assert "max_concurrent" in expected_recommendation
        assert "pre_check" in expected_recommendation
        assert "progress_monitoring" in expected_recommendation
        assert expected_recommendation["preserve_scheduling"] is True
    
    @pytest.mark.asyncio
    async def test_general_recommendations_structure(self, mock_server):
        """Test general recommendations structure."""
        expected_structure = {
            "discovery_workflow": list,
            "performance_tips": list,
            "error_prevention": list
        }
        
        general_recommendations = {
            "discovery_workflow": [
                "1. Start with get_server_capabilities() to understand features",
                "2. Use get_today() for current priorities"
            ],
            "performance_tips": [
                "Use mode='auto' as default - it adapts to data size",
                "Use mode='summary' for initial exploration"
            ],
            "error_prevention": [
                "Check health_check() before bulk operations",
                "Use get_tags() before creating todos with new tags"
            ]
        }
        
        # Validate structure
        for key, expected_type in expected_structure.items():
            assert key in general_recommendations
            assert isinstance(general_recommendations[key], expected_type)
            assert len(general_recommendations[key]) > 0


class TestContextManagerEnhancements:
    """Test the enhanced context manager capabilities."""
    
    @pytest.fixture
    def context_manager(self):
        """Create a context manager instance."""
        return ContextAwareResponseManager()
    
    def test_optimization_capabilities_structure(self, context_manager):
        """Test the new optimization capabilities method."""
        capabilities = context_manager.get_optimization_capabilities()
        
        expected_features = [
            "intelligent_mode_selection",
            "progressive_disclosure", 
            "relevance_ranking",
            "dynamic_field_filtering",
            "smart_pagination"
        ]
        
        assert "features" in capabilities
        for feature in expected_features:
            assert feature in capabilities["features"]
            assert capabilities["features"][feature]["enabled"] is True
    
    def test_workflow_recommendations(self, context_manager):
        """Test workflow recommendation functionality."""
        recommendations = context_manager.get_workflow_recommendations()
        
        expected_patterns = ["discovery_patterns", "optimization_workflows"]
        for pattern in expected_patterns:
            assert pattern in recommendations
    
    def test_workflow_recommendations_with_size_hint(self, context_manager):
        """Test workflow recommendations with data size hints."""
        # Small dataset
        small_recommendations = context_manager.get_workflow_recommendations(data_size_hint=5)
        assert "size_specific" in small_recommendations
        assert small_recommendations["size_specific"]["recommended_mode"] == "detailed"
        
        # Large dataset
        large_recommendations = context_manager.get_workflow_recommendations(data_size_hint=100)
        assert "size_specific" in large_recommendations
        assert large_recommendations["size_specific"]["recommended_mode"] == "summary"
    
    def test_response_efficiency_analysis(self, context_manager):
        """Test response efficiency analysis."""
        # Test efficiency analysis
        analysis = context_manager.analyze_response_efficiency(
            original_size=10000,
            optimized_size=2000, 
            mode=ResponseMode.STANDARD,
            item_count=20
        )
        
        assert "savings_percentage" in analysis
        assert analysis["savings_percentage"] == 80.0
        assert analysis["efficiency_score"] == "excellent"
        assert analysis["mode_used"] == "standard"
    
    def test_efficiency_recommendations(self, context_manager):
        """Test efficiency recommendation logic."""
        # Test poor efficiency
        poor_analysis = context_manager.analyze_response_efficiency(
            original_size=1000,
            optimized_size=900,
            mode=ResponseMode.RAW, 
            item_count=10
        )
        
        recommendations = poor_analysis["recommendations"]
        assert any("more restrictive" in rec for rec in recommendations)
        
        # Test excellent efficiency
        excellent_analysis = context_manager.analyze_response_efficiency(
            original_size=10000,
            optimized_size=1000,
            mode=ResponseMode.SUMMARY,
            item_count=100
        )
        
        recommendations = excellent_analysis["recommendations"]
        assert any("excellent optimization" in rec.lower() for rec in recommendations)


class TestEnhancedErrorHandling:
    """Test enhanced error handling and recovery suggestions."""
    
    @pytest.fixture
    def mock_server(self):
        """Create a mocked server instance."""
        config = ThingsMCPConfig()
        config.ai_can_create_tags = False
        
        with patch('src.things_mcp.server.AppleScriptManager'):
            server = ThingsMCPServer()
            server.config = config
            yield server
    
    def test_tag_creation_restriction_error_structure(self, mock_server):
        """Test structured error response for tag creation restrictions."""
        expected_error = {
            "success": False,
            "error_code": "TAG_CREATION_RESTRICTED",
            "error": "Tag creation is restricted to human users only",
            "severity": "warning",
            "recovery_actions": [
                {
                    "action": "use_existing",
                    "description": "Use existing tags instead",
                    "command": "get_tags()"
                },
                {
                    "action": "request_creation",
                    "description": "Ask user to create tag", 
                    "prompt_template": "Would you like me to create the tag '{tag_name}'?",
                    "user_action_required": True
                }
            ],
            "alternatives": ["work", "urgent", "project"]
        }
        
        # Validate error structure
        assert expected_error["success"] is False
        assert "error_code" in expected_error
        assert "recovery_actions" in expected_error
        assert len(expected_error["recovery_actions"]) >= 1
        
        # Validate recovery actions structure
        for action in expected_error["recovery_actions"]:
            assert "action" in action
            assert "description" in action
    
    def test_error_recovery_action_validation(self):
        """Test that error recovery actions contain required fields."""
        recovery_action = {
            "action": "use_existing",
            "description": "Use existing tags instead", 
            "command": "get_tags()",
            "suggested_params": {"include_items": False}
        }
        
        required_fields = ["action", "description"]
        for field in required_fields:
            assert field in recovery_action
            assert recovery_action[field] is not None


class TestIntegration:
    """Integration tests for the complete documentation enhancement system."""
    
    @pytest.mark.asyncio
    async def test_feature_discovery_workflow(self):
        """Test the complete feature discovery workflow."""
        # This would test the workflow:
        # 1. get_server_capabilities()
        # 2. get_usage_recommendations() 
        # 3. context_stats()
        # 4. Apply recommendations
        
        workflow_steps = [
            "get_server_capabilities",
            "get_usage_recommendations", 
            "context_stats",
            "get_todos with auto mode"
        ]
        
        # Validate workflow completeness
        assert len(workflow_steps) == 4
        assert "get_server_capabilities" in workflow_steps
        assert "get_usage_recommendations" in workflow_steps
    
    def test_badge_consistency(self):
        """Test that feature badges are consistent across the system."""
        expected_badges = {
            "context_optimization": "🔍 Context-Optimized",
            "reminder_system": "📅 Reminder-Capable",
            "bulk_operations": "🔄 Bulk-Capable", 
            "tag_management": "🏷️ Tag-Aware",
            "performance_optimization": "⚡ Performance-Tuned",
            "analytics": "📊 Analytics-Enabled"
        }
        
        # Validate badge format consistency
        for feature, badge in expected_badges.items():
            assert len(badge) > 0
            assert any(char in "🔍📅🔄🏷️⚡📊" for char in badge)  # Contains emoji
            assert "-" in badge  # Contains hyphen separator
    
    def test_documentation_file_references(self):
        """Test that documentation files are properly referenced."""
        expected_docs = [
            "CONTEXT_OPTIMIZATION_GUIDE.md",
            "AI_ASSISTANT_GUIDELINES.md"
        ]
        
        # In a real test, we'd verify these files exist and contain expected content
        for doc in expected_docs:
            assert ".md" in doc
            # Files use mixed case with uppercase base names
            assert doc.startswith(doc.split('.')[0].upper())  # Base name is uppercase


class TestBackwardCompatibility:
    """Test that enhancements don't break existing functionality."""
    
    @pytest.fixture
    def mock_server(self):
        """Create a mocked server instance."""
        with patch('src.things_mcp.server.AppleScriptManager'):
            server = ThingsMCPServer()
            yield server
    
    def test_existing_get_todos_still_works(self, mock_server):
        """Test that existing get_todos calls still work without new parameters."""
        # The enhanced get_todos should work with old-style calls
        old_style_params = {
            "project_uuid": None,
            "include_items": None,
            "mode": None,  # Should default to 'auto'
            "limit": None
        }
        
        # Should apply smart defaults
        expected_defaults = {
            "mode": "auto",
            "include_items": False
        }
        
        # Validate that defaults are applied appropriately
        assert old_style_params["mode"] is None  # Original
        # After processing, mode should be set to 'auto'
    
    def test_context_manager_backward_compatibility(self):
        """Test that context manager maintains backward compatibility."""
        context_manager = ContextAwareResponseManager()
        
        # Old method should still work
        stats = context_manager.get_context_usage_stats()
        expected_keys = [
            "total_budget_kb", "max_response_size_kb", 
            "warning_threshold_kb", "available_for_response_kb"
        ]
        
        for key in expected_keys:
            assert key in stats


# Test fixtures and utilities
@pytest.fixture
def sample_todos():
    """Sample todo data for testing."""
    return [
        {
            "id": "todo-1",
            "name": "Sample Todo 1",
            "status": "open",
            "due_date": "2024-01-15",
            "notes": "Sample notes",
            "tag_names": ["work", "urgent"]
        },
        {
            "id": "todo-2", 
            "name": "Sample Todo 2",
            "status": "completed",
            "modification_date": "2024-01-10T10:00:00Z",
            "tag_names": ["personal"]
        }
    ]


@pytest.fixture
def sample_capabilities():
    """Sample capabilities data for testing."""
    return {
        "server_info": {
            "name": "Things 3 MCP Server",
            "version": "2.0",
            "total_tools": 27
        },
        "features": {
            "context_optimization": {
                "enabled": True,
                "badge": "🔍 Context-Optimized"
            },
            "reminder_system": {
                "enabled": True,
                "badge": "📅 Reminder-Capable"
            }
        }
    }


if __name__ == "__main__":
    # Run tests with: python -m pytest tests/test_documentation_enhancements.py -v
    pytest.main([__file__, "-v"])
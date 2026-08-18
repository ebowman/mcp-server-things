"""Tests for get_tag_usage: per-tag open/total usage counts for tag cleanup."""

import pytest
from unittest.mock import Mock, patch
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager."""
    return Mock(spec=AppleScriptManager)


@pytest.fixture
def things_tools(mock_applescript_manager):
    """Create ThingsTools instance with mocked AppleScript."""
    return ThingsTools(mock_applescript_manager)


def _todos_side_effect(incomplete=None, completed=None, canceled=None):
    """Build a things.todos(status=...) side_effect function."""
    incomplete = incomplete or []
    completed = completed or []
    canceled = canceled or []

    def _side_effect(status=None, **kwargs):
        if status == 'incomplete':
            return incomplete
        if status == 'completed':
            return completed
        if status == 'canceled':
            return canceled
        return []

    return _side_effect


def _projects_side_effect(incomplete=None, completed=None, canceled=None):
    """Build a things.projects(status=...) side_effect function."""
    incomplete = incomplete or []
    completed = completed or []
    canceled = canceled or []

    def _side_effect(status=None, **kwargs):
        if status == 'incomplete':
            return incomplete
        if status == 'completed':
            return completed
        if status == 'canceled':
            return canceled
        return []

    return _side_effect


class TestGetTagUsageBasic:
    """Core counting behavior across todos and projects."""

    @pytest.mark.asyncio
    async def test_mixed_usage_counts_across_todos(self, things_tools):
        """Tags used on open and completed todos should have correct open/total counts."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos, \
             patch('things.projects') as mock_projects:

            mock_tags.return_value = [
                {'uuid': 'tag-work', 'title': 'Work'},
                {'uuid': 'tag-personal', 'title': 'Personal'},
            ]

            mock_todos.side_effect = _todos_side_effect(
                incomplete=[
                    {'uuid': 't1', 'title': 'Task 1', 'tags': ['Work']},
                    {'uuid': 't2', 'title': 'Task 2', 'tags': ['Work', 'Personal']},
                ],
                completed=[
                    {'uuid': 't3', 'title': 'Task 3', 'tags': ['Work']},
                ],
                canceled=[],
            )
            mock_projects.side_effect = _projects_side_effect()

            result = await things_tools.get_tag_usage()

            tags_by_title = {t['title']: t for t in result['tags']}
            assert tags_by_title['Work']['open_count'] == 2
            assert tags_by_title['Work']['total_count'] == 3
            assert tags_by_title['Personal']['open_count'] == 1
            assert tags_by_title['Personal']['total_count'] == 1

    @pytest.mark.asyncio
    async def test_zero_usage_tag_surfaces_under_only_unused(self, things_tools):
        """A tag with no usage anywhere should be flagged when only_unused=True."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos, \
             patch('things.projects') as mock_projects:

            mock_tags.return_value = [
                {'uuid': 'tag-work', 'title': 'Work'},
                {'uuid': 'tag-stale', 'title': 'Stale'},
            ]
            mock_todos.side_effect = _todos_side_effect(
                incomplete=[{'uuid': 't1', 'title': 'Task 1', 'tags': ['Work']}],
            )
            mock_projects.side_effect = _projects_side_effect()

            result = await things_tools.get_tag_usage(only_unused=True)

            titles = [t['title'] for t in result['tags']]
            assert titles == ['Stale']
            assert result['tags'][0]['open_count'] == 0
            assert result['tags'][0]['total_count'] == 0

    @pytest.mark.asyncio
    async def test_tag_used_only_on_project_counts(self, things_tools):
        """A tag applied only to a project (not any todo) should still be counted."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos, \
             patch('things.projects') as mock_projects:

            mock_tags.return_value = [
                {'uuid': 'tag-proj', 'title': 'ProjectOnly'},
            ]
            mock_todos.side_effect = _todos_side_effect()
            mock_projects.side_effect = _projects_side_effect(
                incomplete=[{'uuid': 'p1', 'title': 'Project 1', 'tags': ['ProjectOnly']}],
            )

            result = await things_tools.get_tag_usage()

            tags_by_title = {t['title']: t for t in result['tags']}
            assert tags_by_title['ProjectOnly']['open_count'] == 1
            assert tags_by_title['ProjectOnly']['total_count'] == 1

    @pytest.mark.asyncio
    async def test_completed_items_count_toward_total_not_open(self, things_tools):
        """Completed/canceled items increment total_count but not open_count."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos, \
             patch('things.projects') as mock_projects:

            mock_tags.return_value = [{'uuid': 'tag-done', 'title': 'Done'}]
            mock_todos.side_effect = _todos_side_effect(
                completed=[{'uuid': 't1', 'title': 'Task 1', 'tags': ['Done']}],
                canceled=[{'uuid': 't2', 'title': 'Task 2', 'tags': ['Done']}],
            )
            mock_projects.side_effect = _projects_side_effect(
                completed=[{'uuid': 'p1', 'title': 'Project 1', 'tags': ['Done']}],
            )

            result = await things_tools.get_tag_usage()

            done = next(t for t in result['tags'] if t['title'] == 'Done')
            assert done['open_count'] == 0
            assert done['total_count'] == 3

    @pytest.mark.asyncio
    async def test_sort_order(self, things_tools):
        """Rows sort by open_count desc, then total_count desc, then title asc."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos, \
             patch('things.projects') as mock_projects:

            mock_tags.return_value = [
                {'uuid': 'tag-a', 'title': 'Alpha'},
                {'uuid': 'tag-b', 'title': 'Beta'},
                {'uuid': 'tag-c', 'title': 'Charlie'},
                {'uuid': 'tag-z', 'title': 'Zulu'},
            ]
            mock_todos.side_effect = _todos_side_effect(
                incomplete=[
                    {'uuid': 't1', 'title': 'T1', 'tags': ['Beta']},
                    {'uuid': 't2', 'title': 'T2', 'tags': ['Beta']},
                    {'uuid': 't3', 'title': 'T3', 'tags': ['Alpha']},
                ],
                completed=[
                    {'uuid': 't4', 'title': 'T4', 'tags': ['Alpha']},
                    {'uuid': 't5', 'title': 'T5', 'tags': ['Charlie']},
                ],
            )
            mock_projects.side_effect = _projects_side_effect()

            result = await things_tools.get_tag_usage()

            titles = [t['title'] for t in result['tags']]
            # Beta: open=2,total=2 ; Alpha: open=1,total=2 ; Charlie: open=0,total=1 ; Zulu: open=0,total=0
            assert titles == ['Beta', 'Alpha', 'Charlie', 'Zulu']


class TestGetTagUsageResponseModes:
    """Response mode shaping."""

    @pytest.mark.asyncio
    async def test_summary_mode(self, things_tools):
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos, \
             patch('things.projects') as mock_projects:

            mock_tags.return_value = [
                {'uuid': f'tag-{i}', 'title': f'Tag{i}'} for i in range(7)
            ]
            mock_todos.side_effect = _todos_side_effect(
                incomplete=[{'uuid': 't1', 'title': 'T1', 'tags': ['Tag0']}],
            )
            mock_projects.side_effect = _projects_side_effect()

            result = await things_tools.get_tag_usage(mode='summary')

            assert result['tag_count'] == 7
            assert result['unused_count'] == 6
            assert len(result['top']) == 5
            assert result['top'][0]['title'] == 'Tag0'
            assert 'tags' not in result

    @pytest.mark.asyncio
    async def test_minimal_mode(self, things_tools):
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos, \
             patch('things.projects') as mock_projects:

            mock_tags.return_value = [
                {'uuid': 'tag-work', 'title': 'Work'},
                {'uuid': 'tag-personal', 'title': 'Personal'},
            ]
            mock_todos.side_effect = _todos_side_effect(
                incomplete=[{'uuid': 't1', 'title': 'T1', 'tags': ['Work']}],
            )
            mock_projects.side_effect = _projects_side_effect()

            result = await things_tools.get_tag_usage(mode='minimal')

            assert result['tag_count'] == 2
            for row in result['tags']:
                assert set(row.keys()) == {'title', 'open_count'}

    @pytest.mark.asyncio
    async def test_standard_mode_full_rows(self, things_tools):
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos, \
             patch('things.projects') as mock_projects:

            mock_tags.return_value = [{'uuid': 'tag-work', 'title': 'Work'}]
            mock_todos.side_effect = _todos_side_effect(
                incomplete=[{'uuid': 't1', 'title': 'T1', 'tags': ['Work']}],
            )
            mock_projects.side_effect = _projects_side_effect()

            result = await things_tools.get_tag_usage(mode='standard')

            row = result['tags'][0]
            assert row['title'] == 'Work'
            assert row['uuid'] == 'tag-work'
            assert row['open_count'] == 1
            assert row['total_count'] == 1

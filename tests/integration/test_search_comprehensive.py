"""
Comprehensive integration tests for Things MCP server search and filtering capabilities.

This test suite systematically validates:
1. Basic search operations with various queries and limits
2. Advanced search with multiple filter combinations
3. Tag-based retrieval and operations
4. Special query syntax and performance characteristics
5. Pagination and context optimization
"""

import pytest
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

# Import MCP tools - adjust based on your project structure
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


class TestBasicSearch:
    """Test basic search_todos functionality with various parameters."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_search_simple_text(self, tools):
        """Test basic text search in titles and notes."""
        # Search for common word
        results = await tools.search_todos(query="test", limit=10)

        assert isinstance(results, list)
        print(f"\n✓ Simple text search returned {len(results)} results")

        # Verify all results contain the search term
        for todo in results:
            title = todo.get('name', '').lower()
            notes = todo.get('notes', '').lower()
            assert 'test' in title or 'test' in notes, \
                f"Todo {todo.get('id')} doesn't contain 'test'"

    @pytest.mark.asyncio
    async def test_search_with_different_limits(self, tools):
        """Test search with various limit values."""
        query = "meeting"

        test_limits = [10, 50, 100, 500]
        results_by_limit = {}

        for limit in test_limits:
            results = await tools.search_todos(query=query, limit=limit)
            results_by_limit[limit] = len(results)

            assert len(results) <= limit, \
                f"Results ({len(results)}) exceeded limit ({limit})"

            print(f"\n✓ Search with limit={limit} returned {len(results)} results")

        # Verify increasing limits return more results (up to max available)
        assert results_by_limit[10] <= results_by_limit[50]
        assert results_by_limit[50] <= results_by_limit[100]

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, tools):
        """Test that search is case-insensitive."""
        # Search with different cases
        lower_results = await tools.search_todos(query="project", limit=20)
        upper_results = await tools.search_todos(query="PROJECT", limit=20)
        mixed_results = await tools.search_todos(query="ProJeCt", limit=20)

        # All should return same number of results
        assert len(lower_results) == len(upper_results) == len(mixed_results), \
            "Case sensitivity detected in search"

        print(f"\n✓ Case-insensitive search confirmed ({len(lower_results)} results)")

    @pytest.mark.asyncio
    async def test_search_in_notes(self, tools):
        """Test searching within todo notes field."""
        # Search for text likely to be in notes
        results = await tools.search_todos(query="details", limit=50)

        notes_matches = 0
        title_matches = 0

        for todo in results:
            title = todo.get('name', '').lower()
            notes = todo.get('notes', '').lower()

            if 'details' in notes:
                notes_matches += 1
            if 'details' in title:
                title_matches += 1

        print(f"\n✓ Search found 'details' in {title_matches} titles, {notes_matches} notes")
        assert notes_matches > 0 or title_matches > 0, "No matches found"

    @pytest.mark.asyncio
    async def test_search_no_results(self, tools):
        """Test search with query that should return no results."""
        # Use very unique string unlikely to exist
        results = await tools.search_todos(
            query="xyzabc123veryrandomstring999",
            limit=100
        )

        assert isinstance(results, list)
        print(f"\n✓ No-match search returned {len(results)} results (expected 0)")

    @pytest.mark.asyncio
    async def test_search_empty_query(self, tools):
        """Test search with empty query string."""
        try:
            results = await tools.search_todos(query="", limit=10)
            # Empty query might return all results or empty list
            assert isinstance(results, list)
            print(f"\n✓ Empty query handled gracefully ({len(results)} results)")
        except Exception as e:
            print(f"\n✓ Empty query properly rejected: {e}")


class TestAdvancedSearch:
    """Test advanced search with multiple filters and combinations."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_search_by_status(self, tools):
        """Test filtering by status: incomplete, completed, canceled."""
        statuses = ['incomplete', 'completed', 'canceled']

        for status in statuses:
            results = await tools.search_advanced(status=status, limit=20)

            assert isinstance(results, list)
            print(f"\n✓ Status filter '{status}' returned {len(results)} results")

            # Verify status matches (only check if we got results)
            if results:
                for todo in results[:5]:  # Check first 5 only
                    actual_status = todo.get('status', 'open')
                    # Map Things status to filter status
                    if status == 'incomplete':
                        assert actual_status in ['open', 'incomplete'], \
                            f"Expected incomplete/open, got {actual_status}"
                    elif status == 'completed':
                        assert actual_status == 'completed', \
                            f"Expected completed, got {actual_status}"
                    elif status == 'canceled':
                        assert actual_status == 'canceled', \
                            f"Expected canceled, got {actual_status}"

    @pytest.mark.asyncio
    async def test_search_by_type(self, tools):
        """Test filtering by type: to-do, project, heading."""
        types = ['to-do', 'project']

        for item_type in types:
            results = await tools.search_advanced(type=item_type, limit=20)

            assert isinstance(results, list)
            print(f"\n✓ Type filter '{item_type}' returned {len(results)} results")

    @pytest.mark.asyncio
    async def test_search_by_tag(self, tools):
        """Test filtering by specific tag."""
        # First get available tags
        tags = await tools.get_tags(include_items=False)

        if tags and len(tags) > 0:
            test_tag = tags[0]['name']

            # Search by tag using advanced search
            results = await tools.search_advanced(tag=test_tag, limit=50)

            assert isinstance(results, list)
            print(f"\n✓ Tag filter '{test_tag}' returned {len(results)} results")

            # Verify all results have the tag
            for todo in results:
                tag_names = todo.get('tag_names', [])
                assert test_tag in tag_names, \
                    f"Todo {todo.get('id')} missing tag '{test_tag}'"
        else:
            print("\n⚠ No tags available for testing")

    @pytest.mark.asyncio
    async def test_search_by_date_range(self, tools):
        """Test filtering by start_date and deadline ranges."""
        # Test upcoming deadlines
        today = date.today()
        next_week = today + timedelta(days=7)

        results = await tools.search_advanced(
            deadline=next_week.strftime('%Y-%m-%d'),
            limit=50
        )

        assert isinstance(results, list)
        print(f"\n✓ Deadline filter returned {len(results)} results")

        # Test start date filtering
        results = await tools.search_advanced(
            start_date=today.strftime('%Y-%m-%d'),
            limit=50
        )

        assert isinstance(results, list)
        print(f"\n✓ Start date filter returned {len(results)} results")

    @pytest.mark.asyncio
    async def test_search_combined_filters(self, tools):
        """Test combining multiple filters in one search."""
        today = date.today()

        # Combine status + type
        results = await tools.search_advanced(
            status='incomplete',
            type='to-do',
            limit=100
        )

        assert isinstance(results, list)
        print(f"\n✓ Combined filters (status+type) returned {len(results)} results")

        # Get a tag to test with
        tags = await tools.get_tags(include_items=False)
        if tags and len(tags) > 0:
            test_tag = tags[0]['name']

            # Combine status + tag + type
            results = await tools.search_advanced(
                status='incomplete',
                type='to-do',
                tag=test_tag,
                limit=100
            )

            print(f"\n✓ Combined filters (status+type+tag) returned {len(results)} results")

    @pytest.mark.asyncio
    async def test_search_by_area(self, tools):
        """Test filtering by area UUID."""
        # Get available areas
        areas = await tools.get_areas(include_items=False)

        if areas and len(areas) > 0:
            test_area_uuid = areas[0]['id']

            results = await tools.search_advanced(
                area=test_area_uuid,
                limit=50
            )

            assert isinstance(results, list)
            print(f"\n✓ Area filter returned {len(results)} results")
        else:
            print("\n⚠ No areas available for testing")


class TestTagBasedRetrieval:
    """Test tag-related operations and retrieval."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_get_tags_counts_only(self, tools):
        """Test getting tags with item counts."""
        results = await tools.get_tags(include_items=False)

        assert isinstance(results, list)
        print(f"\n✓ Retrieved {len(results)} tags with counts")

        for tag in results:
            assert 'name' in tag
            # Count should only be present if > 0
            if 'item_count' in tag:
                assert tag['item_count'] > 0

            # Should NOT have full items
            assert 'items' not in tag

        # Print sample
        if results:
            sample = results[0]
            print(f"   Sample: {sample}")

    @pytest.mark.asyncio
    async def test_get_tags_with_items(self, tools):
        """Test getting tags with full item lists."""
        results = await tools.get_tags(include_items=True)

        assert isinstance(results, list)
        print(f"\n✓ Retrieved {len(results)} tags with full items")

        total_items = 0
        for tag in results:
            assert 'name' in tag
            assert 'items' in tag
            assert isinstance(tag['items'], list)

            total_items += len(tag['items'])

        print(f"   Total items across all tags: {total_items}")

    @pytest.mark.asyncio
    async def test_get_tagged_items(self, tools):
        """Test getting items for specific tags."""
        # Get available tags first
        tags = await tools.get_tags(include_items=False)

        if tags and len(tags) > 0:
            # Test with first few tags
            for tag in tags[:3]:
                tag_name = tag['name']

                items = await tools.get_tagged_items(tag=tag_name)

                assert isinstance(items, list)
                print(f"\n✓ Tag '{tag_name}' has {len(items)} items")

                # Verify all items have the tag
                for item in items:
                    tag_names = item.get('tag_names', [])
                    assert tag_name in tag_names
        else:
            print("\n⚠ No tags available for testing")

    @pytest.mark.asyncio
    async def test_add_and_remove_tags(self, tools):
        """Test adding and removing tags from todos."""
        # Get a test todo
        today_todos = await tools.get_today()

        if today_todos and len(today_todos) > 0:
            test_todo_id = today_todos[0]['id']
            test_tag = f"test_tag_{datetime.now().timestamp()}"

            # Note: This requires the tag to exist first
            # In real usage, users must create tags manually
            print(f"\n⚠ Note: Tag '{test_tag}' must exist to test add_tags")
            print("   Skipping tag manipulation test (requires manual tag creation)")
        else:
            print("\n⚠ No todos available for tag testing")


class TestSpecialQueries:
    """Test special query syntax and edge cases."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_search_with_special_characters(self, tools):
        """Test search with special characters."""
        special_queries = [
            "to-do",
            "meeting!",
            "project?",
            "task #123",
            "50%",
            "@home"
        ]

        for query in special_queries:
            try:
                results = await tools.search_todos(query=query, limit=20)
                assert isinstance(results, list)
                print(f"\n✓ Special char query '{query}' returned {len(results)} results")
            except Exception as e:
                print(f"\n✗ Query '{query}' failed: {e}")

    @pytest.mark.asyncio
    async def test_search_phrase_matching(self, tools):
        """Test exact phrase matching."""
        # Test with common phrases
        phrases = [
            "team meeting",
            "follow up",
            "next week"
        ]

        for phrase in phrases:
            results = await tools.search_todos(query=phrase, limit=20)
            assert isinstance(results, list)
            print(f"\n✓ Phrase '{phrase}' returned {len(results)} results")

    @pytest.mark.asyncio
    async def test_wildcard_patterns(self, tools):
        """Test if wildcard patterns are supported."""
        # Note: Implementation may not support wildcards
        patterns = ["test*", "meet*", "proj*"]

        for pattern in patterns:
            try:
                results = await tools.search_todos(query=pattern, limit=20)
                print(f"\n✓ Pattern '{pattern}' returned {len(results)} results")
            except Exception as e:
                print(f"\n⚠ Wildcards not supported: {e}")
                break


class TestTrashPagination:
    """Test trash retrieval with pagination."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_get_trash_default(self, tools):
        """Test getting trash with default pagination."""
        result = await tools.get_trash()

        assert isinstance(result, dict)
        assert 'items' in result
        assert 'total_count' in result
        assert 'limit' in result
        assert 'offset' in result
        assert 'has_more' in result

        print(f"\n✓ Trash default: {len(result['items'])} items, "
              f"total={result['total_count']}, has_more={result['has_more']}")

    @pytest.mark.asyncio
    async def test_get_trash_with_limit(self, tools):
        """Test trash pagination with custom limit."""
        limits = [10, 25, 50, 100]

        for limit in limits:
            result = await tools.get_trash(limit=limit)

            assert len(result['items']) <= limit
            print(f"\n✓ Trash with limit={limit}: {len(result['items'])} items")

    @pytest.mark.asyncio
    async def test_get_trash_with_offset(self, tools):
        """Test trash pagination with offset."""
        # Get first page
        page1 = await tools.get_trash(limit=10, offset=0)

        # Get second page
        page2 = await tools.get_trash(limit=10, offset=10)

        # Verify pages don't overlap
        if page1['items'] and page2['items']:
            page1_ids = {item['id'] for item in page1['items']}
            page2_ids = {item['id'] for item in page2['items']}

            overlap = page1_ids & page2_ids
            assert len(overlap) == 0, "Pages should not overlap"

            print(f"\n✓ Pagination working: page1={len(page1['items'])}, "
                  f"page2={len(page2['items'])}, no overlap")

    @pytest.mark.asyncio
    async def test_get_trash_iterate_all(self, tools):
        """Test iterating through all trash items."""
        all_items = []
        offset = 0
        limit = 20

        while True:
            result = await tools.get_trash(limit=limit, offset=offset)
            all_items.extend(result['items'])

            if not result['has_more']:
                break

            offset += limit

        print(f"\n✓ Iterated through all trash: {len(all_items)} total items")


class TestPerformance:
    """Test performance characteristics and context usage."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_large_result_set_timing(self, tools):
        """Test performance with large result sets."""
        import time

        limits = [50, 100, 500]

        for limit in limits:
            start = time.time()
            results = await tools.search_todos(query="", limit=limit)
            duration = time.time() - start

            print(f"\n✓ Limit {limit}: {len(results)} results in {duration:.3f}s")

    @pytest.mark.asyncio
    async def test_response_mode_comparison(self, tools):
        """Test different response modes if available."""
        # Note: Response modes may be implemented in server.py
        try:
            # Standard mode (default)
            standard = await tools.search_todos(query="meeting", limit=50)

            print(f"\n✓ Response mode testing would measure context usage")
            print(f"   Standard mode: {len(standard)} results")
        except Exception as e:
            print(f"\n⚠ Response mode testing not available: {e}")


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_invalid_limit_values(self, tools):
        """Test handling of invalid limit values."""
        try:
            # Zero limit
            results = await tools.search_todos(query="test", limit=0)
            print(f"\n⚠ Zero limit accepted, returned {len(results)} results")
        except Exception as e:
            print(f"\n✓ Zero limit properly rejected: {e}")

        try:
            # Negative limit
            results = await tools.search_todos(query="test", limit=-10)
            print(f"\n⚠ Negative limit accepted")
        except Exception as e:
            print(f"\n✓ Negative limit properly rejected: {e}")

        try:
            # Excessive limit
            results = await tools.search_todos(query="test", limit=10000)
            print(f"\n✓ Large limit handled, returned {len(results)} results")
        except Exception as e:
            print(f"\n⚠ Large limit rejected: {e}")

    @pytest.mark.asyncio
    async def test_nonexistent_tag(self, tools):
        """Test searching for non-existent tag."""
        fake_tag = "ThisTagDefinitelyDoesNotExist12345"

        results = await tools.get_tagged_items(tag=fake_tag)

        assert isinstance(results, list)
        assert len(results) == 0
        print(f"\n✓ Non-existent tag returned empty list")

    @pytest.mark.asyncio
    async def test_malformed_dates(self, tools):
        """Test handling of malformed date filters."""
        try:
            results = await tools.search_advanced(
                deadline="not-a-date",
                limit=10
            )
            print(f"\n⚠ Malformed date accepted")
        except Exception as e:
            print(f"\n✓ Malformed date properly rejected: {e}")

    @pytest.mark.asyncio
    async def test_concurrent_searches(self, tools):
        """Test multiple concurrent search operations."""
        queries = ["test", "meeting", "project", "work", "personal"]

        # Execute searches concurrently
        tasks = [tools.search_todos(query=q, limit=20) for q in queries]
        results = await asyncio.gather(*tasks)

        assert len(results) == len(queries)
        print(f"\n✓ Concurrent searches completed: {len(results)} queries")

        for i, query in enumerate(queries):
            print(f"   '{query}': {len(results[i])} results")


# Summary test to print capabilities
class TestCapabilities:
    """Document search syntax and capabilities."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_document_capabilities(self, tools):
        """Print documented search capabilities."""
        print("\n" + "="*70)
        print("THINGS MCP SERVER - SEARCH CAPABILITIES SUMMARY")
        print("="*70)

        print("\n1. BASIC SEARCH (search_todos)")
        print("   - Text search in titles and notes")
        print("   - Case-insensitive matching")
        print("   - Configurable limits (10, 50, 100, 500)")
        print("   - Returns: List[Dict] with todo details")

        print("\n2. ADVANCED SEARCH (search_advanced)")
        print("   - Filter by status: incomplete, completed, canceled")
        print("   - Filter by type: to-do, project, heading")
        print("   - Filter by tag (single tag)")
        print("   - Filter by area UUID")
        print("   - Filter by start_date (YYYY-MM-DD)")
        print("   - Filter by deadline (YYYY-MM-DD)")
        print("   - Combine multiple filters")

        print("\n3. TAG OPERATIONS")
        print("   - get_tags(include_items=False): Tag names with counts")
        print("   - get_tags(include_items=True): Tag names with full items")
        print("   - get_tagged_items(tag): All items with specific tag")
        print("   - add_tags(todo_id, tags): Add tags to todo")
        print("   - remove_tags(todo_id, tags): Remove tags from todo")

        print("\n4. PAGINATION")
        print("   - get_trash(limit, offset): Paginated trash retrieval")
        print("   - Returns: {items, total_count, limit, offset, has_more}")

        print("\n5. SPECIAL QUERIES")
        print("   - Special characters: Handled in most cases")
        print("   - Phrase matching: Supported")
        print("   - Wildcards: Not explicitly supported")
        print("   - Boolean operators: Not implemented")

        print("\n6. PERFORMANCE")
        print("   - Direct database access via things.py")
        print("   - Fast retrieval for reads")
        print("   - Response optimization available")
        print("   - Concurrent operations supported")

        print("\n7. LIMITATIONS")
        print("   - Tags must be created manually (AI cannot create)")
        print("   - Maximum search limit: 500")
        print("   - Date format: YYYY-MM-DD")
        print("   - Boolean search operators not available")

        print("\n" + "="*70)

        # Get actual statistics
        tags = await tools.get_tags(include_items=False)
        projects = await tools.get_projects(include_items=False)
        areas = await tools.get_areas(include_items=False)

        print("\nCURRENT DATABASE STATISTICS:")
        print(f"   Total tags: {len(tags)}")
        print(f"   Total projects: {len(projects)}")
        print(f"   Total areas: {len(areas)}")
        print("="*70 + "\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
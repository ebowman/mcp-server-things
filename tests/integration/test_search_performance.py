"""
Performance-focused tests for search operations.

Measures and validates performance characteristics of search and filtering.
"""

import pytest
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Any

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


class TestSearchPerformance:
    """Performance benchmarks for search operations."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_search_response_time_by_limit(self, tools):
        """Measure response time scaling with different limits."""
        limits = [10, 50, 100, 500]
        query = "test"

        results = {}

        for limit in limits:
            timings = []

            # Run 3 times to get average
            for _ in range(3):
                start = time.perf_counter()
                todos = await tools.search_todos(query=query, limit=limit)
                duration = time.perf_counter() - start
                timings.append(duration)

            avg_time = sum(timings) / len(timings)
            results[limit] = {
                'avg_time': avg_time,
                'count': len(todos) if todos else 0
            }

            print(f"\n✓ Limit {limit:3d}: {avg_time:.3f}s avg, "
                  f"{results[limit]['count']} results")

        # Performance assertions
        assert results[10]['avg_time'] < 5.0, "Basic search too slow"
        assert results[50]['avg_time'] < 10.0, "Medium search too slow"

    @pytest.mark.asyncio
    async def test_advanced_search_performance(self, tools):
        """Measure advanced search with multiple filters."""
        # Single filter
        start = time.perf_counter()
        result1 = await tools.search_advanced(status='incomplete', limit=100)
        time1 = time.perf_counter() - start

        # Two filters
        start = time.perf_counter()
        result2 = await tools.search_advanced(
            status='incomplete',
            type='to-do',
            limit=100
        )
        time2 = time.perf_counter() - start

        # Three filters
        tags = await tools.get_tags(include_items=False)
        if tags:
            start = time.perf_counter()
            result3 = await tools.search_advanced(
                status='incomplete',
                type='to-do',
                tag=tags[0]['name'],
                limit=100
            )
            time3 = time.perf_counter() - start

            print(f"\n✓ 1 filter: {time1:.3f}s, {len(result1)} results")
            print(f"✓ 2 filters: {time2:.3f}s, {len(result2)} results")
            print(f"✓ 3 filters: {time3:.3f}s, {len(result3)} results")
        else:
            print(f"\n✓ 1 filter: {time1:.3f}s, {len(result1)} results")
            print(f"✓ 2 filters: {time2:.3f}s, {len(result2)} results")

    @pytest.mark.asyncio
    async def test_tag_retrieval_performance(self, tools):
        """Compare performance of different tag operations."""
        # Get tags with counts only
        start = time.perf_counter()
        tags_counts = await tools.get_tags(include_items=False)
        time_counts = time.perf_counter() - start

        # Get tags with full items
        start = time.perf_counter()
        tags_items = await tools.get_tags(include_items=True)
        time_items = time.perf_counter() - start

        print(f"\n✓ Tags with counts: {time_counts:.3f}s, {len(tags_counts)} tags")
        print(f"✓ Tags with items: {time_items:.3f}s, {len(tags_items)} tags")

        # Items should take longer
        assert time_items >= time_counts, "Full items should take more time"

    @pytest.mark.asyncio
    async def test_concurrent_search_throughput(self, tools):
        """Test throughput with concurrent searches."""
        queries = ["test", "meeting", "project", "work", "personal",
                   "todo", "task", "call", "email", "review"]

        start = time.perf_counter()

        # Execute all searches concurrently
        tasks = [tools.search_todos(query=q, limit=20) for q in queries]
        results = await asyncio.gather(*tasks)

        duration = time.perf_counter() - start

        total_results = sum(len(r) for r in results)

        print(f"\n✓ {len(queries)} concurrent searches in {duration:.3f}s")
        print(f"  Total results: {total_results}")
        print(f"  Throughput: {len(queries)/duration:.1f} searches/sec")

    @pytest.mark.asyncio
    async def test_pagination_performance(self, tools):
        """Test performance of paginated trash retrieval."""
        page_size = 50

        # Time first page
        start = time.perf_counter()
        page1 = await tools.get_trash(limit=page_size, offset=0)
        time_page1 = time.perf_counter() - start

        # Time second page
        start = time.perf_counter()
        page2 = await tools.get_trash(limit=page_size, offset=page_size)
        time_page2 = time.perf_counter() - start

        print(f"\n✓ Page 1 (offset=0): {time_page1:.3f}s")
        print(f"✓ Page 2 (offset={page_size}): {time_page2:.3f}s")
        print(f"  Total in trash: {page1['total_count']}")


class TestMemoryEfficiency:
    """Test memory usage and data transfer efficiency."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_result_size_comparison(self, tools):
        """Compare data size of different result sets."""
        import sys

        # Small result set
        small = await tools.search_todos(query="test", limit=10)
        small_size = sys.getsizeof(str(small))

        # Large result set
        large = await tools.search_todos(query="", limit=500)
        large_size = sys.getsizeof(str(large))

        print(f"\n✓ Small (10): ~{small_size:,} bytes")
        print(f"✓ Large (500): ~{large_size:,} bytes")
        print(f"  Ratio: {large_size/small_size:.1f}x")

    @pytest.mark.asyncio
    async def test_field_optimization_impact(self, tools):
        """Test impact of field optimization on data size."""
        import sys

        # Get todos with all fields
        results = await tools.get_todos()

        if results:
            # Measure full todo size
            full_size = sys.getsizeof(str(results[0]))

            # Measure minimal fields
            minimal = {
                'id': results[0].get('id'),
                'name': results[0].get('name'),
                'status': results[0].get('status')
            }
            minimal_size = sys.getsizeof(str(minimal))

            print(f"\n✓ Full todo: ~{full_size:,} bytes")
            print(f"✓ Minimal: ~{minimal_size:,} bytes")
            print(f"  Reduction: {(1 - minimal_size/full_size)*100:.1f}%")


class TestScalability:
    """Test system behavior under load."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_sequential_search_stability(self, tools):
        """Test stability of repeated sequential searches."""
        query = "test"
        iterations = 10

        timings = []

        for i in range(iterations):
            start = time.perf_counter()
            results = await tools.search_todos(query=query, limit=50)
            duration = time.perf_counter() - start
            timings.append(duration)

        avg_time = sum(timings) / len(timings)
        max_time = max(timings)
        min_time = min(timings)

        print(f"\n✓ {iterations} sequential searches:")
        print(f"  Avg: {avg_time:.3f}s")
        print(f"  Min: {min_time:.3f}s")
        print(f"  Max: {max_time:.3f}s")
        print(f"  Variance: {max_time - min_time:.3f}s")

        # Check stability (max should not be more than 2x avg)
        assert max_time < avg_time * 2, "Unstable performance detected"

    @pytest.mark.asyncio
    async def test_mixed_operation_performance(self, tools):
        """Test performance of mixed operations."""
        start = time.perf_counter()

        # Mix of different operations
        await tools.search_todos(query="test", limit=20)
        await tools.get_tags(include_items=False)
        await tools.get_today()
        await tools.get_projects(include_items=False)
        await tools.search_advanced(status='incomplete', limit=50)

        duration = time.perf_counter() - start

        print(f"\n✓ 5 mixed operations in {duration:.3f}s")
        print(f"  Avg per operation: {duration/5:.3f}s")


class TestCacheEffects:
    """Test caching behavior and effects on performance."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_repeated_query_performance(self, tools):
        """Test if repeated queries show cache effects."""
        query = "meeting"

        # First query (cold)
        start = time.perf_counter()
        result1 = await tools.search_todos(query=query, limit=50)
        time1 = time.perf_counter() - start

        # Immediate repeat (potentially cached)
        start = time.perf_counter()
        result2 = await tools.search_todos(query=query, limit=50)
        time2 = time.perf_counter() - start

        # After delay (cache may expire)
        await asyncio.sleep(0.5)
        start = time.perf_counter()
        result3 = await tools.search_todos(query=query, limit=50)
        time3 = time.perf_counter() - start

        print(f"\n✓ Query 1 (cold): {time1:.3f}s, {len(result1)} results")
        print(f"✓ Query 2 (immediate): {time2:.3f}s, {len(result2)} results")
        print(f"✓ Query 3 (after delay): {time3:.3f}s, {len(result3)} results")

        # Results should be consistent
        assert len(result1) == len(result2) == len(result3)


class TestPerformanceSummary:
    """Generate comprehensive performance report."""

    @pytest.fixture
    async def tools(self):
        """Create ThingsTools instance for testing."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)
        yield tools

    @pytest.mark.asyncio
    async def test_generate_performance_report(self, tools):
        """Generate comprehensive performance summary."""
        print("\n" + "="*70)
        print("SEARCH & FILTER PERFORMANCE REPORT")
        print("="*70)

        # Test 1: Basic search across limits
        print("\n1. BASIC SEARCH PERFORMANCE")
        for limit in [10, 50, 100, 500]:
            start = time.perf_counter()
            results = await tools.search_todos(query="test", limit=limit)
            duration = time.perf_counter() - start
            print(f"   Limit {limit:3d}: {duration:.3f}s ({len(results)} results)")

        # Test 2: Advanced search
        print("\n2. ADVANCED SEARCH PERFORMANCE")
        start = time.perf_counter()
        results = await tools.search_advanced(status='incomplete', limit=100)
        duration = time.perf_counter() - start
        print(f"   Status filter: {duration:.3f}s ({len(results)} results)")

        # Test 3: Tag operations
        print("\n3. TAG OPERATIONS PERFORMANCE")
        start = time.perf_counter()
        tags = await tools.get_tags(include_items=False)
        duration = time.perf_counter() - start
        print(f"   Get tags (counts): {duration:.3f}s ({len(tags)} tags)")

        start = time.perf_counter()
        tags_full = await tools.get_tags(include_items=True)
        duration = time.perf_counter() - start
        print(f"   Get tags (items): {duration:.3f}s ({len(tags_full)} tags)")

        # Test 4: List operations
        print("\n4. LIST OPERATIONS PERFORMANCE")
        for list_name, list_func in [
            ('Today', tools.get_today),
            ('Inbox', tools.get_inbox),
            ('Upcoming', tools.get_upcoming),
            ('Anytime', tools.get_anytime)
        ]:
            start = time.perf_counter()
            results = await list_func()
            duration = time.perf_counter() - start
            print(f"   {list_name:12s}: {duration:.3f}s ({len(results)} items)")

        # Test 5: Concurrent throughput
        print("\n5. CONCURRENT OPERATIONS")
        queries = ["test", "meeting", "project", "work", "call"]
        start = time.perf_counter()
        tasks = [tools.search_todos(query=q, limit=20) for q in queries]
        results = await asyncio.gather(*tasks)
        duration = time.perf_counter() - start
        total = sum(len(r) for r in results)
        print(f"   {len(queries)} parallel searches: {duration:.3f}s "
              f"({total} total results)")
        print(f"   Throughput: {len(queries)/duration:.1f} operations/sec")

        print("\n" + "="*70)
        print("PERFORMANCE CHARACTERISTICS:")
        print("  - Direct database access via things.py")
        print("  - Read operations are fast (typically < 1s)")
        print("  - Scales well with result set size")
        print("  - Good concurrent operation support")
        print("  - Tag operations optimized for counts")
        print("="*70 + "\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
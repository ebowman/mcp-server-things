"""Tests for hq-nxu.14: normalizing things.py date/datetime strings consistently.

Covers:
  1. ToolsHelpers.parse_things_datetime - the shared normalization helper.
  2. get_logbook (_get_logbook_sync) and get_recent using that helper, with
     both naive-local and timezone-aware 'stop_date'/'created' values, to
     confirm aware values no longer raise TypeError and get silently dropped.
"""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import Mock, patch

from things_mcp.tools_helpers.helpers import ToolsHelpers
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


class TestParseThingsDatetime:
    """Unit tests for the ToolsHelpers.parse_things_datetime normalization helper."""

    def test_naive_local_string(self):
        dt = ToolsHelpers.parse_things_datetime('2025-12-31 09:00:00')
        assert dt == datetime(2025, 12, 31, 9, 0, 0)
        assert dt.tzinfo is None

    def test_aware_string_with_z_suffix(self):
        """A 'Z'-suffixed (UTC) string must not raise and must return naive-local."""
        dt = ToolsHelpers.parse_things_datetime('2025-12-31T09:00:00Z')
        assert dt.tzinfo is None
        # Compare against the equivalent aware instant converted to local time.
        expected = datetime(2025, 12, 31, 9, 0, 0, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        assert dt == expected

    def test_aware_string_with_explicit_offset(self):
        dt = ToolsHelpers.parse_things_datetime('2025-12-31T09:00:00+02:00')
        assert dt.tzinfo is None
        expected = datetime(2025, 12, 31, 9, 0, 0, tzinfo=timezone(timedelta(hours=2))).astimezone().replace(tzinfo=None)
        assert dt == expected

    def test_passthrough_naive_datetime(self):
        naive = datetime(2025, 1, 1, 12, 0, 0)
        assert ToolsHelpers.parse_things_datetime(naive) == naive

    def test_passthrough_aware_datetime_converted_to_naive_local(self):
        aware = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = ToolsHelpers.parse_things_datetime(aware)
        assert result.tzinfo is None
        assert result == aware.astimezone().replace(tzinfo=None)

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError):
            ToolsHelpers.parse_things_datetime('not-a-date')

    def test_non_str_non_datetime_raises_type_error(self):
        with pytest.raises(TypeError):
            ToolsHelpers.parse_things_datetime(12345)

    def test_naive_and_aware_compare_consistently_against_cutoff(self):
        """A naive-local timestamp and its aware-UTC equivalent must normalize
        to the same value and therefore compare identically against a cutoff -
        this is the core bug this bead fixes (aware values used to raise
        TypeError against a naive cutoff and be silently dropped)."""
        naive_str = '2025-06-15 10:30:00'
        naive_dt = ToolsHelpers.parse_things_datetime(naive_str)

        # Build the aware-UTC equivalent of that same local wall-clock time.
        local_dt = datetime(2025, 6, 15, 10, 30, 0)
        aware_utc_equivalent = local_dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        aware_dt = ToolsHelpers.parse_things_datetime(aware_utc_equivalent)

        assert naive_dt == aware_dt


@pytest.fixture
def mock_applescript_manager():
    return Mock(spec=AppleScriptManager)


@pytest.fixture
def things_tools(mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


class TestGetLogbookDateNormalization:
    """get_logbook must not silently drop rows whose stop_date is aware."""

    @pytest.mark.asyncio
    async def test_naive_and_aware_stop_dates_both_included(self, things_tools):
        now = datetime.now()
        recent_naive = (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        # Aware-UTC equivalent of "1 day ago, local time" expressed with a 'Z' suffix.
        recent_aware = (now - timedelta(days=1)).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'c1', 'title': 'Naive stop_date', 'status': 'completed', 'stop_date': recent_naive, 'tags': []},
                {'uuid': 'c2', 'title': 'Aware stop_date', 'status': 'completed', 'stop_date': recent_aware, 'tags': []},
            ]

            logbook = await things_tools.get_logbook(period='7d')

            uuids = {item['uuid'] for item in logbook}
            assert uuids == {'c1', 'c2'}, (
                "Aware stop_date rows must not be silently dropped due to a "
                "naive/aware TypeError (hq-nxu.14)"
            )

    @pytest.mark.asyncio
    async def test_aware_stop_date_outside_period_is_excluded(self, things_tools):
        """Sanity check: the normalization doesn't disable the cutoff filter itself."""
        old_aware = (datetime.now() - timedelta(days=30)).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'old1', 'title': 'Too old', 'status': 'completed', 'stop_date': old_aware, 'tags': []},
            ]

            logbook = await things_tools.get_logbook(period='7d')

            assert logbook == []


class TestGetRecentDateNormalization:
    """get_recent must not silently drop rows whose created date is aware."""

    @pytest.mark.asyncio
    async def test_naive_and_aware_created_dates_both_included(self, things_tools):
        now = datetime.now()
        recent_naive = (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        recent_aware = (now - timedelta(days=1)).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

        with patch('things.tasks') as mock_tasks:
            mock_tasks.return_value = [
                {'uuid': 'r1', 'title': 'Naive created', 'type': 'to-do', 'status': 'incomplete', 'created': recent_naive, 'tags': []},
                {'uuid': 'r2', 'title': 'Aware created', 'type': 'to-do', 'status': 'incomplete', 'created': recent_aware, 'tags': []},
            ]

            recent = await things_tools.get_recent('7d')

            uuids = {item['uuid'] for item in recent}
            assert uuids == {'r1', 'r2'}, (
                "Aware created-date rows must not be silently dropped due to a "
                "naive/aware TypeError (hq-nxu.14)"
            )

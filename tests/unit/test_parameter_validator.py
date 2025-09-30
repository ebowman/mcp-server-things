"""
Unit tests for parameter validation module.
"""

import pytest
from datetime import datetime

from things_mcp.parameter_validator import (
    ParameterValidator,
    ValidationError,
    create_validation_error_response
)


class TestValidateLimit:
    """Tests for limit parameter validation."""

    def test_valid_limit_int(self):
        """Test valid integer limit."""
        result = ParameterValidator.validate_limit(50)
        assert result == 50

    def test_valid_limit_string(self):
        """Test valid string limit."""
        result = ParameterValidator.validate_limit("100")
        assert result == 100

    def test_valid_limit_float(self):
        """Test valid float limit (should be converted to int)."""
        result = ParameterValidator.validate_limit(42.7)
        assert result == 42

    def test_limit_none(self):
        """Test None limit returns None."""
        result = ParameterValidator.validate_limit(None)
        assert result is None

    def test_limit_too_low(self):
        """Test limit below minimum."""
        # Test with allow_zero=False (strict validation)
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_limit(0, min_val=1, allow_zero=False)
        assert "must be between 1 and 500" in str(exc_info.value)

    def test_limit_zero_allowed(self):
        """Test limit=0 is allowed when allow_zero=True."""
        result = ParameterValidator.validate_limit(0, min_val=1, allow_zero=True)
        assert result == 0

    def test_limit_too_high(self):
        """Test limit above maximum."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_limit(600, max_val=500)
        assert "must be between 1 and 500" in str(exc_info.value)

    def test_limit_invalid_string(self):
        """Test invalid string limit."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_limit("not_a_number")
        assert "must be a number" in str(exc_info.value)

    def test_custom_range(self):
        """Test custom min/max range."""
        result = ParameterValidator.validate_limit(50, min_val=10, max_val=100)
        assert result == 50


class TestValidateOffset:
    """Tests for offset parameter validation."""

    def test_valid_offset(self):
        """Test valid offset."""
        result = ParameterValidator.validate_offset(25)
        assert result == 25

    def test_offset_zero(self):
        """Test offset of zero."""
        result = ParameterValidator.validate_offset(0)
        assert result == 0

    def test_offset_none(self):
        """Test None offset returns 0."""
        result = ParameterValidator.validate_offset(None)
        assert result == 0

    def test_offset_negative(self):
        """Test negative offset."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_offset(-5)
        assert "must be >= 0" in str(exc_info.value)

    def test_offset_string(self):
        """Test string offset."""
        result = ParameterValidator.validate_offset("10")
        assert result == 10


class TestValidateDays:
    """Tests for days parameter validation."""

    def test_valid_days(self):
        """Test valid days."""
        result = ParameterValidator.validate_days(30)
        assert result == 30

    def test_days_none(self):
        """Test None days raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_days(None)
        assert "is required" in str(exc_info.value)

    def test_days_too_low(self):
        """Test days below minimum."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_days(0)
        assert "must be between 1 and 365" in str(exc_info.value)

    def test_days_too_high(self):
        """Test days above maximum."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_days(400)
        assert "must be between 1 and 365" in str(exc_info.value)

    def test_days_string(self):
        """Test string days."""
        result = ParameterValidator.validate_days("7")
        assert result == 7


class TestValidateBoolean:
    """Tests for boolean parameter validation."""

    def test_boolean_true(self):
        """Test True value."""
        result = ParameterValidator.validate_boolean(True)
        assert result is True

    def test_boolean_false(self):
        """Test False value."""
        result = ParameterValidator.validate_boolean(False)
        assert result is False

    def test_boolean_none(self):
        """Test None returns None."""
        result = ParameterValidator.validate_boolean(None)
        assert result is None

    def test_string_true_variations(self):
        """Test various string representations of True."""
        for value in ['true', 'True', 'TRUE', 'yes', 'Yes', 'YES', '1', 't', 'T', 'y', 'Y']:
            result = ParameterValidator.validate_boolean(value)
            assert result is True, f"Failed for value: {value}"

    def test_string_false_variations(self):
        """Test various string representations of False."""
        for value in ['false', 'False', 'FALSE', 'no', 'No', 'NO', '0', 'f', 'F', 'n', 'N']:
            result = ParameterValidator.validate_boolean(value)
            assert result is False, f"Failed for value: {value}"

    def test_numeric_boolean(self):
        """Test numeric values."""
        assert ParameterValidator.validate_boolean(1) is True
        assert ParameterValidator.validate_boolean(0) is False

    def test_invalid_string(self):
        """Test invalid string value."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_boolean("maybe")
        assert "must be a boolean value" in str(exc_info.value)


class TestValidateDateFormat:
    """Tests for date format validation."""

    def test_valid_iso_date(self):
        """Test valid ISO date."""
        result = ParameterValidator.validate_date_format("2024-12-25")
        assert result == "2024-12-25"

    def test_date_none(self):
        """Test None date returns None."""
        result = ParameterValidator.validate_date_format(None)
        assert result is None

    def test_empty_string(self):
        """Test empty string returns None."""
        result = ParameterValidator.validate_date_format("  ")
        assert result is None

    def test_relative_dates(self):
        """Test relative date strings."""
        for date_str in ['today', 'tomorrow', 'yesterday', 'someday', 'anytime']:
            result = ParameterValidator.validate_date_format(date_str, allow_relative=True)
            assert result == date_str.lower()

    def test_relative_dates_disabled(self):
        """Test relative dates when not allowed."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_date_format("today", allow_relative=False)
        assert "must be in YYYY-MM-DD format" in str(exc_info.value)

    def test_datetime_format(self):
        """Test datetime format with time component."""
        result = ParameterValidator.validate_date_format("2024-12-25@14:30")
        assert result == "2024-12-25@14:30"

    def test_invalid_date_format(self):
        """Test invalid date format."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_date_format("12/25/2024")
        assert "must be in YYYY-MM-DD format" in str(exc_info.value)

    def test_invalid_date_value(self):
        """Test invalid date value."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_date_format("2024-13-45")
        assert "is not a valid date" in str(exc_info.value)

    def test_non_string_input(self):
        """Test non-string input."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_date_format(123)
        assert "must be a string" in str(exc_info.value)


class TestValidatePeriodFormat:
    """Tests for period format validation."""

    def test_valid_periods(self):
        """Test valid period formats."""
        for period in ['7d', '1w', '2m', '1y', '30d', '12w']:
            result = ParameterValidator.validate_period_format(period)
            assert result == period

    def test_period_none(self):
        """Test None period raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_period_format(None)
        assert "is required" in str(exc_info.value)

    def test_invalid_period_format(self):
        """Test invalid period formats."""
        for period in ['7', 'd7', '7days', '1.5d', '7D']:
            with pytest.raises(ValidationError) as exc_info:
                ParameterValidator.validate_period_format(period)
            assert "must match pattern" in str(exc_info.value)

    def test_non_string_period(self):
        """Test non-string period."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_period_format(7)
        assert "must be a string" in str(exc_info.value)


class TestValidateMode:
    """Tests for mode parameter validation."""

    def test_valid_modes(self):
        """Test valid mode values."""
        for mode in ['auto', 'summary', 'minimal', 'standard', 'detailed', 'raw']:
            result = ParameterValidator.validate_mode(mode)
            assert result == mode

    def test_mode_none(self):
        """Test None mode returns None."""
        result = ParameterValidator.validate_mode(None)
        assert result is None

    def test_mode_case_insensitive(self):
        """Test mode is case-insensitive."""
        result = ParameterValidator.validate_mode("SUMMARY")
        assert result == "summary"

    def test_invalid_mode(self):
        """Test invalid mode."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_mode("invalid")
        assert "must be one of" in str(exc_info.value)


class TestValidateStatus:
    """Tests for status parameter validation."""

    def test_valid_statuses(self):
        """Test valid status values."""
        for status in ['incomplete', 'completed', 'canceled', 'open']:
            result = ParameterValidator.validate_status(status)
            assert result == status

    def test_status_none(self):
        """Test None status returns None."""
        result = ParameterValidator.validate_status(None)
        assert result is None

    def test_status_case_insensitive(self):
        """Test status is case-insensitive."""
        result = ParameterValidator.validate_status("COMPLETED")
        assert result == "completed"

    def test_invalid_status(self):
        """Test invalid status."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_status("invalid")
        assert "must be one of" in str(exc_info.value)


class TestValidateNonEmptyString:
    """Tests for non-empty string validation."""

    def test_valid_string(self):
        """Test valid non-empty string."""
        result = ParameterValidator.validate_non_empty_string("test")
        assert result == "test"

    def test_string_with_whitespace(self):
        """Test string with whitespace is trimmed."""
        result = ParameterValidator.validate_non_empty_string("  test  ")
        assert result == "test"

    def test_none_string(self):
        """Test None raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_non_empty_string(None)
        assert "is required" in str(exc_info.value)

    def test_empty_string(self):
        """Test empty string raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_non_empty_string("")
        assert "cannot be empty" in str(exc_info.value)

    def test_whitespace_only(self):
        """Test whitespace-only string raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_non_empty_string("   ")
        assert "cannot be empty" in str(exc_info.value)

    def test_non_string_input(self):
        """Test non-string input."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_non_empty_string(123)
        assert "must be a string" in str(exc_info.value)


class TestValidateTagList:
    """Tests for tag list validation."""

    def test_tag_list_from_string(self):
        """Test comma-separated tag string."""
        result = ParameterValidator.validate_tag_list("work, home, urgent")
        assert result == ["work", "home", "urgent"]

    def test_tag_list_from_list(self):
        """Test tag list."""
        result = ParameterValidator.validate_tag_list(["work", "home", "urgent"])
        assert result == ["work", "home", "urgent"]

    def test_tag_list_none(self):
        """Test None returns None."""
        result = ParameterValidator.validate_tag_list(None)
        assert result is None

    def test_empty_tag_string(self):
        """Test empty string returns None."""
        result = ParameterValidator.validate_tag_list("")
        assert result is None

    def test_empty_tag_list(self):
        """Test empty list returns None."""
        result = ParameterValidator.validate_tag_list([])
        assert result is None

    def test_tag_list_filters_empty(self):
        """Test empty tags are filtered out."""
        result = ParameterValidator.validate_tag_list("work, , urgent,  ")
        assert result == ["work", "urgent"]

    def test_tag_list_trims_whitespace(self):
        """Test tags are trimmed."""
        result = ParameterValidator.validate_tag_list("  work  ,  home  ")
        assert result == ["work", "home"]


class TestValidateIdList:
    """Tests for ID list validation."""

    def test_id_list_from_string(self):
        """Test comma-separated ID string."""
        result = ParameterValidator.validate_id_list("id1, id2, id3")
        assert result == ["id1", "id2", "id3"]

    def test_id_list_from_list(self):
        """Test ID list."""
        result = ParameterValidator.validate_id_list(["id1", "id2", "id3"])
        assert result == ["id1", "id2", "id3"]

    def test_id_list_none(self):
        """Test None raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_id_list(None)
        assert "is required" in str(exc_info.value)

    def test_empty_id_string(self):
        """Test empty string raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_id_list("")
        assert "cannot be empty" in str(exc_info.value)

    def test_id_list_filters_empty(self):
        """Test empty IDs are filtered out."""
        result = ParameterValidator.validate_id_list("id1, , id3")
        assert result == ["id1", "id3"]


class TestSanitizeString:
    """Tests for string sanitization."""

    def test_sanitize_none(self):
        """Test None returns None."""
        result = ParameterValidator.sanitize_string(None)
        assert result is None

    def test_sanitize_empty(self):
        """Test empty string returns None."""
        result = ParameterValidator.sanitize_string("")
        assert result is None

    def test_sanitize_whitespace(self):
        """Test whitespace is trimmed."""
        result = ParameterValidator.sanitize_string("  test  ")
        assert result == "test"

    def test_sanitize_max_length(self):
        """Test string is truncated to max length."""
        result = ParameterValidator.sanitize_string("a" * 100, max_length=50)
        assert len(result) == 50

    def test_sanitize_non_string(self):
        """Test non-string is converted."""
        result = ParameterValidator.sanitize_string(123)
        assert result == "123"


class TestValidateSearchParams:
    """Tests for search parameter validation."""

    def test_valid_search_params(self):
        """Test valid search parameters."""
        result = ParameterValidator.validate_search_params("test query", limit=50, mode="standard")
        assert result['query'] == "test query"
        assert result['limit'] == 50
        assert result['mode'] == "standard"

    def test_search_params_with_none(self):
        """Test search params with None values."""
        result = ParameterValidator.validate_search_params("test", limit=None, mode=None)
        assert result['query'] == "test"
        assert result['limit'] is None
        assert result['mode'] is None

    def test_search_params_invalid_limit(self):
        """Test search params with invalid limit."""
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_search_params("test", limit=1000)
        assert exc_info.value.field == "limit"


class TestValidateUpdateParams:
    """Tests for update parameter validation."""

    def test_valid_update_params(self):
        """Test valid update parameters."""
        result = ParameterValidator.validate_update_params(
            title="New Title",
            notes="New Notes",
            tags="work,home",
            when="today",
            deadline="2024-12-25",
            completed="true",
            canceled="false"
        )
        assert result['title'] == "New Title"
        assert result['notes'] == "New Notes"
        assert result['tags'] == ["work", "home"]
        assert result['when'] == "today"
        assert result['deadline'] == "2024-12-25"
        assert result['completed'] is True
        assert result['canceled'] is False

    def test_update_params_empty_values(self):
        """Test update params with empty values."""
        result = ParameterValidator.validate_update_params(title="  ", notes="")
        # Empty strings should be sanitized to None
        assert 'title' not in result or result['title'] is None
        assert 'notes' not in result or result['notes'] is None


class TestCreateValidationErrorResponse:
    """Tests for error response creation."""

    def test_create_error_response(self):
        """Test creating error response."""
        error = ValidationError("test_field", "test message", "invalid_value")
        response = create_validation_error_response(error)

        assert response['success'] is False
        assert response['error'] == "VALIDATION_ERROR"
        assert response['field'] == "test_field"
        assert response['message'] == "test message"
        assert response['invalid_value'] == "invalid_value"
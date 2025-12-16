"""Tests for events service layer."""

import pytest

from ha_cli.common.exceptions import ValidationError
from ha_cli.domains.events.service import parse_filter_expr


class TestParseFilterExpr:
    """Test filter expression parser."""

    def test_none_filter(self) -> None:
        """Test None returns None."""
        result = parse_filter_expr(None)
        assert result is None

    def test_empty_string_filter(self) -> None:
        """Test empty string returns None."""
        result = parse_filter_expr("")
        assert result is None

    def test_valid_filter(self) -> None:
        """Test valid filter expression."""
        filter_fn = parse_filter_expr("entity_id=light.office")
        assert filter_fn is not None

        # Matching event
        event = {"data": {"entity_id": "light.office"}}
        assert filter_fn(event) is True

        # Non-matching event
        event = {"data": {"entity_id": "light.kitchen"}}
        assert filter_fn(event) is False

    def test_filter_with_spaces(self) -> None:
        """Test filter with spaces around equals."""
        filter_fn = parse_filter_expr("  entity_id  =  light.office  ")
        assert filter_fn is not None

        event = {"data": {"entity_id": "light.office"}}
        assert filter_fn(event) is True

    def test_filter_with_empty_value(self) -> None:
        """Test filter with empty value is valid."""
        filter_fn = parse_filter_expr("field=")
        assert filter_fn is not None

        # Match empty string
        event = {"data": {"field": ""}}
        assert filter_fn(event) is True

        # Non-match
        event = {"data": {"field": "something"}}
        assert filter_fn(event) is False

    def test_filter_missing_equals(self) -> None:
        """Test filter without equals raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            parse_filter_expr("invalid_filter")
        assert "Use 'field=value'" in str(exc_info.value)

    def test_filter_empty_field_name(self) -> None:
        """Test filter with empty field name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            parse_filter_expr("=value")
        assert "field name cannot be empty" in str(exc_info.value)

    def test_filter_non_dict_data(self) -> None:
        """Test filter handles non-dict event data gracefully."""
        filter_fn = parse_filter_expr("field=value")
        assert filter_fn is not None

        # Event with non-dict data
        event = {"data": "string data"}
        assert filter_fn(event) is False

        # Event with None data
        event = {"data": None}
        assert filter_fn(event) is False

        # Event without data key
        event = {}
        assert filter_fn(event) is False

    def test_filter_missing_field(self) -> None:
        """Test filter returns False when field is missing."""
        filter_fn = parse_filter_expr("missing_field=value")
        assert filter_fn is not None

        event = {"data": {"other_field": "value"}}
        assert filter_fn(event) is False

    def test_filter_value_coerced_to_string(self) -> None:
        """Test filter coerces values to string for comparison."""
        filter_fn = parse_filter_expr("count=42")
        assert filter_fn is not None

        # Integer value matches string filter
        event = {"data": {"count": 42}}
        assert filter_fn(event) is True

        # String value also matches
        event = {"data": {"count": "42"}}
        assert filter_fn(event) is True

    def test_filter_multiple_equals_signs(self) -> None:
        """Test filter handles value with equals sign."""
        filter_fn = parse_filter_expr("equation=a=b+c")
        assert filter_fn is not None

        event = {"data": {"equation": "a=b+c"}}
        assert filter_fn(event) is True

    def test_filter_special_characters(self) -> None:
        """Test filter handles special characters in value."""
        filter_fn = parse_filter_expr("unique_id=00:15:8d:00:04:15:2c:d7")
        assert filter_fn is not None

        event = {"data": {"unique_id": "00:15:8d:00:04:15:2c:d7"}}
        assert filter_fn(event) is True

"""Tests for common utility functions."""

import pytest
import re

from ha_cli.common.utils import (
    compile_user_regex,
    RegexValidationError,
    get_entity_domain,
    get_entity_name,
    parse_service_call,
    sanitize_filename,
    truncate_string,
)


class TestCompileUserRegex:
    """Tests for the compile_user_regex function."""

    def test_valid_simple_pattern(self) -> None:
        """Test compiling a simple valid regex pattern."""
        pattern = compile_user_regex("light\\..*")
        assert isinstance(pattern, re.Pattern)
        assert pattern.match("light.living_room")

    def test_valid_complex_pattern(self) -> None:
        """Test compiling a complex regex with groups."""
        pattern = compile_user_regex("^sensor\\.(.*)_temperature$")
        match = pattern.match("sensor.bedroom_temperature")
        assert match is not None
        assert match.group(1) == "bedroom"

    def test_invalid_pattern_unclosed_bracket(self) -> None:
        """Test that unclosed bracket raises RegexValidationError."""
        with pytest.raises(RegexValidationError) as exc_info:
            compile_user_regex("[unclosed")
        assert "Invalid regex" in str(exc_info.value)
        assert "[unclosed" in str(exc_info.value)

    def test_invalid_pattern_bad_escape(self) -> None:
        """Test that invalid escape sequence raises RegexValidationError."""
        with pytest.raises(RegexValidationError) as exc_info:
            compile_user_regex("\\")
        assert "Invalid regex" in str(exc_info.value)

    def test_invalid_pattern_unbalanced_parens(self) -> None:
        """Test that unbalanced parentheses raises RegexValidationError."""
        with pytest.raises(RegexValidationError) as exc_info:
            compile_user_regex("(unclosed")
        assert "Invalid regex" in str(exc_info.value)

    def test_custom_description_in_error(self) -> None:
        """Test that custom description appears in error message."""
        with pytest.raises(RegexValidationError) as exc_info:
            compile_user_regex("[bad", description="search filter")
        assert "search filter" in str(exc_info.value)

    def test_error_includes_position(self) -> None:
        """Test that error message includes position information."""
        with pytest.raises(RegexValidationError) as exc_info:
            compile_user_regex("abc[def")
        error_msg = str(exc_info.value)
        # Should include position information
        assert "position" in error_msg.lower() or "^" in error_msg

    def test_empty_pattern(self) -> None:
        """Test that empty pattern is valid (matches everything)."""
        pattern = compile_user_regex("")
        assert pattern.match("anything")

    def test_regex_validation_error_is_value_error(self) -> None:
        """Test that RegexValidationError is a ValueError subclass."""
        assert issubclass(RegexValidationError, ValueError)


class TestEntityDomainParsing:
    """Tests for entity ID parsing functions."""

    def test_get_entity_domain(self) -> None:
        """Test extracting domain from entity ID."""
        assert get_entity_domain("light.living_room") == "light"
        assert get_entity_domain("sensor.temperature") == "sensor"
        assert get_entity_domain("climate.bedroom_ac") == "climate"

    def test_get_entity_domain_no_dot(self) -> None:
        """Test domain extraction when no dot present."""
        assert get_entity_domain("nodot") == ""

    def test_get_entity_name(self) -> None:
        """Test extracting name from entity ID."""
        assert get_entity_name("light.living_room") == "living_room"
        assert get_entity_name("sensor.bedroom_temperature") == "bedroom_temperature"

    def test_get_entity_name_no_dot(self) -> None:
        """Test name extraction when no dot present."""
        assert get_entity_name("nodot") == "nodot"


class TestParseServiceCall:
    """Tests for service call parsing."""

    def test_parse_service_call(self) -> None:
        """Test parsing service calls."""
        assert parse_service_call("light.turn_on") == ("light", "turn_on")
        assert parse_service_call("climate.set_temperature") == ("climate", "set_temperature")

    def test_parse_service_call_no_domain(self) -> None:
        """Test parsing service with no domain."""
        assert parse_service_call("turn_on") == ("", "turn_on")


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_sanitize_filename_basic(self) -> None:
        """Test basic filename sanitization."""
        assert sanitize_filename("simple") == "simple"
        assert sanitize_filename("with spaces") == "with_spaces"

    def test_sanitize_filename_special_chars(self) -> None:
        """Test sanitization of special characters."""
        assert sanitize_filename("file/with:special*chars") == "file-with-special-chars"

    def test_sanitize_filename_empty(self) -> None:
        """Test sanitization of empty strings."""
        assert sanitize_filename("") == "unnamed"
        # Note: spaces become underscores, not stripped
        assert sanitize_filename("   ") == "___"

    def test_sanitize_filename_length_limit(self) -> None:
        """Test that long filenames are truncated."""
        long_name = "a" * 150
        result = sanitize_filename(long_name)
        assert len(result) <= 100


class TestTruncateString:
    """Tests for string truncation."""

    def test_truncate_string_under_limit(self) -> None:
        """Test that strings under limit are unchanged."""
        assert truncate_string("short", 10) == "short"

    def test_truncate_string_at_limit(self) -> None:
        """Test that strings at limit are unchanged."""
        assert truncate_string("exact", 5) == "exact"

    def test_truncate_string_over_limit(self) -> None:
        """Test that strings over limit are truncated with suffix."""
        assert truncate_string("this is a long string", 10) == "this is..."

    def test_truncate_string_custom_suffix(self) -> None:
        """Test truncation with custom suffix."""
        assert truncate_string("this is long", 10, suffix=">>") == "this is >>"

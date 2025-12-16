"""Unit tests for client helper functions."""

import json
from unittest.mock import MagicMock

import pytest

from ha_cli.common.client import _extract_error_message


class TestExtractErrorMessage:
    """Tests for _extract_error_message helper function."""

    def test_extract_message_from_json_message_field(self):
        """Test extracting message from JSON 'message' field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": "Specific error message"}
        mock_response.text = "Fallback text"
        mock_response.status_code = 400

        result = _extract_error_message(mock_response)
        assert result == "Specific error message"

    def test_extract_message_from_json_error_field(self):
        """Test extracting message from JSON 'error' field when 'message' is absent."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "Error field content"}
        mock_response.text = "Fallback text"
        mock_response.status_code = 400

        result = _extract_error_message(mock_response)
        assert result == "Error field content"

    def test_extract_message_prefers_message_over_error(self):
        """Test that 'message' field is preferred over 'error' field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": "Message field content",
            "error": "Error field content"
        }
        mock_response.text = "Fallback text"
        mock_response.status_code = 400

        result = _extract_error_message(mock_response)
        assert result == "Message field content"

    def test_extract_message_falls_back_to_text(self):
        """Test falling back to response.text when JSON has no message/error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"other_field": "value"}
        mock_response.text = "Plain text response"
        mock_response.status_code = 400

        result = _extract_error_message(mock_response)
        assert result == "Plain text response"

    def test_extract_message_from_plain_text(self):
        """Test extracting message when response is not JSON."""
        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_response.text = "Plain text error"
        mock_response.status_code = 400

        result = _extract_error_message(mock_response)
        assert result == "Plain text error"

    def test_extract_message_empty_response(self):
        """Test extracting message when response is empty."""
        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_response.text = ""
        mock_response.status_code = 500

        result = _extract_error_message(mock_response)
        assert result == "HTTP 500"

    def test_extract_message_value_error(self):
        """Test extracting message when json() raises ValueError."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Fallback text"
        mock_response.status_code = 400

        result = _extract_error_message(mock_response)
        assert result == "Fallback text"

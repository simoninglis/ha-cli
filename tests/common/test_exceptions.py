"""Tests for exception helpers and error classification."""

from ha_cli.common.exceptions import (
    EXIT_HA_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_USAGE_ERROR,
    HA_ERROR_CODES,
    TRANSPORT_ERROR_KEYWORDS,
    WebSocketError,
    classify_websocket_error,
    is_transport_error,
)


class TestHAErrorCodes:
    """Tests for HA error code constants."""

    def test_known_codes_are_strings(self) -> None:
        """All known HA error codes should be lowercase strings."""
        for code in HA_ERROR_CODES:
            assert isinstance(code, str)
            assert code == code.lower()

    def test_includes_common_codes(self) -> None:
        """Should include common HA WebSocket error codes."""
        expected = {"not_found", "unauthorized", "validation_error", "home_assistant_error"}
        assert expected.issubset(HA_ERROR_CODES)


class TestTransportErrorKeywords:
    """Tests for transport error keyword constants."""

    def test_is_tuple(self) -> None:
        """Transport keywords should be a tuple for immutability."""
        assert isinstance(TRANSPORT_ERROR_KEYWORDS, tuple)

    def test_no_bare_connect(self) -> None:
        """Should not contain bare 'connect' to avoid matching entity IDs."""
        # Bare "connect" would match "binary_sensor.ha_connected"
        assert "connect" not in TRANSPORT_ERROR_KEYWORDS

    def test_includes_timeout_variants(self) -> None:
        """Should include both 'timeout' and 'timed out' patterns."""
        assert "timeout" in TRANSPORT_ERROR_KEYWORDS
        assert "timed out" in TRANSPORT_ERROR_KEYWORDS

    def test_includes_connection_phrases(self) -> None:
        """Should include specific connection error phrases."""
        assert "not connected" in TRANSPORT_ERROR_KEYWORDS
        assert "failed to connect" in TRANSPORT_ERROR_KEYWORDS


class TestClassifyWebSocketError:
    """Tests for classify_websocket_error function."""

    # --- HA Error Code Prefix Tests (must be classified correctly) ---

    def test_not_found_error(self) -> None:
        """not_found errors should return NOT_FOUND and EXIT_USAGE_ERROR."""
        error = WebSocketError("not_found: Entity light.test not found")
        code, exit_code = classify_websocket_error(error)
        assert code == "NOT_FOUND"
        assert exit_code == EXIT_USAGE_ERROR

    def test_unknown_command_error(self) -> None:
        """unknown_command errors should return NOT_FOUND and EXIT_USAGE_ERROR."""
        error = WebSocketError("unknown_command: Command not supported")
        code, exit_code = classify_websocket_error(error)
        assert code == "NOT_FOUND"
        assert exit_code == EXIT_USAGE_ERROR

    def test_validation_error(self) -> None:
        """validation_error should return VALIDATION_ERROR and EXIT_USAGE_ERROR."""
        error = WebSocketError("validation_error: Invalid format")
        code, exit_code = classify_websocket_error(error)
        assert code == "VALIDATION_ERROR"
        assert exit_code == EXIT_USAGE_ERROR

    def test_invalid_format_error(self) -> None:
        """invalid_format should return VALIDATION_ERROR and EXIT_USAGE_ERROR."""
        error = WebSocketError("invalid_format: Bad request")
        code, exit_code = classify_websocket_error(error)
        assert code == "VALIDATION_ERROR"
        assert exit_code == EXIT_USAGE_ERROR

    def test_unauthorized_error(self) -> None:
        """unauthorized should return AUTH_ERROR and EXIT_HA_ERROR."""
        error = WebSocketError("unauthorized: Access denied")
        code, exit_code = classify_websocket_error(error)
        assert code == "AUTH_ERROR"
        assert exit_code == EXIT_HA_ERROR

    def test_home_assistant_error(self) -> None:
        """home_assistant_error should return HA_ERROR and EXIT_HA_ERROR."""
        error = WebSocketError("home_assistant_error: Internal error")
        code, exit_code = classify_websocket_error(error)
        assert code == "HA_ERROR"
        assert exit_code == EXIT_HA_ERROR

    # --- Critical: HA errors with transport-like keywords should NOT be transport errors ---

    def test_ha_error_with_connected_keyword_not_misclassified(self) -> None:
        """HA error containing 'connected' should NOT be classified as transport.

        This is the critical case that was previously misclassified.
        'home_assistant_error: Not connected to Nabu Casa' should be HA_ERROR,
        not WEBSOCKET_ERROR (transport).
        """
        error = WebSocketError("home_assistant_error: Not connected to Nabu Casa")
        code, exit_code = classify_websocket_error(error)
        # Should be classified as HA error, NOT transport/network error
        assert code == "HA_ERROR"
        assert exit_code == EXIT_HA_ERROR

    def test_not_found_with_connect_in_entity_id(self) -> None:
        """not_found with 'connect' in entity ID should NOT be transport error.

        Entity IDs like 'binary_sensor.ha_connected' contain 'connect' but
        should be classified based on the HA error code, not the keyword.
        """
        error = WebSocketError("not_found: binary_sensor.ha_connected not found")
        code, exit_code = classify_websocket_error(error)
        assert code == "NOT_FOUND"
        assert exit_code == EXIT_USAGE_ERROR

    # --- Transport Error Tests ---

    def test_websocket_timed_out(self) -> None:
        """'WebSocket call timed out' should return WEBSOCKET_ERROR and EXIT_NETWORK_ERROR."""
        error = WebSocketError("WebSocket call timed out after 30s")
        code, exit_code = classify_websocket_error(error)
        assert code == "WEBSOCKET_ERROR"
        assert exit_code == EXIT_NETWORK_ERROR

    def test_connection_closed(self) -> None:
        """'connection closed' should return WEBSOCKET_ERROR and EXIT_NETWORK_ERROR."""
        error = WebSocketError("WebSocket connection closed unexpectedly")
        code, exit_code = classify_websocket_error(error)
        assert code == "WEBSOCKET_ERROR"
        assert exit_code == EXIT_NETWORK_ERROR

    def test_failed_to_connect(self) -> None:
        """'failed to connect' should return WEBSOCKET_ERROR and EXIT_NETWORK_ERROR."""
        error = WebSocketError("Failed to connect to Home Assistant")
        code, exit_code = classify_websocket_error(error)
        assert code == "WEBSOCKET_ERROR"
        assert exit_code == EXIT_NETWORK_ERROR

    # --- Unknown Error Tests ---

    def test_unknown_error_no_prefix(self) -> None:
        """Unknown errors without HA prefix should default to HA_ERROR."""
        error = WebSocketError("Something went wrong")
        code, exit_code = classify_websocket_error(error)
        assert code == "HA_ERROR"
        assert exit_code == EXIT_HA_ERROR


class TestIsTransportError:
    """Tests for is_transport_error function."""

    def test_transport_error_returns_true(self) -> None:
        """Transport errors should return True."""
        error = WebSocketError("WebSocket call timed out after 30s")
        assert is_transport_error(error) is True

    def test_ha_error_returns_false(self) -> None:
        """HA errors should return False."""
        error = WebSocketError("not_found: Entity not found")
        assert is_transport_error(error) is False

    def test_ha_error_with_connected_returns_false(self) -> None:
        """HA error with 'connected' keyword should return False (not misclassified)."""
        error = WebSocketError("home_assistant_error: Not connected to Nabu Casa")
        assert is_transport_error(error) is False

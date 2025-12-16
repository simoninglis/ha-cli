"""Tests for events CLI commands (ha_cli/domains/events/cli.py)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.cli import app
from ha_cli.common.exceptions import (
    ConfigurationError,
    ConnectionError,
    HAAutomationError,
    ValidationError,
    WebSocketError,
)

runner = CliRunner()


class TestEventsListen:
    """Test events listen command."""

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_basic_interrupt(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test basic listen that gets interrupted (simulated by empty event stream)."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        # Empty async generator (simulates immediate stop)
        async def empty_events(*args, **kwargs):
            return
            yield  # Make it a generator

        mock_client.subscribe_events = empty_events

        result = runner.invoke(app, ["events", "listen", "state_changed", "--duration", "1"])
        assert result.exit_code == 0
        assert "Listening for state_changed events" in result.stdout

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_with_count(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test listen with --count stops after N events."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        # Generate 5 events
        async def generate_events(*args, **kwargs):
            for i in range(5):
                yield {"data": {"entity_id": f"light.test_{i}", "old_state": {}, "new_state": {}}}

        mock_client.subscribe_events = generate_events

        result = runner.invoke(app, ["events", "listen", "state_changed", "--count", "3"])
        assert result.exit_code == 0
        # Should only show 3 events
        assert "Received 3 events" in result.stdout

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_porcelain_output(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test listen with porcelain output produces JSONL."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def generate_events(*args, **kwargs):
            yield {"data": {"entity_id": "light.office"}}

        mock_client.subscribe_events = generate_events

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--count", "1", "--porcelain"]
        )
        assert result.exit_code == 0

        # Parse JSONL output
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 2  # metadata + event(s) + summary

        # First line should be metadata
        metadata = json.loads(lines[0])
        assert metadata["type"] == "metadata"
        assert metadata["schema_version"] == 1
        assert metadata["command"] == "events listen"

        # Last line should be summary
        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert "event_count" in summary
        assert "exit_reason" in summary

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_porcelain_count_reached(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test porcelain output shows count_reached exit reason."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def generate_events(*args, **kwargs):
            for i in range(10):
                yield {"data": {"entity_id": f"light.test_{i}"}}

        mock_client.subscribe_events = generate_events

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--count", "2", "--porcelain"]
        )
        assert result.exit_code == 0

        lines = result.stdout.strip().split("\n")
        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["exit_reason"] == "count_reached"
        assert summary["event_count"] == 2

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_porcelain_timeout(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test porcelain output shows timeout exit reason."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        # Slow generator that will be interrupted by timeout
        async def slow_events(*args, **kwargs):
            await asyncio.sleep(10)  # This will be cut short by duration
            yield {"data": {"entity_id": "light.test"}}

        mock_client.subscribe_events = slow_events

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--duration", "1", "--porcelain"]
        )
        assert result.exit_code == 0

        lines = result.stdout.strip().split("\n")
        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["exit_reason"] == "timeout"

    def test_listen_invalid_filter_format(self) -> None:
        """Test error on invalid filter format (missing =)."""
        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--filter", "invalid_filter", "--duration", "1"]
        )
        assert result.exit_code != 0
        assert "Use 'field=value'" in result.stdout

    def test_listen_empty_field_name(self) -> None:
        """Test error on empty field name in filter."""
        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--filter", "=value", "--duration", "1"]
        )
        assert result.exit_code != 0
        assert "field name cannot be empty" in result.stdout

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_with_filter(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test listen with filter option."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def empty_events(*args, **kwargs):
            return
            yield

        mock_client.subscribe_events = empty_events

        result = runner.invoke(
            app,
            ["events", "listen", "deconz_event", "--filter", "unique_id=abc123", "--duration", "1"],
        )
        assert result.exit_code == 0
        assert "Filter: unique_id=abc123" in result.stdout

    @patch("ha_cli.domains.events.cli.get_client_config")
    def test_listen_connection_error(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Test connection error handling."""
        mock_config.side_effect = ConfigurationError("Missing HA_URL")

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--duration", "1"]
        )
        assert result.exit_code != 0

    @patch("ha_cli.domains.events.cli.get_client_config")
    def test_listen_porcelain_validation_error(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Test porcelain mode handles validation errors with proper exit code."""
        mock_config.return_value = ("http://test:8123", "test-token")

        # Invalid filter will trigger ValidationError
        result = runner.invoke(
            app,
            ["events", "listen", "state_changed", "--filter", "invalid", "--porcelain"],
        )
        # Should exit with EXIT_USAGE_ERROR (1)
        assert result.exit_code == 1

        lines = result.stdout.strip().split("\n")
        # First line is metadata (emitted before error)
        metadata = json.loads(lines[0])
        assert metadata["type"] == "metadata"

        # Should have error line
        error_found = False
        for line in lines:
            obj = json.loads(line)
            if obj["type"] == "error":
                error_found = True
                assert obj["error_type"] == "usage_error"
                assert obj["recoverable"] is False
        assert error_found

        # Last line is summary
        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["exit_reason"] == "error"

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_websocket_error(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test WebSocket error handling in human mode."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def raise_error(*args, **kwargs):
            raise WebSocketError("Connection failed")
            yield  # Make it a generator

        mock_client.subscribe_events = raise_error

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--duration", "1"]
        )
        assert result.exit_code != 0

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_porcelain_websocket_error(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test WebSocket error handling in porcelain mode."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def raise_error(*args, **kwargs):
            raise WebSocketError("Connection failed")
            yield

        mock_client.subscribe_events = raise_error

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--porcelain"]
        )
        # Should exit with EXIT_NETWORK_ERROR (2)
        assert result.exit_code == 2

        lines = result.stdout.strip().split("\n")
        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["exit_reason"] == "error"

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_ha_error(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test HA API error handling in human mode."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def raise_error(*args, **kwargs):
            raise HAAutomationError("Subscription failed")
            yield

        mock_client.subscribe_events = raise_error

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--duration", "1"]
        )
        assert result.exit_code != 0

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_porcelain_ha_error(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test HA API error handling in porcelain mode."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def raise_error(*args, **kwargs):
            raise HAAutomationError("Subscription failed")
            yield

        mock_client.subscribe_events = raise_error

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--porcelain"]
        )
        # Should exit with EXIT_HA_ERROR (3)
        assert result.exit_code == 3

        lines = result.stdout.strip().split("\n")
        # Find error line
        error_found = False
        for line in lines:
            obj = json.loads(line)
            if obj["type"] == "error":
                error_found = True
                assert obj["error_type"] == "ha_error"
        assert error_found

    @patch("ha_cli.domains.events.cli.get_client_config")
    @patch("ha_cli.domains.events.cli.HAClient")
    def test_listen_state_changed_human_format(
        self,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test state_changed events show entity and state change."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def generate_events(*args, **kwargs):
            yield {
                "data": {
                    "entity_id": "light.office",
                    "old_state": {"state": "off"},
                    "new_state": {"state": "on"},
                }
            }

        mock_client.subscribe_events = generate_events

        result = runner.invoke(
            app, ["events", "listen", "state_changed", "--count", "1"]
        )
        assert result.exit_code == 0
        assert "light.office" in result.stdout
        assert "off → on" in result.stdout


class TestEventsVersion:
    """Test events version command."""

    def test_version(self) -> None:
        """Test version command."""
        result = runner.invoke(app, ["events", "version"])
        assert result.exit_code == 0
        assert "version" in result.stdout.lower()

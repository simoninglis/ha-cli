"""Tests for dashboard screenshot capture."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.domains.dashboards import cli
from ha_cli.domains.dashboards.screenshot import (
    capture_dashboard_screenshot,
    get_credentials,
    list_available_dashboards,
)


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Set up environment variables for testing."""
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://localhost:8123")
    monkeypatch.setenv("HA_USERNAME", "test-user")
    monkeypatch.setenv("HA_PASSWORD", "test-pass")


class TestCredentials:
    """Test credential loading functions."""

    def test_get_credentials_from_env(self, monkeypatch):
        """Test getting credentials from environment variables."""
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://test:8123")
        monkeypatch.setenv("HA_USERNAME", "admin")
        monkeypatch.setenv("HA_PASSWORD", "secret")

        url, username, password = get_credentials()

        assert url == "http://test:8123"
        assert username == "admin"
        assert password == "secret"

    def test_get_credentials_missing_username(self, monkeypatch):
        """Test error when username is missing."""
        # Clear env vars and prevent load_dotenv from finding a .env file
        monkeypatch.delenv("HA_USERNAME", raising=False)
        monkeypatch.delenv("HA_PASSWORD", raising=False)
        monkeypatch.delenv("HOME_ASSISTANT_URL", raising=False)
        monkeypatch.delenv("HA_URL", raising=False)

        # Patch load_dotenv to do nothing (prevent loading from .env)
        with patch("ha_cli.domains.dashboards.screenshot.load_dotenv"):
            with pytest.raises(ValueError, match="HA_USERNAME and HA_PASSWORD"):
                get_credentials()

    def test_get_credentials_default_url(self, monkeypatch):
        """Test default URL is used when not set."""
        monkeypatch.delenv("HOME_ASSISTANT_URL", raising=False)
        monkeypatch.delenv("HA_URL", raising=False)
        monkeypatch.setenv("HA_USERNAME", "admin")
        monkeypatch.setenv("HA_PASSWORD", "secret")

        url, username, password = get_credentials()

        assert url == "http://homeassistant.local:8123"

    def test_get_credentials_supports_ha_url(self, monkeypatch):
        """Test that HA_URL env var is supported as fallback."""
        # Clear HOME_ASSISTANT_URL to test HA_URL fallback (setup_env fixture sets HOME_ASSISTANT_URL)
        monkeypatch.delenv("HOME_ASSISTANT_URL", raising=False)
        # Also clear HA_URL first to avoid test pollution
        monkeypatch.delenv("HA_URL", raising=False)
        # Now set only HA_URL
        monkeypatch.setenv("HA_URL", "http://ha-url:8123")
        monkeypatch.setenv("HA_USERNAME", "admin")
        monkeypatch.setenv("HA_PASSWORD", "secret")

        # Patch load_dotenv to prevent it from loading .env which might have HOME_ASSISTANT_URL
        with patch("ha_cli.domains.dashboards.screenshot.load_dotenv"):
            url, username, password = get_credentials()

        assert url == "http://ha-url:8123"

    def test_get_credentials_home_assistant_url_takes_priority(self, monkeypatch):
        """Test that HOME_ASSISTANT_URL takes priority over HA_URL."""
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://primary:8123")
        monkeypatch.setenv("HA_URL", "http://fallback:8123")
        monkeypatch.setenv("HA_USERNAME", "admin")
        monkeypatch.setenv("HA_PASSWORD", "secret")

        url, username, password = get_credentials()

        assert url == "http://primary:8123"


class TestListDashboards:
    """Test dashboard listing."""

    def test_list_available_dashboards(self):
        """Test listing available dashboards."""
        dashboards = list_available_dashboards()

        assert "mobile-home" in dashboards
        assert "room-office" in dashboards
        assert "room-lounge" in dashboards
        assert "domain-climate" in dashboards
        assert len(dashboards) >= 10


class TestScreenshotCapture:
    """Test screenshot capture functionality."""

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_capture_screenshot_success(self, mock_playwright, monkeypatch, tmp_path):
        """Test successful screenshot capture."""
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://localhost:8123")
        monkeypatch.setenv("HA_USERNAME", "test")
        monkeypatch.setenv("HA_PASSWORD", "test")

        # Mock the playwright chain
        mock_page = AsyncMock()
        mock_page.url = "http://localhost:8123/room-lounge"

        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context

        mock_chromium = AsyncMock()
        mock_chromium.launch.return_value = mock_browser

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium = mock_chromium

        mock_pw_context = AsyncMock()
        mock_pw_context.__aenter__.return_value = mock_pw_instance

        mock_playwright.return_value = mock_pw_context

        output_file = str(tmp_path / "test-screenshot.png")
        result = await capture_dashboard_screenshot(
            dashboard_name="room-lounge",
            output_path=output_file,
        )

        assert result == output_file
        mock_page.goto.assert_called_once()
        mock_page.screenshot.assert_called_once()
        mock_browser.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_capture_screenshot_with_login(self, mock_playwright, monkeypatch, tmp_path):
        """Test screenshot capture when login is required."""
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://localhost:8123")
        monkeypatch.setenv("HA_USERNAME", "test")
        monkeypatch.setenv("HA_PASSWORD", "test")

        # Mock the playwright chain - simulating auth redirect
        mock_page = AsyncMock()
        mock_page.url = "http://localhost:8123/auth/login"

        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context

        mock_chromium = AsyncMock()
        mock_chromium.launch.return_value = mock_browser

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium = mock_chromium

        mock_pw_context = AsyncMock()
        mock_pw_context.__aenter__.return_value = mock_pw_instance

        mock_playwright.return_value = mock_pw_context

        output_file = str(tmp_path / "test-screenshot.png")
        await capture_dashboard_screenshot(
            dashboard_name="room-lounge",
            output_path=output_file,
        )

        # Verify login was attempted
        mock_page.fill.assert_any_call('input[name="username"]', "test")
        mock_page.fill.assert_any_call('input[name="password"]', "test")
        mock_page.click.assert_called_with("ha-button")

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_capture_screenshot_custom_viewport(self, mock_playwright, monkeypatch, tmp_path):
        """Test screenshot with custom viewport size."""
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://localhost:8123")
        monkeypatch.setenv("HA_USERNAME", "test")
        monkeypatch.setenv("HA_PASSWORD", "test")

        mock_page = AsyncMock()
        mock_page.url = "http://localhost:8123/room-lounge"

        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context

        mock_chromium = AsyncMock()
        mock_chromium.launch.return_value = mock_browser

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium = mock_chromium

        mock_pw_context = AsyncMock()
        mock_pw_context.__aenter__.return_value = mock_pw_instance

        mock_playwright.return_value = mock_pw_context

        output_file = str(tmp_path / "test-screenshot.png")
        await capture_dashboard_screenshot(
            dashboard_name="room-lounge",
            output_path=output_file,
            viewport_width=1920,
            viewport_height=1080,
        )

        mock_browser.new_context.assert_called_once_with(
            viewport={"width": 1920, "height": 1080}
        )

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_capture_screenshot_default_output_path(self, mock_playwright, monkeypatch):
        """Test screenshot with default output path generation."""
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://localhost:8123")
        monkeypatch.setenv("HA_USERNAME", "test")
        monkeypatch.setenv("HA_PASSWORD", "test")

        mock_page = AsyncMock()
        mock_page.url = "http://localhost:8123/room-lounge"

        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context

        mock_chromium = AsyncMock()
        mock_chromium.launch.return_value = mock_browser

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium = mock_chromium

        mock_pw_context = AsyncMock()
        mock_pw_context.__aenter__.return_value = mock_pw_instance

        mock_playwright.return_value = mock_pw_context

        result = await capture_dashboard_screenshot(dashboard_name="room-lounge")

        assert result.startswith("/tmp/dashboard-room-lounge-")
        assert result.endswith(".png")


class TestScreenshotCLI:
    """Test screenshot CLI command."""

    @patch("ha_cli.domains.dashboards.screenshot.capture_dashboard_screenshot")
    def test_screenshot_command(self, mock_capture, runner):
        """Test screenshot CLI command."""
        mock_capture.return_value = "/tmp/dashboard-room-lounge-20251220.png"

        result = runner.invoke(cli.app, ["screenshot", "room-lounge"])

        assert result.exit_code == 0
        assert "Screenshot saved" in result.output
        assert "/tmp/dashboard-room-lounge-20251220.png" in result.output

    @patch("ha_cli.domains.dashboards.screenshot.capture_dashboard_screenshot")
    def test_screenshot_command_with_options(self, mock_capture, runner):
        """Test screenshot CLI command with custom options."""
        mock_capture.return_value = "/tmp/custom.png"

        result = runner.invoke(cli.app, [
            "screenshot", "room-lounge",
            "--output", "/tmp/custom.png",
            "--width", "1920",
            "--height", "1080",
            "--wait", "10",
        ])

        assert result.exit_code == 0
        mock_capture.assert_called_once_with(
            dashboard_name="room-lounge",
            output_path="/tmp/custom.png",
            viewport_width=1920,
            viewport_height=1080,
            wait_seconds=10,
        )

    @patch("ha_cli.domains.dashboards.screenshot.capture_dashboard_screenshot", new_callable=AsyncMock)
    def test_screenshot_command_missing_credentials(self, mock_capture, runner):
        """Test screenshot CLI when credentials are missing."""
        mock_capture.side_effect = ValueError(
            "HA_USERNAME and HA_PASSWORD environment variables are required."
        )

        result = runner.invoke(cli.app, ["screenshot", "room-lounge"])

        assert result.exit_code == 1  # EXIT_USAGE_ERROR (from exceptions.py)
        assert "HA_USERNAME and HA_PASSWORD" in result.output

    @patch("ha_cli.domains.dashboards.screenshot.capture_dashboard_screenshot")
    def test_screenshot_command_playwright_error(self, mock_capture, runner):
        """Test screenshot CLI when playwright fails."""
        mock_capture.side_effect = Exception("Browser launch failed")

        result = runner.invoke(cli.app, ["screenshot", "room-lounge"])

        assert result.exit_code == 3  # EXIT_HA_ERROR
        assert "Screenshot failed" in result.output
        assert "Browser launch failed" in result.output

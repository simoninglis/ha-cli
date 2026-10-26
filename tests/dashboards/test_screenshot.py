"""Tests for dashboard screenshot capture."""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.common.frontend_auth import (
    FrontendAuth,
    FrontendAuthError,
    assert_logged_in,
    canonical_origin,
    ensure_logged_in,
    resolve_frontend_auth,
    token_init_script,
)
from ha_cli.domains.dashboards import cli
from ha_cli.domains.dashboards.screenshot import (
    capture_dashboard_screenshot,
    list_available_dashboards,
)

TOKEN = "eyJhbGciOiJIUzI1NiJ9.tok'en\"</script>.sig"


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Password auth by default; no token, no .env leaking in from the developer's shell."""
    for var in ("HA_TOKEN", "HOME_ASSISTANT_TOKEN", "HA_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://localhost:8123")
    monkeypatch.setenv("HA_USERNAME", "test-user")
    monkeypatch.setenv("HA_PASSWORD", "test-pass")
    with patch("ha_cli.common.envfile.read_env_file", return_value={}):
        yield


def _playwright_chain(mock_playwright, page_url):
    """Wire async_playwright() -> chromium -> browser -> context -> page."""
    mock_page = AsyncMock()
    mock_page.url = page_url
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
    return mock_chromium, mock_browser, mock_context, mock_page


class TestCredentials:
    """Credential resolution: token first, then username/password."""

    def test_login_from_env(self, monkeypatch):
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://test:8123/")
        monkeypatch.setenv("HA_USERNAME", "admin")
        monkeypatch.setenv("HA_PASSWORD", "secret")

        auth = resolve_frontend_auth()

        assert (auth.url, auth.method, auth.username, auth.password) == (
            "http://test:8123", "login", "admin", "secret"
        )

    def test_token_preferred_over_login(self, monkeypatch):
        monkeypatch.setenv("HA_TOKEN", TOKEN)
        auth = resolve_frontend_auth()
        assert auth.method == "token"
        assert auth.token == TOKEN

    def test_token_alone_is_enough(self, monkeypatch):
        """The bao-run case: a token and no HA password at all."""
        monkeypatch.delenv("HA_USERNAME")
        monkeypatch.delenv("HA_PASSWORD")
        monkeypatch.setenv("HOME_ASSISTANT_TOKEN", TOKEN)
        assert resolve_frontend_auth().method == "token"

    def test_repr_hides_secrets(self):
        auth = FrontendAuth(url="http://x:8123", token=TOKEN, username="u", password="pw-secret")
        assert TOKEN not in repr(auth)
        assert "pw-secret" not in repr(auth)

    def test_missing_everything_names_both_options(self, monkeypatch):
        monkeypatch.delenv("HA_USERNAME")
        monkeypatch.delenv("HA_PASSWORD")
        with pytest.raises(FrontendAuthError, match="HA_TOKEN.*HA_USERNAME and HA_PASSWORD"):
            resolve_frontend_auth()

    def test_password_without_username_is_not_enough(self, monkeypatch):
        monkeypatch.delenv("HA_USERNAME")
        with pytest.raises(ValueError):  # FrontendAuthError is a ValueError (CLI exit 1)
            resolve_frontend_auth()

    def test_default_url(self, monkeypatch):
        monkeypatch.delenv("HOME_ASSISTANT_URL")
        assert resolve_frontend_auth().url == "http://homeassistant.local:8123"

    def test_supports_ha_url(self, monkeypatch):
        monkeypatch.delenv("HOME_ASSISTANT_URL")
        monkeypatch.setenv("HA_URL", "http://ha-url:8123")
        assert resolve_frontend_auth().url == "http://ha-url:8123"

    def test_home_assistant_url_takes_priority(self, monkeypatch):
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://primary:8123")
        monkeypatch.setenv("HA_URL", "http://fallback:8123")
        assert resolve_frontend_auth().url == "http://primary:8123"


class TestTokenInitScript:
    """The localStorage seed the HA frontend reads its auth from."""

    def _stored(self, script: str) -> dict:
        literal = script.split("setItem('hassTokens', ", 1)[1].split("); } catch", 1)[0]
        return json.loads(json.loads(literal))

    def test_stores_token_for_the_ha_origin(self):
        script = token_init_script(FrontendAuth(url="http://10.0.0.5:8123/", token=TOKEN))
        stored = self._stored(script)
        assert stored["access_token"] == TOKEN  # survives quotes and </script> intact
        assert stored["hassUrl"] == "http://10.0.0.5:8123"
        assert stored["clientId"] == "http://10.0.0.5:8123/"
        assert stored["refresh_token"] == ""
        assert stored["expires"] > 4_000_000_000_000  # never "expired" -> no refresh attempt

    def test_only_writes_on_the_ha_origin(self):
        script = token_init_script(FrontendAuth(url="http://10.0.0.5:8123/lovelace", token=TOKEN))
        assert 'window.location.origin !== "http://10.0.0.5:8123") return;' in script
        assert script.index("return;") < script.index("setItem")

    def test_token_cannot_break_out_of_the_string(self):
        script = token_init_script(FrontendAuth(url="http://x:8123", token=TOKEN))
        # Quotes in the token are escaped, so it can't end the JS string literal early
        assert TOKEN not in script

    def test_requires_a_token(self):
        with pytest.raises(FrontendAuthError):
            token_init_script(FrontendAuth(url="http://x:8123", username="u", password="p"))


class TestOrigin:
    @pytest.mark.parametrize("url,origin", [
        ("http://10.0.0.5:8123/lovelace", "http://10.0.0.5:8123"),
        ("http://HA.Local:8123", "http://ha.local:8123"),
        ("http://ha:80/x", "http://ha"),
        ("https://ha.example:443", "https://ha.example"),
        ("https://ha.example:8443", "https://ha.example:8443"),
        ("http://[fd00::1]:8123", "http://[fd00::1]:8123"),
    ])
    def test_canonical_origin(self, url, origin):
        assert canonical_origin(url) == origin

    @pytest.mark.parametrize("url", [
        "ftp://ha:21", "ha.local:8123", "http://", "http://user:pw@ha:8123", "http://ha:99999",
    ])
    def test_rejected_urls(self, url):
        with pytest.raises(FrontendAuthError):
            canonical_origin(url)

    def test_seed_uses_normalized_origin(self):
        script = token_init_script(FrontendAuth(url="http://HA.local:80/", token=TOKEN))
        assert '"http://ha.local") return;' in script


class TestLoginOriginGuard:
    """Credentials only ever go to the Home Assistant origin."""

    def _page(self, url):
        page = AsyncMock()
        page.url = url
        return page

    @pytest.mark.asyncio
    async def test_password_not_typed_into_another_origin(self):
        auth = FrontendAuth(url="http://ha:8123", username="u", password="pw")
        page = self._page("https://evil.example/auth/authorize")
        with pytest.raises(FrontendAuthError, match="left Home Assistant"):
            await ensure_logged_in(page, auth)
        page.fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_redirect_away_while_form_loads(self):
        auth = FrontendAuth(url="http://ha:8123", username="u", password="pw")
        page = self._page("http://ha:8123/auth/authorize")

        async def navigate_away(*a, **k):
            page.url = "https://evil.example/auth/authorize"

        page.wait_for_selector.side_effect = navigate_away
        with pytest.raises(FrontendAuthError, match="left Home Assistant"):
            await ensure_logged_in(page, auth)
        page.fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_that_lands_elsewhere_fails(self):
        auth = FrontendAuth(url="http://ha:8123", username="u", password="pw")
        page = self._page("http://ha:8123/auth/authorize")

        async def redirected(*a, **k):
            page.url = "https://evil.example/dashboard"

        page.click.side_effect = redirected
        with pytest.raises(FrontendAuthError, match="left Home Assistant"):
            await ensure_logged_in(page, auth)

    @pytest.mark.asyncio
    async def test_token_auth_on_another_origin_fails(self):
        auth = FrontendAuth(url="http://ha:8123", token=TOKEN)
        with pytest.raises(FrontendAuthError, match="left Home Assistant"):
            await ensure_logged_in(self._page("https://evil.example/lovelace"), auth)

    def test_assert_logged_in(self):
        auth = FrontendAuth(url="http://ha:8123", token=TOKEN)
        assert_logged_in(self._page("http://ha:8123/lovelace/0"), auth)
        with pytest.raises(FrontendAuthError, match="login page"):
            assert_logged_in(self._page("http://ha:8123/auth/authorize?x"), auth)
        with pytest.raises(FrontendAuthError, match="left Home Assistant"):
            assert_logged_in(self._page("about:blank"), auth)


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

    @pytest.fixture(autouse=True)
    def no_render_wait(self):
        with patch("ha_cli.domains.dashboards.screenshot.asyncio.sleep", new=AsyncMock()):
            yield

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_capture_screenshot_success(self, mock_playwright, tmp_path):
        """Test successful screenshot capture."""
        _, mock_browser, mock_context, mock_page = _playwright_chain(
            mock_playwright, "http://localhost:8123/room-lounge"
        )

        output_file = str(tmp_path / "test-screenshot.png")
        result = await capture_dashboard_screenshot(
            dashboard_name="room-lounge",
            output_path=output_file,
        )

        assert result == output_file
        mock_page.goto.assert_called_once()
        mock_page.screenshot.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_context.add_init_script.assert_not_called()  # password auth seeds nothing

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_capture_screenshot_with_login(self, mock_playwright, tmp_path):
        """Password auth: fill the login form, then capture once redirected."""
        _, _, _, mock_page = _playwright_chain(mock_playwright, "http://localhost:8123/auth/login")

        async def redirected(*args, **kwargs):
            mock_page.url = "http://localhost:8123/room-lounge"

        mock_page.click.side_effect = redirected

        output_file = str(tmp_path / "test-screenshot.png")
        await capture_dashboard_screenshot(
            dashboard_name="room-lounge",
            output_path=output_file,
        )

        mock_page.fill.assert_any_call('input[name="username"]', "test-user", timeout=10000)
        mock_page.fill.assert_any_call('input[name="password"]', "test-pass", timeout=10000)
        mock_page.click.assert_called_with("ha-button", timeout=10000)
        mock_page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_login_never_leaving_auth_is_an_error(self, mock_playwright, tmp_path):
        """Wrong password: no screenshot of the login page reported as success."""
        _, _, _, mock_page = _playwright_chain(mock_playwright, "http://localhost:8123/auth/login")
        mock_page.wait_for_url.side_effect = Exception("Timeout 30000ms exceeded")

        with pytest.raises(FrontendAuthError, match="Login failed"):
            await capture_dashboard_screenshot("room-lounge", output_path=str(tmp_path / "x.png"))
        mock_page.screenshot.assert_not_called()

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_token_auth_seeds_storage_and_skips_login(self, mock_playwright, monkeypatch, tmp_path):
        monkeypatch.setenv("HA_TOKEN", TOKEN)
        mock_chromium, _, mock_context, mock_page = _playwright_chain(
            mock_playwright, "http://localhost:8123/room-lounge"
        )

        await capture_dashboard_screenshot("room-lounge", output_path=str(tmp_path / "x.png"))

        script = mock_context.add_init_script.call_args.kwargs["script"]
        assert "hassTokens" in script
        assert mock_context.add_init_script.await_count == 1
        # Seeded before the first page exists, so the frontend never sees a login
        assert mock_context.method_calls.index(
            next(c for c in mock_context.method_calls if c[0] == "add_init_script")
        ) < mock_context.method_calls.index(
            next(c for c in mock_context.method_calls if c[0] == "new_page")
        )
        mock_page.fill.assert_not_called()
        mock_page.screenshot.assert_called_once()
        # The token goes over Playwright's pipe, never into the browser's argv
        assert TOKEN not in repr(mock_chromium.launch.call_args)
        assert "eyJhbGciOiJIUzI1NiJ9" not in repr(mock_chromium.launch.call_args)

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_rejected_token_is_an_error_not_a_login_screenshot(self, mock_playwright, monkeypatch, tmp_path):
        monkeypatch.setenv("HA_TOKEN", TOKEN)
        _, mock_browser, _, mock_page = _playwright_chain(mock_playwright, "http://localhost:8123/auth/authorize")

        with pytest.raises(FrontendAuthError, match="rejected the access token") as exc:
            await capture_dashboard_screenshot("room-lounge", output_path=str(tmp_path / "x.png"))

        assert TOKEN not in str(exc.value)
        mock_page.fill.assert_not_called()
        mock_page.screenshot.assert_not_called()
        mock_browser.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_late_bounce_to_login_is_an_error(self, mock_playwright, monkeypatch, tmp_path):
        """The frontend can drop to /auth after load, once its websocket auth fails."""
        monkeypatch.setenv("HA_TOKEN", TOKEN)
        _, _, _, mock_page = _playwright_chain(mock_playwright, "http://localhost:8123/room-lounge")

        async def bounce(_seconds):
            mock_page.url = "http://localhost:8123/auth/authorize"

        with patch("ha_cli.domains.dashboards.screenshot.asyncio.sleep", new=AsyncMock(side_effect=bounce)):
            with pytest.raises(FrontendAuthError, match="login page"):
                await capture_dashboard_screenshot("room-lounge", output_path=str(tmp_path / "x.png"))
        mock_page.screenshot.assert_not_called()

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_capture_screenshot_custom_viewport(self, mock_playwright, tmp_path):
        """Test screenshot with custom viewport size."""
        _, mock_browser, _, _ = _playwright_chain(mock_playwright, "http://localhost:8123/room-lounge")

        await capture_dashboard_screenshot(
            dashboard_name="room-lounge",
            output_path=str(tmp_path / "test-screenshot.png"),
            viewport_width=1920,
            viewport_height=1080,
        )

        mock_browser.new_context.assert_called_once_with(
            viewport={"width": 1920, "height": 1080}
        )

    @pytest.mark.asyncio
    @patch("ha_cli.domains.dashboards.screenshot.async_playwright")
    async def test_capture_screenshot_default_output_path(self, mock_playwright):
        """Test screenshot with default output path generation."""
        _playwright_chain(mock_playwright, "http://localhost:8123/room-lounge")

        result = await capture_dashboard_screenshot(dashboard_name="room-lounge")

        assert result.startswith(os.path.join(tempfile.gettempdir(), "dashboard-room-lounge-"))
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
        mock_capture.side_effect = FrontendAuthError(
            "No Home Assistant credentials for the browser: set HA_TOKEN or HA_USERNAME and HA_PASSWORD."
        )

        result = runner.invoke(cli.app, ["screenshot", "room-lounge"])

        assert result.exit_code == 1  # EXIT_USAGE_ERROR (from exceptions.py)
        assert "HA_TOKEN" in result.output

    @patch("ha_cli.domains.dashboards.screenshot.capture_dashboard_screenshot")
    def test_screenshot_command_playwright_error(self, mock_capture, runner):
        """Test screenshot CLI when playwright fails."""
        mock_capture.side_effect = Exception("Browser launch failed")

        result = runner.invoke(cli.app, ["screenshot", "room-lounge"])

        assert result.exit_code == 3  # EXIT_HA_ERROR
        assert "Screenshot failed" in result.output
        assert "Browser launch failed" in result.output

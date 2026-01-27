"""End-to-end tests for system domain.

These tests connect to a live Home Assistant instance.
They require SSH access and API credentials to be configured.

Skip these tests if no live HA instance is available:
    pytest tests/system/test_e2e.py -v

Run with specific markers:
    pytest tests/system/test_e2e.py -v -m "e2e"
"""

import json
import os

import pytest
from typer.testing import CliRunner

from ha_cli.cli import app
from ha_cli.common.config import get_client_config
from ha_cli.domains.system.service import SystemService

runner = CliRunner()

# Check if we have credentials for live testing
try:
    _url, _token = get_client_config(None, None)
    HAS_CREDENTIALS = True
except Exception:
    HAS_CREDENTIALS = False

# Default SSH settings for HA instance
HA_HOST = os.environ.get("HA_HOST") or os.environ.get("HA_SSH_HOST", "homeassistant")
HA_SSH_USER = os.environ.get("HA_SSH_USER", "root")


def skip_without_credentials(reason: str = "No HA credentials available"):
    """Skip test if no credentials are available."""
    return pytest.mark.skipif(not HAS_CREDENTIALS, reason=reason)


def skip_without_ssh(reason: str = "SSH access required"):
    """Skip test if SSH is not available (for CI environments)."""
    return pytest.mark.skipif(
        os.environ.get("CI") == "true" or os.environ.get("SKIP_SSH_TESTS") == "true",
        reason=reason,
    )


@pytest.mark.e2e
class TestSystemInfoE2E:
    """E2E tests for system info command."""

    @skip_without_credentials()
    @skip_without_ssh()
    def test_info_live(self) -> None:
        """Test info command against live HA instance."""
        result = runner.invoke(app, ["system", "info"])

        assert result.exit_code == 0
        # Should show version info
        assert "Version" in result.stdout or "version" in result.stdout

    @skip_without_credentials()
    @skip_without_ssh()
    def test_info_json_live(self) -> None:
        """Test info command with JSON output against live HA."""
        result = runner.invoke(app, ["system", "info", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert "version" in output
        assert "installation_type" in output
        assert "host" in output

    @skip_without_credentials()
    @skip_without_ssh()
    def test_info_porcelain_live(self) -> None:
        """Test info command with porcelain output against live HA."""
        result = runner.invoke(app, ["system", "info", "--porcelain"])

        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert "version" in output["data"]


@pytest.mark.e2e
class TestSystemLogsE2E:
    """E2E tests for system logs command."""

    @skip_without_credentials()
    @skip_without_ssh()
    def test_logs_live(self) -> None:
        """Test logs command against live HA instance."""
        result = runner.invoke(app, ["system", "logs", "--lines", "10"])

        assert result.exit_code == 0
        # Should have some log content
        assert len(result.stdout) > 0

    @skip_without_credentials()
    @skip_without_ssh()
    def test_logs_with_filter_live(self) -> None:
        """Test logs with filter against live HA."""
        result = runner.invoke(
            app, ["system", "logs", "--lines", "50", "--filter", "homeassistant"]
        )

        # May or may not find matches, but shouldn't error
        assert result.exit_code == 0

    @skip_without_credentials()
    @skip_without_ssh()
    def test_logs_raw_live(self) -> None:
        """Test logs with raw output against live HA."""
        result = runner.invoke(app, ["system", "logs", "--lines", "5", "--raw"])

        assert result.exit_code == 0
        # Raw output should not have Rich formatting
        assert "╭" not in result.stdout or "│" not in result.stdout

    @skip_without_credentials()
    @skip_without_ssh()
    def test_logs_json_live(self) -> None:
        """Test logs with JSON output against live HA."""
        result = runner.invoke(app, ["system", "logs", "--lines", "5", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert "logs" in output
        assert "lines_requested" in output
        assert output["lines_requested"] == 5

    @skip_without_credentials()
    def test_logs_errors_only_live(self) -> None:
        """Test logs with --errors-only via API (no SSH needed)."""
        result = runner.invoke(app, ["system", "logs", "--errors-only", "--raw"])

        # This uses API, so should work even without SSH
        assert result.exit_code == 0


@pytest.mark.e2e
class TestSystemCheckE2E:
    """E2E tests for system check command."""

    @skip_without_credentials()
    @skip_without_ssh()
    def test_check_live(self) -> None:
        """Test check command against live HA instance."""
        result = runner.invoke(app, ["system", "check"])

        # Should succeed (assuming config is valid)
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    @skip_without_credentials()
    @skip_without_ssh()
    def test_check_json_live(self) -> None:
        """Test check command with JSON output against live HA."""
        result = runner.invoke(app, ["system", "check", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert "valid" in output
        assert output["valid"] is True


@pytest.mark.e2e
class TestSystemReloadE2E:
    """E2E tests for system reload command.

    Note: These tests actually reload components in HA.
    They are safe to run but may briefly affect automations.
    """

    @skip_without_credentials()
    def test_reload_automations_live(self) -> None:
        """Test reload automations against live HA."""
        result = runner.invoke(app, ["system", "reload", "automations"])

        assert result.exit_code == 0
        assert "reload" in result.stdout.lower()

    @skip_without_credentials()
    def test_reload_scripts_live(self) -> None:
        """Test reload scripts against live HA."""
        result = runner.invoke(app, ["system", "reload", "scripts"])

        assert result.exit_code == 0

    @skip_without_credentials()
    def test_reload_json_live(self) -> None:
        """Test reload with JSON output against live HA."""
        result = runner.invoke(app, ["system", "reload", "automations", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert output["component"] == "automations"


@pytest.mark.e2e
class TestSystemServiceE2E:
    """E2E tests for SystemService directly."""

    @skip_without_credentials()
    @pytest.mark.asyncio
    async def test_get_info_via_api(self) -> None:
        """Test get_info via API."""
        from ha_cli.common.client import HAClient

        url, token = get_client_config(None, None)

        async with HAClient(url, token) as client:
            service = SystemService(client=client, host=HA_HOST, user=HA_SSH_USER)
            info = await service.get_info()

        assert info is not None
        assert info.version is not None
        assert "." in info.version  # Version should have dots (e.g., 2025.12.1)

    @skip_without_credentials()
    @pytest.mark.asyncio
    async def test_reload_via_api(self) -> None:
        """Test reload via API."""
        from ha_cli.common.client import HAClient

        url, token = get_client_config(None, None)

        async with HAClient(url, token) as client:
            service = SystemService(client=client)
            success, message = await service.reload("automations")

        assert success is True
        assert "automations" in message.lower()

    @skip_without_credentials()
    @pytest.mark.asyncio
    async def test_get_error_log_via_api(self) -> None:
        """Test get_error_log via API."""
        from ha_cli.common.client import HAClient

        url, token = get_client_config(None, None)

        async with HAClient(url, token) as client:
            service = SystemService(client=client)
            result = await service.get_error_log_via_api()

        # Should return something (could be empty if no errors)
        assert isinstance(result, str)

    @skip_without_credentials()
    @skip_without_ssh()
    @pytest.mark.asyncio
    async def test_check_config_via_ssh(self) -> None:
        """Test check_config via SSH."""
        service = SystemService(host=HA_HOST, user=HA_SSH_USER)
        is_valid, message = await service.check_config()

        # Assuming config is valid on test instance
        assert is_valid is True

    @skip_without_credentials()
    @skip_without_ssh()
    @pytest.mark.asyncio
    async def test_get_logs_via_ssh(self) -> None:
        """Test get_logs via SSH."""
        service = SystemService(host=HA_HOST, user=HA_SSH_USER)
        result = await service.get_logs(lines=10)

        assert isinstance(result, str)
        assert len(result) > 0

    @skip_without_credentials()
    @skip_without_ssh()
    @pytest.mark.asyncio
    async def test_get_info_via_ssh_fallback(self) -> None:
        """Test get_info falls back to SSH when API unavailable."""
        # Create service without API client to force SSH
        service = SystemService(host=HA_HOST, user=HA_SSH_USER)
        info = await service.get_info()

        assert info is not None
        assert info.version is not None


@pytest.mark.e2e
class TestSystemRestartE2E:
    """E2E tests for system restart command.

    WARNING: These tests actually restart Home Assistant!
    They are marked with a special marker and skipped by default.
    Only run these if you want to actually restart HA.
    """

    @pytest.mark.skip(reason="Restart test disabled by default - would restart HA")
    @skip_without_credentials()
    def test_restart_with_check_live(self) -> None:
        """Test restart with config check against live HA.

        WARNING: This will restart Home Assistant!
        """
        result = runner.invoke(app, ["system", "restart"])

        assert result.exit_code == 0
        assert "restarted" in result.stdout.lower()

    @pytest.mark.skip(reason="Restart test disabled by default - would restart HA")
    @skip_without_credentials()
    def test_restart_no_check_live(self) -> None:
        """Test restart without config check against live HA.

        WARNING: This will restart Home Assistant!
        """
        result = runner.invoke(app, ["system", "restart", "--no-check"])

        assert result.exit_code == 0


@pytest.mark.e2e
class TestSSHSecurityE2E:
    """E2E tests for SSH security measures."""

    @skip_without_credentials()
    @skip_without_ssh()
    @pytest.mark.asyncio
    async def test_ssh_timeout_works(self) -> None:
        """Test that SSH timeout is respected."""
        import asyncio

        from ha_cli.domains.system.service import SSHError

        service = SystemService(host=HA_HOST, user=HA_SSH_USER)

        # Run a command that should complete quickly
        stdout, stderr, returncode = await service._run_ssh_command_async(
            "echo test", timeout=10
        )

        assert returncode == 0
        assert "test" in stdout

    @skip_without_credentials()
    @skip_without_ssh()
    @pytest.mark.asyncio
    async def test_ssh_batch_mode_prevents_prompts(self) -> None:
        """Test that BatchMode prevents password prompts."""
        from ha_cli.domains.system.service import SSHError

        # Connect to a non-existent host - should fail quickly, not hang
        service = SystemService(host="192.168.255.255", user="nonexistent")

        with pytest.raises(SSHError) as exc_info:
            await service._run_ssh_command_async("echo test", timeout=15)

        # Should fail with connection error, not hang waiting for password
        assert exc_info.value.returncode in (255, -1)

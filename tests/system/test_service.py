"""Tests for system service (ha_cli/domains/system/service.py)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_cli.domains.system.service import SSHError, SystemInfo, SystemService


class TestSSHError:
    """Test SSHError exception class."""

    def test_ssh_error_basic(self) -> None:
        """Test SSHError with message only."""
        error = SSHError("Connection failed")
        assert str(error) == "Connection failed"
        assert error.returncode == 1

    def test_ssh_error_with_returncode(self) -> None:
        """Test SSHError with custom returncode."""
        error = SSHError("SSH connection error", returncode=255)
        assert str(error) == "SSH connection error"
        assert error.returncode == 255

    def test_ssh_error_timeout_returncode(self) -> None:
        """Test SSHError with timeout returncode."""
        error = SSHError("Command timed out", returncode=-1)
        assert error.returncode == -1


class TestSystemInfo:
    """Test SystemInfo dataclass."""

    def test_system_info_creation(self) -> None:
        """Test creating SystemInfo."""
        info = SystemInfo(
            version="2025.12.1",
            installation_type="Home Assistant OS",
            host="10.0.20.35",
        )
        assert info.version == "2025.12.1"
        assert info.installation_type == "Home Assistant OS"
        assert info.host == "10.0.20.35"

    def test_system_info_to_dict(self) -> None:
        """Test SystemInfo.to_dict()."""
        info = SystemInfo(
            version="2025.12.1",
            installation_type="Home Assistant OS",
            host="10.0.20.35",
        )
        result = info.to_dict()
        assert result == {
            "version": "2025.12.1",
            "installation_type": "Home Assistant OS",
            "host": "10.0.20.35",
        }


class TestSystemServiceInit:
    """Test SystemService initialization."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        service = SystemService()
        assert service.client is None
        assert service.host == "10.0.20.35"
        assert service.user == "root"

    def test_init_with_client(self) -> None:
        """Test initialization with HAClient."""
        mock_client = MagicMock()
        service = SystemService(client=mock_client)
        assert service.client is mock_client

    def test_init_with_custom_ssh(self) -> None:
        """Test initialization with custom SSH settings."""
        service = SystemService(host="192.168.1.100", user="admin")
        assert service.host == "192.168.1.100"
        assert service.user == "admin"


class TestSystemServiceAPI:
    """Test API-based methods."""

    @pytest.mark.asyncio
    async def test_restart_via_api_no_client(self) -> None:
        """Test restart_via_api without client."""
        service = SystemService()
        success, message = await service.restart_via_api()
        assert success is False
        assert message == "No API client available"

    @pytest.mark.asyncio
    async def test_restart_via_api_success(self) -> None:
        """Test restart_via_api success."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(return_value=None)

        service = SystemService(client=mock_client)
        success, message = await service.restart_via_api()

        assert success is True
        assert "successfully" in message.lower()
        mock_client._ws_call.assert_called_once_with(
            "call_service",
            domain="homeassistant",
            service="restart",
        )

    @pytest.mark.asyncio
    async def test_restart_via_api_failure(self) -> None:
        """Test restart_via_api failure."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(side_effect=Exception("Connection lost"))

        service = SystemService(client=mock_client)
        success, message = await service.restart_via_api()

        assert success is False
        assert "failed" in message.lower()

    @pytest.mark.asyncio
    async def test_reload_via_api_no_client(self) -> None:
        """Test reload_via_api without client."""
        service = SystemService()
        success, message = await service.reload_via_api("automations")
        assert success is False
        assert message == "No API client available"

    @pytest.mark.asyncio
    async def test_reload_via_api_automations(self) -> None:
        """Test reload_via_api for automations."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(return_value=None)

        service = SystemService(client=mock_client)
        success, message = await service.reload_via_api("automations")

        assert success is True
        assert "automations" in message.lower()
        mock_client._ws_call.assert_called_once_with(
            "call_service",
            domain="automation",
            service="reload",
        )

    @pytest.mark.asyncio
    async def test_reload_via_api_scripts(self) -> None:
        """Test reload_via_api for scripts."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(return_value=None)

        service = SystemService(client=mock_client)
        success, message = await service.reload_via_api("scripts")

        assert success is True
        mock_client._ws_call.assert_called_once_with(
            "call_service",
            domain="script",
            service="reload",
        )

    @pytest.mark.asyncio
    async def test_reload_via_api_unknown_component(self) -> None:
        """Test reload_via_api for unknown component."""
        mock_client = MagicMock()
        service = SystemService(client=mock_client)
        success, message = await service.reload_via_api("unknown_component")

        assert success is False
        assert "Unknown component" in message

    @pytest.mark.asyncio
    async def test_reload_via_api_all_triggers_restart(self) -> None:
        """Test reload_via_api with 'all' triggers restart."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(return_value=None)

        service = SystemService(client=mock_client)
        success, message = await service.reload_via_api("all")

        assert success is True
        mock_client._ws_call.assert_called_once_with(
            "call_service",
            domain="homeassistant",
            service="restart",
        )

    @pytest.mark.asyncio
    async def test_reload_via_api_no_component(self) -> None:
        """Test reload_via_api without component reloads common components."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(return_value=None)

        service = SystemService(client=mock_client)
        success, message = await service.reload_via_api(None)

        assert success is True
        # Should have called for automation, script, scene
        assert mock_client._ws_call.call_count == 3

    @pytest.mark.asyncio
    async def test_get_error_log_via_api_no_client(self) -> None:
        """Test get_error_log_via_api without client."""
        service = SystemService()
        result = await service.get_error_log_via_api()
        assert result == "No API client available"

    @pytest.mark.asyncio
    async def test_get_error_log_via_api_success(self) -> None:
        """Test get_error_log_via_api success."""
        mock_client = MagicMock()
        mock_client._rest = AsyncMock(return_value="Error log content here")

        service = SystemService(client=mock_client)
        result = await service.get_error_log_via_api()

        assert result == "Error log content here"
        mock_client._rest.assert_called_once_with("GET", "/api/error_log")

    @pytest.mark.asyncio
    async def test_get_config_via_api_no_client(self) -> None:
        """Test get_config_via_api without client."""
        service = SystemService()
        result = await service.get_config_via_api()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_config_via_api_success(self) -> None:
        """Test get_config_via_api success."""
        mock_client = MagicMock()
        mock_client._rest = AsyncMock(
            return_value={
                "version": "2025.12.1",
                "installation_type": "Home Assistant OS",
            }
        )

        service = SystemService(client=mock_client)
        result = await service.get_config_via_api()

        assert result is not None
        assert result["version"] == "2025.12.1"


class TestSystemServiceSSH:
    """Test SSH-based methods."""

    @pytest.mark.asyncio
    async def test_run_ssh_command_success(self) -> None:
        """Test _run_ssh_command_async success."""
        service = SystemService(host="test-host", user="test-user")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            stdout, stderr, returncode = await service._run_ssh_command_async(
                "ha core info"
            )

        assert stdout == "output"
        assert stderr == ""
        assert returncode == 0

    @pytest.mark.asyncio
    async def test_run_ssh_command_connection_error(self) -> None:
        """Test _run_ssh_command_async with connection error (returncode 255)."""
        service = SystemService(host="test-host", user="test-user")

        mock_proc = MagicMock()
        mock_proc.returncode = 255
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"Connection refused")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(SSHError) as exc_info:
                await service._run_ssh_command_async("ha core info")

        assert exc_info.value.returncode == 255
        assert "SSH connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_ssh_command_timeout(self) -> None:
        """Test _run_ssh_command_async timeout."""
        service = SystemService(host="test-host", user="test-user")

        mock_proc = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                with pytest.raises(SSHError) as exc_info:
                    await service._run_ssh_command_async("ha core info", timeout=1)

        assert exc_info.value.returncode == -1
        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_ssh_command_not_found(self) -> None:
        """Test _run_ssh_command_async when SSH not installed."""
        service = SystemService(host="test-host", user="test-user")

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("ssh not found"),
        ):
            with pytest.raises(SSHError) as exc_info:
                await service._run_ssh_command_async("ha core info")

        assert "SSH client not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_check_config_valid(self) -> None:
        """Test check_config with valid config."""
        service = SystemService()

        with patch.object(
            service,
            "_run_ssh_command_async",
            return_value=("Configuration valid!", "", 0),
        ):
            is_valid, message = await service.check_config()

        assert is_valid is True
        assert "valid" in message.lower()

    @pytest.mark.asyncio
    async def test_check_config_invalid(self) -> None:
        """Test check_config with invalid config."""
        service = SystemService()

        with patch.object(
            service,
            "_run_ssh_command_async",
            return_value=("", "Invalid configuration at line 42", 1),
        ):
            is_valid, message = await service.check_config()

        assert is_valid is False
        assert "Invalid" in message

    @pytest.mark.asyncio
    async def test_restart_api_first_then_ssh(self) -> None:
        """Test restart tries API first, falls back to SSH."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(side_effect=Exception("API failed"))

        service = SystemService(client=mock_client, host="test-host", user="test-user")

        with patch.object(
            service,
            "_run_ssh_command_async",
            return_value=("Restart initiated", "", 0),
        ):
            success, message = await service.restart()

        assert success is True
        assert "Restart" in message

    @pytest.mark.asyncio
    async def test_restart_api_success_no_ssh(self) -> None:
        """Test restart succeeds via API without SSH fallback."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(return_value=None)

        service = SystemService(client=mock_client)

        with patch.object(service, "_run_ssh_command_async") as mock_ssh:
            success, message = await service.restart()

        assert success is True
        # SSH should not be called when API succeeds
        mock_ssh.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_logs_full(self) -> None:
        """Test get_logs for full logs via SSH."""
        service = SystemService()

        log_content = "2025-12-11 INFO homeassistant.core: Starting\n" * 10

        with patch.object(
            service,
            "_run_ssh_command_async",
            return_value=(log_content, "", 0),
        ):
            result = await service.get_logs(lines=100)

        assert "Starting" in result

    @pytest.mark.asyncio
    async def test_get_logs_filtered(self) -> None:
        """Test get_logs with filter pattern."""
        service = SystemService()

        with patch.object(
            service,
            "_run_ssh_command_async",
            return_value=("Filtered output", "", 0),
        ) as mock_ssh:
            result = await service.get_logs(lines=50, filter_pattern="error")

        # Should include grep in command
        call_args = mock_ssh.call_args[0][0]
        assert "grep" in call_args
        assert "error" in call_args

    @pytest.mark.asyncio
    async def test_get_logs_errors_only_via_api(self) -> None:
        """Test get_logs with errors_only uses API."""
        mock_client = MagicMock()
        mock_client._rest = AsyncMock(return_value="Error log from API")

        service = SystemService(client=mock_client)

        with patch.object(service, "_run_ssh_command_async") as mock_ssh:
            result = await service.get_logs(errors_only=True)

        assert result == "Error log from API"
        mock_ssh.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_info_api_first(self) -> None:
        """Test get_info tries API first."""
        mock_client = MagicMock()
        mock_client._rest = AsyncMock(
            return_value={
                "version": "2025.12.1",
                "installation_type": "Home Assistant OS",
            }
        )

        service = SystemService(client=mock_client, host="10.0.20.35")

        with patch.object(service, "_run_ssh_command_async") as mock_ssh:
            result = await service.get_info()

        assert result is not None
        assert result.version == "2025.12.1"
        mock_ssh.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_info_ssh_fallback(self) -> None:
        """Test get_info falls back to SSH."""
        mock_client = MagicMock()
        mock_client._rest = AsyncMock(return_value=None)

        service = SystemService(client=mock_client, host="10.0.20.35")

        ssh_output = "version: 2025.12.1\nmachine: qemux86-64\n"

        with patch.object(
            service,
            "_run_ssh_command_async",
            return_value=(ssh_output, "", 0),
        ):
            result = await service.get_info()

        assert result is not None
        assert result.version == "2025.12.1"
        assert result.installation_type == "qemux86-64"

    @pytest.mark.asyncio
    async def test_get_info_all_failed(self) -> None:
        """Test get_info returns None when all methods fail."""
        service = SystemService()

        with patch.object(
            service,
            "_run_ssh_command_async",
            return_value=("", "Error", 1),
        ):
            result = await service.get_info()

        assert result is None


class TestSSHCommandSecurity:
    """Test SSH command security measures."""

    @pytest.mark.asyncio
    async def test_ssh_uses_exec_not_shell(self) -> None:
        """Test SSH uses create_subprocess_exec (not shell)."""
        service = SystemService(host="test-host", user="test-user")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await service._run_ssh_command_async("ha core info")

        # Should use exec, not shell
        mock_exec.assert_called_once()
        # First arg should be "ssh"
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "ssh"

    @pytest.mark.asyncio
    async def test_ssh_includes_batch_mode(self) -> None:
        """Test SSH includes BatchMode=yes option."""
        service = SystemService(host="test-host", user="test-user")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await service._run_ssh_command_async("ha core info")

        call_args = mock_exec.call_args[0]
        # BatchMode should be in the args
        assert "-o" in call_args
        args_str = " ".join(call_args)
        assert "BatchMode=yes" in args_str

    @pytest.mark.asyncio
    async def test_ssh_includes_connect_timeout(self) -> None:
        """Test SSH includes ConnectTimeout option."""
        service = SystemService(host="test-host", user="test-user")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await service._run_ssh_command_async("ha core info")

        call_args = mock_exec.call_args[0]
        args_str = " ".join(call_args)
        assert "ConnectTimeout" in args_str

    @pytest.mark.asyncio
    async def test_ssh_command_as_single_arg(self) -> None:
        """Test remote command is passed as single argument."""
        service = SystemService(host="test-host", user="test-user")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await service._run_ssh_command_async("ha core info && echo done")

        call_args = mock_exec.call_args[0]
        # The remote command should be the last argument as a single string
        assert call_args[-1] == "ha core info && echo done"


class TestSystemServiceIntegrations:
    """Test get_integrations() method."""

    @pytest.mark.asyncio
    async def test_get_integrations_no_client(self) -> None:
        """Test get_integrations without client raises error."""
        from ha_cli.common.exceptions import HAAutomationError

        service = SystemService()
        with pytest.raises(HAAutomationError, match="No API client available"):
            await service.get_integrations()

    @pytest.mark.asyncio
    async def test_get_integrations_success(self) -> None:
        """Test get_integrations returns correctly mapped entries."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(
            return_value=[
                {
                    "entry_id": "abc123",
                    "domain": "sonos",
                    "title": "Living Room",
                    "state": "loaded",
                    "disabled_by": None,
                },
                {
                    "entry_id": "def456",
                    "domain": "zha",
                    "title": "Zigbee",
                    "state": "loaded",
                    "disabled_by": None,
                },
            ]
        )

        service = SystemService(client=mock_client)
        entries = await service.get_integrations()

        # Verify WS call was made with correct message type
        mock_client._ws_call.assert_called_once_with("config_entries/get")

        assert len(entries) == 2
        assert entries[0]["entry_id"] == "abc123"
        assert entries[0]["domain"] == "sonos"
        assert entries[1]["entry_id"] == "def456"
        assert entries[1]["domain"] == "zha"

    @pytest.mark.asyncio
    async def test_get_integrations_domain_filter(self) -> None:
        """Test get_integrations filters by domain."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(
            return_value=[
                {"entry_id": "abc", "domain": "sonos", "title": "S1", "state": "loaded"},
                {"entry_id": "def", "domain": "zha", "title": "Z1", "state": "loaded"},
                {"entry_id": "ghi", "domain": "sonos", "title": "S2", "state": "loaded"},
            ]
        )

        service = SystemService(client=mock_client)
        entries = await service.get_integrations(domain="sonos")

        assert len(entries) == 2
        assert all(e["domain"] == "sonos" for e in entries)

    @pytest.mark.asyncio
    async def test_get_integrations_unhealthy_filter(self) -> None:
        """Test get_integrations filters unhealthy only."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(
            return_value=[
                {"entry_id": "abc", "domain": "good", "title": "G", "state": "loaded"},
                {"entry_id": "def", "domain": "bad", "title": "B", "state": "setup_error"},
                {"entry_id": "ghi", "domain": "retry", "title": "R", "state": "setup_retry"},
            ]
        )

        service = SystemService(client=mock_client)
        entries = await service.get_integrations(unhealthy_only=True)

        assert len(entries) == 2
        assert entries[0]["state"] == "setup_error"
        assert entries[1]["state"] == "setup_retry"

    @pytest.mark.asyncio
    async def test_get_integrations_unexpected_response_type(self) -> None:
        """Test get_integrations raises error on non-list response."""
        from ha_cli.common.exceptions import HAAutomationError

        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(return_value={"error": "unexpected"})

        service = SystemService(client=mock_client)
        with pytest.raises(HAAutomationError, match="Unexpected response"):
            await service.get_integrations()

    @pytest.mark.asyncio
    async def test_get_integrations_type_coercion(self) -> None:
        """Test get_integrations handles None/non-string values safely."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(
            return_value=[
                {
                    "entry_id": "abc123",
                    "domain": None,  # Should become ""
                    "title": None,   # Should become ""
                    "state": None,   # Should become "unknown"
                },
                {
                    "entry_id": "def456",
                    "domain": 123,   # Should become "123"
                    "title": "Test",
                    "state": "loaded",
                },
            ]
        )

        service = SystemService(client=mock_client)
        entries = await service.get_integrations()

        assert len(entries) == 2
        # First entry with None values
        assert entries[0]["domain"] == ""
        assert entries[0]["title"] == ""
        assert entries[0]["state"] == "unknown"
        # Second entry with numeric domain
        assert entries[1]["domain"] == "123"

    @pytest.mark.asyncio
    async def test_get_integrations_skips_invalid_entries(self) -> None:
        """Test get_integrations skips entries without valid entry_id."""
        mock_client = MagicMock()
        mock_client._ws_call = AsyncMock(
            return_value=[
                {"entry_id": "", "domain": "bad1", "title": "No ID", "state": "loaded"},
                {"entry_id": None, "domain": "bad2", "title": "Null ID", "state": "loaded"},
                {"domain": "bad3", "title": "Missing ID", "state": "loaded"},
                {"entry_id": "valid", "domain": "good", "title": "Valid", "state": "loaded"},
                "not_a_dict",  # Should be skipped
            ]
        )

        service = SystemService(client=mock_client)
        entries = await service.get_integrations()

        assert len(entries) == 1
        assert entries[0]["entry_id"] == "valid"

    @pytest.mark.asyncio
    async def test_get_integrations_preserves_haautomation_error(self) -> None:
        """Test that HAAutomationError is not double-wrapped."""
        from ha_cli.common.exceptions import HAAutomationError

        mock_client = MagicMock()
        original_error = HAAutomationError("Original error", details={"key": "value"})
        mock_client._ws_call = AsyncMock(side_effect=original_error)

        service = SystemService(client=mock_client)

        with pytest.raises(HAAutomationError) as exc_info:
            await service.get_integrations()

        # Should be the exact same error, not wrapped
        assert exc_info.value is original_error
        assert exc_info.value.details == {"key": "value"}

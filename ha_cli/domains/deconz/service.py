"""deCONZ service for API interactions."""

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# SSH connection options for safety (consistent with system domain)
SSH_OPTIONS = [
    "-o", "BatchMode=yes",           # Never prompt for password/passphrase
    "-o", "ConnectTimeout=10",       # Connection timeout in seconds
    "-o", "StrictHostKeyChecking=accept-new",  # Accept new keys, reject changed
]

# SSH command timeout (seconds)
SSH_TIMEOUT = 30


class DeconzError(Exception):
    """deCONZ-specific error for structured error handling."""

    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.returncode = returncode


class SSHError(DeconzError):
    """SSH-specific error for connection failures."""
    pass


class APIError(DeconzError):
    """deCONZ API-specific error."""
    pass


@dataclass
class DeconzConfig:
    """deCONZ connection configuration."""

    host: str
    port: int
    api_key: str


@dataclass
class DeconzDevice:
    """Represents a deCONZ device."""

    id: str
    name: str
    model: str
    ieee: str
    device_type: str  # 'light' or 'sensor'
    sensor_type: str | None = None  # e.g., 'ZHASwitch', 'ZHAPresence'


class DeconzService:
    """Service for interacting with deCONZ API."""

    def __init__(self, ssh_host: str = "homeassistant"):
        self.ssh_host = ssh_host
        self._config: DeconzConfig | None = None

    def _run_ssh(self, cmd: str, timeout: int = SSH_TIMEOUT) -> str:
        """Run command on Home Assistant via SSH.

        Args:
            cmd: Command to run on remote host
            timeout: Timeout in seconds (default: SSH_TIMEOUT)

        Returns:
            Command stdout

        Raises:
            SSHError: On connection failure or timeout
        """
        ssh_args = ["ssh", *SSH_OPTIONS, self.ssh_host, cmd]
        logger.debug(f"Running SSH command: {' '.join(ssh_args)}")

        try:
            result = subprocess.run(
                ssh_args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise SSHError(f"SSH command timed out after {timeout}s", returncode=-1) from e
        except FileNotFoundError as e:
            raise SSHError("SSH client not found. Is OpenSSH installed?", returncode=-1) from e
        except OSError as e:
            raise SSHError(f"SSH execution error: {e}", returncode=-1) from e

        # Check for SSH-specific connection errors
        if result.returncode == 255:
            error_msg = result.stderr.strip() or "SSH connection failed"
            raise SSHError(f"SSH connection error: {error_msg}", returncode=255)

        if result.returncode != 0:
            raise SSHError(f"SSH command failed: {result.stderr}", returncode=result.returncode)

        return result.stdout

    def get_config(self) -> DeconzConfig:
        """Auto-discover deCONZ configuration from Home Assistant."""
        if self._config:
            return self._config

        output = self._run_ssh("cat /config/.storage/core.config_entries")
        data = json.loads(output)

        for entry in data.get("data", {}).get("entries", []):
            if entry.get("domain") == "deconz":
                config_data = entry.get("data", {})
                self._config = DeconzConfig(
                    host=config_data.get("host", "core-deconz"),
                    port=config_data.get("port", 40850),
                    api_key=config_data.get("api_key", ""),
                )
                return self._config

        raise RuntimeError("deCONZ integration not found in Home Assistant config")

    def _api_call(self, endpoint: str, method: str = "GET") -> dict[str, Any]:
        """Make deCONZ REST API call.

        Args:
            endpoint: API endpoint (e.g., 'lights', 'sensors/1')
            method: HTTP method (GET or DELETE)

        Returns:
            Response as dictionary

        Raises:
            APIError: When API returns an error response
            SSHError: When SSH command fails
        """
        config = self.get_config()
        url = f"http://{config.host}:{config.port}/api/{config.api_key}/{endpoint}"

        if method == "GET":
            cmd = f"curl -s '{url}'"
        elif method == "DELETE":
            cmd = f"curl -s -X DELETE '{url}'"
        else:
            raise ValueError(f"Unsupported method: {method}")

        output = self._run_ssh(cmd)
        if not output.strip():
            return {}

        try:
            result = json.loads(output)
        except json.JSONDecodeError as e:
            raise APIError(f"Invalid JSON response from deCONZ: {e}") from e

        # deCONZ returns errors as a list: [{"error": {"type": 3, "description": "..."}}]
        if isinstance(result, list):
            if result and isinstance(result[0], dict) and "error" in result[0]:
                error_info = result[0]["error"]
                error_desc = error_info.get("description", "Unknown error")
                error_type = error_info.get("type", 0)
                raise APIError(f"deCONZ API error (type {error_type}): {error_desc}")
            # Success responses can also be lists (e.g., DELETE returns [{"success": "..."}])
            # Return as-is for delete operations to handle in caller
            if result and isinstance(result[0], dict) and "success" in result[0]:
                return {"_success_list": result}

        # At this point result should be a dict (normal API response)
        if isinstance(result, dict):
            return result
        return {}

    def list_lights(self, search: str | None = None) -> list[DeconzDevice]:
        """List all lights from deCONZ."""
        lights = self._api_call("lights")
        result = []

        for light_id, light in lights.items():
            name = light.get("name", "")
            if search and search.lower() not in name.lower():
                continue

            result.append(
                DeconzDevice(
                    id=light_id,
                    name=name,
                    model=light.get("modelid", ""),
                    ieee=light.get("uniqueid", "").split("-")[0],
                    device_type="light",
                )
            )

        return sorted(result, key=lambda d: int(d.id))

    def list_sensors(self, search: str | None = None) -> list[DeconzDevice]:
        """List all sensors from deCONZ."""
        sensors = self._api_call("sensors")
        result = []

        for sensor_id, sensor in sensors.items():
            name = sensor.get("name", "")
            if search and search.lower() not in name.lower():
                continue

            result.append(
                DeconzDevice(
                    id=sensor_id,
                    name=name,
                    model=sensor.get("modelid", ""),
                    ieee=sensor.get("uniqueid", "").split("-")[0],
                    device_type="sensor",
                    sensor_type=sensor.get("type"),
                )
            )

        return sorted(result, key=lambda d: int(d.id))

    def list_groups(self) -> list[dict]:
        """List all groups from deCONZ."""
        groups = self._api_call("groups")
        result = []

        for group_id, group in groups.items():
            result.append(
                {
                    "id": group_id,
                    "name": group.get("name", ""),
                    "lights": group.get("lights", []),
                }
            )

        return sorted(result, key=lambda g: int(g["id"]))

    def get_device(self, device_type: str, device_id: str) -> DeconzDevice | None:
        """Get a specific device by type and ID."""
        endpoint = f"{device_type}s/{device_id}"
        try:
            device = self._api_call(endpoint)
            return DeconzDevice(
                id=device_id,
                name=device.get("name", "Unknown"),
                model=device.get("modelid", ""),
                ieee=device.get("uniqueid", "").split("-")[0],
                device_type=device_type,
                sensor_type=device.get("type") if device_type == "sensor" else None,
            )
        except Exception:
            return None

    def delete_device(self, device_type: str, device_id: str) -> bool:
        """Delete a device from deCONZ.

        Args:
            device_type: Type of device ('light' or 'sensor')
            device_id: deCONZ device ID

        Returns:
            True if deletion succeeded

        Raises:
            APIError: If deCONZ returns an error
            SSHError: If SSH connection fails
        """
        endpoint = f"{device_type}s/{device_id}"
        result = self._api_call(endpoint, method="DELETE")

        # Success list is now wrapped in {"_success_list": [...]}
        if isinstance(result, dict) and "_success_list" in result:
            return True
        return False

    def search(self, query: str) -> tuple[list[DeconzDevice], list[DeconzDevice]]:
        """Search for devices by name."""
        lights = self.list_lights(search=query)
        sensors = self.list_sensors(search=query)
        return lights, sensors

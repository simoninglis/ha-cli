"""Service layer for system operations.

Supports two modes:
1. API mode: Uses HA REST/WebSocket API (preferred when available)
2. SSH mode: Falls back to SSH for operations not available via API (e.g., full logs)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...common.client import HAClient

logger = logging.getLogger(__name__)

# SSH connection options for safety
SSH_OPTIONS = [
    "-o", "BatchMode=yes",           # Never prompt for password/passphrase
    "-o", "ConnectTimeout=10",       # Connection timeout in seconds
    "-o", "StrictHostKeyChecking=accept-new",  # Accept new keys, reject changed
]


class SSHError(Exception):
    """SSH-specific error for structured error handling."""

    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


@dataclass
class SystemInfo:
    """Home Assistant system information."""

    version: str
    installation_type: str
    host: str

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "installation_type": self.installation_type,
            "host": self.host,
        }


class SystemService:
    """Service for system operations.

    Uses HA API when possible, falls back to SSH for operations like full logs.
    """

    def __init__(
        self,
        client: "HAClient | None" = None,
        host: str = "10.0.20.35",
        user: str = "root",
    ) -> None:
        """Initialize with optional HAClient and SSH details.

        Args:
            client: HAClient for API operations (optional)
            host: SSH host for fallback operations
            user: SSH user for fallback operations
        """
        self.client = client
        self.host = host
        self.user = user

    # -------------------------------------------------------------------------
    # API-based methods (preferred)
    # -------------------------------------------------------------------------

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_ids: list[str] | None = None,
        service_data: dict | None = None,
    ) -> dict:
        """Call a Home Assistant service via WebSocket API.

        Args:
            domain: Service domain (e.g., "light", "switch", "automation")
            service: Service name (e.g., "turn_on", "turn_off")
            entity_ids: Optional list of entity IDs to target
            service_data: Optional additional service data

        Returns:
            Result dict from service call

        Raises:
            HAAutomationError: If no API client or service call fails
        """
        from ...common.exceptions import HAAutomationError

        if not self.client:
            raise HAAutomationError("No API client available")

        # Build target dict if entity_ids provided
        target: dict | None = None
        if entity_ids:
            target = {"entity_id": entity_ids}

        try:
            # Build call arguments
            call_kwargs: dict = {
                "domain": domain,
                "service": service,
            }
            if service_data:
                call_kwargs["service_data"] = service_data
            if target:
                call_kwargs["target"] = target

            result = await self.client._ws_call("call_service", **call_kwargs)
            return dict(result) if isinstance(result, dict) else {"success": True}
        except Exception as e:
            raise HAAutomationError(f"Service call failed: {e}") from e

    async def restart_via_api(self) -> tuple[bool, str]:
        """Restart Home Assistant via API.

        Returns:
            Tuple of (success, message)
        """
        if not self.client:
            return False, "No API client available"

        try:
            await self.client._ws_call(
                "call_service",
                domain="homeassistant",
                service="restart",
            )
            return True, "Restart initiated successfully"
        except Exception as e:
            return False, f"API restart failed: {e}"

    async def reload_via_api(self, component: str | None = None) -> tuple[bool, str]:
        """Reload configuration via API.

        Args:
            component: Specific component to reload. Supported:
                - automations, scripts, scenes, groups
                - input_boolean, input_number, input_text, input_datetime, input_select
                - template, person, zone, timer
                - all/core (full restart)

        Returns:
            Tuple of (success, message)
        """
        if not self.client:
            return False, "No API client available"

        # Map component names to service domains
        reload_services = {
            "automations": ("automation", "reload"),
            "automation": ("automation", "reload"),
            "scripts": ("script", "reload"),
            "script": ("script", "reload"),
            "scenes": ("scene", "reload"),
            "scene": ("scene", "reload"),
            "groups": ("group", "reload"),
            "group": ("group", "reload"),
            "input_boolean": ("input_boolean", "reload"),
            "input_number": ("input_number", "reload"),
            "input_text": ("input_text", "reload"),
            "input_datetime": ("input_datetime", "reload"),
            "input_select": ("input_select", "reload"),
            "template": ("template", "reload"),
            "person": ("person", "reload"),
            "zone": ("zone", "reload"),
            "timer": ("timer", "reload"),
            "intent_script": ("intent_script", "reload"),
            "all": None,  # Full restart
            "core": None,  # Full restart
        }

        if component and component.lower() in reload_services:
            service_info = reload_services[component.lower()]
            if service_info is None:
                # Full restart requested
                return await self.restart_via_api()

            domain, service = service_info
            try:
                await self.client._ws_call(
                    "call_service",
                    domain=domain,
                    service=service,
                )
                return True, f"Reloaded {component} successfully"
            except Exception as e:
                return False, f"Failed to reload {component}: {e}"

        # If no specific component or unknown, try homeassistant.reload_all
        if not component:
            try:
                # Try to reload common components
                reloaded = []
                for comp in ["automation", "script", "scene"]:
                    try:
                        await self.client._ws_call(
                            "call_service",
                            domain=comp,
                            service="reload",
                        )
                        reloaded.append(comp)
                    except Exception as e:
                        logger.debug(f"Failed to reload {comp}: {e}")
                if reloaded:
                    return True, f"Reloaded: {', '.join(reloaded)}"
                return False, "No components reloaded"
            except Exception as e:
                return False, f"Reload failed: {e}"

        return False, f"Unknown component: {component}. Use: {', '.join(reload_services.keys())}"

    async def render_template(self, template_str: str) -> str:
        """Render a Jinja2 template against Home Assistant state.

        Args:
            template_str: The Jinja2 template string to evaluate

        Returns:
            Rendered template result as string

        Raises:
            HAAutomationError: If no API client or template fails to render
        """
        from ...common.exceptions import HAAutomationError

        if not self.client:
            raise HAAutomationError("No API client available")

        try:
            # POST /api/template returns plain text, not JSON
            result = await self.client._rest(
                "POST",
                "/api/template",
                json_data={"template": template_str},
                expect_json=False,
            )
            return str(result) if result else ""
        except Exception as e:
            raise HAAutomationError(f"Template rendering failed: {e}") from e

    async def get_error_log_via_api(self) -> str:
        """Get error log via REST API.

        Note: This only returns errors, not full logs.

        Returns:
            Error log content
        """
        if not self.client:
            return "No API client available"

        try:
            result = await self.client._rest("GET", "/api/error_log")
            return str(result) if result else "No errors logged"
        except Exception as e:
            return f"Failed to get error log: {e}"

    async def get_config_via_api(self) -> dict | None:
        """Get Home Assistant config via API.

        Returns:
            Config dict or None if unavailable
        """
        if not self.client:
            return None

        try:
            result = await self.client._rest("GET", "/api/config")
            return dict(result) if isinstance(result, dict) else None
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # SSH-based methods (fallback)
    # -------------------------------------------------------------------------

    async def _run_ssh_command_async(
        self, command: str, timeout: int = 120
    ) -> tuple[str, str, int]:
        """Run a command via SSH asynchronously.

        Uses create_subprocess_exec with proper argument handling to prevent
        command injection. Includes BatchMode and ConnectTimeout for safety.

        Args:
            command: Command to run on remote host
            timeout: Timeout in seconds

        Returns:
            Tuple of (stdout, stderr, returncode)

        Raises:
            SSHError: On connection failure or timeout
        """
        # Build SSH command as argument list (not shell string) for security
        # This prevents command injection via host/user parameters
        # Note: No shell quoting needed with create_subprocess_exec - args are passed directly
        ssh_args = [
            "ssh",
            *SSH_OPTIONS,
            f"{self.user}@{self.host}",
            command,  # Command is passed as single argument to SSH
        ]

        logger.debug(f"Running SSH command: {' '.join(ssh_args)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""

            # Check for SSH-specific connection errors
            if proc.returncode == 255:
                # SSH connection failed
                error_msg = stderr_str.strip() or "SSH connection failed"
                raise SSHError(f"SSH connection error: {error_msg}", returncode=255)

            return stdout_str, stderr_str, proc.returncode or 0

        except asyncio.TimeoutError as e:
            if proc:
                proc.kill()
            raise SSHError(f"SSH command timed out after {timeout}s", returncode=-1) from e
        except FileNotFoundError as e:
            raise SSHError("SSH client not found. Is OpenSSH installed?", returncode=-1) from e
        except OSError as e:
            raise SSHError(f"SSH execution error: {e}", returncode=-1) from e

    async def check_config(self) -> tuple[bool, str]:
        """Check Home Assistant configuration validity via SSH.

        Returns:
            Tuple of (is_valid, message)
        """
        stdout, stderr, returncode = await self._run_ssh_command_async(
            "ha core check", timeout=60
        )
        is_valid = returncode == 0
        message = stdout.strip() if is_valid else stderr.strip() or stdout.strip()
        return is_valid, message

    async def restart(self) -> tuple[bool, str]:
        """Restart Home Assistant core.

        Tries API first, falls back to SSH.

        Returns:
            Tuple of (success, message)
        """
        # Try API first
        if self.client:
            success, message = await self.restart_via_api()
            if success:
                return success, message
            logger.info(f"API restart failed ({message}), falling back to SSH")

        # Fall back to SSH
        logger.debug("Restarting via SSH")
        stdout, stderr, returncode = await self._run_ssh_command_async(
            "ha core restart", timeout=120
        )
        success = returncode == 0
        message = stdout.strip() if success else stderr.strip() or stdout.strip()
        return success, message

    async def reload(self, component: str | None = None) -> tuple[bool, str]:
        """Reload Home Assistant configuration or specific component.

        Tries API first for component reloads.

        Args:
            component: Specific component to reload (e.g., 'automations', 'scripts')
                      If None, reloads common components

        Returns:
            Tuple of (success, message)
        """
        # Try API first
        if self.client:
            return await self.reload_via_api(component)

        # Fall back to SSH for full restart
        if component in ("core", "all", None):
            return await self.restart()

        return False, f"Component reload for '{component}' requires API client"

    async def get_logs(
        self,
        lines: int = 100,
        filter_pattern: str | None = None,
        errors_only: bool = False,
    ) -> str:
        """Get Home Assistant logs.

        Uses SSH for full logs, API for error log only.

        Args:
            lines: Number of lines to retrieve
            filter_pattern: Optional grep pattern to filter logs
            errors_only: If True, use API to get only error log

        Returns:
            Log output as string
        """
        # If errors only and we have API client, use it
        if errors_only and self.client:
            return await self.get_error_log_via_api()

        # Use SSH for full logs
        cmd = f"ha core logs 2>&1 | tail -{lines}"
        if filter_pattern:
            cmd = f"ha core logs 2>&1 | grep -i -A3 -B3 {filter_pattern!r} | tail -{lines}"

        stdout, stderr, returncode = await self._run_ssh_command_async(
            cmd, timeout=30
        )

        if returncode != 0 and not stdout:
            return stderr or "Failed to retrieve logs"

        return stdout

    async def get_info(self) -> SystemInfo | None:
        """Get Home Assistant system info.

        Tries API first, falls back to SSH.

        Returns:
            SystemInfo object or None if unavailable
        """
        # Try API first
        if self.client:
            config = await self.get_config_via_api()
            if config:
                return SystemInfo(
                    version=config.get("version", "unknown"),
                    installation_type=config.get("installation_type", "unknown"),
                    host=self.host,
                )
            logger.info("API config retrieval failed, falling back to SSH")

        # Fall back to SSH
        logger.debug("Getting system info via SSH")
        stdout, stderr, returncode = await self._run_ssh_command_async(
            "ha core info", timeout=30
        )

        if returncode != 0:
            return None

        # Parse the output (it's YAML-like key: value format)
        info: dict[str, str] = {}
        for line in stdout.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                info[key.strip().lower().replace(" ", "_")] = value.strip()

        return SystemInfo(
            version=info.get("version", "unknown"),
            installation_type=info.get("machine", "unknown"),
            host=self.host,
        )

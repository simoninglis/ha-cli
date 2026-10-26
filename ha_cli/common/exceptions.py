"""Custom exceptions for Home Assistant Automation CLI."""

import re
from dataclasses import dataclass
from typing import Any


class HAAutomationError(Exception):
    """Base exception for Home Assistant Automation errors.

    All exceptions in the ha-cli tool inherit from this class, allowing
    callers to catch all tool-specific errors with a single except clause.

    Attributes:
        message: Human-readable error description.
        details: Optional dictionary with additional context (e.g., entity_id,
            HTTP status code, API response).

    Example:
        try:
            await service.get_automation(automation_id)
        except HAAutomationError as e:
            print(f"Error: {e.message}")
            if e.details:
                print(f"Details: {e.details}")
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize exception with message and optional details."""
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConnectionError(HAAutomationError):
    """Raised when connection to Home Assistant fails.

    Common causes:
        - Home Assistant is not running or unreachable
        - Incorrect URL (wrong host, port, or protocol)
        - Network issues (firewall, DNS resolution)
        - SSL/TLS certificate problems

    Example:
        try:
            async with HAClient(url, token) as client:
                ...
        except ConnectionError as e:
            print(f"Cannot connect to Home Assistant: {e.message}")
    """

    pass


class AuthenticationError(HAAutomationError):
    """Raised when authentication fails (HTTP 401).

    Common causes:
        - Invalid or expired access token
        - Token lacks required permissions
        - Token revoked in Home Assistant

    Resolution:
        Generate a new long-lived access token in Home Assistant:
        Profile → Long-Lived Access Tokens → Create Token

    Example:
        try:
            await client.get_states()
        except AuthenticationError:
            print("Invalid token. Please generate a new access token.")
    """

    pass


class NotFoundError(HAAutomationError):
    """Raised when a requested resource is not found (HTTP 404).

    Common causes:
        - Entity, automation, or dashboard doesn't exist
        - Typo in resource identifier
        - Resource was deleted
        - REST API endpoint not available (requires config integration)

    Example:
        try:
            config = await service.get_dashboard("my-dashboard")
        except NotFoundError as e:
            print(f"Dashboard not found: {e.message}")
    """

    pass


class ValidationError(HAAutomationError):
    """Raised when validation fails (HTTP 400).

    Common causes:
        - Invalid configuration structure
        - Missing required fields
        - Invalid field values or types
        - Schema validation failure

    The details dict often contains specific validation errors from
    Home Assistant's response.

    Example:
        try:
            await service.create_automation(config)
        except ValidationError as e:
            print(f"Invalid configuration: {e.message}")
            for field, error in e.details.items():
                print(f"  {field}: {error}")
    """

    pass


class ConfigurationError(HAAutomationError):
    """Raised when local CLI configuration is invalid or missing.

    Common causes:
        - Missing HA_URL or HA_TOKEN environment variables
        - Malformed config file (~/.config/home-assistant-cli/config.json)
        - Invalid URL format

    Resolution:
        Set environment variables or create config file:
        - export HA_URL="http://homeassistant.local:8123"
        - export HA_TOKEN="your-long-lived-access-token"

    Example:
        try:
            url, token = get_client_config()
        except ConfigurationError as e:
            print(f"Configuration error: {e.message}")
    """

    pass


class MissingCredentialsError(ConfigurationError, ValueError):
    """No Home Assistant URL and/or token could be found, and no prompt was possible.

    Also a ValueError, which is what get_client_config raised before it had a type of
    its own, so existing `except ValueError` callers keep working.
    """

    pass


class AutomationNotFoundError(NotFoundError):
    """Raised when a specific automation is not found.

    This is a specialized NotFoundError that includes the automation_id
    for easier error handling and reporting.

    Attributes:
        automation_id: The ID of the automation that wasn't found.

    Example:
        try:
            config = await service.get_automation("motion_lights")
        except AutomationNotFoundError as e:
            print(f"Automation '{e.automation_id}' does not exist")
    """

    def __init__(self, automation_id: str) -> None:
        """Initialize with automation ID."""
        super().__init__(
            f"Automation '{automation_id}' not found",
            {"automation_id": automation_id}
        )
        self.automation_id = automation_id


class HAServerError(HAAutomationError):
    """Raised when Home Assistant returns a server error (HTTP 5xx).

    Common causes:
        - Home Assistant internal error
        - Integration crash or timeout
        - Database issues
        - Resource exhaustion

    These errors are typically transient and may resolve on retry.
    Check Home Assistant logs for more details.

    Example:
        try:
            await client.call_service("light", "turn_on", {"entity_id": "light.living_room"})
        except HAServerError as e:
            print(f"Home Assistant error: {e.message}")
            print("Check Home Assistant logs for details.")
    """

    pass


class WebSocketError(HAAutomationError):
    """Raised when a WebSocket operation fails.

    Common causes:
        - WebSocket connection closed unexpectedly
        - Message format error
        - Subscription failure
        - Authentication required for WebSocket

    WebSocket is used for real-time operations like monitoring
    automation triggers and subscribing to state changes.

    Example:
        try:
            async for event in client.subscribe_automation_events():
                process(event)
        except WebSocketError as e:
            print(f"WebSocket error: {e.message}")
    """

    pass


class TimeoutError(HAAutomationError):
    """Raised when an operation exceeds the configured timeout.

    Common causes:
        - Network latency
        - Home Assistant under heavy load
        - Large response payload
        - Slow integration response

    Resolution:
        Increase timeout with --timeout flag or check network connectivity.

    Example:
        try:
            states = await client.get_states()
        except TimeoutError:
            print("Operation timed out. Try increasing --timeout value.")
    """

    pass


# Exit codes for CLI commands
EXIT_SUCCESS = 0        # Operation completed successfully
EXIT_USAGE_ERROR = 1    # Invalid arguments or usage
EXIT_NETWORK_ERROR = 2  # Network/connection failure
EXIT_HA_ERROR = 3       # Home Assistant returned an error


# Known HA WebSocket error code prefixes (format: "{code}: {message}")
# These have specific classifications based on their code
HA_ERROR_CODE_USAGE: set[str] = {
    "not_found",
    "unknown_command",
    "validation_error",
    "invalid_format",
}

HA_ERROR_CODE_AUTH: set[str] = {
    "unauthorized",
}

# Transport error keywords - use specific phrases to avoid false positives
# Note: Avoid bare "connect" as it matches entity IDs like "binary_sensor.ha_connected"
TRANSPORT_ERROR_KEYWORDS: tuple[str, ...] = (
    "timeout",
    "timed out",
    "connection closed",
    "not connected",
    "failed to connect",
    "connection refused",
    "connection reset",
)

# Pattern for HA error code prefix: lowercase letters and underscores only
# e.g., "not_found:", "home_assistant_error:", "unknown:"
_HA_CODE_PREFIX_PATTERN = re.compile(r"^[a-z_]+$")


def _looks_like_ha_code_prefix(prefix: str) -> bool:
    """Check if a prefix looks like an HA WebSocket error code.

    HA error codes are lowercase with underscores (e.g., "not_found", "home_assistant_error").
    This catches unknown codes that aren't in our allowlist.
    """
    return bool(_HA_CODE_PREFIX_PATTERN.match(prefix))


def classify_websocket_error(error: WebSocketError) -> tuple[str, int]:
    """Classify a WebSocketError and return (error_code, exit_code).

    Classification order (IMPORTANT - prevents misclassification):
    1. Check for HA error code prefix first (any "code:" pattern)
    2. Only check transport keywords if message doesn't have code prefix

    Args:
        error: The WebSocketError to classify

    Returns:
        Tuple of (error_code, exit_code) for CLI output

    Examples:
        >>> classify_websocket_error(WebSocketError("not_found: Entity not found"))
        ("NOT_FOUND", EXIT_USAGE_ERROR)
        >>> classify_websocket_error(WebSocketError("WebSocket call timed out after 30s"))
        ("WEBSOCKET_ERROR", EXIT_NETWORK_ERROR)
        >>> classify_websocket_error(WebSocketError("unknown: timed out waiting"))
        ("HA_ERROR", EXIT_HA_ERROR)  # Not transport - has HA code prefix
    """
    error_str = str(error)
    error_lower = error_str.lower()

    # Step 1: Check for HA error code prefix FIRST
    # Any message matching "code: message" pattern is treated as HA-level
    # This prevents misclassifying "unknown: timed out" as transport
    if ":" in error_str:
        code_prefix = error_str.split(":", 1)[0].strip().lower()
        if _looks_like_ha_code_prefix(code_prefix):
            # Classify based on the HA error code
            if code_prefix in ("not_found", "unknown_command"):
                return ("NOT_FOUND", EXIT_USAGE_ERROR)
            elif code_prefix in ("validation_error", "invalid_format"):
                return ("VALIDATION_ERROR", EXIT_USAGE_ERROR)
            elif code_prefix == "unauthorized":
                return ("AUTH_ERROR", EXIT_HA_ERROR)
            else:
                # Other HA errors (home_assistant_error, service_not_found, unknown, etc.)
                return ("HA_ERROR", EXIT_HA_ERROR)

    # Step 2: Check for transport keywords only if no HA error code prefix
    if any(kw in error_lower for kw in TRANSPORT_ERROR_KEYWORDS):
        return ("WEBSOCKET_ERROR", EXIT_NETWORK_ERROR)

    # Step 3: Default to HA error
    return ("HA_ERROR", EXIT_HA_ERROR)


def is_transport_error(error: WebSocketError) -> bool:
    """Check if a WebSocketError is a transport-level error.

    Transport errors affect all operations and should propagate immediately
    rather than being collected as per-entity failures.

    Args:
        error: The WebSocketError to check

    Returns:
        True if this is a transport error (timeout, connection closed, etc.)

    Examples:
        >>> is_transport_error(WebSocketError("WebSocket call timed out after 30s"))
        True
        >>> is_transport_error(WebSocketError("not_found: Entity not found"))
        False
    """
    error_code, exit_code = classify_websocket_error(error)
    return exit_code == EXIT_NETWORK_ERROR


@dataclass
class EntityFailure:
    """Structured failure info for entity operations.

    Used by set_entities_exposure() to return rich failure information
    that allows the CLI to pick the most severe exit code.
    """

    entity_id: str
    error_code: str
    exit_code: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for porcelain output."""
        return {
            "entity_id": self.entity_id,
            "error_code": self.error_code,
            "message": self.message,
        }


def get_most_severe_exit_code(failures: list[EntityFailure], default: int = EXIT_USAGE_ERROR) -> int:
    """Get the most severe exit code from a list of failures.

    Exit code severity order (highest to lowest):
    - EXIT_HA_ERROR (3) - Server-side issues
    - EXIT_NETWORK_ERROR (2) - Connection issues
    - EXIT_USAGE_ERROR (1) - Client-side issues

    Args:
        failures: List of EntityFailure objects
        default: Default exit code if list is empty

    Returns:
        The most severe exit code found, or default if empty
    """
    if not failures:
        return default

    # Higher exit code = more severe
    return max(f.exit_code for f in failures)

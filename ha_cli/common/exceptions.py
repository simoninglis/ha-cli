"""Custom exceptions for Home Assistant Automation CLI."""

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

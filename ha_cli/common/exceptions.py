"""Custom exceptions for Home Assistant Automation CLI."""

from typing import Any


class HAAutomationError(Exception):
    """Base exception for Home Assistant Automation errors."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize exception with message and optional details."""
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConnectionError(HAAutomationError):
    """Raised when connection to Home Assistant fails."""
    
    pass


class AuthenticationError(HAAutomationError):
    """Raised when authentication fails (401)."""
    
    pass


class NotFoundError(HAAutomationError):
    """Raised when resource is not found (404)."""
    
    pass


class ValidationError(HAAutomationError):
    """Raised when validation fails (400)."""
    
    pass


class ConfigurationError(HAAutomationError):
    """Raised when configuration is invalid or missing."""
    
    pass


class AutomationNotFoundError(NotFoundError):
    """Raised when automation is not found."""
    
    def __init__(self, automation_id: str) -> None:
        """Initialize with automation ID."""
        super().__init__(
            f"Automation '{automation_id}' not found",
            {"automation_id": automation_id}
        )
        self.automation_id = automation_id


class HAServerError(HAAutomationError):
    """Raised when Home Assistant returns server error (5xx)."""
    
    pass


class WebSocketError(HAAutomationError):
    """Raised when WebSocket operation fails."""
    
    pass


class TimeoutError(HAAutomationError):
    """Raised when operation times out."""
    
    pass


# Exit codes as per spec
EXIT_SUCCESS = 0
EXIT_USAGE_ERROR = 1
EXIT_NETWORK_ERROR = 2
EXIT_HA_ERROR = 3
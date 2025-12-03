"""Custom exceptions for Home Assistant Automation CLI.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.common.exceptions instead.

This module re-exports all exceptions from ha_cli.common.exceptions
for backward compatibility with existing code that imports from
ha_automation.exceptions.
"""

# Re-export all exceptions from ha_cli.common.exceptions
from ha_cli.common.exceptions import (  # noqa: F401
    AuthenticationError,
    AutomationNotFoundError,
    ConfigurationError,
    ConnectionError,
    EXIT_HA_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    HAAutomationError,
    HAServerError,
    NotFoundError,
    TimeoutError,
    ValidationError,
    WebSocketError,
)

__all__ = [
    "HAAutomationError",
    "ConnectionError",
    "AuthenticationError",
    "NotFoundError",
    "ValidationError",
    "ConfigurationError",
    "AutomationNotFoundError",
    "HAServerError",
    "WebSocketError",
    "TimeoutError",
    "EXIT_SUCCESS",
    "EXIT_USAGE_ERROR",
    "EXIT_NETWORK_ERROR",
    "EXIT_HA_ERROR",
]

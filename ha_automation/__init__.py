"""Home Assistant Automation CLI Tool.

A command-line interface for managing Home Assistant automations.
"""

__version__ = "0.1.0"
__author__ = "Simbo"
__email__ = "simbo@example.com"

from .client import HAClient
from .exceptions import (
    AuthenticationError,
    ConnectionError,
    HAAutomationError,
    ValidationError,
)
from .models import Automation
from .service import AutomationCRUD, AutomationWS

__all__ = [
    "HAClient",
    "Automation",
    "AutomationCRUD",
    "AutomationWS",
    "HAAutomationError",
    "ConnectionError",
    "AuthenticationError",
    "ValidationError",
]
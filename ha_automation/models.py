"""Data models for Home Assistant automations using Pydantic v2.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.models instead.

This module re-exports all models from ha_cli.domains.automations.models
for backward compatibility with existing code.
"""

# Re-export all models from ha_cli.domains.automations.models
from ha_cli.domains.automations.models import (  # noqa: F401
    Automation,
    AutomationListResponse,
    AutomationState,
)

__all__ = [
    "Automation",
    "AutomationListResponse",
    "AutomationState",
]

"""Service layer for automation operations.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.service instead.

This module re-exports all services from ha_cli.domains.automations.service
for backward compatibility with existing code.
"""

# Re-export all services from ha_cli.domains.automations.service
from ha_cli.domains.automations.service import (  # noqa: F401
    AutomationCRUD,
    AutomationWS,
)

__all__ = [
    "AutomationCRUD",
    "AutomationWS",
]

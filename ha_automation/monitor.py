"""Automation execution monitor for real-time tracking.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.monitor instead.

This module re-exports monitor classes from ha_cli.domains.automations.monitor
for backward compatibility with existing code.
"""

# Re-export all classes from ha_cli.domains.automations.monitor
from ha_cli.domains.automations.monitor import (  # noqa: F401
    AutomationExecutionEvent,
    AutomationMonitor,
)

__all__ = [
    "AutomationExecutionEvent",
    "AutomationMonitor",
]

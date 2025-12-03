"""Trigger testing functionality for automations.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.trigger_tester instead.

This module re-exports trigger testing classes from
ha_cli.domains.automations.trigger_tester for backward compatibility.
"""

# Re-export all classes from ha_cli.domains.automations.trigger_tester
from ha_cli.domains.automations.trigger_tester import (  # noqa: F401
    TriggerEvent,
    TriggerTester,
    TriggerTestResult,
)

__all__ = [
    "TriggerEvent",
    "TriggerTestResult",
    "TriggerTester",
]

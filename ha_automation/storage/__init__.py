"""Storage module for handling both UI and file-based automations.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.storage instead.

This module re-exports storage classes from ha_cli.domains.automations.storage
for backward compatibility with existing code.
"""

# Re-export all classes from ha_cli.domains.automations.storage
from ha_cli.domains.automations.storage import (  # noqa: F401
    AutomationTypeDetector,
    FileAutomationManager,
    FormatConverter,
    UIAutomationManager,
    UnifiedAutomationService,
)

__all__ = [
    "AutomationTypeDetector",
    "FileAutomationManager",
    "FormatConverter",
    "UIAutomationManager",
    "UnifiedAutomationService",
]

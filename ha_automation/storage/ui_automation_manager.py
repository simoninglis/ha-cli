"""UI-based automation manager.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.storage.ui_automation_manager instead.
"""

from ha_cli.domains.automations.storage.ui_automation_manager import (  # noqa: F401
    UIAutomationManager,
)

__all__ = ["UIAutomationManager"]

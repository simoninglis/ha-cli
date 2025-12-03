"""File-based automation manager.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.storage.file_automation_manager instead.
"""

from ha_cli.domains.automations.storage.file_automation_manager import (  # noqa: F401
    FileAutomationManager,
)

__all__ = ["FileAutomationManager"]

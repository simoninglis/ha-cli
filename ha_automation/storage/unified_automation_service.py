"""Unified automation service.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.storage.unified_automation_service instead.
"""

from ha_cli.domains.automations.storage.unified_automation_service import (  # noqa: F401
    UnifiedAutomationService,
)

__all__ = ["UnifiedAutomationService"]

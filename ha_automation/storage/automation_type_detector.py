"""Automation type detector.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.storage.automation_type_detector instead.
"""

from ha_cli.domains.automations.storage.automation_type_detector import (  # noqa: F401
    AutomationTypeDetector,
    StorageType,
)

__all__ = ["AutomationTypeDetector", "StorageType"]

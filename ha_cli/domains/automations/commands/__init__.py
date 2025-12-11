"""Automation CLI command modules.

This package splits the automations CLI into smaller, focused modules:
- list_cmd: List automations
- read_cmd: Read automation details
- control_cmd: Enable, disable, reload operations
- crud_cmd: Create, update, delete operations
"""

from .control_cmd import disable, enable, reload
from .crud_cmd import create, delete, update
from .list_cmd import list_automations
from .read_cmd import read

__all__ = [
    "list_automations",
    "read",
    "enable",
    "disable",
    "reload",
    "create",
    "update",
    "delete",
]

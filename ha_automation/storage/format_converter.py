"""Format converter for automations.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.domains.automations.storage.format_converter instead.
"""

from ha_cli.domains.automations.storage.format_converter import (  # noqa: F401
    FormatConverter,
)

__all__ = ["FormatConverter"]

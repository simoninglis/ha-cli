"""Home Assistant API client with REST and WebSocket support.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.common.client instead.

This module re-exports HAClient from ha_cli.common.client
for backward compatibility with existing code.
"""

# Re-export HAClient from ha_cli.common.client
from ha_cli.common.client import HAClient  # noqa: F401

__all__ = ["HAClient"]

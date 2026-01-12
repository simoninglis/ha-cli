"""Zones domain for managing Home Assistant zones."""

from .cli import app
from .models import Zone
from .service import ZoneService

__all__ = ["app", "Zone", "ZoneService"]

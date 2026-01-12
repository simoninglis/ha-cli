"""Repairs domain for retrieving Home Assistant system repair notices."""

from .cli import app
from .models import Repair
from .service import RepairService

__all__ = ["app", "Repair", "RepairService"]

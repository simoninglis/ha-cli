"""Areas domain for managing Home Assistant areas and registry metadata."""

from .models import Area, AreaWithCounts, Device, Floor, Label
from .service import AreaService

__all__ = [
    "Area",
    "AreaService",
    "AreaWithCounts",
    "Device",
    "Floor",
    "Label",
]

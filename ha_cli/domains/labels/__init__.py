"""Labels domain for managing Home Assistant labels."""

from .cli import app
from .service import Label, LabelsService

__all__ = ["app", "Label", "LabelsService"]

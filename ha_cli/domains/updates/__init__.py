"""Updates domain: list, check and install update entities, with verification."""

from .cli import app
from .models import InstallResult, UpdateInfo
from .service import UpdatesService

__all__ = ["app", "InstallResult", "UpdateInfo", "UpdatesService"]

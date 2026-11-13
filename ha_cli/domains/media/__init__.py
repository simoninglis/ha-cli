"""Media domain: prove a media player actually played a TTS clip."""

from .cli import app
from .models import TtsEngine, TtsTestResult
from .service import MediaService

__all__ = ["app", "MediaService", "TtsEngine", "TtsTestResult"]

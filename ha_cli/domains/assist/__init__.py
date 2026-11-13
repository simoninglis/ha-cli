"""Assist domain: pipelines, and what a pipeline or agent does with a phrase."""

from .cli import app
from .models import AssistResult, Pipeline
from .service import AssistService

__all__ = ["app", "AssistResult", "AssistService", "Pipeline"]

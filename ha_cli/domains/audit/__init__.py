"""Audit domain for identifying Home Assistant tech debt and issues."""

from .models import (
    AuditFinding,
    AuditResult,
    AuditSeverity,
    BrokenAutomationFinding,
    DeadEntityFinding,
    DuplicateEntityFinding,
    IntegrationHealthSummary,
    TriggerStatsFinding,
    UnusedAutomationFinding,
)
from .service import AuditService

__all__ = [
    "AuditFinding",
    "AuditResult",
    "AuditSeverity",
    "AuditService",
    "BrokenAutomationFinding",
    "DeadEntityFinding",
    "DuplicateEntityFinding",
    "IntegrationHealthSummary",
    "TriggerStatsFinding",
    "UnusedAutomationFinding",
]

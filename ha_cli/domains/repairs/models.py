"""Data models for repairs domain."""

import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Repair:
    """Home Assistant repair issue model.

    Repairs represent system issues requiring user intervention, surfaced via
    the Repairs dashboard (Settings > System > Repairs).
    """

    domain: str
    issue_id: str
    active: bool
    severity: str  # "error", "warning", or "critical"
    is_fixable: bool | None = None
    is_persistent: bool = False
    breaks_in_ha_version: str | None = None
    created: datetime | None = None
    dismissed_version: str | None = None
    issue_domain: str | None = None
    learn_more_url: str | None = None
    translation_key: str | None = None
    translation_placeholders: dict[str, Any] | None = None
    data: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Repair":
        """Create Repair from dictionary.

        Args:
            data: Dictionary from Home Assistant WebSocket API

        Returns:
            Repair instance
        """
        # Parse created timestamp if present
        created = None
        if data.get("created"):
            with contextlib.suppress(ValueError, AttributeError):
                # HA returns ISO format timestamps
                created = datetime.fromisoformat(data["created"].replace("Z", "+00:00"))

        return cls(
            domain=data.get("domain", ""),
            issue_id=data.get("issue_id", ""),
            active=data.get("active", True),
            severity=data.get("severity", "warning"),
            is_fixable=data.get("is_fixable"),
            is_persistent=data.get("is_persistent", False),
            breaks_in_ha_version=data.get("breaks_in_ha_version"),
            created=created,
            dismissed_version=data.get("dismissed_version"),
            issue_domain=data.get("issue_domain"),
            learn_more_url=data.get("learn_more_url"),
            translation_key=data.get("translation_key"),
            translation_placeholders=data.get("translation_placeholders"),
            data=data.get("data"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        result: dict[str, Any] = {
            "domain": self.domain,
            "issue_id": self.issue_id,
            "active": self.active,
            "severity": self.severity,
            "is_persistent": self.is_persistent,
        }

        # Include optional fields only if set
        if self.is_fixable is not None:
            result["is_fixable"] = self.is_fixable
        if self.breaks_in_ha_version:
            result["breaks_in_ha_version"] = self.breaks_in_ha_version
        if self.created:
            result["created"] = self.created.isoformat()
        if self.dismissed_version:
            result["dismissed_version"] = self.dismissed_version
        if self.issue_domain:
            result["issue_domain"] = self.issue_domain
        if self.learn_more_url:
            result["learn_more_url"] = self.learn_more_url
        if self.translation_key:
            result["translation_key"] = self.translation_key
        if self.translation_placeholders:
            result["translation_placeholders"] = self.translation_placeholders
        if self.data:
            result["data"] = self.data

        return result

    @property
    def full_id(self) -> str:
        """Get full repair identifier in domain/issue_id format.

        Returns:
            Full identifier string
        """
        return f"{self.domain}/{self.issue_id}"

    @property
    def severity_order(self) -> int:
        """Get numeric severity for sorting (lower = more severe).

        Returns:
            Numeric severity value
        """
        severity_map = {"critical": 0, "error": 1, "warning": 2}
        return severity_map.get(self.severity, 3)

    @property
    def created_display(self) -> str:
        """Get created date in display format.

        Returns:
            Date string or 'Unknown'
        """
        if self.created:
            return self.created.strftime("%Y-%m-%d")
        return "Unknown"

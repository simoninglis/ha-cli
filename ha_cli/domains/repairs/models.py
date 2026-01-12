"""Data models for repairs domain."""

import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _str_or_none(value: Any) -> str | None:
    """Convert value to string or None.

    Args:
        value: Any value that might be a string

    Returns:
        String representation or None if value is None/empty
    """
    if value is None:
        return None
    return str(value) if value else None


def _parse_bool(value: Any, default: bool) -> bool:
    """Parse a value as boolean with proper type handling.

    Args:
        value: Any value that should be interpreted as boolean
        default: Default value if value is None

    Returns:
        Boolean value
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    # Handle string "true"/"false" from API edge cases
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    # Fallback for other types
    return bool(value)


def _parse_optional_bool(value: Any) -> bool | None:
    """Parse a value as optional boolean (can be None, True, or False).

    Args:
        value: Any value that might be a boolean

    Returns:
        Boolean value or None if value is None or unrecognized
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    # Handle string "true"/"false" from API edge cases
    if isinstance(value, str):
        lower_val = value.lower()
        if lower_val in ("true", "1", "yes"):
            return True
        if lower_val in ("false", "0", "no"):
            return False
        # Unknown string - preserve tri-state by returning None
        return None
    # For other types (int, etc.), use standard bool conversion
    return bool(value)


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
        created_raw = data.get("created")
        if created_raw:
            with contextlib.suppress(ValueError, AttributeError, TypeError):
                # HA returns ISO format timestamps
                created_str = str(created_raw) if created_raw else ""
                if created_str:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))

        # Type-safe extraction with coercion for required string fields
        domain = data.get("domain")
        issue_id = data.get("issue_id")
        severity_raw = data.get("severity")

        # Normalize severity to lowercase for consistent matching
        severity = str(severity_raw).lower() if severity_raw is not None else "warning"
        if severity not in ("critical", "error", "warning"):
            severity = "warning"  # Default unknown severities

        return cls(
            domain=str(domain) if domain is not None else "",
            issue_id=str(issue_id) if issue_id is not None else "",
            active=_parse_bool(data.get("active"), default=True),
            severity=severity,
            is_fixable=_parse_optional_bool(data.get("is_fixable")),
            is_persistent=_parse_bool(data.get("is_persistent"), default=False),
            breaks_in_ha_version=_str_or_none(data.get("breaks_in_ha_version")),
            created=created,
            dismissed_version=_str_or_none(data.get("dismissed_version")),
            issue_domain=_str_or_none(data.get("issue_domain")),
            learn_more_url=_str_or_none(data.get("learn_more_url")),
            translation_key=_str_or_none(data.get("translation_key")),
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

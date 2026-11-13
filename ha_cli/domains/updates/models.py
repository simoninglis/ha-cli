"""Data models for the updates domain."""

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# What an update entity is telling us, in the order a reader cares about
AVAILABLE = "available"
INSTALLING = "installing"
CHECK_FAILING = "check_failing"
UNAVAILABLE = "unavailable"
CURRENT = "current"

STATUS_LABELS = {
    AVAILABLE: "update available",
    INSTALLING: "installing",
    CHECK_FAILING: "no version reported (its update check may be failing)",
    UNAVAILABLE: "unavailable",
    CURRENT: "up to date",
}


@dataclass
class UpdateInfo:
    """One ``update.*`` entity."""

    entity_id: str
    name: str
    state: str
    installed_version: str
    latest_version: str
    in_progress: bool
    update_percentage: int | None
    title: str
    release_url: str

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> "UpdateInfo":
        """Create from a get_states item (or a tracked state + attributes)."""
        attrs = data.get("attributes") or {}
        pct = attrs.get("update_percentage")
        return cls(
            entity_id=str(data.get("entity_id") or ""),
            name=str(attrs.get("friendly_name") or data.get("entity_id") or ""),
            state=str(data.get("state") or ""),
            installed_version=str(attrs.get("installed_version") or ""),
            latest_version=str(attrs.get("latest_version") or ""),
            in_progress=bool(attrs.get("in_progress")),
            update_percentage=int(pct) if isinstance(pct, int | float) else None,
            title=str(attrs.get("title") or ""),
            release_url=str(attrs.get("release_url") or ""),
        )

    @property
    def status(self) -> str:
        """Classify the entity.

        A blank installed or latest version is not "up to date": it means the
        entity has never reported a version, which for device-checked updates
        (an ESPHome Voice PE fetching its own manifest) means the device's check
        is failing. Two voices sat a year behind on exactly this.
        """
        if self.state in ("unavailable", "unknown", ""):
            return UNAVAILABLE
        if self.in_progress:
            return INSTALLING
        if not self.installed_version or not self.latest_version:
            return CHECK_FAILING
        if self.state == "on":
            return AVAILABLE
        return CURRENT

    def to_dict(self) -> dict[str, Any]:
        """Serialise, including the derived status."""
        return {**asdict(self), "status": self.status}


def version_matches(reported: str, version: str) -> bool:
    """Whether a device's ``sw_version`` reports ``version``.

    ``sw_version`` is often decorated ("26.9.0 (ESPHome 2026.6.0)"), so match a
    whole token, never a substring: "26.9.0" must not match "126.9.0" or "26.9.01".
    """
    if not reported or not version:
        return False
    return version in re.split(r"[\s(),;]+", reported.strip())


@dataclass
class InstallResult:
    """What happened during an install, and whether the new version was confirmed."""

    entity_id: str
    from_version: str
    target_version: str
    installed_version: str = ""
    device_sw_version: str | None = None
    verified: bool = False
    rebooted: bool = False
    offline_seconds: float | None = None
    duration_seconds: float = 0.0
    problem: str | None = None
    timeline: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return asdict(self)

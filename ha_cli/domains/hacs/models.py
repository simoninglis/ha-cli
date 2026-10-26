"""Data models for the HACS domain."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, parse_qs, urljoin, urlsplit

HACSFILES_PREFIX = "/hacsfiles/"


def _origin(parts: SplitResult) -> tuple[str, str, int | None]:
    """(scheme, host, port) with the default port made explicit, for comparison."""
    scheme = parts.scheme.lower()
    try:
        port = parts.port
    except ValueError:
        port = -1
    default = 443 if scheme == "https" else 80
    return scheme, (parts.hostname or ""), port if port is not None else default


@dataclass
class HacsRepository:
    """A repository HACS knows about (installed or not)."""

    id: str
    full_name: str
    category: str
    installed: bool
    local_path: str
    installed_version: str
    available_version: str
    pending_upgrade: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HacsRepository":
        """Create from a hacs/repositories/list item."""
        return cls(
            id=str(data.get("id") or ""),
            full_name=str(data.get("full_name") or ""),
            category=str(data.get("category") or ""),
            installed=data.get("installed") is True,
            local_path=str(data.get("local_path") or ""),
            installed_version=str(data.get("installed_version") or ""),
            available_version=str(data.get("available_version") or ""),
            pending_upgrade=data.get("pending_upgrade") is True,
        )

    @property
    def hacsfiles_dir(self) -> str | None:
        """For a frontend plugin, the directory served at /hacsfiles/<dir>/."""
        if self.category != "plugin" or "/www/community/" not in self.local_path:
            return None
        return self.local_path.rstrip("/").rsplit("/", 1)[-1] or None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "full_name": self.full_name,
            "category": self.category,
            "installed": self.installed,
            "local_path": self.local_path,
            "installed_version": self.installed_version,
            "available_version": self.available_version,
            "pending_upgrade": self.pending_upgrade,
        }


@dataclass
class LovelaceResource:
    """A dashboard resource (lovelace/resources)."""

    id: str
    url: str
    type: str
    ha_url: str | None = None  # the instance it came from: resolves absolute URLs

    @classmethod
    def from_dict(cls, data: dict[str, Any], ha_url: str | None = None) -> "LovelaceResource":
        """Create from a lovelace/resources item."""
        return cls(
            id=str(data.get("id") or ""),
            url=str(data.get("url") or ""),
            type=str(data.get("res_type") or data.get("type") or ""),
            ha_url=ha_url,
        )

    @property
    def hacsfiles_dir(self) -> str | None:
        """The <dir> in /hacsfiles/<dir>/..., or None if HACS on this instance doesn't serve it.

        Relative, protocol-relative and absolute URLs all count when they resolve to
        the Home Assistant origin; another host is not HACS's.
        """
        base = (self.ha_url or "http://ha.invalid").rstrip("/") + "/"
        parts = urlsplit(urljoin(base, self.url))
        if _origin(parts) != _origin(urlsplit(base)):
            return None
        if not parts.path.startswith(HACSFILES_PREFIX):
            return None
        rest = parts.path[len(HACSFILES_PREFIX):]
        return rest.split("/", 1)[0] or None

    @property
    def hacstag(self) -> str:
        """HACS's cache-buster: the repository id followed by the version digits."""
        values = parse_qs(urlsplit(self.url).query).get("hacstag") or [""]
        return values[0]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {"id": self.id, "url": self.url, "type": self.type}


# Audit finding kinds
UNMAPPED = "unmapped"  # installed card with no /www/community/<dir>: can't check its resources
UNTRACKED = "untracked"  # dashboard loads it, files exist, HACS says not installed
UNKNOWN_RESOURCE = "unknown_resource"  # /hacsfiles/<dir> that no HACS repository owns
NO_RESOURCE = "no_resource"  # installed plugin that no dashboard resource loads


@dataclass
class HacsFinding:
    """One HACS / dashboard-resource mismatch."""

    kind: str
    severity: str  # error | warning
    message: str
    repository: str | None = None  # full_name
    repository_id: str | None = None
    resource_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "repository": self.repository,
            "repository_id": self.repository_id,
            "resource_url": self.resource_url,
        }


@dataclass
class HacsAuditResult:
    """Result of `hacs audit`."""

    findings: list[HacsFinding]
    installed_count: int
    resource_count: int

    @property
    def exit_code(self) -> int:
        """0 = clean, 1 = findings (same convention as `ha-cli audit`)."""
        return 1 if self.findings else 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "installed_count": self.installed_count,
            "resource_count": self.resource_count,
        }

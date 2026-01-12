"""Data models for integrations domain."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _str_or_none(value: Any) -> str | None:
    """Convert value to string or None."""
    if value is None:
        return None
    return str(value) if value else None


def _parse_bool(value: Any, default: bool) -> bool:
    """Parse a value as boolean with proper type handling."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _parse_float(value: Any, default: float = 0.0) -> float:
    """Parse a value as float with proper type handling."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


@dataclass
class ConfigEntry:
    """Home Assistant config entry model.

    Config entries represent integration instances configured via the UI
    (Settings > Devices & Services).
    """

    entry_id: str
    domain: str
    title: str
    state: str  # loaded, not_loaded, failed_unload, setup_error, etc.
    source: str  # user, discovery, import, zeroconf, etc.
    created_at: float = 0.0
    modified_at: float = 0.0
    disabled_by: str | None = None
    supports_options: bool = False
    supports_unload: bool = False
    supports_reconfigure: bool = False
    supports_remove_device: bool = False
    pref_disable_new_entities: bool = False
    pref_disable_polling: bool = False
    reason: str | None = None
    error_reason_translation_key: str | None = None
    num_subentries: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigEntry":
        """Create ConfigEntry from dictionary.

        Args:
            data: Dictionary from Home Assistant WebSocket API

        Returns:
            ConfigEntry instance
        """
        return cls(
            entry_id=data.get("entry_id") or "",
            domain=data.get("domain") or "",
            title=data.get("title") or "",
            state=data.get("state") or "unknown",
            source=data.get("source") or "unknown",
            created_at=_parse_float(data.get("created_at")),
            modified_at=_parse_float(data.get("modified_at")),
            disabled_by=_str_or_none(data.get("disabled_by")),
            supports_options=_parse_bool(data.get("supports_options"), False),
            supports_unload=_parse_bool(data.get("supports_unload"), False),
            supports_reconfigure=_parse_bool(data.get("supports_reconfigure"), False),
            supports_remove_device=_parse_bool(data.get("supports_remove_device"), False),
            pref_disable_new_entities=_parse_bool(data.get("pref_disable_new_entities"), False),
            pref_disable_polling=_parse_bool(data.get("pref_disable_polling"), False),
            reason=_str_or_none(data.get("reason")),
            error_reason_translation_key=_str_or_none(data.get("error_reason_translation_key")),
            num_subentries=int(data.get("num_subentries") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "entry_id": self.entry_id,
            "domain": self.domain,
            "title": self.title,
            "state": self.state,
            "source": self.source,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "supports_options": self.supports_options,
            "supports_unload": self.supports_unload,
            "supports_reconfigure": self.supports_reconfigure,
            "supports_remove_device": self.supports_remove_device,
            "pref_disable_new_entities": self.pref_disable_new_entities,
            "pref_disable_polling": self.pref_disable_polling,
        }

        # Include optional fields only if set
        if self.disabled_by:
            result["disabled_by"] = self.disabled_by
        if self.reason:
            result["reason"] = self.reason
        if self.error_reason_translation_key:
            result["error_reason_translation_key"] = self.error_reason_translation_key
        if self.num_subentries > 0:
            result["num_subentries"] = self.num_subentries

        return result

    @property
    def created_display(self) -> str:
        """Get created date in display format."""
        if self.created_at > 0:
            dt = datetime.fromtimestamp(self.created_at)
            return dt.strftime("%Y-%m-%d")
        return "Unknown"

    @property
    def is_disabled(self) -> bool:
        """Check if entry is disabled."""
        return self.disabled_by is not None

    @property
    def state_display(self) -> str:
        """Get human-readable state display."""
        state_map = {
            "loaded": "Loaded",
            "not_loaded": "Not Loaded",
            "failed_unload": "Failed Unload",
            "setup_error": "Setup Error",
            "setup_retry": "Retrying Setup",
            "setup_in_progress": "Setting Up",
            "migration_error": "Migration Error",
        }
        return state_map.get(self.state, self.state.replace("_", " ").title())


@dataclass
class ConfigFlowStep:
    """A step in a config flow."""

    flow_id: str
    handler: str  # domain
    step_id: str
    type: str  # form, create_entry, abort, external, etc.
    data_schema: list[dict[str, Any]] = field(default_factory=list)
    errors: dict[str, str] | None = None
    description_placeholders: dict[str, str] | None = None
    last_step: bool | None = None
    title: str | None = None
    result: dict[str, Any] | None = None  # Stores create_entry result
    reason: str | None = None  # Abort reason (for type="abort")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigFlowStep":
        """Create ConfigFlowStep from dictionary."""
        return cls(
            flow_id=data.get("flow_id") or "",
            handler=data.get("handler") or "",
            step_id=data.get("step_id") or "",
            type=data.get("type") or "form",
            data_schema=data.get("data_schema") or [],
            errors=data.get("errors"),
            description_placeholders=data.get("description_placeholders"),
            last_step=data.get("last_step"),
            title=data.get("title"),
            result=data.get("result"),
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        output: dict[str, Any] = {
            "flow_id": self.flow_id,
            "handler": self.handler,
            "step_id": self.step_id,
            "type": self.type,
            "data_schema": self.data_schema,
        }
        if self.errors:
            output["errors"] = self.errors
        if self.description_placeholders:
            output["description_placeholders"] = self.description_placeholders
        if self.last_step is not None:
            output["last_step"] = self.last_step
        if self.title:
            output["title"] = self.title
        if self.result:
            output["result"] = self.result
        if self.reason:
            output["reason"] = self.reason
        return output

    @property
    def requires_input(self) -> bool:
        """Check if this step requires user input."""
        return len(self.data_schema) > 0

    @property
    def is_complete(self) -> bool:
        """Check if this step completes the flow."""
        return self.type == "create_entry"

    @property
    def is_aborted(self) -> bool:
        """Check if this flow was aborted."""
        return self.type == "abort"

    @property
    def abort_reason(self) -> str:
        """Get the abort reason, with fallback to step_id or generic message.

        HA abort responses may include:
        - `reason` field (most explicit)
        - `step_id` like 'already_configured', 'single_instance_allowed'
        - `description_placeholders` with context
        """
        if self.reason:
            return self.reason
        # step_id often contains the abort reason
        if self.step_id and self.step_id not in ("user", "init"):
            return self.step_id.replace("_", " ")
        return "Unknown reason"

    def get_required_fields(self) -> list[str]:
        """Get list of required field names."""
        return [
            field.get("name", "")
            for field in self.data_schema
            if field.get("required", False)
        ]

    def get_field_defaults(self) -> dict[str, Any]:
        """Get default values for fields."""
        return {
            field.get("name", ""): field.get("default")
            for field in self.data_schema
            if "default" in field and field.get("name")
        }


@dataclass
class ConfigFlowProgress:
    """In-progress config flow."""

    flow_id: str
    handler: str  # domain
    step_id: str
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigFlowProgress":
        """Create ConfigFlowProgress from dictionary."""
        return cls(
            flow_id=str(data.get("flow_id", "")),
            handler=str(data.get("handler", "")),
            step_id=str(data.get("step_id", "")),
            context=data.get("context") or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "flow_id": self.flow_id,
            "handler": self.handler,
            "step_id": self.step_id,
            "context": self.context,
        }

    @property
    def source(self) -> str:
        """Get the source of this flow (user, discovery, etc.)."""
        source = self.context.get("source")
        return str(source) if source else "unknown"

    @property
    def title(self) -> str:
        """Get title from context placeholders if available."""
        placeholders = self.context.get("title_placeholders", {})
        name = placeholders.get("name") if isinstance(placeholders, dict) else None
        return str(name) if name else self.handler


@dataclass
class ConfigEntryResult:
    """Result of a config entry operation."""

    entry_id: str
    domain: str
    title: str
    require_restart: bool = False

    @classmethod
    def from_create_response(cls, data: dict[str, Any]) -> "ConfigEntryResult":
        """Create from config flow create_entry response."""
        result = data.get("result", {})
        return cls(
            entry_id=str(result.get("entry_id", "")),
            domain=str(data.get("handler", result.get("domain", ""))),
            title=str(data.get("title", result.get("title", ""))),
            require_restart=False,
        )

    @classmethod
    def from_delete_response(cls, entry_id: str, domain: str, data: dict[str, Any]) -> "ConfigEntryResult":
        """Create from delete response."""
        return cls(
            entry_id=entry_id,
            domain=domain,
            title="",
            require_restart=data.get("require_restart", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entry_id": self.entry_id,
            "domain": self.domain,
            "title": self.title,
            "require_restart": self.require_restart,
        }

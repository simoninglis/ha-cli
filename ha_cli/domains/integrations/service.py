"""Service layer for integrations domain."""

from typing import Any, cast

from ...common.client import HAClient
from ...common.exceptions import NotFoundError, ValidationError
from .models import ConfigEntry, ConfigEntryResult, ConfigFlowProgress, ConfigFlowStep


class IntegrationService:
    """Service for managing Home Assistant config entries (integrations).

    Config entries represent integration instances configured via the UI
    (Settings > Devices & Services).
    """

    def __init__(self, client: HAClient) -> None:
        """Initialize integration service.

        Args:
            client: Home Assistant client
        """
        self.client = client

    # ==========================================================================
    # Config Entry Operations (WebSocket API)
    # ==========================================================================

    async def list_entries(
        self,
        domain: str | None = None,
        state: str | None = None,
    ) -> list[ConfigEntry]:
        """Get all config entries from Home Assistant.

        Args:
            domain: Filter by integration domain (e.g., "esphome")
            state: Filter by state (e.g., "loaded", "setup_error")

        Returns:
            List of config entries sorted by domain then title

        Raises:
            ValidationError: If response format is unexpected
        """
        result = await self.client._ws_call("config_entries/get")

        # Validate response is a list
        if result is None:
            result = []
        if not isinstance(result, list):
            raise ValidationError(f"Unexpected response type: {type(result).__name__}")

        entries = []
        for item in result:
            if not isinstance(item, dict):
                continue
            entry = ConfigEntry.from_dict(item)

            # Apply filters
            if domain and entry.domain.lower() != domain.lower():
                continue
            if state and entry.state.lower() != state.lower():
                continue

            entries.append(entry)

        # Sort by domain then title
        return sorted(
            entries,
            key=lambda e: (e.domain.lower(), e.title.lower()),
        )

    async def get_entry(self, entry_id: str) -> ConfigEntry | None:
        """Get a specific config entry by ID.

        Args:
            entry_id: Config entry ID

        Returns:
            ConfigEntry if found, None otherwise

        Raises:
            WebSocketError: If connection fails or authentication error
        """
        from ...common.exceptions import WebSocketError

        try:
            result = await self.client._ws_call(
                "config_entries/get_single",
                entry_id=entry_id,
            )
        except WebSocketError as e:
            # HA returns "not_found" error for non-existent entries
            error_str = str(e).lower()
            if "not_found" in error_str:
                return None
            # Re-raise connection/auth/other errors
            raise

        if not result or not isinstance(result, dict):
            return None

        config_entry = result.get("config_entry")
        if not config_entry or not isinstance(config_entry, dict):
            return None

        return ConfigEntry.from_dict(config_entry)

    async def find_entry(
        self,
        entry_id_or_partial: str,
        *,
        allow_ambiguous: bool = False,
    ) -> ConfigEntry | None:
        """Find config entry by ID or partial match.

        Supports:
        - Full entry_id match (always unambiguous)
        - Partial entry_id prefix match
        - Domain match

        Args:
            entry_id_or_partial: Full or partial entry ID, or domain name
            allow_ambiguous: If False, raises ValidationError when multiple
                matches found. Use True for non-destructive operations like show.

        Returns:
            ConfigEntry if found, None otherwise

        Raises:
            ValidationError: If multiple matches found and allow_ambiguous=False
        """
        # Try exact match first (always unambiguous)
        entry = await self.get_entry(entry_id_or_partial)
        if entry:
            return entry

        # Try partial/domain match
        entries = await self.list_entries()
        search_lower = entry_id_or_partial.lower()

        # Collect all matches
        matches: list[ConfigEntry] = []
        for e in entries:
            # Check partial ID match
            if e.entry_id.lower().startswith(search_lower) or e.domain.lower() == search_lower:
                matches.append(e)

        if not matches:
            return None

        if len(matches) == 1:
            return matches[0]

        # Multiple matches found
        if allow_ambiguous:
            # Return first match for non-destructive operations
            return matches[0]

        # Raise error with candidate list for destructive operations
        match_list = "\n".join(
            f"  - {m.entry_id} ({m.domain}: {m.title})" for m in matches[:5]
        )
        if len(matches) > 5:
            match_list += f"\n  ... and {len(matches) - 5} more"
        raise ValidationError(
            f"Ambiguous identifier '{entry_id_or_partial}' matches {len(matches)} "
            f"entries:\n{match_list}\n\nUse the full entry_id for destructive operations."
        )

    async def disable_entry(self, entry_id: str) -> dict[str, Any]:
        """Disable a config entry.

        Args:
            entry_id: Config entry ID

        Returns:
            Response dict with require_restart field

        Raises:
            NotFoundError: If entry not found
        """
        # Verify entry exists
        entry = await self.get_entry(entry_id)
        if not entry:
            raise NotFoundError(f"Config entry not found: {entry_id}")

        result = await self.client._ws_call(
            "config_entries/disable",
            entry_id=entry_id,
            disabled_by="user",
        )
        return cast(dict[str, Any], result) if result else {"require_restart": False}

    async def enable_entry(self, entry_id: str) -> dict[str, Any]:
        """Enable a disabled config entry.

        Args:
            entry_id: Config entry ID

        Returns:
            Response dict with require_restart field

        Raises:
            NotFoundError: If entry not found
        """
        # Verify entry exists
        entry = await self.get_entry(entry_id)
        if not entry:
            raise NotFoundError(f"Config entry not found: {entry_id}")

        result = await self.client._ws_call(
            "config_entries/disable",
            entry_id=entry_id,
            disabled_by=None,
        )
        return cast(dict[str, Any], result) if result else {"require_restart": False}

    async def delete_entry(self, entry_id: str) -> ConfigEntryResult:
        """Delete a config entry.

        Args:
            entry_id: Config entry ID

        Returns:
            ConfigEntryResult with require_restart info

        Raises:
            NotFoundError: If entry not found
        """
        # Get entry first for domain info
        entry = await self.get_entry(entry_id)
        if not entry:
            raise NotFoundError(f"Config entry not found: {entry_id}")

        result = await self.client._rest(
            "DELETE",
            f"/api/config/config_entries/entry/{entry_id}",
        )

        return ConfigEntryResult.from_delete_response(
            entry_id=entry_id,
            domain=entry.domain,
            data=result if isinstance(result, dict) else {},
        )

    # ==========================================================================
    # Config Flow Operations (REST API)
    # ==========================================================================

    async def list_flows(self) -> list[ConfigFlowProgress]:
        """List in-progress config flows.

        Returns:
            List of pending config flows

        Raises:
            ValidationError: If response format is unexpected
        """
        result = await self.client._ws_call("config_entries/flow/progress")

        # Validate response is a list (empty list is OK)
        if result is None:
            result = []
        if not isinstance(result, list):
            raise ValidationError(f"Unexpected response type: {type(result).__name__}")

        flows = []
        for item in result:
            if isinstance(item, dict):
                flows.append(ConfigFlowProgress.from_dict(item))

        return flows

    async def get_flow(
        self,
        flow_id: str,
        *,
        options: bool = False,
    ) -> ConfigFlowStep:
        """Get the current form and schema for an in-progress flow.

        Args:
            flow_id: Config or options flow ID
            options: Read an options flow rather than a config flow

        Returns:
            Current config flow step
        """
        flow_type = "options/flow" if options else "flow"
        result = await self.client._rest(
            "GET",
            f"/api/config/config_entries/{flow_type}/{flow_id}",
        )

        if not result or not isinstance(result, dict):
            raise ValidationError(f"Unexpected flow response for flow {flow_id}")

        return ConfigFlowStep.from_dict(result)

    async def start_flow(self, domain: str) -> ConfigFlowStep:
        """Start a config flow for an integration.

        Args:
            domain: Integration domain (e.g., "media_extractor", "esphome")

        Returns:
            ConfigFlowStep with form requirements or result
        """
        result = await self.client._rest(
            "POST",
            "/api/config/config_entries/flow",
            json_data={"handler": domain},
        )

        if not result or not isinstance(result, dict):
            raise ValidationError(f"Unexpected flow response for {domain}")

        return ConfigFlowStep.from_dict(result)

    async def submit_flow(
        self,
        flow_id: str,
        data: dict[str, Any] | None = None,
        *,
        options: bool = False,
    ) -> ConfigFlowStep:
        """Submit data to a config or options flow step.

        Args:
            flow_id: Config or options flow ID
            data: Form data to submit (empty dict for no-input flows)
            options: Submit to an options flow rather than a config flow

        Returns:
            ConfigFlowStep with next step or result
        """
        flow_type = "options/flow" if options else "flow"
        result = await self.client._rest(
            "POST",
            f"/api/config/config_entries/{flow_type}/{flow_id}",
            json_data=data or {},
        )

        if not result or not isinstance(result, dict):
            raise ValidationError(f"Unexpected flow response for flow {flow_id}")

        return ConfigFlowStep.from_dict(result)

    async def cancel_flow(self, flow_id: str, *, options: bool = False) -> None:
        """Cancel an in-progress config or options flow.

        Args:
            flow_id: Config or options flow ID
            options: Cancel an options flow rather than a config flow
        """
        flow_type = "options/flow" if options else "flow"
        await self.client._rest(
            "DELETE",
            f"/api/config/config_entries/{flow_type}/{flow_id}",
        )

    async def start_options_flow(self, entry_id: str) -> ConfigFlowStep:
        """Start an options flow for a config entry.

        Args:
            entry_id: Config entry ID

        Returns:
            Initial options flow step

        Raises:
            NotFoundError: If the config entry does not exist
            ValidationError: If the entry has no options flow or response is invalid
        """
        entry = await self.get_entry(entry_id)
        if not entry:
            raise NotFoundError(f"Config entry not found: {entry_id}")
        if not entry.supports_options:
            raise ValidationError(
                f"Config entry does not support options: {entry_id} ({entry.domain})"
            )

        result = await self.client._rest(
            "POST",
            "/api/config/config_entries/options/flow",
            json_data={"handler": entry_id},
        )

        if not result or not isinstance(result, dict):
            raise ValidationError(f"Unexpected options flow response for {entry_id}")

        return ConfigFlowStep.from_dict(result)

    # ==========================================================================
    # High-Level Operations
    # ==========================================================================

    async def setup_integration(
        self,
        domain: str,
        host: str | None = None,
        port: int | None = None,
    ) -> ConfigEntryResult:
        """Set up an integration via config flow.

        This is a high-level operation that:
        1. Starts a config flow
        2. Submits required data (if any)
        3. Returns the created config entry

        Args:
            domain: Integration domain
            host: Host for network-based integrations (e.g., ESPHome)
            port: Port for network-based integrations

        Returns:
            ConfigEntryResult with created entry info

        Raises:
            ValidationError: If flow requires unsupported input
        """
        # Start the flow
        step = await self.start_flow(domain)

        # Check if flow was aborted immediately
        if step.is_aborted:
            raise ValidationError(f"Config flow aborted: {step.abort_reason}")

        # Check if already complete (shouldn't happen but handle it)
        if step.is_complete:
            return ConfigEntryResult.from_create_response(step.to_dict())

        # Build form data
        form_data: dict[str, Any] = {}
        required_fields = step.get_required_fields()
        defaults = step.get_field_defaults()

        # Handle known field types
        for field in step.data_schema:
            field_name = field.get("name", "")

            if field_name == "host" and host:
                form_data["host"] = host
            elif field_name == "port":
                form_data["port"] = port if port else defaults.get("port", 6053)
            elif field_name in defaults:
                form_data[field_name] = defaults[field_name]

        # Check if we have all required fields
        missing = [f for f in required_fields if f not in form_data]
        if missing:
            # Cancel the flow and report error
            await self.cancel_flow(step.flow_id)
            # Provide specific guidance based on missing fields
            if missing == ["host"]:
                hint = "Use --host <ip_or_hostname> option."
            elif set(missing) == {"host", "port"}:
                hint = "Use --host <ip_or_hostname> [--port <port>] options."
            else:
                hint = (
                    "This integration requires interactive setup. "
                    "Please use the Home Assistant UI."
                )
            raise ValidationError(
                f"Missing required fields for {domain}: {', '.join(missing)}. {hint}"
            )

        # Submit the form
        result = await self.submit_flow(step.flow_id, form_data)

        # Handle multi-step flows
        max_steps = 5  # Safety limit
        step_count = 0
        while not result.is_complete and not result.is_aborted and step_count < max_steps:
            step_count += 1
            if result.requires_input:
                # We don't support interactive multi-step flows
                await self.cancel_flow(result.flow_id)
                raise ValidationError(
                    f"Integration {domain} requires interactive setup. "
                    f"Please use the Home Assistant UI."
                )
            # Auto-submit empty form for confirmation steps
            result = await self.submit_flow(result.flow_id, {})

        if result.is_aborted:
            raise ValidationError(f"Config flow aborted: {result.abort_reason}")

        if not result.is_complete:
            raise ValidationError(
                f"Config flow did not complete for {domain}. "
                f"Please use the Home Assistant UI."
            )

        return ConfigEntryResult.from_create_response(result.to_dict())

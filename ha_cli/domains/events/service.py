"""Events service layer for Home Assistant CLI."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

from ...common.client import HAClient
from ...common.exceptions import ValidationError

logger = logging.getLogger(__name__)


def parse_filter_expr(filter_expr: str | None) -> Callable[[dict[str, Any]], bool] | None:
    """Parse 'field=value' into a filter function for event data.

    Args:
        filter_expr: Filter string in "field=value" format, or None.

    Returns:
        Callable that takes an event dict and returns True if it matches,
        or None if no filter specified.

    Raises:
        ValidationError: If filter format is invalid (missing '=' or empty field).
    """
    if not filter_expr:
        return None

    if "=" not in filter_expr:
        raise ValidationError(f"Invalid filter format: '{filter_expr}'. Use 'field=value'.")

    field, value = filter_expr.split("=", 1)
    field = field.strip()
    value = value.strip()

    # Validate field is non-empty (v17 fix)
    if not field:
        raise ValidationError(f"Invalid filter: field name cannot be empty in '{filter_expr}'.")

    def event_filter(event: dict[str, Any]) -> bool:
        """Return True if event data matches the filter."""
        data = event.get("data")
        # Guard against non-dict data (v17 fix - defensive even if HA guarantees dict)
        if not isinstance(data, dict):
            return False
        return str(data.get(field, "")) == value

    return event_filter


class EventsService:
    """Service for Home Assistant event operations."""

    def __init__(self, client: HAClient) -> None:
        """Initialize events service.

        Args:
            client: Home Assistant API client
        """
        self.client = client

    async def listen_events(
        self,
        event_type: str,
        event_filter: Callable[[dict[str, Any]], bool] | None = None,
        duration: int = 0,
        count: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Listen for events with optional filtering and limits.

        Args:
            event_type: Event type to subscribe to (e.g., "state_changed")
            event_filter: Optional filter function for events
            duration: Stop after N seconds (0=forever)
            count: Stop after N events (0=unlimited)

        Yields:
            Event data dictionaries
        """
        events_seen = 0
        start_time = datetime.now(UTC)

        async def event_generator() -> AsyncIterator[dict[str, Any]]:
            """Generate events from subscription."""
            nonlocal events_seen
            async for event in self.client.subscribe_events(event_type, event_filter):
                events_seen += 1
                yield event
                if count and events_seen >= count:
                    return

        if duration > 0:
            # Use wait_for with timeout
            try:
                async for event in event_generator():
                    yield event
                    # Check duration on each event
                    elapsed = (datetime.now(UTC) - start_time).total_seconds()
                    if elapsed >= duration:
                        return
            except asyncio.TimeoutError:
                return
        else:
            async for event in event_generator():
                yield event

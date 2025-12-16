"""CLI commands for events domain - real-time event listening."""

import asyncio
import logging
import sys
from datetime import UTC, datetime

import typer
from rich.console import Console
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from ...common.cli_utils import run_async_command, setup_logging
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import (
    EXIT_HA_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    ConfigurationError,
    ConnectionError,
    HAAutomationError,
    TimeoutError,
    ValidationError,
    WebSocketError,
)
from ...common.porcelain import StreamingPorcelainFormatter
from .service import parse_filter_expr

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="events",
    help="Home Assistant event operations (listen for events)",
    no_args_is_help=True,
)

console = Console()


def _print_human_event(event: dict, event_type: str) -> None:
    """Print event in human-readable format."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    data = event.get("data", {})

    console.print(f"\n[cyan]{timestamp}[/cyan] [bold]{event_type}[/bold]")

    # For state_changed events, show entity_id and states
    if event_type == "state_changed" and isinstance(data, dict):
        entity_id = data.get("entity_id", "unknown")
        old_state = data.get("old_state", {})
        new_state = data.get("new_state", {})
        old_val = old_state.get("state", "N/A") if old_state else "N/A"
        new_val = new_state.get("state", "N/A") if new_state else "N/A"
        console.print(f"  Entity: [yellow]{entity_id}[/yellow]")
        console.print(f"  State: {old_val} → {new_val}")
    else:
        # Generic event display
        if isinstance(data, dict):
            for key, value in list(data.items())[:5]:  # Show first 5 fields
                console.print(f"  {key}: {value}")
            if len(data) > 5:
                console.print(f"  [dim]... and {len(data) - 5} more fields[/dim]")
        else:
            console.print(f"  Data: {data}")


@app.command("listen")
def listen(
    event_type: str = typer.Argument(..., help="Event type to listen for (e.g., deconz_event, state_changed)"),
    filter_expr: str | None = typer.Option(
        None, "--filter", "-f", help="Filter expression (field=value)"
    ),
    duration: int = typer.Option(0, "--duration", "-d", help="Stop after N seconds (0=forever)"),
    count: int = typer.Option(0, "--count", "-n", help="Stop after N events (0=unlimited)"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output JSONL format"),
    url: str | None = typer.Option(None, "--url", envvar="HA_URL", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", envvar="HA_TOKEN", help="Access token"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Listen for Home Assistant events in real-time.

    Examples:
        ha-cli events listen state_changed
        ha-cli events listen deconz_event --filter "unique_id=00:15:8d:00:04:15:2c:d7"
        ha-cli events listen state_changed --duration 60
        ha-cli events listen state_changed --count 5 --porcelain
        ha-cli events listen zha_event --filter "device_id=abc123"
    """
    setup_logging(debug)

    async def _listen() -> None:
        formatter = StreamingPorcelainFormatter("events listen") if porcelain else None
        events_seen = 0
        exit_reason = "completed"
        exit_code = EXIT_SUCCESS

        # Emit metadata FIRST (v17 fix - before any operation that can fail)
        # This ensures consumers always get metadata line even on early errors
        if formatter:
            formatter.emit_metadata(event_type=event_type)

        try:
            # Parse filter expression AFTER metadata emission (v17 fix)
            # ValidationError here will be caught and handled properly
            event_filter = parse_filter_expr(filter_expr)

            # Get client config and connect
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                if not porcelain:
                    console.print(f"[dim]Listening for {event_type} events...[/dim]")
                    if filter_expr:
                        console.print(f"[dim]Filter: {filter_expr}[/dim]")
                    if duration:
                        console.print(f"[dim]Duration: {duration}s[/dim]")
                    if count:
                        console.print(f"[dim]Max events: {count}[/dim]")
                    console.print("[dim]Press Ctrl+C to stop[/dim]")

                async def event_loop() -> None:
                    nonlocal events_seen, exit_reason
                    async for event in client.subscribe_events(event_type, event_filter):
                        if formatter:
                            formatter.emit_event(event.get("data", {}), event_type=event_type)
                        else:
                            _print_human_event(event, event_type)

                        events_seen += 1
                        if count and events_seen >= count:
                            exit_reason = "count_reached"
                            return  # Exit loop, exit_reason already set

                if duration > 0:
                    try:
                        await asyncio.wait_for(event_loop(), timeout=duration)
                        # event_loop() only returns normally on count_reached
                    except asyncio.TimeoutError:
                        exit_reason = "timeout"
                else:
                    await event_loop()

        except asyncio.CancelledError:
            # Ctrl+C triggers this - treat as clean exit, don't re-raise
            exit_reason = "interrupted"
        except (ValidationError, ConfigurationError) as e:
            # v17 fix: Usage errors get EXIT_USAGE_ERROR (1), not EXIT_HA_ERROR
            exit_reason = "error"
            exit_code = EXIT_USAGE_ERROR
            if formatter:
                formatter.emit_error(str(e), recoverable=False, error_type="usage_error")
            else:
                raise  # Let run_async_command handle (only in human mode)
        except (ConnectionClosed, ConnectionClosedError) as e:
            # v17 fix: Catch websockets exceptions explicitly to prevent JSONL corruption
            exit_reason = "error"
            exit_code = EXIT_NETWORK_ERROR
            if formatter:
                formatter.emit_error(f"WebSocket closed: {e}", recoverable=False, error_type="connection")
            else:
                raise WebSocketError(f"WebSocket closed unexpectedly: {e}") from e
        except (ConnectionError, WebSocketError, TimeoutError) as e:
            # Network-level error
            exit_reason = "error"
            exit_code = EXIT_NETWORK_ERROR
            if formatter:
                formatter.emit_error(str(e), recoverable=False, error_type="connection")
            else:
                raise  # Let run_async_command handle (only in human mode)
        except HAAutomationError as e:
            # HA API error (auth, not found, server error)
            exit_reason = "error"
            exit_code = EXIT_HA_ERROR
            if formatter:
                formatter.emit_error(str(e), recoverable=False, error_type="ha_error")
            else:
                raise  # Let run_async_command handle (only in human mode)
        finally:
            # Always emit summary (idempotent guard in formatter handles double-calls)
            if formatter:
                formatter.emit_summary(exit_reason=exit_reason)
                # In porcelain mode, exit directly to avoid run_async_command printing human text
                if exit_code != EXIT_SUCCESS:
                    sys.exit(exit_code)

        # Human mode summary
        if not porcelain:
            console.print(f"\n[dim]Received {events_seen} events[/dim]")

    asyncio.run(run_async_command(_listen()))


@app.command("version")
def version() -> None:
    """Show events domain version."""
    from ... import __version__

    console.print(f"ha-cli events version {__version__}")

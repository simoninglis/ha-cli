"""Cloud CLI commands for Home Assistant Cloud (Nabu Casa)."""

import asyncio
import sys

import typer
from rich.console import Console
from rich.markup import escape as rich_escape
from rich.table import Table

from ...common.cli_utils import (
    run_async_command,
    set_porcelain_mode,
    setup_logging,
    write_output,
)
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import (
    EXIT_HA_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_USAGE_ERROR,
    AuthenticationError,
    ConfigurationError,
    ConnectionError,
    NotFoundError,
    ValidationError,
    WebSocketError,
)
from ...common.porcelain import PorcelainFormatter
from .service import CloudService

app = typer.Typer(
    name="cloud",
    help="Manage Home Assistant Cloud (Nabu Casa) - Alexa, Google, Remote UI",
    no_args_is_help=True,
)

alexa_app = typer.Typer(
    name="alexa",
    help="Alexa-specific cloud commands",
    no_args_is_help=True,
)
app.add_typer(alexa_app, name="alexa")

console = Console()


def _handle_error(
    e: Exception,
    porcelain: bool,
    formatter: PorcelainFormatter | None,
) -> None:
    """Handle errors with appropriate output format and exit code."""
    if isinstance(e, NotFoundError):
        error_code = "NOT_FOUND"
        exit_code = EXIT_USAGE_ERROR
    elif isinstance(e, ValidationError | ConfigurationError):
        error_code = "VALIDATION_ERROR" if isinstance(e, ValidationError) else "CONFIG_ERROR"
        exit_code = EXIT_USAGE_ERROR
    elif isinstance(e, ConnectionError | WebSocketError):
        error_code = "CONNECTION_ERROR" if isinstance(e, ConnectionError) else "WEBSOCKET_ERROR"
        exit_code = EXIT_NETWORK_ERROR
    elif isinstance(e, AuthenticationError):
        error_code = "AUTH_ERROR"
        exit_code = EXIT_HA_ERROR
    else:
        error_code = "ERROR"
        exit_code = EXIT_HA_ERROR

    if porcelain and formatter:
        output = formatter.error(e, error_code=error_code)
        write_output(output)
    else:
        console.print(f"[red]Error: {rich_escape(str(e))}[/red]")

    sys.exit(exit_code)


@app.command("status")
def cloud_status(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show Home Assistant Cloud connection status.

    Displays:
    - Cloud login state
    - Remote UI status
    - Alexa/Google Assistant enabled state
    - Subscription information
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _status() -> None:
        formatter = PorcelainFormatter("cloud status") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)
                status = await service.get_status()

                if porcelain:
                    assert formatter is not None
                    issues = []
                    suggestions = []

                    if not status.logged_in:
                        issues.append("Not logged in to Home Assistant Cloud")
                        suggestions.append("Log in via Settings > Home Assistant Cloud")
                    elif not status.cloud_connected:
                        issues.append("Cloud connection not established")
                        suggestions.append("Check internet connection")
                    else:
                        if not status.alexa_enabled:
                            suggestions.append("Enable Alexa: Settings > Voice Assistants > Alexa")
                        if not status.remote_enabled:
                            suggestions.append("Enable Remote UI: Settings > Home Assistant Cloud")

                    output = formatter.success(
                        data=status.to_dict(),
                        metadata={
                            "issues_count": len(issues),
                        },
                        suggestions={
                            "issues": issues if issues else None,
                            "next_steps": suggestions if suggestions else None,
                            "common_actions": [
                                "ha-cli cloud alexa entities",
                                "ha-cli cloud alexa sync",
                            ],
                        },
                    )
                    write_output(output)
                else:
                    console.print("[bold]Home Assistant Cloud Status[/bold]\n")

                    if not status.logged_in:
                        console.print("[red]✗ Not logged in[/red]")
                        console.print("[dim]Log in via Settings > Home Assistant Cloud[/dim]")
                        return

                    # Account info
                    console.print(f"[green]✓ Logged in[/green] as {rich_escape(status.email or 'unknown')}")
                    if status.subscription_expiration:
                        console.print(f"  Subscription expires: {rich_escape(status.subscription_expiration)}")

                    # Cloud connection
                    if status.cloud_connected:
                        console.print("[green]✓ Cloud connected[/green]")
                    else:
                        console.print("[red]✗ Cloud disconnected[/red]")

                    # Remote UI
                    if status.remote_enabled:
                        if status.remote_connected:
                            console.print(f"[green]✓ Remote UI enabled[/green] ({rich_escape(status.remote_domain or '')})")
                        else:
                            console.print("[yellow]⚠ Remote UI enabled but not connected[/yellow]")
                    else:
                        console.print("[dim]- Remote UI disabled[/dim]")

                    # Voice assistants
                    console.print()
                    console.print("[bold]Alexa[/bold]")
                    if status.alexa_enabled:
                        console.print("[green]  ✓ Enabled[/green]")
                    else:
                        console.print("[dim]  - Disabled[/dim]")

                    if status.alexa_registered:
                        console.print("[green]  ✓ Skill linked[/green]")
                    else:
                        console.print("[yellow]  ⚠ Skill not linked[/yellow] - Link in Alexa app")

                    if status.alexa_entity_count > 0:
                        console.print(f"[green]  ✓ {status.alexa_entity_count} entities configured[/green] (YAML filter)")
                    else:
                        console.print("[dim]  - No entities in YAML filter[/dim]")

                    console.print()
                    console.print("[bold]Google Assistant[/bold]")
                    if status.google_enabled:
                        console.print("[green]  ✓ Enabled[/green]")
                    else:
                        console.print("[dim]  - Disabled[/dim]")

                    if status.google_registered:
                        console.print("[green]  ✓ Linked[/green]")
                    else:
                        console.print("[dim]  - Not linked[/dim]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_status(), command="cloud status"))


@alexa_app.command("entities")
def alexa_entities(
    exposed_only: bool = typer.Option(False, "--exposed", "-e", help="Show only exposed entities"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List entities available to Alexa.

    Shows all entities that can be exposed to Alexa and their current state.
    Use --exposed to show only currently exposed entities.
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _entities() -> None:
        formatter = PorcelainFormatter("cloud alexa entities") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)
                entities = await service.get_alexa_entities()

                if exposed_only:
                    entities = [e for e in entities if e.should_expose]

                # Sort by entity_id
                entities.sort(key=lambda e: e.entity_id)

                if porcelain:
                    assert formatter is not None
                    exposed_count = sum(1 for e in entities if e.should_expose)
                    output = formatter.success(
                        data=[e.to_dict() for e in entities],
                        metadata={
                            "total_count": len(entities),
                            "exposed_count": exposed_count,
                            "filter_applied": "exposed_only" if exposed_only else None,
                        },
                        suggestions={
                            "next_steps": [
                                "ha-cli cloud alexa sync  # Tell Alexa to rediscover",
                                "Say 'Alexa, discover devices'",
                            ],
                        },
                    )
                    write_output(output)
                else:
                    exposed_count = sum(1 for e in entities if e.should_expose)

                    table = Table(title="Alexa Entities")
                    table.add_column("Entity ID", style="cyan")
                    table.add_column("Exposed", justify="center")
                    table.add_column("Categories")

                    for entity in entities:
                        exposed = "[green]✓[/green]" if entity.should_expose else "[dim]-[/dim]"
                        categories = ", ".join(entity.display_categories) if entity.display_categories else "-"
                        table.add_row(
                            rich_escape(entity.entity_id),
                            exposed,
                            rich_escape(categories),
                        )

                    console.print(table)
                    console.print(f"\n[dim]Total: {len(entities)} entities, {exposed_count} exposed[/dim]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_entities(), command="cloud alexa entities"))


@alexa_app.command("sync")
def alexa_sync(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Trigger Alexa to rediscover devices.

    This sends a proactive discovery request to Alexa, telling it to
    refresh its view of your Home Assistant entities.

    Equivalent to saying "Alexa, discover devices" but from the command line.
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _sync() -> None:
        formatter = PorcelainFormatter("cloud alexa sync") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)
                result = await service.sync_alexa()

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        data={"sync_triggered": True, "response": result},
                        suggestions={
                            "next_steps": [
                                "Wait 30-60 seconds for Alexa to process",
                                "Check Alexa app for discovered devices",
                                "Try 'Alexa, turn on <device>'",
                            ],
                        },
                    )
                    write_output(output)
                else:
                    console.print("[green]✓ Alexa sync triggered[/green]")
                    console.print("[dim]Alexa should discover devices within 30-60 seconds[/dim]")
                    console.print("[dim]Check the Alexa app to verify devices appear[/dim]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_sync(), command="cloud alexa sync"))

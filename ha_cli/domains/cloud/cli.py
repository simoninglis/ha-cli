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
    help="Home Assistant Cloud (Nabu Casa) status and Alexa commands",
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

                if porcelain and formatter:
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
                            "detected_issues": issues,
                            "next_steps": suggestions,
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
                    email = rich_escape(status.email or "unknown")
                    console.print(f"[green]✓ Logged in[/green] as {email}")
                    if status.subscription_expiration:
                        expires = rich_escape(status.subscription_expiration)
                        console.print(f"  Subscription expires: {expires}")

                    # Cloud connection
                    if status.cloud_connected:
                        console.print("[green]✓ Cloud connected[/green]")
                    else:
                        console.print("[red]✗ Cloud disconnected[/red]")

                    # Remote UI
                    if status.remote_enabled:
                        if status.remote_connected:
                            if status.remote_domain:
                                domain = rich_escape(status.remote_domain)
                                console.print(f"[green]✓ Remote UI enabled[/green] ({domain})")
                            else:
                                console.print("[green]✓ Remote UI enabled[/green]")
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
                        count = status.alexa_entity_count
                        console.print(f"[green]  ✓ {count} entities configured[/green]")
                    else:
                        console.print("[dim]  - No entities in filter[/dim]")

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

    Shows all entities that can be exposed to Alexa, their exposure status,
    and Alexa display categories. Use --exposed to filter to only exposed entities.
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _entities() -> None:
        formatter = PorcelainFormatter("cloud alexa entities") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)
                all_entities = await service.get_alexa_entities()
                total_count = len(all_entities)
                # Compute total exposed from unfiltered list
                total_exposed = sum(1 for e in all_entities if e.should_expose)

                # Apply filter if requested (service already sorted by entity_id)
                entities = (
                    [e for e in all_entities if e.should_expose]
                    if exposed_only
                    else all_entities
                )

                if porcelain and formatter:
                    output = formatter.success(
                        data=[e.to_dict() for e in entities],
                        metadata={
                            "total_count": total_count,
                            "total_exposed": total_exposed,
                            "filtered_count": len(entities),
                            "filters_applied": ["exposed_only"] if exposed_only else [],
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
                    table = Table(title="Alexa Entities")
                    table.add_column("Entity ID", style="cyan")
                    table.add_column("Exposed", justify="center")
                    table.add_column("Categories")

                    for entity in entities:
                        exposed_mark = "[green]✓[/green]" if entity.should_expose else "[dim]-[/dim]"
                        cats = entity.display_categories
                        categories_str = ", ".join(cats) if cats else "-"
                        table.add_row(
                            rich_escape(entity.entity_id),
                            exposed_mark,
                            rich_escape(categories_str),
                        )

                    console.print(table)
                    shown = len(entities)
                    summary = f"\n[dim]Showing: {shown} entities, {total_exposed} exposed"
                    if exposed_only:
                        summary += f" (of {total_count} total)"
                    summary += "[/dim]"
                    console.print(summary)

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

                if porcelain and formatter:
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

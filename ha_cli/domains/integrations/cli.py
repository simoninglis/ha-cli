"""CLI commands for integrations domain."""

import asyncio
import json
import sys

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ...common.cli_utils import (
    run_async_command,
    set_porcelain_mode,
    setup_logging,
    write_output,
)
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_USAGE_ERROR, NotFoundError, ValidationError
from ...common.porcelain import PorcelainFormatter, create_home_assistant_metadata
from .service import IntegrationService

app = typer.Typer(
    name="integrations",
    help="Manage Home Assistant integrations (config entries)",
    no_args_is_help=True,
)

console = Console()

# State color mapping
STATE_COLORS = {
    "loaded": "green",
    "not_loaded": "yellow",
    "setup_error": "red",
    "setup_retry": "yellow",
    "failed_unload": "red",
    "migration_error": "red",
}


@app.command("list")
def list_entries(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    domain: str | None = typer.Option(
        None, "--domain", "-d", help="Filter by integration domain"
    ),
    state: str | None = typer.Option(
        None, "--state", "-s", help="Filter by state (loaded, setup_error, etc.)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all config entries (integrations)."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _list() -> None:
        formatter = PorcelainFormatter("integrations list") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = IntegrationService(client)
            try:
                entries = await service.list_entries(domain=domain, state=state)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

            if porcelain:
                assert formatter is not None
                data = [e.to_dict() for e in entries]
                domains = sorted({e.domain for e in entries})
                states = sorted({e.state for e in entries})
                output = formatter.success(
                    data,
                    metadata={
                        "total_count": len(entries),
                        "domains": domains,
                        "states": states,
                        "filters_applied": {
                            "domain": domain,
                            "state": state,
                        },
                        "home_assistant": create_home_assistant_metadata(
                            url_final, "websocket"
                        ),
                    },
                    suggestions={
                        "common_actions": [
                            "View entry details: ha-cli integrations show <entry_id>",
                            "Setup new integration: ha-cli integrations setup <domain>",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                data = [e.to_dict() for e in entries]
                write_output(json.dumps(data, indent=2))
            else:
                if not entries:
                    console.print("[yellow]No config entries found[/yellow]")
                    return

                table = Table(title="Home Assistant Integrations")
                table.add_column("Domain", style="cyan")
                table.add_column("Title")
                table.add_column("State")
                table.add_column("Entry ID", style="dim")

                for entry in entries:
                    state_style = STATE_COLORS.get(entry.state, "white")
                    state_display = entry.state_display
                    if entry.is_disabled:
                        state_display = f"Disabled ({entry.disabled_by})"
                        state_style = "dim"

                    table.add_row(
                        escape(entry.domain),
                        escape(entry.title),
                        f"[{state_style}]{state_display}[/{state_style}]",
                        entry.entry_id[:12] + "...",
                    )

                console.print(table)
                console.print(f"\nTotal: {len(entries)} integrations")

    asyncio.run(run_async_command(_list(), command="integrations list"))


@app.command("show")
def show_entry(
    entry_id: str = typer.Argument(..., help="Config entry ID or domain name"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show details for a specific config entry."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _show() -> None:
        formatter = PorcelainFormatter("integrations show") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = IntegrationService(client)
            # show is non-destructive, allow ambiguous matches
            entry = await service.find_entry(entry_id, allow_ambiguous=True)

            if not entry:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(
                        f"Config entry '{entry_id}' not found",
                        error_code="NOT_FOUND",
                    )
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] Config entry '{escape(entry_id)}' not found")
                sys.exit(EXIT_USAGE_ERROR)

            if porcelain:
                assert formatter is not None
                output = formatter.success(
                    entry.to_dict(),
                    metadata={
                        "entry_id": entry.entry_id,
                        "home_assistant": create_home_assistant_metadata(
                            url_final, "websocket"
                        ),
                    },
                    suggestions={
                        "common_actions": [
                            "List all integrations: ha-cli integrations list",
                            f"Delete: ha-cli integrations delete {entry.entry_id}",
                            f"Disable: ha-cli integrations disable {entry.entry_id}",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                write_output(json.dumps(entry.to_dict(), indent=2))
            else:
                state_style = STATE_COLORS.get(entry.state, "white")
                console.print(f"\n[bold cyan]Integration: {escape(entry.title)}[/bold cyan]")
                console.print(f"  Entry ID: {entry.entry_id}")
                console.print(f"  Domain: {escape(entry.domain)}")
                console.print(f"  State: [{state_style}]{entry.state_display}[/{state_style}]")
                console.print(f"  Source: {escape(entry.source)}")
                console.print(f"  Created: {entry.created_display}")

                if entry.is_disabled:
                    console.print(f"  [yellow]Disabled by: {entry.disabled_by}[/yellow]")
                if entry.reason:
                    console.print(f"  [dim]Reason: {escape(entry.reason)}[/dim]")

                console.print(f"\n  Supports Options: {'Yes' if entry.supports_options else 'No'}")
                console.print(f"  Supports Unload: {'Yes' if entry.supports_unload else 'No'}")
                console.print(f"  Supports Reconfigure: {'Yes' if entry.supports_reconfigure else 'No'}")

    asyncio.run(run_async_command(_show(), command="integrations show"))


@app.command("enable")
def enable_entry(
    entry_id: str = typer.Argument(..., help="Config entry ID"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Enable a disabled config entry."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _enable() -> None:
        formatter = PorcelainFormatter("integrations enable") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = IntegrationService(client)

            # Find entry first (destructive op - disallow ambiguous)
            try:
                entry = await service.find_entry(entry_id)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="AMBIGUOUS_MATCH")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

            if not entry:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(
                        f"Config entry '{entry_id}' not found",
                        error_code="NOT_FOUND",
                    )
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] Config entry '{escape(entry_id)}' not found")
                sys.exit(EXIT_USAGE_ERROR)

            try:
                result = await service.enable_entry(entry.entry_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {
                            "entry_id": entry.entry_id,
                            "domain": entry.domain,
                            "title": entry.title,
                            "enabled": True,
                            "require_restart": result.get("require_restart", False),
                        },
                        metadata={
                            "action": "enabled",
                            "home_assistant": create_home_assistant_metadata(
                                url_final, "websocket"
                            ),
                        },
                    )
                    write_output(output)
                else:
                    console.print(
                        f"[green]Enabled '[bold]{escape(entry.title)}[/bold]' ({entry.domain})[/green]"
                    )
                    if result.get("require_restart"):
                        console.print("[yellow]Note: Home Assistant restart required[/yellow]")
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_enable(), command="integrations enable"))


@app.command("disable")
def disable_entry(
    entry_id: str = typer.Argument(..., help="Config entry ID"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Disable a config entry."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _disable() -> None:
        formatter = PorcelainFormatter("integrations disable") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = IntegrationService(client)

            # Find entry first (destructive op - disallow ambiguous)
            try:
                entry = await service.find_entry(entry_id)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="AMBIGUOUS_MATCH")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

            if not entry:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(
                        f"Config entry '{entry_id}' not found",
                        error_code="NOT_FOUND",
                    )
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] Config entry '{escape(entry_id)}' not found")
                sys.exit(EXIT_USAGE_ERROR)

            try:
                result = await service.disable_entry(entry.entry_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {
                            "entry_id": entry.entry_id,
                            "domain": entry.domain,
                            "title": entry.title,
                            "enabled": False,
                            "require_restart": result.get("require_restart", False),
                        },
                        metadata={
                            "action": "disabled",
                            "home_assistant": create_home_assistant_metadata(
                                url_final, "websocket"
                            ),
                        },
                    )
                    write_output(output)
                else:
                    console.print(
                        f"[green]Disabled '[bold]{escape(entry.title)}[/bold]' ({entry.domain})[/green]"
                    )
                    if result.get("require_restart"):
                        console.print("[yellow]Note: Home Assistant restart required[/yellow]")
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_disable(), command="integrations disable"))


@app.command("delete")
def delete_entry(
    entry_id: str = typer.Argument(..., help="Config entry ID"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt"
    ),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Delete a config entry."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _delete() -> None:
        formatter = PorcelainFormatter("integrations delete") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = IntegrationService(client)

            # Find entry first (destructive op - disallow ambiguous)
            try:
                entry = await service.find_entry(entry_id)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="AMBIGUOUS_MATCH")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

            if not entry:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(
                        f"Config entry '{entry_id}' not found",
                        error_code="NOT_FOUND",
                    )
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] Config entry '{escape(entry_id)}' not found")
                sys.exit(EXIT_USAGE_ERROR)

            # Confirm unless --force or --porcelain
            if not force and not porcelain:
                confirm = typer.confirm(
                    f"Delete integration '{entry.title}' ({entry.domain})?"
                )
                if not confirm:
                    console.print("[yellow]Cancelled[/yellow]")
                    return

            try:
                result = await service.delete_entry(entry.entry_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        result.to_dict(),
                        metadata={
                            "action": "deleted",
                            "home_assistant": create_home_assistant_metadata(
                                url_final, "rest"
                            ),
                        },
                        suggestions={
                            "common_actions": [
                                "List remaining integrations: ha-cli integrations list",
                                f"Re-add integration: ha-cli integrations setup {entry.domain}",
                            ]
                        },
                    )
                    write_output(output)
                else:
                    console.print(
                        f"[green]Deleted '[bold]{escape(entry.title)}[/bold]' ({entry.domain})[/green]"
                    )
                    if result.require_restart:
                        console.print("[yellow]Note: Home Assistant restart required[/yellow]")
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_delete(), command="integrations delete"))


@app.command("setup")
def setup_integration(
    domain_name: str = typer.Argument(..., help="Integration domain to set up"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    host: str | None = typer.Option(
        None, "--host", "-h", help="Host for network integrations (e.g., ESPHome)"
    ),
    port: int | None = typer.Option(
        None, "--port", "-p", help="Port for network integrations"
    ),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Set up a new integration via config flow.

    For simple integrations (media_extractor, etc.), no options are needed.
    For network integrations (ESPHome), use --host and optionally --port.

    Examples:
        ha-cli integrations setup media_extractor
        ha-cli integrations setup esphome --host 10.0.20.50
        ha-cli integrations setup esphome --host 10.0.20.51 --port 6053
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _setup() -> None:
        formatter = PorcelainFormatter("integrations setup") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = IntegrationService(client)

            try:
                result = await service.setup_integration(
                    domain=domain_name,
                    host=host,
                    port=port,
                )

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        result.to_dict(),
                        metadata={
                            "action": "created",
                            "domain": domain_name,
                            "home_assistant": create_home_assistant_metadata(
                                url_final, "rest"
                            ),
                        },
                        suggestions={
                            "common_actions": [
                                "List integrations: ha-cli integrations list",
                                f"Show details: ha-cli integrations show {result.entry_id}",
                            ]
                        },
                    )
                    write_output(output)
                else:
                    console.print(
                        f"[green]Created '[bold]{escape(result.title)}[/bold]' ({result.domain})[/green]"
                    )
                    console.print(f"  Entry ID: {result.entry_id}")
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_setup(), command="integrations setup"))


@app.command("flows")
def list_flows(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List in-progress config flows."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _flows() -> None:
        formatter = PorcelainFormatter("integrations flows") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = IntegrationService(client)
            try:
                flows = await service.list_flows()
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

            if porcelain:
                assert formatter is not None
                data = [f.to_dict() for f in flows]
                output = formatter.success(
                    data,
                    metadata={
                        "total_count": len(flows),
                        "home_assistant": create_home_assistant_metadata(
                            url_final, "websocket"
                        ),
                    },
                    suggestions={
                        "common_actions": [
                            "Cancel flow: ha-cli integrations flow-cancel <flow_id>",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                data = [f.to_dict() for f in flows]
                write_output(json.dumps(data, indent=2))
            else:
                if not flows:
                    console.print("[dim]No in-progress config flows[/dim]")
                    return

                table = Table(title="In-Progress Config Flows")
                table.add_column("Handler", style="cyan")
                table.add_column("Title")
                table.add_column("Step")
                table.add_column("Source")
                table.add_column("Flow ID", style="dim")

                for flow in flows:
                    table.add_row(
                        escape(flow.handler),
                        escape(flow.title),
                        escape(flow.step_id),
                        escape(flow.source),
                        flow.flow_id[:12] + "...",
                    )

                console.print(table)
                console.print(f"\nTotal: {len(flows)} pending flows")

    asyncio.run(run_async_command(_flows(), command="integrations flows"))


@app.command("flow-cancel")
def cancel_flow(
    flow_id: str = typer.Argument(..., help="Config flow ID to cancel"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Cancel an in-progress config flow."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _cancel() -> None:
        formatter = PorcelainFormatter("integrations flow-cancel") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = IntegrationService(client)

            try:
                await service.cancel_flow(flow_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {"flow_id": flow_id, "cancelled": True},
                        metadata={
                            "action": "cancelled",
                            "home_assistant": create_home_assistant_metadata(
                                url_final, "rest"
                            ),
                        },
                    )
                    write_output(output)
                else:
                    console.print(f"[green]Cancelled flow '{flow_id}'[/green]")
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_cancel(), command="integrations flow-cancel"))

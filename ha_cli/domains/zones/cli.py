"""CLI commands for zones domain."""

import asyncio
import json
import sys

import typer
from rich.console import Console
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
from ...common.porcelain import PorcelainFormatter
from .service import ZoneService

app = typer.Typer(
    name="zones",
    help="Manage Home Assistant zones for presence detection",
    no_args_is_help=True,
)

console = Console()


@app.command("list")
def list_zones(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all zones with coordinates and radius."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _list() -> None:
        formatter = PorcelainFormatter("zones list") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = ZoneService(client)
            zones = await service.list_zones()

            if porcelain:
                assert formatter is not None
                data = [z.to_dict() for z in zones]
                summary = await service.get_zone_summary()
                output = formatter.success(
                    data,
                    metadata={
                        "total_count": len(zones),
                        **summary,
                    },
                    suggestions={
                        "common_actions": [
                            "View zone details: ha-cli zones show <zone_id>",
                            "Update zone: ha-cli zones update <zone_id> --lat <lat> --lon <lon>",
                            "Create zone: ha-cli zones create <name> --lat <lat> --lon <lon>",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                data = [z.to_dict() for z in zones]
                write_output(json.dumps(data, indent=2))
            else:
                if not zones:
                    console.print("[yellow]No zones found[/yellow]")
                    return

                table = Table(title="Home Assistant Zones")
                table.add_column("Zone ID", style="cyan")
                table.add_column("Name", style="green")
                table.add_column("Latitude", justify="right")
                table.add_column("Longitude", justify="right")
                table.add_column("Radius (m)", justify="right")
                table.add_column("Passive")

                for zone in zones:
                    table.add_row(
                        zone.zone_id,
                        zone.name,
                        f"{zone.latitude:.6f}",
                        f"{zone.longitude:.6f}",
                        str(int(zone.radius)),
                        "Yes" if zone.passive else "No",
                    )

                console.print(table)
                console.print(f"\nTotal: {len(zones)} zones")

    asyncio.run(run_async_command(_list(), command="zones list"))


@app.command("show")
def show_zone(
    zone_id: str = typer.Argument(..., help="Zone ID or name to show"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show details for a specific zone."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _show() -> None:
        formatter = PorcelainFormatter("zones show") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = ZoneService(client)
            zone = await service.get_zone(zone_id)

            if not zone:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(
                        f"Zone '{zone_id}' not found",
                        error_code="NOT_FOUND",
                    )
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] Zone '{zone_id}' not found")
                sys.exit(EXIT_USAGE_ERROR)

            if porcelain:
                assert formatter is not None
                output = formatter.success(
                    zone.to_dict(),
                    metadata={"zone_id": zone.zone_id},
                    suggestions={
                        "common_actions": [
                            f"Update zone: ha-cli zones update {zone.zone_id} --lat <lat> --lon <lon>",
                            "List all zones: ha-cli zones list",
                            f"Google Maps: {zone.google_maps_url}",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                write_output(json.dumps(zone.to_dict(), indent=2))
            else:
                console.print(f"\n[bold cyan]Zone: {zone.name}[/bold cyan]")
                console.print(f"  ID: {zone.zone_id}")
                console.print(f"  Entity ID: {zone.entity_id}")
                console.print(f"  Latitude: {zone.latitude:.8f}")
                console.print(f"  Longitude: {zone.longitude:.8f}")
                console.print(f"  Radius: {int(zone.radius)}m")
                if zone.icon:
                    console.print(f"  Icon: {zone.icon}")
                console.print(f"  Passive: {'Yes' if zone.passive else 'No'}")
                if zone.persons:
                    console.print(f"  Persons in zone: {', '.join(zone.persons)}")
                console.print(f"\n  [dim]Google Maps: {zone.google_maps_url}[/dim]")

    asyncio.run(run_async_command(_show(), command="zones show"))


@app.command("create")
def create_zone(
    name: str = typer.Argument(..., help="Name for the new zone"),
    latitude: float = typer.Option(
        ..., "--lat", "-y", help="Center point latitude"
    ),
    longitude: float = typer.Option(
        ..., "--lon", "-x", help="Center point longitude"
    ),
    radius: float = typer.Option(
        100.0, "--radius", "-r", help="Radius in meters"
    ),
    icon: str | None = typer.Option(
        None, "--icon", "-i", help="Icon (e.g., mdi:school)"
    ),
    passive: bool = typer.Option(
        False, "--passive", "-p", help="Hide from UI and device tracker"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Create a new zone."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _create() -> None:
        formatter = PorcelainFormatter("zones create") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = ZoneService(client)

            try:
                zone = await service.create_zone(
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    radius=radius,
                    icon=icon,
                    passive=passive,
                )

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        zone.to_dict(),
                        metadata={"zone_id": zone.zone_id, "action": "created"},
                        suggestions={
                            "common_actions": [
                                f"View zone: ha-cli zones show {zone.zone_id}",
                                "List all zones: ha-cli zones list",
                            ]
                        },
                    )
                    write_output(output)
                elif json_output:
                    write_output(json.dumps(zone.to_dict(), indent=2))
                else:
                    console.print(
                        f"[green]Created zone '[bold]{zone.name}[/bold]' "
                        f"(ID: {zone.zone_id})[/green]"
                    )
                    console.print(f"  Location: {zone.latitude:.6f}, {zone.longitude:.6f}")
                    console.print(f"  Radius: {int(zone.radius)}m")
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {e}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_create(), command="zones create"))


@app.command("update")
def update_zone(
    zone_id: str = typer.Argument(..., help="Zone ID to update"),
    name: str | None = typer.Option(None, "--name", "-n", help="New zone name"),
    latitude: float | None = typer.Option(
        None, "--lat", "-y", help="New center point latitude"
    ),
    longitude: float | None = typer.Option(
        None, "--lon", "-x", help="New center point longitude"
    ),
    radius: float | None = typer.Option(
        None, "--radius", "-r", help="New radius in meters"
    ),
    icon: str | None = typer.Option(
        None, "--icon", "-i", help="New icon (empty string to clear)"
    ),
    passive: bool | None = typer.Option(
        None, "--passive/--no-passive", help="Set passive mode"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Update an existing zone's location or metadata."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _update() -> None:
        formatter = PorcelainFormatter("zones update") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = ZoneService(client)

            try:
                zone = await service.update_zone(
                    zone_id=zone_id,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    radius=radius,
                    icon=icon,
                    passive=passive,
                )

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        zone.to_dict(),
                        metadata={"zone_id": zone.zone_id, "action": "updated"},
                        suggestions={
                            "common_actions": [
                                f"View zone: ha-cli zones show {zone.zone_id}",
                                "List all zones: ha-cli zones list",
                            ]
                        },
                    )
                    write_output(output)
                elif json_output:
                    write_output(json.dumps(zone.to_dict(), indent=2))
                else:
                    console.print(
                        f"[green]Updated zone '[bold]{zone.name}[/bold]'[/green]"
                    )
                    console.print(f"  Location: {zone.latitude:.6f}, {zone.longitude:.6f}")
                    console.print(f"  Radius: {int(zone.radius)}m")
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {e}")
                sys.exit(EXIT_USAGE_ERROR)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {e}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_update(), command="zones update"))


@app.command("delete")
def delete_zone(
    zone_id: str = typer.Argument(..., help="Zone ID to delete"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Delete a zone. The 'home' zone cannot be deleted."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _delete() -> None:
        formatter = PorcelainFormatter("zones delete") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = ZoneService(client)

            try:
                # Get zone info before deletion for output
                zone_info = await service.get_zone(zone_id)
                if not zone_info:
                    raise NotFoundError(f"Zone not found: {zone_id}")

                zone_name = zone_info.name

                # Confirm deletion unless --force
                if not force and not porcelain:
                    confirm = typer.confirm(
                        f"Delete zone '{zone_name}' at "
                        f"({zone_info.latitude:.4f}, {zone_info.longitude:.4f})?"
                    )
                    if not confirm:
                        console.print("[yellow]Cancelled[/yellow]")
                        return

                await service.delete_zone(zone_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {"zone_id": zone_id, "deleted": True},
                        metadata={"zone_id": zone_id, "action": "deleted"},
                        suggestions={
                            "common_actions": [
                                "List all zones: ha-cli zones list",
                            ]
                        },
                    )
                    write_output(output)
                else:
                    console.print(
                        f"[green]Deleted zone '[bold]{zone_name}[/bold]'[/green]"
                    )
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {e}")
                sys.exit(EXIT_USAGE_ERROR)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {e}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_delete(), command="zones delete"))


@app.command("version")
def version() -> None:
    """Show zones domain version."""
    from ... import __version__

    console.print(f"ha-cli zones version {__version__}")

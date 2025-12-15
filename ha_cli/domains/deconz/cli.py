"""deCONZ CLI commands for migration management."""

import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ...common.cli_utils import write_output
from ...common.exceptions import EXIT_HA_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from ...common.porcelain import PorcelainFormatter
from .service import APIError, DeconzService, SSHError

app = typer.Typer(
    name="deconz",
    help="Manage deCONZ devices for ZHA migration",
    no_args_is_help=True,
)

console = Console()

# Valid device types for list command
VALID_LIST_TYPES = ("lights", "sensors", "groups", "all")
VALID_DELETE_TYPES = ("light", "sensor")


def get_service() -> DeconzService:
    """Create and return deCONZ service."""
    return DeconzService()


@app.command("list")
def list_devices(
    device_type: str = typer.Argument(
        ...,
        help="Type of devices to list: lights, sensors, groups, or all",
    ),
    search: Optional[str] = typer.Option(
        None,
        "--search",
        "-s",
        help="Filter devices by name (case-insensitive)",
    ),
    porcelain: bool = typer.Option(
        False,
        "--porcelain",
        help="Output in machine-readable format",
    ),
) -> None:
    """List deCONZ devices."""
    formatter = PorcelainFormatter("deconz list") if porcelain else None

    # Validate device_type argument
    if device_type not in VALID_LIST_TYPES:
        if porcelain:
            assert formatter is not None
            output = formatter.error(
                f"Invalid device type: {device_type}",
                error_code="INVALID_ARGUMENT",
                details={"valid_types": list(VALID_LIST_TYPES)},
            )
            write_output(output)
        else:
            console.print(
                f"[red]Invalid device type: {device_type}[/red]\n"
                f"Valid types: {', '.join(VALID_LIST_TYPES)}"
            )
        sys.exit(EXIT_USAGE_ERROR)

    service = get_service()

    try:
        config = service.get_config()
        if not porcelain:
            console.print(f"Connected to deCONZ at {config.host}:{config.port}")

        # Collect data for porcelain output
        result_data: dict = {}

        if device_type in ("lights", "all"):
            lights = service.list_lights(search=search)
            if porcelain:
                result_data["lights"] = [vars(d) for d in lights]
            else:
                table = Table(title="Lights" if device_type == "lights" else None)
                table.add_column("ID", style="cyan", width=4)
                table.add_column("Name", width=30)
                table.add_column("Model", width=25)
                table.add_column("IEEE Address", style="dim")

                for light in lights:
                    table.add_row(light.id, light.name, light.model[:24], light.ieee)

                console.print(table)
                console.print(f"Total: {len(lights)} lights\n")

        if device_type in ("sensors", "all"):
            sensors = service.list_sensors(search=search)
            if porcelain:
                result_data["sensors"] = [vars(d) for d in sensors]
            else:
                table = Table(title="Sensors" if device_type == "sensors" else None)
                table.add_column("ID", style="cyan", width=4)
                table.add_column("Name", width=30)
                table.add_column("Type", width=20)
                table.add_column("Model", width=20)
                table.add_column("IEEE Address", style="dim")

                for sensor in sensors:
                    table.add_row(
                        sensor.id,
                        sensor.name,
                        (sensor.sensor_type or "")[:19],
                        sensor.model[:19],
                        sensor.ieee,
                    )

                console.print(table)
                console.print(f"Total: {len(sensors)} sensors\n")

        if device_type in ("groups", "all"):
            groups = service.list_groups()
            if porcelain:
                result_data["groups"] = groups
            else:
                table = Table(title="Groups" if device_type == "groups" else None)
                table.add_column("ID", style="cyan", width=4)
                table.add_column("Name", width=30)
                table.add_column("Lights")

                for group in groups:
                    table.add_row(group["id"], group["name"], ", ".join(group["lights"]))

                console.print(table)
                console.print(f"Total: {len(groups)} groups\n")

        # Output porcelain format
        if porcelain:
            assert formatter is not None
            total_count = sum(len(v) if isinstance(v, list) else 0 for v in result_data.values())
            output = formatter.success(
                result_data,
                metadata={
                    "device_type": device_type,
                    "search": search,
                    "total_count": total_count,
                    "deconz_host": f"{config.host}:{config.port}",
                },
                suggestions={
                    "common_actions": [
                        "Search devices: ha-cli deconz search <query>",
                        "Delete device: ha-cli deconz delete light|sensor <id>",
                    ],
                    "related_commands": [
                        "entities list --domain light",
                        "entities list --domain sensor",
                    ],
                },
            )
            write_output(output)

    except SSHError as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="SSH_ERROR")
            write_output(output)
        else:
            console.print(f"[red]SSH Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)
    except APIError as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="API_ERROR")
            write_output(output)
        else:
            console.print(f"[red]API Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)
    except Exception as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="UNKNOWN_ERROR")
            write_output(output)
        else:
            console.print(f"[red]Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)


@app.command("search")
def search_devices(
    query: str = typer.Argument(..., help="Search query"),
    porcelain: bool = typer.Option(
        False,
        "--porcelain",
        help="Output in machine-readable format",
    ),
) -> None:
    """Search for deCONZ devices by name."""
    formatter = PorcelainFormatter("deconz search") if porcelain else None
    service = get_service()

    try:
        config = service.get_config()
        if not porcelain:
            console.print(f"Connected to deCONZ at {config.host}:{config.port}")
            console.print(f"\nSearching for '{query}'...")

        lights, sensors = service.search(query)

        if porcelain:
            assert formatter is not None
            result_data = {
                "lights": [vars(d) for d in lights],
                "sensors": [vars(d) for d in sensors],
            }
            output = formatter.success(
                result_data,
                metadata={
                    "query": query,
                    "lights_found": len(lights),
                    "sensors_found": len(sensors),
                    "total_found": len(lights) + len(sensors),
                    "deconz_host": f"{config.host}:{config.port}",
                },
                suggestions={
                    "common_actions": [
                        "Delete device: ha-cli deconz delete light|sensor <id>",
                        "List all: ha-cli deconz list all",
                    ],
                },
            )
            write_output(output)
        else:
            if lights:
                console.print(f"\n[bold]=== Lights ({len(lights)}) ===[/bold]")
                for light in lights:
                    console.print(f"  ID {light.id}: {light.name} ({light.ieee})")

            if sensors:
                console.print(f"\n[bold]=== Sensors ({len(sensors)}) ===[/bold]")
                for sensor in sensors:
                    console.print(
                        f"  ID {sensor.id}: {sensor.name} [{sensor.sensor_type}] ({sensor.ieee})"
                    )

            if not lights and not sensors:
                console.print("[yellow]No devices found matching query[/yellow]")

    except SSHError as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="SSH_ERROR")
            write_output(output)
        else:
            console.print(f"[red]SSH Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)
    except APIError as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="API_ERROR")
            write_output(output)
        else:
            console.print(f"[red]API Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)
    except Exception as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="UNKNOWN_ERROR")
            write_output(output)
        else:
            console.print(f"[red]Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)


@app.command("delete")
def delete_device(
    device_type: str = typer.Argument(
        ...,
        help="Type of device: light or sensor",
    ),
    device_id: str = typer.Argument(..., help="deCONZ device ID"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
    porcelain: bool = typer.Option(
        False,
        "--porcelain",
        help="Output in machine-readable format",
    ),
) -> None:
    """Delete a device from deCONZ."""
    formatter = PorcelainFormatter("deconz delete") if porcelain else None

    # Validate device_type argument
    if device_type not in VALID_DELETE_TYPES:
        if porcelain:
            assert formatter is not None
            output = formatter.error(
                f"Invalid device type: {device_type}",
                error_code="INVALID_ARGUMENT",
                details={"valid_types": list(VALID_DELETE_TYPES)},
            )
            write_output(output)
        else:
            console.print(
                f"[red]Invalid device type: {device_type}[/red]\n"
                f"Valid types: {', '.join(VALID_DELETE_TYPES)}"
            )
        sys.exit(EXIT_USAGE_ERROR)

    service = get_service()

    try:
        config = service.get_config()
        if not porcelain:
            console.print(f"Connected to deCONZ at {config.host}:{config.port}")

        # Get device info first
        device = service.get_device(device_type, device_id)
        if not device:
            if porcelain:
                assert formatter is not None
                output = formatter.error(
                    f"Device {device_type}/{device_id} not found",
                    error_code="NOT_FOUND",
                    details={"device_type": device_type, "device_id": device_id},
                )
                write_output(output)
            else:
                console.print(f"[red]Device {device_type}/{device_id} not found[/red]")
            sys.exit(EXIT_HA_ERROR)

        if not porcelain:
            console.print("\n[bold]Device to delete:[/bold]")
            console.print(f"  Type: {device_type}")
            console.print(f"  ID:   {device_id}")
            console.print(f"  Name: {device.name}")
            console.print(f"  IEEE: {device.ieee}")

        if not force and not porcelain:
            confirm = typer.confirm("\nDelete this device?", default=False)
            if not confirm:
                console.print("Cancelled")
                sys.exit(EXIT_SUCCESS)

        if service.delete_device(device_type, device_id):
            if porcelain:
                assert formatter is not None
                output = formatter.success(
                    {
                        "action": "delete",
                        "device_type": device_type,
                        "device_id": device_id,
                        "device_name": device.name,
                        "device_ieee": device.ieee,
                        "success": True,
                    },
                    metadata={"deconz_host": f"{config.host}:{config.port}"},
                    suggestions={
                        "common_actions": [
                            "List remaining devices: ha-cli deconz list all",
                            "Pair to ZHA: Enable ZHA pairing mode in Home Assistant",
                        ],
                    },
                )
                write_output(output)
            else:
                console.print(f"[green]✓ Successfully deleted {device_type} {device_id}[/green]")
        else:
            if porcelain:
                assert formatter is not None
                output = formatter.error(
                    "Delete operation failed",
                    error_code="DELETE_FAILED",
                    details={"device_type": device_type, "device_id": device_id},
                )
                write_output(output)
            else:
                console.print("[red]✗ Failed to delete device[/red]")
            sys.exit(EXIT_HA_ERROR)

    except SSHError as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="SSH_ERROR")
            write_output(output)
        else:
            console.print(f"[red]SSH Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)
    except APIError as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="API_ERROR")
            write_output(output)
        else:
            console.print(f"[red]API Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)
    except Exception as e:
        if porcelain:
            assert formatter is not None
            output = formatter.error(e, error_code="UNKNOWN_ERROR")
            write_output(output)
        else:
            console.print(f"[red]Error: {e}[/red]")
        sys.exit(EXIT_HA_ERROR)


@app.command("version")
def version() -> None:
    """Show deCONZ domain version."""
    console.print("deCONZ Migration Helper v1.0.0")

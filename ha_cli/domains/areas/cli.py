"""CLI commands for areas domain."""

import asyncio
import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from ...common.cli_utils import run_async_command, set_porcelain_mode, setup_logging, write_output
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_USAGE_ERROR, NotFoundError, ValidationError
from ...common.porcelain import PorcelainFormatter
from .service import AreaService

app = typer.Typer(
    name="areas",
    help="Manage Home Assistant areas and registry metadata",
    no_args_is_help=True,
)

console = Console()


@app.command("list")
def list_areas(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    show_counts: bool = typer.Option(
        True, "--counts/--no-counts", help="Show device/entity counts"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all areas with device and entity counts."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _list() -> None:
        formatter = PorcelainFormatter("areas list") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)

            if show_counts:
                areas = await service.list_areas_with_counts()
            else:
                areas_basic = await service.list_areas()
                areas = areas_basic  # type: ignore

            if porcelain:
                assert formatter is not None
                data = [a.to_dict() for a in areas]
                summary = await service.get_area_summary()
                output = formatter.success(
                    data,
                    metadata={
                        "total_count": len(areas),
                        **summary,
                    },
                    suggestions={
                        "common_actions": [
                            "View area details: ha-cli areas show <area_id>",
                            "Audit area naming: ha-cli areas audit",
                            "List floors: ha-cli areas floors",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                data = [a.to_dict() for a in areas]
                write_output(json.dumps(data, indent=2))
            else:
                if not areas:
                    console.print("[yellow]No areas found[/yellow]")
                    return

                table = Table(title="Home Assistant Areas")
                table.add_column("Area ID", style="cyan")
                table.add_column("Name", style="green")
                if show_counts:
                    table.add_column("Devices", justify="right")
                    table.add_column("Entities", justify="right")
                table.add_column("Floor")
                table.add_column("Labels")

                for area in areas:
                    row = [area.area_id, area.name]
                    if show_counts and hasattr(area, "device_count"):
                        row.append(str(area.device_count))
                        row.append(str(area.entity_count))
                    else:
                        if show_counts:
                            row.extend(["", ""])
                    row.append(area.floor_id or "-")
                    row.append(", ".join(area.labels) if area.labels else "-")
                    table.add_row(*row)

                console.print(table)
                console.print(f"\nTotal: {len(areas)} areas")

    asyncio.run(run_async_command(_list(), command="areas list"))


@app.command("show")
def show_area(
    area_id: str = typer.Argument(..., help="Area ID or name to show"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show details for a specific area."""
    setup_logging(debug)

    async def _show() -> None:
        formatter = PorcelainFormatter("areas show") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)
            area = await service.get_area(area_id)

            if not area:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(
                        f"Area '{area_id}' not found",
                        error_code="NOT_FOUND",
                    )
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] Area '{area_id}' not found")
                sys.exit(EXIT_USAGE_ERROR)

            if porcelain:
                assert formatter is not None
                output = formatter.success(
                    area.to_dict(),
                    metadata={"area_id": area.area_id},
                    suggestions={
                        "common_actions": [
                            "List all areas: ha-cli areas list",
                            "Audit areas: ha-cli areas audit",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                write_output(json.dumps(area.to_dict(), indent=2))
            else:
                console.print(f"\n[bold cyan]Area: {area.name}[/bold cyan]")
                console.print(f"  ID: {area.area_id}")
                if area.floor_id:
                    console.print(f"  Floor: {area.floor_id}")
                if area.icon:
                    console.print(f"  Icon: {area.icon}")
                if area.labels:
                    console.print(f"  Labels: {', '.join(area.labels)}")
                if area.aliases:
                    console.print(f"  Aliases: {', '.join(area.aliases)}")

                console.print(f"\n  [bold]Devices:[/bold] {area.device_count}")
                if area.devices:
                    for device in area.devices[:10]:
                        console.print(f"    - {device}")
                    if len(area.devices) > 10:
                        console.print(
                            f"    ... and {len(area.devices) - 10} more"
                        )

                console.print(f"\n  [bold]Entities:[/bold] {area.entity_count}")
                if area.entities:
                    for entity in area.entities[:10]:
                        console.print(f"    - {entity}")
                    if len(area.entities) > 10:
                        console.print(
                            f"    ... and {len(area.entities) - 10} more"
                        )

    asyncio.run(run_async_command(_show()))


@app.command("floors")
def list_floors(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all floors."""
    setup_logging(debug)

    async def _list() -> None:
        formatter = PorcelainFormatter("areas floors") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)
            floors = await service.list_floors()

            if porcelain:
                assert formatter is not None
                data = [f.to_dict() for f in floors]
                output = formatter.success(
                    data,
                    metadata={"total_count": len(floors)},
                )
                write_output(output)
            elif json_output:
                data = [f.to_dict() for f in floors]
                write_output(json.dumps(data, indent=2))
            else:
                if not floors:
                    console.print("[yellow]No floors defined[/yellow]")
                    return

                table = Table(title="Home Assistant Floors")
                table.add_column("Floor ID", style="cyan")
                table.add_column("Name", style="green")
                table.add_column("Level", justify="right")
                table.add_column("Icon")

                for floor in floors:
                    table.add_row(
                        floor.floor_id,
                        floor.name,
                        str(floor.level),
                        floor.icon or "-",
                    )

                console.print(table)

    asyncio.run(run_async_command(_list()))


@app.command("labels")
def list_labels(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all labels."""
    setup_logging(debug)

    async def _list() -> None:
        formatter = PorcelainFormatter("areas labels") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)
            labels = await service.list_labels()

            if porcelain:
                assert formatter is not None
                data = [lbl.to_dict() for lbl in labels]
                output = formatter.success(
                    data,
                    metadata={"total_count": len(labels)},
                )
                write_output(output)
            elif json_output:
                data = [lbl.to_dict() for lbl in labels]
                write_output(json.dumps(data, indent=2))
            else:
                if not labels:
                    console.print("[yellow]No labels defined[/yellow]")
                    return

                table = Table(title="Home Assistant Labels")
                table.add_column("Label ID", style="cyan")
                table.add_column("Name", style="green")
                table.add_column("Color")
                table.add_column("Description")

                for label in labels:
                    table.add_row(
                        label.label_id,
                        label.name,
                        label.color or "-",
                        (label.description or "-")[:50],
                    )

                console.print(table)

    asyncio.run(run_async_command(_list()))


@app.command("audit")
def audit_areas(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Audit areas for naming issues and problems."""
    setup_logging(debug)

    async def _audit() -> None:
        formatter = PorcelainFormatter("areas audit") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)

            # Get all audit data
            naming_issues = await service.check_naming_issues()
            empty_areas = await service.find_empty_areas()
            summary = await service.get_area_summary()

            findings = []

            # Add naming issues
            for issue in naming_issues:
                findings.append({
                    "category": "naming",
                    "severity": "warning",
                    **issue,
                })

            # Add empty areas
            for area in empty_areas:
                findings.append({
                    "category": "empty_area",
                    "severity": "info",
                    "area_id": area.area_id,
                    "area_name": area.name,
                    "message": f"Area '{area.name}' has no devices or entities",
                    "suggestion": "Consider removing or assigning devices/entities",
                })

            # Add coverage warnings
            if summary["area_coverage_entities"] < 10:
                findings.append({
                    "category": "low_coverage",
                    "severity": "warning",
                    "message": (
                        f"Only {summary['area_coverage_entities']}% of entities "
                        f"have area assignments"
                    ),
                    "suggestion": "Consider assigning entities to areas for "
                    "better organization",
                })

            has_issues = len(findings) > 0

            if porcelain:
                assert formatter is not None
                output = formatter.success(
                    findings,
                    metadata={
                        "total_findings": len(findings),
                        "naming_issues": len(naming_issues),
                        "empty_areas": len(empty_areas),
                        **summary,
                    },
                    suggestions={
                        "common_actions": [
                            "List all areas: ha-cli areas list",
                            "Show area details: ha-cli areas show <area_id>",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                output_data = {
                    "findings": findings,
                    "summary": summary,
                }
                write_output(json.dumps(output_data, indent=2))
            else:
                console.print("\n[bold]Area Audit Report[/bold]\n")

                # Summary
                console.print("[bold cyan]Summary:[/bold cyan]")
                console.print(f"  Total areas: {summary['total_areas']}")
                console.print(f"  Empty areas: {summary['empty_areas']}")
                console.print(
                    f"  Entity coverage: {summary['area_coverage_entities']}%"
                )
                console.print(
                    f"  Device coverage: {summary['area_coverage_devices']}%"
                )

                if not findings:
                    console.print("\n[green]No issues found![/green]")
                else:
                    msg = f"Issues Found: {len(findings)}"
                    console.print(f"\n[bold yellow]{msg}[/bold yellow]\n")

                    # Group by category
                    by_category: dict[str, list] = {}
                    for finding in findings:
                        cat = finding["category"]
                        if cat not in by_category:
                            by_category[cat] = []
                        by_category[cat].append(finding)

                    for category, items in by_category.items():
                        console.print(f"[bold]{category}[/bold] ({len(items)}):")
                        for item in items:
                            severity = item.get("severity", "info")
                            color = {
                                "error": "red",
                                "warning": "yellow",
                                "info": "blue",
                            }.get(severity, "white")
                            console.print(
                                f"  [{color}]•[/{color}] {item['message']}"
                            )
                            if item.get("suggestion"):
                                console.print(
                                    f"    [dim]Suggestion: {item['suggestion']}[/dim]"
                                )
                        console.print()

            if has_issues:
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_audit()))


@app.command("create")
def create_area(
    name: str = typer.Argument(..., help="Name for the new area"),
    floor: str | None = typer.Option(None, "--floor", "-f", help="Floor ID to assign"),
    icon: str | None = typer.Option(None, "--icon", "-i", help="Icon (e.g., mdi:home)"),
    aliases: str | None = typer.Option(
        None, "--aliases", "-a", help="Comma-separated aliases"
    ),
    labels: str | None = typer.Option(
        None, "--labels", "-l", help="Comma-separated label IDs"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Create a new area."""
    setup_logging(debug)

    async def _create() -> None:
        formatter = PorcelainFormatter("areas create") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)

            # Parse comma-separated values
            aliases_list = (
                [a.strip() for a in aliases.split(",") if a.strip()]
                if aliases
                else None
            )
            labels_list = (
                [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
                if labels
                else None
            )

            try:
                area = await service.create_area(
                    name=name,
                    floor_id=floor,
                    icon=icon,
                    aliases=aliases_list,
                    labels=labels_list,
                )

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        area.to_dict(),
                        metadata={"area_id": area.area_id, "action": "created"},
                        suggestions={
                            "common_actions": [
                                f"View area: ha-cli areas show {area.area_id}",
                                "List all areas: ha-cli areas list",
                            ]
                        },
                    )
                    write_output(output)
                elif json_output:
                    write_output(json.dumps(area.to_dict(), indent=2))
                else:
                    console.print(
                        f"[green]✓[/green] Created area '[bold]{area.name}[/bold]' "
                        f"(ID: {area.area_id})"
                    )
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {e}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_create()))


@app.command("rename")
def rename_area(
    area_id: str = typer.Argument(..., help="Area ID to rename"),
    new_name: str = typer.Argument(..., help="New name for the area"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Rename an existing area."""
    setup_logging(debug)

    async def _rename() -> None:
        formatter = PorcelainFormatter("areas rename") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)

            try:
                area = await service.rename_area(area_id, new_name)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        area.to_dict(),
                        metadata={
                            "area_id": area.area_id,
                            "action": "renamed",
                            "new_name": new_name,
                        },
                        suggestions={
                            "common_actions": [
                                f"View area: ha-cli areas show {area.area_id}",
                                "List all areas: ha-cli areas list",
                            ]
                        },
                    )
                    write_output(output)
                elif json_output:
                    write_output(json.dumps(area.to_dict(), indent=2))
                else:
                    console.print(
                        f"[green]✓[/green] Renamed area to '[bold]{area.name}[/bold]'"
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

    asyncio.run(run_async_command(_rename()))


@app.command("update")
def update_area(
    area_id: str = typer.Argument(..., help="Area ID to update"),
    name: str | None = typer.Option(None, "--name", "-n", help="New area name"),
    floor: str | None = typer.Option(
        None, "--floor", "-f", help="Floor ID (empty string to clear)"
    ),
    icon: str | None = typer.Option(
        None, "--icon", "-i", help="Icon (empty string to clear)"
    ),
    aliases: str | None = typer.Option(
        None, "--aliases", "-a", help="Comma-separated aliases (replaces existing)"
    ),
    labels: str | None = typer.Option(
        None, "--labels", "-l", help="Comma-separated label IDs (replaces existing)"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Update an existing area's metadata."""
    setup_logging(debug)

    async def _update() -> None:
        formatter = PorcelainFormatter("areas update") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)

            # Parse comma-separated values if provided
            aliases_list: list[str] | None = None
            labels_list: list[str] | None = None
            if aliases is not None:
                aliases_list = (
                    [a.strip() for a in aliases.split(",") if a.strip()]
                    if aliases
                    else []
                )
            if labels is not None:
                labels_list = (
                    [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
                    if labels
                    else []
                )

            try:
                area = await service.update_area(
                    area_id=area_id,
                    name=name,
                    floor_id=floor,
                    icon=icon,
                    aliases=aliases_list,
                    labels=labels_list,
                )

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        area.to_dict(),
                        metadata={"area_id": area.area_id, "action": "updated"},
                        suggestions={
                            "common_actions": [
                                f"View area: ha-cli areas show {area.area_id}",
                                "List all areas: ha-cli areas list",
                            ]
                        },
                    )
                    write_output(output)
                elif json_output:
                    write_output(json.dumps(area.to_dict(), indent=2))
                else:
                    console.print(
                        f"[green]✓[/green] Updated area '[bold]{area.name}[/bold]'"
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

    asyncio.run(run_async_command(_update()))


@app.command("delete")
def delete_area(
    area_id: str = typer.Argument(..., help="Area ID to delete"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Delete even if area has devices/entities"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Delete an area."""
    setup_logging(debug)

    async def _delete() -> None:
        formatter = PorcelainFormatter("areas delete") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = AreaService(client)

            try:
                # Get area info before deletion for output
                area_info = await service.get_area(area_id)
                area_name = area_info.name if area_info else area_id

                await service.delete_area(area_id, force=force)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {"area_id": area_id, "deleted": True},
                        metadata={"area_id": area_id, "action": "deleted"},
                        suggestions={
                            "common_actions": [
                                "List all areas: ha-cli areas list",
                            ]
                        },
                    )
                    write_output(output)
                else:
                    console.print(
                        f"[green]✓[/green] Deleted area '[bold]{area_name}[/bold]'"
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

    asyncio.run(run_async_command(_delete()))


@app.command("version")
def version() -> None:
    """Show areas domain version."""
    from ... import __version__

    console.print(f"ha-cli areas version {__version__}")

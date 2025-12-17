"""Labels CLI commands for managing Home Assistant labels."""

import asyncio
import sys

import typer
from rich.console import Console
from rich.markup import escape as rich_escape
from rich.table import Table

from ...common.cli_utils import run_async_command, set_porcelain_mode, setup_logging, write_output
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import (
    EXIT_HA_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    AuthenticationError,
    ConfigurationError,
    ConnectionError,
    NotFoundError,
    ValidationError,
    WebSocketError,
)
from ...common.porcelain import PorcelainFormatter
from .service import LabelsService

app = typer.Typer(
    name="labels",
    help="Manage Home Assistant labels (semantic grouping per ADR-0006)",
    no_args_is_help=True,
)

console = Console()

# Valid colors for labels (from HA UI) - set for O(1) lookup
VALID_COLORS = {
    "red", "pink", "purple", "deep-purple", "indigo", "blue", "light-blue",
    "cyan", "teal", "green", "light-green", "lime", "yellow", "amber",
    "orange", "deep-orange", "brown", "grey", "blue-grey",
}


def _handle_error(
    e: Exception,
    porcelain: bool,
    formatter: PorcelainFormatter | None,
) -> None:
    """Handle errors with appropriate output format and exit code.

    Maps exception types to appropriate error codes and exit codes:
    - NotFoundError, ValidationError, ConfigurationError -> EXIT_USAGE_ERROR (1)
    - ConnectionError, WebSocketError -> EXIT_NETWORK_ERROR (2)
    - AuthenticationError, other HAAutomationError -> EXIT_HA_ERROR (3)
    """
    # Map exception type to error code and exit code
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
        # Pass exception object directly - formatter extracts type and details
        output = formatter.error(e, error_code=error_code)
        write_output(output)
    else:
        console.print(f"[red]Error: {rich_escape(str(e))}[/red]")

    sys.exit(exit_code)


@app.command("list")
def list_labels(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all labels in the registry."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _list() -> None:
        formatter = PorcelainFormatter("labels list") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = LabelsService(client)
                labels = await service.list_labels()

                if porcelain:
                    assert formatter is not None
                    data = [label.to_dict() for label in labels]
                    output = formatter.success(
                        data=data,
                        metadata={"total_count": len(labels)},
                        suggestions={
                            "common_actions": [
                                "ha-cli labels entities <label_id>",
                                "ha-cli labels create <name>",
                                "ha-cli labels assign <entity_id> <label_id>",
                            ]
                        },
                    )
                    write_output(output)
                else:
                    if not labels:
                        console.print("[yellow]No labels found[/yellow]")
                        return

                    table = Table(title="Labels")
                    table.add_column("ID", style="cyan")
                    table.add_column("Name")
                    table.add_column("Icon")
                    table.add_column("Color")

                    for label in labels:
                        table.add_row(
                            rich_escape(label.label_id),
                            rich_escape(label.name),
                            rich_escape(label.icon or ""),
                            rich_escape(label.color or ""),
                        )

                    console.print(table)
                    console.print(f"\n[dim]Total: {len(labels)} labels[/dim]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_list(), command="labels list"))


@app.command("create")
def create_label(
    name: str = typer.Argument(..., help="Label name"),
    icon: str | None = typer.Option(
        None, "--icon", "-i", help="MDI icon (e.g., mdi:lightbulb-group)"
    ),
    color: str | None = typer.Option(
        None, "--color", "-c", help="Color (e.g., orange, blue)"
    ),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Description"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Create a new label."""
    setup_logging(debug)

    # Validate color if provided
    if color and color not in VALID_COLORS:
        formatter = PorcelainFormatter("labels create") if porcelain else None
        if porcelain and formatter:
            output = formatter.error(
                f"Invalid color: {color}",
                error_code="INVALID_ARGUMENT",
                details={"valid_colors": sorted(VALID_COLORS)},
            )
            write_output(output)
        else:
            console.print(f"[red]Invalid color: {rich_escape(color)}[/red]")
            console.print(f"[dim]Valid colors: {', '.join(sorted(VALID_COLORS))}[/dim]")
        sys.exit(EXIT_USAGE_ERROR)

    async def _create() -> None:
        formatter = PorcelainFormatter("labels create") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = LabelsService(client)
                label = await service.create_label(
                    name, icon=icon, color=color, description=description
                )

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        data=label.to_dict(),
                        suggestions={
                            "next_steps": [
                                f"ha-cli labels assign <entity_id> {label.label_id}",
                                f"ha-cli labels entities {label.label_id}",
                            ]
                        },
                    )
                    write_output(output)
                else:
                    console.print(f"[green]✓ Label created: {rich_escape(label.label_id)}[/green]")
                    if label.icon:
                        console.print(f"  Icon: {rich_escape(label.icon)}")
                    if label.color:
                        console.print(f"  Color: {rich_escape(label.color)}")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_create(), command="labels create"))


@app.command("delete")
def delete_label(
    label_id: str = typer.Argument(..., help="Label ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Delete a label.

    In porcelain mode, --force is required to prevent accidental deletion.
    """
    setup_logging(debug)

    # Safety: require --force in porcelain mode to prevent accidental deletion
    if porcelain and not force:
        formatter = PorcelainFormatter("labels delete")
        output = formatter.error(
            "Delete requires --force flag in porcelain mode for safety",
            error_code="FORCE_REQUIRED",
        )
        write_output(output)
        sys.exit(EXIT_USAGE_ERROR)

    async def _delete() -> None:
        formatter = PorcelainFormatter("labels delete") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = LabelsService(client)

                # Check if label exists and show details
                label = await service.get_label(label_id)
                if not label:
                    if porcelain:
                        assert formatter is not None
                        output = formatter.error(
                            f"Label not found: {label_id}", error_code="NOT_FOUND"
                        )
                        write_output(output)
                    else:
                        console.print(f"[red]Label not found: {rich_escape(label_id)}[/red]")
                    sys.exit(EXIT_USAGE_ERROR)

                # Check entities using this label
                entities = await service.list_entities_with_label(label_id)

                if not force:
                    console.print(f"Label: [cyan]{rich_escape(label.name)}[/cyan] ({rich_escape(label_id)})")
                    if entities:
                        console.print(
                            f"[yellow]Warning: {len(entities)} entities use this label[/yellow]"
                        )
                        for ent_id in entities[:5]:
                            console.print(f"  - {rich_escape(ent_id)}")
                        if len(entities) > 5:
                            console.print(f"  ... and {len(entities) - 5} more")

                    if not typer.confirm("Delete this label?"):
                        console.print("[dim]Cancelled[/dim]")
                        sys.exit(EXIT_SUCCESS)

                # Pass skip_check=True since we already verified label exists
                await service.delete_label(label_id, skip_check=True)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        data={"deleted": label_id, "affected_entities": len(entities)},
                    )
                    write_output(output)
                else:
                    console.print(f"[green]✓ Deleted label: {rich_escape(label_id)}[/green]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_delete(), command="labels delete"))


@app.command("assign")
def assign_label(
    entity_id: str = typer.Argument(..., help="Entity ID"),
    label_id: str = typer.Argument(..., help="Label ID to assign"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Assign a label to an entity."""
    setup_logging(debug)

    async def _assign() -> None:
        formatter = PorcelainFormatter("labels assign") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = LabelsService(client)
                status = await service.assign_label(entity_id, label_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        data={
                            "entity_id": entity_id,
                            "label_id": label_id,
                            "action": status,
                        },
                    )
                    write_output(output)
                else:
                    if status == "already_assigned":
                        console.print(
                            f"[yellow]Label {rich_escape(label_id)} already assigned to {rich_escape(entity_id)}[/yellow]"
                        )
                    else:
                        console.print(
                            f"[green]✓ Assigned {rich_escape(label_id)} to {rich_escape(entity_id)}[/green]"
                        )

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_assign(), command="labels assign"))


@app.command("remove")
def remove_label(
    entity_id: str = typer.Argument(..., help="Entity ID"),
    label_id: str = typer.Argument(..., help="Label ID to remove"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Remove a label from an entity."""
    setup_logging(debug)

    async def _remove() -> None:
        formatter = PorcelainFormatter("labels remove") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = LabelsService(client)
                status = await service.remove_label(entity_id, label_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        data={
                            "entity_id": entity_id,
                            "label_id": label_id,
                            "action": status,
                        },
                    )
                    write_output(output)
                else:
                    if status == "not_present":
                        console.print(
                            f"[yellow]Label {rich_escape(label_id)} not present on {rich_escape(entity_id)}[/yellow]"
                        )
                    else:
                        console.print(
                            f"[green]✓ Removed {rich_escape(label_id)} from {rich_escape(entity_id)}[/green]"
                        )

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_remove(), command="labels remove"))


@app.command("entities")
def list_entities(
    label_id: str = typer.Argument(..., help="Label ID"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all entities with a specific label."""
    setup_logging(debug)

    async def _entities() -> None:
        formatter = PorcelainFormatter("labels entities") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = LabelsService(client)

                # Verify label exists
                label = await service.get_label(label_id)
                if not label:
                    if porcelain:
                        assert formatter is not None
                        output = formatter.error(
                            f"Label not found: {label_id}", error_code="NOT_FOUND"
                        )
                        write_output(output)
                    else:
                        console.print(f"[red]Label not found: {rich_escape(label_id)}[/red]")
                    sys.exit(EXIT_USAGE_ERROR)

                entities = await service.list_entities_with_label(label_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        data={
                            "label_id": label_id,
                            "label_name": label.name,
                            "entities": entities,
                        },
                        metadata={"entity_count": len(entities)},
                    )
                    write_output(output)
                else:
                    console.print(
                        f"Entities with label [cyan]{rich_escape(label.name)}[/cyan] ({rich_escape(label_id)}):\n"
                    )
                    if not entities:
                        console.print("[yellow]No entities have this label[/yellow]")
                    else:
                        for ent_id in entities:
                            console.print(f"  - {rich_escape(ent_id)}")
                        console.print(f"\n[dim]Total: {len(entities)} entities[/dim]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_entities(), command="labels entities"))

"""CRUD commands for automations (create, update, delete)."""

import asyncio
import sys

import typer
from rich.console import Console

from ....common.cli_utils import run_async_command, setup_logging, write_output
from ....common.client import HAClient
from ....common.config import get_client_config
from ....common.exceptions import EXIT_HA_ERROR
from ....common.porcelain import PorcelainFormatter
from ..service import AutomationCRUD

console = Console()

REST_API_TROUBLESHOOTING = [
    "Add 'config:' to your Home Assistant configuration.yaml",
    "Restart Home Assistant after adding the config integration",
]


def _handle_rest_api_error(error_msg: str, formatter: PorcelainFormatter | None, porcelain: bool) -> None:
    """Handle REST API unavailable errors."""
    if porcelain and formatter:
        write_output(formatter.error(error_msg, error_code="REST_API_UNAVAILABLE",
            suggestions={"troubleshooting": REST_API_TROUBLESHOOTING + ["Alternatively, use the Home Assistant UI"]}))
    else:
        console.print(f"[red]Error:[/red] {error_msg}")
    sys.exit(EXIT_HA_ERROR)


def _handle_not_found_error(automation_id: str, formatter: PorcelainFormatter | None, porcelain: bool) -> None:
    """Handle automation not found errors."""
    if porcelain and formatter:
        write_output(formatter.error(f"Automation '{automation_id}' not found", error_code="NOT_FOUND",
            suggestions={"troubleshooting": ["Use 'ha-cli automations list' to verify automation exists",
                f"Check if '{automation_id}' is the correct ID"]}))
    else:
        console.print(f"[red]Error:[/red] Automation '{automation_id}' not found")
    sys.exit(EXIT_HA_ERROR)


def create(
    file_path: str = typer.Argument(..., help="Path to YAML/JSON automation file"),
    url: str | None = typer.Option(None, "--url", "-u"),
    token: str | None = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without creating"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Create a new automation from a YAML or JSON file.

    Requires the 'config' integration to be enabled in Home Assistant.
    """
    setup_logging(debug)

    async def _create() -> None:
        formatter = PorcelainFormatter("automations create") if porcelain else None
        try:
            url_final, token_final = get_client_config(url, token)
            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationCRUD(client)
                try:
                    numeric_id = await service.create_automation(file_path, dry_run=dry_run)
                    if porcelain:
                        assert formatter is not None
                        result_data: dict = {"created": not dry_run, "dry_run": dry_run, "file_path": file_path}
                        if not dry_run:
                            result_data.update({"numeric_id": numeric_id, "entity_id": f"automation.{numeric_id}"})
                        write_output(formatter.success(result_data,
                            {"action": "create", "file_path": file_path, "dry_run": dry_run},
                            {"common_actions": [f"Read: ha-cli automations read {numeric_id}" if not dry_run
                                else "Run without --dry-run to create", "ha-cli automations list --porcelain"]}))
                    else:
                        if dry_run:
                            console.print(f"[yellow]Dry run:[/yellow] Would create automation from {file_path}")
                        else:
                            console.print(f"[green]✓[/green] Created automation with ID: {numeric_id}")
                except Exception as e:
                    if "REST API not available" in str(e):
                        _handle_rest_api_error(str(e), formatter, porcelain)
                    raise
        except Exception as e:
            if porcelain and formatter:
                write_output(formatter.error(e))
                sys.exit(EXIT_HA_ERROR)
            raise

    asyncio.run(run_async_command(_create(), command="automations create"))


def update(
    automation_id: str = typer.Argument(..., help="Automation ID to update"),
    file_path: str = typer.Argument(..., help="Path to YAML/JSON automation file"),
    url: str | None = typer.Option(None, "--url", "-u"),
    token: str | None = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without updating"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Update an existing automation from a YAML or JSON file.

    Requires the 'config' integration to be enabled in Home Assistant.
    """
    setup_logging(debug)

    async def _update() -> None:
        formatter = PorcelainFormatter("automations update") if porcelain else None
        try:
            url_final, token_final = get_client_config(url, token)
            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationCRUD(client)
                try:
                    await service.update_automation(automation_id, file_path, dry_run=dry_run)
                    if porcelain:
                        assert formatter is not None
                        write_output(formatter.success(
                            {"updated": not dry_run, "dry_run": dry_run, "automation_id": automation_id, "file_path": file_path},
                            {"action": "update", "automation_id": automation_id, "dry_run": dry_run},
                            {"common_actions": [f"Read: ha-cli automations read {automation_id}", "ha-cli automations list --porcelain"]}))
                    else:
                        if dry_run:
                            console.print(f"[yellow]Dry run:[/yellow] Would update automation '{automation_id}' from {file_path}")
                        else:
                            console.print(f"[green]✓[/green] Updated automation '{automation_id}'")
                except Exception as e:
                    error_msg = str(e)
                    if "REST API not available" in error_msg:
                        _handle_rest_api_error(error_msg, formatter, porcelain)
                    elif "not found" in error_msg.lower():
                        _handle_not_found_error(automation_id, formatter, porcelain)
                    raise
        except Exception as e:
            if porcelain and formatter:
                write_output(formatter.error(e))
                sys.exit(EXIT_HA_ERROR)
            raise

    asyncio.run(run_async_command(_update(), command="automations update"))


def delete(
    automation_id: str = typer.Argument(..., help="Automation ID to delete"),
    url: str | None = typer.Option(None, "--url", "-u"),
    token: str | None = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without deleting"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Delete an automation.

    Requires the 'config' integration to be enabled in Home Assistant.
    """
    setup_logging(debug)

    async def _delete() -> None:
        formatter = PorcelainFormatter("automations delete") if porcelain else None
        try:
            url_final, token_final = get_client_config(url, token)
            # Confirmation prompt (unless --force or --porcelain or --dry-run)
            if not force and not porcelain and not dry_run:
                if not typer.confirm(f"Delete automation '{automation_id}'?"):
                    console.print("[yellow]Cancelled[/yellow]")
                    return
            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationCRUD(client)
                try:
                    await service.delete_automation(automation_id, dry_run=dry_run)
                    if porcelain:
                        assert formatter is not None
                        write_output(formatter.success(
                            {"deleted": not dry_run, "dry_run": dry_run, "automation_id": automation_id},
                            {"action": "delete", "automation_id": automation_id, "dry_run": dry_run},
                            {"common_actions": ["ha-cli automations list --porcelain"]}))
                    else:
                        if dry_run:
                            console.print(f"[yellow]Dry run:[/yellow] Would delete automation '{automation_id}'")
                        else:
                            console.print(f"[green]✓[/green] Deleted automation '{automation_id}'")
                except Exception as e:
                    error_msg = str(e)
                    if "REST API not available" in error_msg:
                        _handle_rest_api_error(error_msg, formatter, porcelain)
                    elif "not found" in error_msg.lower():
                        _handle_not_found_error(automation_id, formatter, porcelain)
                    raise
        except Exception as e:
            if porcelain and formatter:
                write_output(formatter.error(e))
                sys.exit(EXIT_HA_ERROR)
            raise

    asyncio.run(run_async_command(_delete(), command="automations delete"))

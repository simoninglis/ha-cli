"""List automations command."""

import asyncio
import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from ....common.cli_utils import run_async_command, setup_logging, write_output
from ....common.client import HAClient
from ....common.config import get_client_config
from ....common.exceptions import EXIT_HA_ERROR, EXIT_USAGE_ERROR
from ....common.porcelain import (
    PorcelainFormatter,
    create_automation_suggestions,
    create_home_assistant_metadata,
    create_workflow_recommendations,
    detect_advanced_issues,
    get_home_assistant_health,
)

console = Console()


def list_automations(
    url: str | None = typer.Option(None, "--url", "-u"),
    token: str | None = typer.Option(None, "--token", "-t", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"),
    timeout: int = typer.Option(10, "--timeout"),
    storage: str | None = typer.Option(None, "--storage"),
    json_output: bool = typer.Option(False, "--json"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
    websocket: bool = typer.Option(False, "--websocket"),
) -> None:
    """List all automations."""
    setup_logging(debug)

    # Validate mutually exclusive flags
    output_flags = sum([json_output, porcelain])
    if output_flags > 1:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)

    async def _list() -> None:
        formatter = PorcelainFormatter("automations list") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final, timeout) as client:
                from ..storage.automation_type_detector import (
                    AutomationTypeDetector,
                    StorageType,
                )
                from ..storage.unified_automation_service import UnifiedAutomationService

                service = UnifiedAutomationService(client)
                detector = AutomationTypeDetector()

                # Determine filter
                storage_filter = None
                filters_applied: list[str] = []
                if storage:
                    if storage.lower() == "ui":
                        storage_filter = StorageType.UI
                        filters_applied.append(f"storage={storage.lower()}")
                    elif storage.lower() == "file":
                        storage_filter = StorageType.FILE
                        filters_applied.append(f"storage={storage.lower()}")
                    elif storage.lower() != "all":
                        if porcelain:
                            assert formatter is not None
                            error_output = formatter.error(
                                f"Invalid storage filter: {storage}. Use 'ui', 'file', or 'all'",
                                error_code="INVALID_FILTER",
                                suggestions={
                                    "troubleshooting": [
                                        "Use --storage ui for UI-created automations",
                                        "Use --storage file for file-based automations",
                                        "Use --storage all or omit flag for all automations",
                                    ]
                                },
                            )
                            write_output(error_output)
                        else:
                            console.print(
                                f"[red]Error:[/red] Invalid storage filter: {storage}. "
                                "Use 'ui', 'file', or 'all'"
                            )
                        sys.exit(EXIT_USAGE_ERROR)

                automations = await service.list_all(use_websocket=websocket)

                # Filter by storage type if requested
                if storage_filter:
                    filtered = []
                    for automation in automations:
                        if detector.detect_storage_type(automation) == storage_filter:
                            filtered.append(automation)
                    automations = filtered

                # Count storage types
                ui_count = 0
                file_count = 0
                for automation in automations:
                    storage_type = detector.detect_storage_type(automation)
                    if storage_type == StorageType.UI:
                        ui_count += 1
                    else:
                        file_count += 1

                if porcelain:
                    assert formatter is not None
                    # Convert automations to porcelain-friendly format
                    data = []
                    for automation in automations:
                        storage_type = detector.detect_storage_type(automation)
                        automation_data = {
                            "id": automation.id,
                            "alias": automation.alias,
                            "mode": automation.mode,
                            "storage_type": "ui" if storage_type == StorageType.UI else "file",
                            "last_triggered": (
                                automation.last_triggered.isoformat()
                                if automation.last_triggered
                                else None
                            ),
                            "enabled": getattr(automation, "enabled", True),
                            "entity_id": f"automation.{automation.id}" if automation.id else None,
                        }
                        data.append(automation_data)

                    # Get Home Assistant health information
                    health_info = await get_home_assistant_health(client)

                    # Create metadata
                    metadata = {
                        "total_count": len(automations),
                        "filtered_count": len(automations),
                        "filters_applied": filters_applied,
                        "storage_breakdown": {"ui": ui_count, "file": file_count},
                        "home_assistant": create_home_assistant_metadata(
                            url_final,
                            "websocket" if websocket else "rest",
                            health_info=health_info,
                        ),
                    }

                    # Create suggestions
                    suggestions = create_automation_suggestions(
                        len(automations), {"ui": ui_count, "file": file_count}
                    )

                    # Add workflow recommendations
                    workflow_recommendations = create_workflow_recommendations(
                        "automations list",
                        {
                            "total_count": len(automations),
                            "storage_breakdown": {"ui": ui_count, "file": file_count},
                        },
                        health_info,
                    )
                    suggestions.update(workflow_recommendations)

                    # Detect advanced issues
                    advanced_issues = detect_advanced_issues(
                        "automations list", data, metadata, health_info
                    )
                    if advanced_issues:
                        suggestions.setdefault("detected_issues", []).extend(advanced_issues)

                    porcelain_output = formatter.success(data, metadata, suggestions)
                    write_output(porcelain_output)

                elif json_output:
                    data = [automation.to_json_dict() for automation in automations]
                    json_str = json.dumps(data, indent=2)
                    write_output(json_str)

                else:
                    # Original table output
                    if not automations:
                        console.print("No automations found")
                        return

                    # Create table
                    table = Table(
                        title=(
                            f"Home Assistant Automations"
                            f"{f' ({storage})' if storage and storage != 'all' else ''}"
                        )
                    )
                    table.add_column("ID", style="cyan")
                    table.add_column("Alias", style="white")
                    table.add_column("Mode", style="yellow")
                    table.add_column("Storage", style="magenta")
                    table.add_column("Last Triggered", style="green")

                    for automation in automations:
                        last_triggered = "Never"
                        if automation.last_triggered:
                            last_triggered = automation.last_triggered.strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )

                        # Detect storage type
                        storage_type = detector.detect_storage_type(automation)
                        storage_display = "UI" if storage_type == StorageType.UI else "File"

                        table.add_row(
                            automation.id or "N/A",
                            automation.alias,
                            automation.mode,
                            storage_display,
                            last_triggered,
                        )

                    console.print(table)
                    console.print(f"\nTotal: {len(automations)} automations")
                    if not storage_filter:
                        console.print(f"  UI-style: {ui_count}")
                        console.print(f"  File-based: {file_count}")

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                write_output(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_list(), command="automations list"))

"""Automation CLI commands for ha-cli."""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.cli_utils import run_async_command, setup_logging
from ...common.exceptions import (
    EXIT_HA_ERROR,
    EXIT_USAGE_ERROR,
    HAAutomationError,
)
from ...common.porcelain import (
    PorcelainFormatter,
    create_automation_suggestions,
    create_home_assistant_metadata,
    get_home_assistant_health,
    analyze_automation_complexity,
    extract_entity_references,
    create_workflow_recommendations,
    detect_advanced_issues,
)
from .service import AutomationCRUD, AutomationWS

# Initialize Typer app
app = typer.Typer(
    name="automations",
    help="Manage Home Assistant automations",
    add_completion=True,
)

# Console for rich output
console = Console()

# Logging setup
logger = logging.getLogger(__name__)


@app.command()
def list(
    url: Optional[str] = typer.Option(None, "--url", "-u"),
    token: Optional[str] = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    storage: Optional[str] = typer.Option(None, "--storage"),
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
                from .storage.unified_automation_service import UnifiedAutomationService
                from .storage.automation_type_detector import AutomationTypeDetector, StorageType
                
                service = UnifiedAutomationService(client)
                detector = AutomationTypeDetector()
                
                # Determine filter
                storage_filter = None
                filters_applied = []
                if storage:
                    if storage.lower() == "ui":
                        storage_filter = StorageType.UI
                        filters_applied.append(f"storage={storage.lower()}")
                    elif storage.lower() == "file":
                        storage_filter = StorageType.FILE
                        filters_applied.append(f"storage={storage.lower()}")
                    elif storage.lower() != "all":
                        if porcelain:
                            error_output = formatter.error(
                                f"Invalid storage filter: {storage}. Use 'ui', 'file', or 'all'",
                                error_code="INVALID_FILTER",
                                suggestions={
                                    "troubleshooting": [
                                        "Use --storage ui for UI-created automations",
                                        "Use --storage file for file-based automations", 
                                        "Use --storage all or omit flag for all automations"
                                    ]
                                }
                            )
                            sys.stdout.write(error_output)
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        else:
                            console.print(f"[red]Error:[/red] Invalid storage filter: {storage}. Use 'ui', 'file', or 'all'")
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
                    # Convert automations to porcelain-friendly format
                    data = []
                    for automation in automations:
                        storage_type = detector.detect_storage_type(automation)
                        automation_data = {
                            "id": automation.id,
                            "alias": automation.alias,
                            "mode": automation.mode,
                            "storage_type": "ui" if storage_type == StorageType.UI else "file",
                            "last_triggered": automation.last_triggered.isoformat() if automation.last_triggered else None,
                            "enabled": getattr(automation, 'enabled', True),
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
                        "storage_breakdown": {
                            "ui": ui_count,
                            "file": file_count
                        },
                        "home_assistant": create_home_assistant_metadata(
                            url_final,
                            "websocket" if websocket else "rest",
                            health_info=health_info
                        )
                    }
                    
                    # Create suggestions
                    suggestions = create_automation_suggestions(len(automations), {"ui": ui_count, "file": file_count})
                    
                    # Add workflow recommendations
                    workflow_recommendations = create_workflow_recommendations(
                        "automations list",
                        {"total_count": len(automations), "storage_breakdown": {"ui": ui_count, "file": file_count}},
                        health_info
                    )
                    suggestions.update(workflow_recommendations)
                    
                    # Detect advanced issues
                    advanced_issues = detect_advanced_issues("automations list", data, metadata, health_info)
                    if advanced_issues:
                        suggestions.setdefault("detected_issues", []).extend(advanced_issues)
                    
                    porcelain_output = formatter.success(data, metadata, suggestions)
                    sys.stdout.write(porcelain_output)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    
                elif json_output:
                    data = [automation.to_json_dict() for automation in automations]
                    json_str = json.dumps(data, indent=2)
                    sys.stdout.write(json_str)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    
                else:
                    # Original table output
                    if not automations:
                        console.print("No automations found")
                        return
                    
                    # Create table
                    table = Table(title=f"Home Assistant Automations{f' ({storage})' if storage and storage != 'all' else ''}")
                    table.add_column("ID", style="cyan")
                    table.add_column("Alias", style="white")
                    table.add_column("Mode", style="yellow")
                    table.add_column("Storage", style="magenta")
                    table.add_column("Last Triggered", style="green")
                    
                    for automation in automations:
                        last_triggered = "Never"
                        if automation.last_triggered:
                            last_triggered = automation.last_triggered.strftime("%Y-%m-%d %H:%M:%S")
                        
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
                sys.stdout.write(error_output)
                sys.stdout.write('\n')
                sys.stdout.flush()
                sys.exit(EXIT_HA_ERROR)
            else:
                raise
    
    asyncio.run(run_async_command(_list()))


@app.command()
def read(
    automation_id: str = typer.Argument(..., help="Automation ID to read"),
    url: Optional[str] = typer.Option(None, "--url", "-u"),
    token: Optional[str] = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    json_output: bool = typer.Option(False, "--json"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Read a specific automation by ID."""
    setup_logging(debug)
    
    # Validate mutually exclusive flags
    output_flags = sum([json_output, porcelain])
    if output_flags > 1:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _read() -> None:
        formatter = PorcelainFormatter("automations read") if porcelain else None
        
        try:
            url_final, token_final = get_client_config(url, token)
            
            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationCRUD(client)
                
                try:
                    automation = await service.get_automation(automation_id)
                except Exception as e:
                    if "404" in str(e) or "not found" in str(e).lower():
                        if porcelain:
                            error_output = formatter.error(
                                f"Automation '{automation_id}' not found",
                                error_code="NOT_FOUND",
                                details={"automation_id": automation_id},
                                suggestions={
                                    "troubleshooting": [
                                        f"Verify automation ID '{automation_id}' exists",
                                        "Use 'ha-cli automations list --porcelain' to see all automations",
                                        "Check if automation was recently deleted",
                                        "Ensure you have permission to access this automation"
                                    ],
                                    "related_commands": [
                                        "ha-cli automations list --porcelain",
                                        f"ha-cli automations list --storage file | grep {automation_id}"
                                    ]
                                }
                            )
                            sys.stdout.write(error_output)
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        else:
                            console.print(f"[red]Error:[/red] Automation '{automation_id}' not found")
                        sys.exit(EXIT_HA_ERROR)
                    else:
                        raise
                
                if porcelain:
                    # Convert automation to porcelain-friendly format
                    automation_data = {
                        "id": automation.id,
                        "alias": automation.alias,
                        "description": automation.description,
                        "mode": automation.mode,
                        "max": automation.max,
                        "enabled": getattr(automation, 'enabled', True),
                        "entity_id": f"automation.{automation.id}" if automation.id else None,
                        "trigger": automation.trigger,
                        "condition": automation.condition,
                        "action": automation.action,
                        "variables": getattr(automation, 'variables', {}),
                        "trace": getattr(automation, 'trace', {}),
                    }
                    
                    # Analyze automation complexity
                    complexity_analysis = analyze_automation_complexity(automation_data)
                    
                    # Extract entity dependencies
                    entity_analysis = extract_entity_references(automation_data)
                    
                    # Get Home Assistant health information
                    health_info = await get_home_assistant_health(client)
                    
                    # Create metadata
                    metadata = {
                        "automation_id": automation_id,
                        "configuration_size": {
                            "triggers": len(automation.trigger) if automation.trigger else 0,
                            "conditions": len(automation.condition) if automation.condition else 0,
                            "actions": len(automation.action) if automation.action else 0,
                        },
                        "complexity": complexity_analysis,
                        "entity_dependencies": {
                            "total_entities": len(entity_analysis["referenced"]),
                            "by_domain": entity_analysis["by_domain"],
                            "by_section": {
                                "triggers": len(entity_analysis["triggers"]),
                                "conditions": len(entity_analysis["conditions"]),
                                "actions": len(entity_analysis["actions"])
                            }
                        },
                        "home_assistant": create_home_assistant_metadata(
                            url_final,
                            "rest",  # get_automation uses REST API
                            health_info=health_info
                        )
                    }
                    
                    # Create enhanced suggestions based on analysis
                    suggestions = {
                        "common_actions": [
                            f"Enable: ha-cli automations enable {automation_id}",
                            f"Disable: ha-cli automations disable {automation_id}",
                            f"Update: ha-cli automations update {automation_id} --file <yaml-file>",
                            f"Delete: ha-cli automations delete {automation_id}",
                        ],
                        "related_commands": [
                            "ha-cli automations list --porcelain",
                            "ha-cli automations monitor --porcelain",
                        ],
                        "detected_issues": [],
                        "optimizations": [],
                        "entity_insights": []
                    }
                    
                    # Add complexity-based optimizations
                    if complexity_analysis["optimizations"]:
                        suggestions["optimizations"].extend(complexity_analysis["optimizations"])
                    
                    # Analyze automation for potential issues
                    if not automation.trigger:
                        suggestions["detected_issues"].append("No triggers defined - automation will never execute")
                    if not automation.action:
                        suggestions["detected_issues"].append("No actions defined - automation will do nothing")
                    if automation.mode in ["queued", "parallel"] and not automation.max:
                        suggestions["detected_issues"].append(f"Mode '{automation.mode}' should define 'max' parameter")
                    
                    # Add complexity warnings
                    if complexity_analysis["level"] == "very_complex":
                        suggestions["detected_issues"].append(f"Very complex automation (score: {complexity_analysis['score']}) may be hard to maintain")
                    elif complexity_analysis["level"] == "complex":
                        suggestions["detected_issues"].append(f"Complex automation (score: {complexity_analysis['score']}) consider reviewing")
                    
                    # Add entity-based insights
                    total_entities = len(entity_analysis["referenced"])
                    if total_entities > 10:
                        suggestions["entity_insights"].append(f"References many entities ({total_entities}) - consider impact on system performance")
                    
                    if len(entity_analysis["by_domain"]) > 5:
                        suggestions["entity_insights"].append(f"Spans multiple domains ({len(entity_analysis['by_domain'])}) - ensure proper integration testing")
                    
                    # Add domain-specific insights
                    for domain, entities in entity_analysis["by_domain"].items():
                        if domain == "sensor" and len(entities) > 5:
                            suggestions["entity_insights"].append(f"Uses many sensors ({len(entities)}) - monitor for state change frequency")
                        elif domain == "device_tracker" and len(entities) > 0:
                            suggestions["entity_insights"].append("Uses device tracking - consider privacy and battery impact")
                        elif domain == "camera" and len(entities) > 0:
                            suggestions["entity_insights"].append("Uses cameras - ensure adequate bandwidth and storage")
                    
                    # Add related commands based on entities
                    if entity_analysis["referenced"]:
                        # Find dashboards that might contain these entities
                        suggestions["related_commands"].append("ha-cli dashboards list --porcelain")
                        suggestions["related_commands"].append("Check entity states with MCP tools")
                    
                    # Add complexity-specific suggestions
                    if complexity_analysis["level"] in ["complex", "very_complex"]:
                        suggestions["common_actions"].insert(1, "Review automation logic for optimization opportunities")
                        suggestions["common_actions"].insert(2, "Consider documenting complex logic in description")
                    
                    # Add workflow recommendations
                    workflow_recommendations = create_workflow_recommendations(
                        "automations read",
                        {
                            "automation_id": automation_id,
                            "complexity": complexity_analysis,
                            "entity_dependencies": {
                                "total_entities": len(entity_analysis["referenced"]),
                                "by_domain": entity_analysis["by_domain"]
                            }
                        },
                        health_info
                    )
                    suggestions.update(workflow_recommendations)
                    
                    # Detect advanced issues
                    advanced_issues = detect_advanced_issues("automations read", automation_data, metadata, health_info)
                    if advanced_issues:
                        suggestions.setdefault("detected_issues", []).extend(advanced_issues)
                    
                    porcelain_output = formatter.success(automation_data, metadata, suggestions)
                    sys.stdout.write(porcelain_output)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    
                elif json_output:
                    json_str = json.dumps(automation.to_json_dict(), indent=2)
                    sys.stdout.write(json_str)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    
                else:
                    # Original human-readable output
                    console.print(f"[bold cyan]Automation:[/bold cyan] {automation.alias}")
                    console.print(f"[bold]ID:[/bold] {automation.id}")
                    if automation.description:
                        console.print(f"[bold]Description:[/bold] {automation.description}")
                    console.print(f"[bold]Mode:[/bold] {automation.mode}")
                    if automation.max:
                        console.print(f"[bold]Max:[/bold] {automation.max}")
                    
                    console.print(f"\n[bold yellow]Triggers ({len(automation.trigger) if automation.trigger else 0}):[/bold yellow]")
                    if automation.trigger:
                        for i, trigger in enumerate(automation.trigger, 1):
                            console.print(f"  {i}. {trigger.get('platform', 'Unknown')} trigger")
                    else:
                        console.print("  None")
                    
                    console.print(f"\n[bold yellow]Conditions ({len(automation.condition) if automation.condition else 0}):[/bold yellow]")
                    if automation.condition:
                        for i, condition in enumerate(automation.condition, 1):
                            console.print(f"  {i}. {condition.get('condition', 'Unknown')} condition")
                    else:
                        console.print("  None")
                    
                    console.print(f"\n[bold yellow]Actions ({len(automation.action) if automation.action else 0}):[/bold yellow]")
                    if automation.action:
                        for i, action in enumerate(automation.action, 1):
                            service_name = action.get('service', action.get('action', 'Unknown'))
                            console.print(f"  {i}. {service_name}")
                    else:
                        console.print("  None")
                        
        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                sys.stdout.write(error_output)
                sys.stdout.write('\n')
                sys.stdout.flush()
                sys.exit(EXIT_HA_ERROR)
            else:
                raise
    
    asyncio.run(run_async_command(_read()))


@app.command()
def version() -> None:
    """Show version information."""
    from ... import __version__
    
    console.print(f"ha-cli automations version {__version__}")


@app.command()
def enable(
    automation_id: str = typer.Argument(..., help="Automation ID to enable"),
    url: Optional[str] = typer.Option(None, "--url", "-u"),
    token: Optional[str] = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Enable an automation."""
    setup_logging(debug)

    async def _enable() -> None:
        formatter = PorcelainFormatter("automations enable") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationWS(client)
                await service.enable_automation(automation_id)

                if porcelain:
                    porcelain_output = formatter.success(
                        {"automation_id": automation_id, "state": "enabled"},
                        {"action": "enable", "automation_id": automation_id},
                        {"common_actions": [
                            f"Disable: ha-cli automations disable {automation_id}",
                            f"Read: ha-cli automations read {automation_id}",
                        ]}
                    )
                    sys.stdout.write(porcelain_output)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                else:
                    console.print(f"[green]✓[/green] Automation '{automation_id}' enabled")

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                sys.stdout.write(error_output)
                sys.stdout.write('\n')
                sys.stdout.flush()
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_enable()))


@app.command()
def disable(
    automation_id: str = typer.Argument(..., help="Automation ID to disable"),
    url: Optional[str] = typer.Option(None, "--url", "-u"),
    token: Optional[str] = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Disable an automation."""
    setup_logging(debug)

    async def _disable() -> None:
        formatter = PorcelainFormatter("automations disable") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationWS(client)
                await service.disable_automation(automation_id)

                if porcelain:
                    porcelain_output = formatter.success(
                        {"automation_id": automation_id, "state": "disabled"},
                        {"action": "disable", "automation_id": automation_id},
                        {"common_actions": [
                            f"Enable: ha-cli automations enable {automation_id}",
                            f"Read: ha-cli automations read {automation_id}",
                        ]}
                    )
                    sys.stdout.write(porcelain_output)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                else:
                    console.print(f"[yellow]○[/yellow] Automation '{automation_id}' disabled")

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                sys.stdout.write(error_output)
                sys.stdout.write('\n')
                sys.stdout.flush()
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_disable()))


@app.command()
def reload(
    url: Optional[str] = typer.Option(None, "--url", "-u"),
    token: Optional[str] = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Reload all automations from configuration."""
    setup_logging(debug)

    async def _reload() -> None:
        formatter = PorcelainFormatter("automations reload") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationWS(client)
                await service.reload_automations()

                if porcelain:
                    porcelain_output = formatter.success(
                        {"reloaded": True},
                        {"action": "reload"},
                        {"common_actions": [
                            "ha-cli automations list --porcelain",
                        ]}
                    )
                    sys.stdout.write(porcelain_output)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                else:
                    console.print("[green]✓[/green] All automations reloaded")

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                sys.stdout.write(error_output)
                sys.stdout.write('\n')
                sys.stdout.flush()
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_reload()))


@app.command()
def create(
    file_path: str = typer.Argument(..., help="Path to YAML/JSON automation file"),
    url: Optional[str] = typer.Option(None, "--url", "-u"),
    token: Optional[str] = typer.Option(None, "--token", "-t"),
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
                        result_data = {
                            "created": not dry_run,
                            "dry_run": dry_run,
                            "file_path": file_path,
                        }
                        if not dry_run:
                            result_data["numeric_id"] = numeric_id
                            result_data["entity_id"] = f"automation.{numeric_id}"

                        porcelain_output = formatter.success(
                            result_data,
                            {"action": "create", "file_path": file_path, "dry_run": dry_run},
                            {"common_actions": [
                                f"Read: ha-cli automations read {numeric_id}" if not dry_run else "Run without --dry-run to create",
                                "ha-cli automations list --porcelain",
                            ]}
                        )
                        sys.stdout.write(porcelain_output)
                        sys.stdout.write('\n')
                        sys.stdout.flush()
                    else:
                        if dry_run:
                            console.print(f"[yellow]Dry run:[/yellow] Would create automation from {file_path}")
                        else:
                            console.print(f"[green]✓[/green] Created automation with ID: {numeric_id}")

                except Exception as e:
                    error_msg = str(e)
                    if "REST API not available" in error_msg:
                        if porcelain:
                            error_output = formatter.error(
                                error_msg,
                                error_code="REST_API_UNAVAILABLE",
                                suggestions={
                                    "troubleshooting": [
                                        "Add 'config:' to your Home Assistant configuration.yaml",
                                        "Restart Home Assistant after adding the config integration",
                                        "Alternatively, create automations via the Home Assistant UI",
                                    ]
                                }
                            )
                            sys.stdout.write(error_output)
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        else:
                            console.print(f"[red]Error:[/red] {error_msg}")
                        sys.exit(EXIT_HA_ERROR)
                    raise

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                sys.stdout.write(error_output)
                sys.stdout.write('\n')
                sys.stdout.flush()
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_create()))


@app.command()
def update(
    automation_id: str = typer.Argument(..., help="Automation ID to update"),
    file_path: str = typer.Argument(..., help="Path to YAML/JSON automation file"),
    url: Optional[str] = typer.Option(None, "--url", "-u"),
    token: Optional[str] = typer.Option(None, "--token", "-t"),
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
                        porcelain_output = formatter.success(
                            {
                                "updated": not dry_run,
                                "dry_run": dry_run,
                                "automation_id": automation_id,
                                "file_path": file_path,
                            },
                            {"action": "update", "automation_id": automation_id, "dry_run": dry_run},
                            {"common_actions": [
                                f"Read: ha-cli automations read {automation_id}",
                                "ha-cli automations list --porcelain",
                            ]}
                        )
                        sys.stdout.write(porcelain_output)
                        sys.stdout.write('\n')
                        sys.stdout.flush()
                    else:
                        if dry_run:
                            console.print(f"[yellow]Dry run:[/yellow] Would update automation '{automation_id}' from {file_path}")
                        else:
                            console.print(f"[green]✓[/green] Updated automation '{automation_id}'")

                except Exception as e:
                    error_msg = str(e)
                    if "REST API not available" in error_msg:
                        if porcelain:
                            error_output = formatter.error(
                                error_msg,
                                error_code="REST_API_UNAVAILABLE",
                                suggestions={
                                    "troubleshooting": [
                                        "Add 'config:' to your Home Assistant configuration.yaml",
                                        "Restart Home Assistant after adding the config integration",
                                    ]
                                }
                            )
                            sys.stdout.write(error_output)
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        else:
                            console.print(f"[red]Error:[/red] {error_msg}")
                        sys.exit(EXIT_HA_ERROR)
                    elif "not found" in error_msg.lower():
                        if porcelain:
                            error_output = formatter.error(
                                f"Automation '{automation_id}' not found",
                                error_code="NOT_FOUND",
                                suggestions={
                                    "troubleshooting": [
                                        "Use 'ha-cli automations list' to verify automation exists",
                                        f"Check if '{automation_id}' is the correct ID",
                                    ]
                                }
                            )
                            sys.stdout.write(error_output)
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        else:
                            console.print(f"[red]Error:[/red] Automation '{automation_id}' not found")
                        sys.exit(EXIT_HA_ERROR)
                    raise

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                sys.stdout.write(error_output)
                sys.stdout.write('\n')
                sys.stdout.flush()
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_update()))


@app.command()
def delete(
    automation_id: str = typer.Argument(..., help="Automation ID to delete"),
    url: Optional[str] = typer.Option(None, "--url", "-u"),
    token: Optional[str] = typer.Option(None, "--token", "-t"),
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
                confirm = typer.confirm(f"Delete automation '{automation_id}'?")
                if not confirm:
                    console.print("[yellow]Cancelled[/yellow]")
                    return

            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationCRUD(client)

                try:
                    await service.delete_automation(automation_id, dry_run=dry_run)

                    if porcelain:
                        porcelain_output = formatter.success(
                            {
                                "deleted": not dry_run,
                                "dry_run": dry_run,
                                "automation_id": automation_id,
                            },
                            {"action": "delete", "automation_id": automation_id, "dry_run": dry_run},
                            {"common_actions": [
                                "ha-cli automations list --porcelain",
                            ]}
                        )
                        sys.stdout.write(porcelain_output)
                        sys.stdout.write('\n')
                        sys.stdout.flush()
                    else:
                        if dry_run:
                            console.print(f"[yellow]Dry run:[/yellow] Would delete automation '{automation_id}'")
                        else:
                            console.print(f"[green]✓[/green] Deleted automation '{automation_id}'")

                except Exception as e:
                    error_msg = str(e)
                    if "REST API not available" in error_msg:
                        if porcelain:
                            error_output = formatter.error(
                                error_msg,
                                error_code="REST_API_UNAVAILABLE",
                                suggestions={
                                    "troubleshooting": [
                                        "Add 'config:' to your Home Assistant configuration.yaml",
                                        "Restart Home Assistant after adding the config integration",
                                    ]
                                }
                            )
                            sys.stdout.write(error_output)
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        else:
                            console.print(f"[red]Error:[/red] {error_msg}")
                        sys.exit(EXIT_HA_ERROR)
                    elif "not found" in error_msg.lower():
                        if porcelain:
                            error_output = formatter.error(
                                f"Automation '{automation_id}' not found",
                                error_code="NOT_FOUND",
                                suggestions={
                                    "troubleshooting": [
                                        "Use 'ha-cli automations list' to verify automation exists",
                                        f"Check if '{automation_id}' is the correct ID",
                                    ]
                                }
                            )
                            sys.stdout.write(error_output)
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        else:
                            console.print(f"[red]Error:[/red] Automation '{automation_id}' not found")
                        sys.exit(EXIT_HA_ERROR)
                    raise

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                sys.stdout.write(error_output)
                sys.stdout.write('\n')
                sys.stdout.flush()
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_delete()))
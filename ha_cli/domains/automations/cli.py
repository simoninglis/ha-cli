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
from ...common.exceptions import (
    EXIT_HA_ERROR,
    EXIT_NETWORK_ERROR,
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


def setup_logging(debug: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )




async def run_async_command(coro):
    """Run async command and handle exceptions."""
    try:
        return await coro
    except HAAutomationError as e:
        console.print(f"[red]Error:[/red] {e.message}")
        if e.details:
            logger.debug(f"Error details: {e.details}")
        sys.exit(EXIT_HA_ERROR)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.exception("Unexpected error")
        sys.exit(EXIT_NETWORK_ERROR)


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
    
    async def _list():
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
                            print(error_output)
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
                    print(porcelain_output)
                    
                elif json_output:
                    data = [automation.to_json_dict() for automation in automations]
                    print(json.dumps(data, indent=2))
                    
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
                print(error_output)
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
    
    async def _read():
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
                            print(error_output)
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
                    print(porcelain_output)
                    
                elif json_output:
                    print(json.dumps(automation.to_json_dict(), indent=2))
                    
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
                print(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise
    
    asyncio.run(run_async_command(_read()))


@app.command()
def version() -> None:
    """Show version information."""
    from ... import __version__
    
    console.print(f"ha-cli automations version {__version__}")


# For now, just implement the most essential commands
# More commands can be added by importing and adapting from the original CLI
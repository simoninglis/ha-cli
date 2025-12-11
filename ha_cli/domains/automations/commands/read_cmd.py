"""Read automation command."""

import asyncio
import json
import sys

import typer
from rich.console import Console

from ....common.cli_utils import run_async_command, setup_logging, write_output
from ....common.client import HAClient
from ....common.config import get_client_config
from ....common.exceptions import EXIT_HA_ERROR, EXIT_USAGE_ERROR
from ....common.porcelain import (
    PorcelainFormatter,
    analyze_automation_complexity,
    create_home_assistant_metadata,
    create_workflow_recommendations,
    detect_advanced_issues,
    extract_entity_references,
    get_home_assistant_health,
)
from ..service import AutomationCRUD

console = Console()


def read(
    automation_id: str = typer.Argument(..., help="Automation ID to read"),
    url: str | None = typer.Option(None, "--url", "-u"),
    token: str | None = typer.Option(None, "--token", "-t"),
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
                            assert formatter is not None
                            error_output = formatter.error(
                                f"Automation '{automation_id}' not found",
                                error_code="NOT_FOUND",
                                details={"automation_id": automation_id},
                                suggestions={
                                    "troubleshooting": [
                                        f"Verify automation ID '{automation_id}' exists",
                                        "Use 'ha-cli automations list --porcelain' to see all automations",
                                        "Check if automation was recently deleted",
                                        "Ensure you have permission to access this automation",
                                    ],
                                    "related_commands": [
                                        "ha-cli automations list --porcelain",
                                        f"ha-cli automations list --storage file | grep {automation_id}",
                                    ],
                                },
                            )
                            write_output(error_output)
                        else:
                            console.print(
                                f"[red]Error:[/red] Automation '{automation_id}' not found"
                            )
                        sys.exit(EXIT_HA_ERROR)
                    else:
                        raise

                if porcelain:
                    assert formatter is not None
                    # Convert automation to porcelain-friendly format
                    automation_data = {
                        "id": automation.id,
                        "alias": automation.alias,
                        "description": automation.description,
                        "mode": automation.mode,
                        "max": automation.max,
                        "enabled": getattr(automation, "enabled", True),
                        "entity_id": f"automation.{automation.id}" if automation.id else None,
                        "trigger": automation.trigger,
                        "condition": automation.condition,
                        "action": automation.action,
                        "variables": getattr(automation, "variables", {}),
                        "trace": getattr(automation, "trace", {}),
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
                            "conditions": (
                                len(automation.condition) if automation.condition else 0
                            ),
                            "actions": len(automation.action) if automation.action else 0,
                        },
                        "complexity": complexity_analysis,
                        "entity_dependencies": {
                            "total_entities": len(entity_analysis["referenced"]),
                            "by_domain": entity_analysis["by_domain"],
                            "by_section": {
                                "triggers": len(entity_analysis["triggers"]),
                                "conditions": len(entity_analysis["conditions"]),
                                "actions": len(entity_analysis["actions"]),
                            },
                        },
                        "home_assistant": create_home_assistant_metadata(
                            url_final,
                            "rest",  # get_automation uses REST API
                            health_info=health_info,
                        ),
                    }

                    # Create enhanced suggestions based on analysis
                    suggestions = _build_read_suggestions(
                        automation_id, automation, automation_data, complexity_analysis,
                        entity_analysis, health_info
                    )

                    porcelain_output = formatter.success(automation_data, metadata, suggestions)
                    write_output(porcelain_output)

                elif json_output:
                    json_str = json.dumps(automation.to_json_dict(), indent=2)
                    write_output(json_str)

                else:
                    # Original human-readable output
                    _print_automation_details(automation)

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                write_output(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_read()))


def _build_read_suggestions(
    automation_id: str, automation: object, automation_data: dict,
    complexity_analysis: dict, entity_analysis: dict, health_info: dict | None,
) -> dict:
    """Build suggestions for the read command output."""
    suggestions: dict = {
        "common_actions": [
            f"Enable: ha-cli automations enable {automation_id}",
            f"Disable: ha-cli automations disable {automation_id}",
            f"Update: ha-cli automations update {automation_id} --file <yaml-file>",
            f"Delete: ha-cli automations delete {automation_id}",
        ],
        "related_commands": ["ha-cli automations list --porcelain", "ha-cli automations monitor --porcelain"],
        "detected_issues": [],
        "optimizations": complexity_analysis.get("optimizations", []).copy(),
        "entity_insights": [],
    }
    # Check automation config issues
    trigger, action = getattr(automation, "trigger", None), getattr(automation, "action", None)
    mode, max_val = getattr(automation, "mode", None), getattr(automation, "max", None)
    if not trigger:
        suggestions["detected_issues"].append("No triggers defined - automation will never execute")
    if not action:
        suggestions["detected_issues"].append("No actions defined - automation will do nothing")
    if mode in ["queued", "parallel"] and not max_val:
        suggestions["detected_issues"].append(f"Mode '{mode}' should define 'max' parameter")
    # Complexity warnings
    level, score = complexity_analysis.get("level"), complexity_analysis.get("score", 0)
    if level == "very_complex":
        suggestions["detected_issues"].append(f"Very complex automation (score: {score}) may be hard to maintain")
    elif level == "complex":
        suggestions["detected_issues"].append(f"Complex automation (score: {score}) consider reviewing")
    # Entity insights
    total_entities = len(entity_analysis.get("referenced", []))
    by_domain = entity_analysis.get("by_domain", {})
    if total_entities > 10:
        suggestions["entity_insights"].append(f"References many entities ({total_entities}) - consider impact")
    if len(by_domain) > 5:
        suggestions["entity_insights"].append(f"Spans multiple domains ({len(by_domain)}) - ensure proper testing")
    for domain, entities in by_domain.items():
        if domain == "sensor" and len(entities) > 5:
            suggestions["entity_insights"].append(f"Uses many sensors ({len(entities)}) - monitor state frequency")
        elif domain == "device_tracker" and entities:
            suggestions["entity_insights"].append("Uses device tracking - consider privacy and battery impact")
        elif domain == "camera" and entities:
            suggestions["entity_insights"].append("Uses cameras - ensure adequate bandwidth and storage")
    if entity_analysis.get("referenced"):
        suggestions["related_commands"].extend(["ha-cli dashboards list --porcelain", "Check entity states with MCP"])
    if level in ["complex", "very_complex"]:
        suggestions["common_actions"].insert(1, "Review automation logic for optimization opportunities")
        suggestions["common_actions"].insert(2, "Consider documenting complex logic in description")
    # Workflow recommendations and advanced issues
    suggestions.update(create_workflow_recommendations(
        "automations read",
        {"automation_id": automation_id, "complexity": complexity_analysis,
         "entity_dependencies": {"total_entities": total_entities, "by_domain": by_domain}},
        health_info,
    ))
    advanced_issues = detect_advanced_issues("automations read", automation_data,
        {"automation_id": automation_id, "complexity": complexity_analysis}, health_info)
    if advanced_issues:
        suggestions["detected_issues"].extend(advanced_issues)
    return suggestions


def _print_automation_details(automation: object) -> None:
    """Print automation details in human-readable format."""
    alias = getattr(automation, "alias", "Unknown")
    auto_id = getattr(automation, "id", "Unknown")
    description = getattr(automation, "description", None)
    mode = getattr(automation, "mode", "Unknown")
    max_val = getattr(automation, "max", None)
    trigger = getattr(automation, "trigger", None)
    condition = getattr(automation, "condition", None)
    action = getattr(automation, "action", None)

    console.print(f"[bold cyan]Automation:[/bold cyan] {alias}")
    console.print(f"[bold]ID:[/bold] {auto_id}")
    if description:
        console.print(f"[bold]Description:[/bold] {description}")
    console.print(f"[bold]Mode:[/bold] {mode}")
    if max_val:
        console.print(f"[bold]Max:[/bold] {max_val}")

    trigger_count = len(trigger) if trigger else 0
    console.print(f"\n[bold yellow]Triggers ({trigger_count}):[/bold yellow]")
    if trigger:
        for i, trig in enumerate(trigger, 1):
            console.print(f"  {i}. {trig.get('platform', 'Unknown')} trigger")
    else:
        console.print("  None")

    condition_count = len(condition) if condition else 0
    console.print(f"\n[bold yellow]Conditions ({condition_count}):[/bold yellow]")
    if condition:
        for i, cond in enumerate(condition, 1):
            console.print(f"  {i}. {cond.get('condition', 'Unknown')} condition")
    else:
        console.print("  None")

    action_count = len(action) if action else 0
    console.print(f"\n[bold yellow]Actions ({action_count}):[/bold yellow]")
    if action:
        for i, act in enumerate(action, 1):
            service_name = act.get("service", act.get("action", "Unknown"))
            console.print(f"  {i}. {service_name}")
    else:
        console.print("  None")

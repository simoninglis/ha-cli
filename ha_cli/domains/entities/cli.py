"""Entity CLI commands for ha-cli."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

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
    create_home_assistant_metadata,
    get_home_assistant_health,
    create_workflow_recommendations,
    detect_advanced_issues,
)
from .service import EntityService
from .models import RenamePreview

# Initialize Typer app
app = typer.Typer(
    name="entities",
    help="Manage Home Assistant entities",
    add_completion=True,
)

# Console for rich output
console = Console()

# Logging setup
logger = logging.getLogger(__name__)


@app.command()
def list(
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Search pattern (regex)"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filter by domain"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List entities with optional filtering."""
    setup_logging(debug)
    
    # Validate mutually exclusive flags
    output_flags = sum([json_output, porcelain])
    if output_flags > 1:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _list() -> None:
        formatter = PorcelainFormatter("entities list") if porcelain else None
        
        try:
            url_final, token_final = get_client_config(url, token)
            
            async with HAClient(url_final, token_final, timeout) as client:
                service = EntityService(client)
                entities = await service.list_entities(search, domain)
                
                if porcelain:
                    # Group by domain for analysis
                    domains = {}
                    for entity in entities:
                        if entity.domain not in domains:
                            domains[entity.domain] = []
                        domains[entity.domain].append(entity)
                    
                    # Convert entities to porcelain-friendly format
                    data = []
                    for entity in entities:
                        entity_data = {
                            "entity_id": entity.entity_id,
                            "friendly_name": entity.friendly_name,
                            "domain": entity.domain,
                            "state": entity.state,
                            "last_changed": entity.last_changed.isoformat() if entity.last_changed else None,
                            "last_updated": entity.last_updated.isoformat() if entity.last_updated else None,
                        }
                        data.append(entity_data)
                    
                    # Create filters applied list
                    filters_applied = []
                    if search:
                        filters_applied.append(f"search={search}")
                    if domain:
                        filters_applied.append(f"domain={domain}")
                    
                    # Get Home Assistant health information
                    health_info = await get_home_assistant_health(client)
                    
                    # Create metadata
                    domain_breakdown = {domain_name: len(entity_list) for domain_name, entity_list in domains.items()}
                    metadata = {
                        "total_entities": len(entities),
                        "filtered_entities": len(entities),
                        "filters_applied": filters_applied,
                        "domain_breakdown": domain_breakdown,
                        "unique_domains": len(domains),
                        "performance_score": min(100, max(0, 100 - len(entities) // 10)),  # Simple score based on entity count
                        "home_assistant": create_home_assistant_metadata(
                            url_final,
                            "rest",
                            health_info=health_info
                        )
                    }
                    
                    # Create suggestions
                    suggestions = {
                        "common_actions": [
                            "Export entities: ha-cli entities export entities.csv --porcelain",
                            "Backup entities: ha-cli entities backup --porcelain",
                        ],
                        "related_commands": [
                            "ha-cli automations list --porcelain",
                            "ha-cli dashboards list --porcelain",
                        ],
                        "detected_issues": [],
                        "optimization_recommendations": [],
                        "filtering_suggestions": []
                    }
                    
                    # Add filtering suggestions
                    if not search and not domain and len(entities) > 100:
                        suggestions["filtering_suggestions"].append("Consider filtering with --domain or --search for large entity sets")
                    
                    if len(domains) > 10:
                        top_domains = sorted(domain_breakdown.items(), key=lambda x: x[1], reverse=True)[:3]
                        domain_names = [d[0] for d in top_domains]
                        suggestions["filtering_suggestions"].append(f"Top domains to explore: {', '.join(domain_names)}")
                    
                    # Add domain-specific suggestions
                    for domain_name, count in domain_breakdown.items():
                        if domain_name == "sensor" and count > 50:
                            suggestions["optimization_recommendations"].append(f"Many sensors ({count}) - consider grouping or filtering")
                        elif domain_name == "light" and count > 20:
                            suggestions["common_actions"].append(f"Rename lights: ha-cli entities rename --domain light --search pattern --replace new_pattern")
                        elif domain_name == "climate" and count > 0:
                            suggestions["common_actions"].append("Check climate entities: ha-cli entities list --domain climate --porcelain")
                    
                    # Performance suggestions
                    if len(entities) > 500:
                        suggestions["optimization_recommendations"].append("Large number of entities may impact performance")
                    
                    # Add rename suggestions if patterns detected
                    inconsistent_naming = []
                    for domain_name, entity_list in domains.items():
                        if len(entity_list) > 2:
                            # Check for naming inconsistencies (simplified heuristic)
                            has_underscores = any("_" in e.entity_id.split(".", 1)[1] for e in entity_list)
                            has_no_underscores = any("_" not in e.entity_id.split(".", 1)[1] for e in entity_list)
                            if has_underscores and has_no_underscores:
                                inconsistent_naming.append(domain_name)
                    
                    if inconsistent_naming:
                        suggestions["detected_issues"].append(f"Inconsistent naming patterns in domains: {', '.join(inconsistent_naming)}")
                        suggestions["common_actions"].append("Standardize naming: ha-cli entities rename --search pattern --replace standardized_pattern")
                    
                    # Add workflow recommendations
                    workflow_recommendations = create_workflow_recommendations(
                        "entities list",
                        {
                            "total_entities": len(entities),
                            "domain_breakdown": domain_breakdown,
                            "search_pattern": search,
                            "domain_filter": domain
                        },
                        health_info
                    )
                    suggestions.update(workflow_recommendations)
                    
                    # Detect advanced issues
                    advanced_issues = detect_advanced_issues("entities list", data, metadata, health_info)
                    if advanced_issues:
                        suggestions.setdefault("detected_issues", []).extend(advanced_issues)
                    
                    porcelain_output = formatter.success(data, metadata, suggestions)
                    import sys
                    sys.stdout.write(porcelain_output)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    
                elif json_output:
                    data = [entity.to_dict() for entity in entities]
                    json_str = json.dumps(data, indent=2)
                    import sys
                    sys.stdout.write(json_str)
                    sys.stdout.write('\n')  # Add final newline
                    sys.stdout.flush()
                    
                else:
                    # Rich table output
                    if not entities:
                        console.print("No entities found")
                        return
                    
                    # Group by domain for better organization
                    domains = {}
                    for entity in entities:
                        if entity.domain not in domains:
                            domains[entity.domain] = []
                        domains[entity.domain].append(entity)
                    
                    # Create summary
                    title_parts = ["Home Assistant Entities"]
                    if search:
                        title_parts.append(f"(search: {search})")
                    if domain:
                        title_parts.append(f"(domain: {domain})")
                    
                    table = Table(title=" ".join(title_parts))
                    table.add_column("Entity ID", style="cyan")
                    table.add_column("Friendly Name", style="white")
                    table.add_column("Domain", style="yellow")
                    table.add_column("State", style="green")
                    
                    # Add rows grouped by domain
                    for domain_name in sorted(domains.keys()):
                        domain_entities = sorted(domains[domain_name], key=lambda e: e.entity_id)
                        for entity in domain_entities:
                            table.add_row(
                                entity.entity_id,
                                entity.friendly_name or "N/A",
                                entity.domain,
                                entity.state[:50] + "..." if len(entity.state) > 50 else entity.state,
                            )
                    
                    console.print(table)
                    
                    # Summary
                    total_entities = len(entities)
                    domain_breakdown = {domain: len(entities) for domain, entities in domains.items()}
                    console.print(f"\n[cyan]Summary:[/cyan] {total_entities} entities across {len(domains)} domains")
                    for domain_name, count in sorted(domain_breakdown.items()):
                        console.print(f"  {domain_name}: {count}")
                        
        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                print(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise
    
    asyncio.run(run_async_command(_list()))


@app.command()
def export(
    output: str = typer.Argument(..., help="Output CSV file path"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Search pattern (regex)"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filter by domain"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Export entities to CSV file."""
    setup_logging(debug)
    
    async def _export() -> None:
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = EntityService(client)
            entities = await service.list_entities(search, domain)
            
            # Export to CSV
            service.export_entities_to_csv(entities, output)
            
            console.print(f"[green]✓ Exported {len(entities)} entities to {output}[/green]")
            
            # Show summary
            domains = {}
            for entity in entities:
                domains[entity.domain] = domains.get(entity.domain, 0) + 1
            
            console.print(f"[cyan]Summary:[/cyan] {len(entities)} entities across {len(domains)} domains")
            for domain_name, count in sorted(domains.items()):
                console.print(f"  {domain_name}: {count}")
    
    asyncio.run(run_async_command(_export()))


@app.command()
def backup(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output CSV file (auto-generated if omitted)"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Create a backup of all entities."""
    setup_logging(debug)
    
    async def _backup() -> None:
        # Generate filename if not provided
        if not output:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"entities_backup_{timestamp}.csv"
        else:
            output_file = output
        
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = EntityService(client)
            entities = await service.list_entities()
            
            # Export to CSV
            service.export_entities_to_csv(entities, output_file)
            
            console.print(f"[green]✓ Backed up {len(entities)} entities to {output_file}[/green]")
            
            # Show summary
            domains = {}
            for entity in entities:
                domains[entity.domain] = domains.get(entity.domain, 0) + 1
            
            console.print(f"[cyan]Backup Summary:[/cyan] {len(entities)} entities across {len(domains)} domains")
            for domain_name, count in sorted(domains.items()):
                console.print(f"  {domain_name}: {count}")
    
    asyncio.run(run_async_command(_backup()))


@app.command()
def rename(
    search: str = typer.Option(..., "--search", "-s", help="Search pattern (regex)"),
    replace: str = typer.Option(..., "--replace", "-r", help="Replace pattern (regex)"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filter by domain"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be renamed without doing it"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Rename entities using regex patterns."""
    setup_logging(debug)
    
    async def _rename() -> None:
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = EntityService(client)
            
            # Get entities that match the search pattern
            entities = await service.list_entities(search, domain)
            
            if not entities:
                console.print("[yellow]No entities found matching the search pattern[/yellow]")
                return
            
            # Preview the rename operations
            preview = service.preview_rename(search, replace, entities)
            
            if preview.invalid_operations:
                console.print("[red]Invalid operations found:[/red]")
                for invalid_op in preview.invalid_operations:
                    console.print(f"  {invalid_op['operation']['old_entity_id']} -> {invalid_op['operation']['new_entity_id']}")
                    for issue in invalid_op['issues']:
                        console.print(f"    Issue: {issue}")
                console.print()
            
            if not preview.operations:
                console.print("[yellow]No valid rename operations to perform[/yellow]")
                return
            
            # Perform impact analysis for each entity being renamed
            console.print("[cyan]Analyzing impact on automations and dashboards...[/cyan]")
            high_impact_entities = []
            medium_impact_entities = []
            total_automation_refs = 0
            total_dashboard_refs = 0
            
            for operation in preview.operations:
                impact = await service.analyze_entity_impact(operation.old_entity_id)
                total_automation_refs += len(impact.automation_references)
                total_dashboard_refs += len(impact.dashboard_references)
                
                if impact.impact_level == "high":
                    high_impact_entities.append((operation.old_entity_id, impact))
                elif impact.impact_level == "medium":
                    medium_impact_entities.append((operation.old_entity_id, impact))
            
            # Show preview table with impact analysis
            console.print(f"[cyan]Found {preview.valid_count} entities to rename:[/cyan]")
            table = Table()
            table.add_column("Current Entity ID", style="cyan")
            table.add_column("New Entity ID", style="green")
            table.add_column("Friendly Name", style="white")
            table.add_column("Impact", style="yellow")
            table.add_column("References", style="red")
            
            # Create impact lookup for display
            impact_lookup = {}
            for operation in preview.operations:
                impact = await service.analyze_entity_impact(operation.old_entity_id)
                impact_lookup[operation.old_entity_id] = impact
            
            for operation in preview.operations:
                impact = impact_lookup[operation.old_entity_id]
                impact_color = {
                    "low": "green",
                    "medium": "yellow", 
                    "high": "red"
                }.get(impact.impact_level, "white")
                
                ref_count = f"A:{len(impact.automation_references)} D:{len(impact.dashboard_references)}"
                
                table.add_row(
                    operation.old_entity_id,
                    operation.new_entity_id,
                    operation.friendly_name or "N/A",
                    f"[{impact_color}]{impact.impact_level}[/{impact_color}]",
                    ref_count if impact.total_references > 0 else "[green]none[/green]"
                )
            
            console.print(table)
            
            # Show impact summary
            console.print(f"\n[bold yellow]Impact Summary:[/bold yellow]")
            console.print(f"  Total automation references: {total_automation_refs}")
            console.print(f"  Total dashboard references: {total_dashboard_refs}")
            
            if high_impact_entities:
                console.print(f"\n[bold red]High Impact Entities ({len(high_impact_entities)}):[/bold red]")
                for entity_id, impact in high_impact_entities:
                    console.print(f"  • {entity_id} - {len(impact.automation_references)} automations, {len(impact.dashboard_references)} dashboards")
            
            if medium_impact_entities:
                console.print(f"\n[bold yellow]Medium Impact Entities ({len(medium_impact_entities)}):[/bold yellow]")
                for entity_id, impact in medium_impact_entities:
                    console.print(f"  • {entity_id} - {len(impact.automation_references)} automations, {len(impact.dashboard_references)} dashboards")
            
            # Show warnings
            if preview.warnings:
                console.print("\n[yellow]Warnings:[/yellow]")
                for warning in preview.warnings:
                    console.print(f"  • {warning}")
            
            if dry_run:
                console.print("\n[yellow]Dry run mode - no changes made[/yellow]")
                return
            
            # Enhanced confirmation with impact warnings
            console.print()
            
            # Add impact-based warnings to confirmation
            warning_msg = f"Proceed with renaming {preview.valid_count} entities?"
            if high_impact_entities:
                warning_msg = f"[red]WARNING:[/red] {len(high_impact_entities)} high-impact entities detected. " + warning_msg
            elif medium_impact_entities:
                warning_msg = f"[yellow]CAUTION:[/yellow] {len(medium_impact_entities)} medium-impact entities detected. " + warning_msg
            
            if total_automation_refs > 0 or total_dashboard_refs > 0:
                console.print(f"[yellow]⚠ This operation will affect {total_automation_refs} automations and {total_dashboard_refs} dashboards[/yellow]")
                console.print("[yellow]⚠ Manual updates to configurations may be required after renaming[/yellow]")
            
            confirm = typer.confirm(warning_msg)
            if not confirm:
                console.print("[yellow]Rename operation cancelled[/yellow]")
                return
            
            # Execute rename operations
            console.print("[cyan]Executing rename operations...[/cyan]")
            results = await service.execute_rename_operations(preview.operations)
            
            # Show results
            success_count = sum(1 for r in results if r.success)
            failure_count = len(results) - success_count
            
            if success_count > 0:
                console.print(f"[green]✓ Successfully renamed {success_count} entities[/green]")
            
            if failure_count > 0:
                console.print(f"[red]✗ Failed to rename {failure_count} entities:[/red]")
                for result in results:
                    if not result.success:
                        console.print(f"  {result.operation.old_entity_id}: {result.error_message}")
            
            # Summary
            console.print(f"\n[cyan]Summary:[/cyan] {success_count} succeeded, {failure_count} failed")
    
    asyncio.run(run_async_command(_rename()))


@app.command()
def import_operations(
    csv_file: str = typer.Argument(..., help="CSV file containing rename operations"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be renamed without doing it"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Import and execute rename operations from CSV file."""
    setup_logging(debug)
    
    async def _import() -> None:
        # Check if CSV file exists
        if not Path(csv_file).exists():
            console.print(f"[red]Error:[/red] CSV file '{csv_file}' not found")
            sys.exit(EXIT_USAGE_ERROR)
        
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = EntityService(client)
            
            try:
                # Import operations from CSV
                operations = service.import_operations_from_csv(csv_file)
                
                if not operations:
                    console.print("[yellow]No rename operations found in CSV file[/yellow]")
                    return
                
                # Validate operations
                preview = RenamePreview.from_operations(operations)
                
                if preview.invalid_operations:
                    console.print("[red]Invalid operations found:[/red]")
                    for invalid_op in preview.invalid_operations:
                        console.print(f"  {invalid_op['operation']['old_entity_id']} -> {invalid_op['operation']['new_entity_id']}")
                        for issue in invalid_op['issues']:
                            console.print(f"    Issue: {issue}")
                    console.print()
                
                if not preview.operations:
                    console.print("[yellow]No valid rename operations to perform[/yellow]")
                    return
                
                # Show preview
                console.print(f"[cyan]Loaded {preview.valid_count} valid operations from {csv_file}:[/cyan]")
                table = Table()
                table.add_column("Current Entity ID", style="cyan")
                table.add_column("New Entity ID", style="green")
                table.add_column("Friendly Name", style="white")
                
                for operation in preview.operations:
                    table.add_row(
                        operation.old_entity_id,
                        operation.new_entity_id,
                        operation.friendly_name or "N/A"
                    )
                
                console.print(table)
                
                if dry_run:
                    console.print("\n[yellow]Dry run mode - no changes made[/yellow]")
                    return
                
                # Confirm with user
                console.print()
                confirm = typer.confirm(f"Proceed with renaming {preview.valid_count} entities?")
                if not confirm:
                    console.print("[yellow]Import operation cancelled[/yellow]")
                    return
                
                # Execute operations
                console.print("[cyan]Executing rename operations...[/cyan]")
                results = await service.execute_rename_operations(preview.operations)
                
                # Show results
                success_count = sum(1 for r in results if r.success)
                failure_count = len(results) - success_count
                
                if success_count > 0:
                    console.print(f"[green]✓ Successfully renamed {success_count} entities[/green]")
                
                if failure_count > 0:
                    console.print(f"[red]✗ Failed to rename {failure_count} entities:[/red]")
                    for result in results:
                        if not result.success:
                            console.print(f"  {result.operation.old_entity_id}: {result.error_message}")
                
                console.print(f"\n[cyan]Summary:[/cyan] {success_count} succeeded, {failure_count} failed")
                
            except Exception as e:
                console.print(f"[red]Error importing CSV file:[/red] {e}")
                sys.exit(EXIT_HA_ERROR)
    
    asyncio.run(run_async_command(_import()))


@app.command()
def analyze(
    entity_id: Optional[str] = typer.Argument(None, help="Entity ID to analyze"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Search pattern for batch analysis"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filter by domain for batch analysis"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Analyze entity usage in automations and dashboards."""
    setup_logging(debug)
    
    async def _analyze() -> None:
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = EntityService(client)
            
            # Handle single entity analysis vs batch analysis
            if entity_id:
                # Single entity analysis
                entity = await service.get_entity(entity_id)
                if not entity:
                    console.print(f"[red]Error:[/red] Entity '{entity_id}' not found")
                    sys.exit(EXIT_HA_ERROR)
                
                # Analyze impact
                console.print(f"[cyan]Analyzing entity:[/cyan] {entity_id}")
                impact_analysis = await service.analyze_entity_impact(entity_id)
                
                if json_output:
                    data = {
                        "entity_id": impact_analysis.entity_id,
                        "automation_references": impact_analysis.automation_references,
                        "dashboard_references": impact_analysis.dashboard_references,
                        "total_references": impact_analysis.total_references,
                        "impact_level": impact_analysis.impact_level,
                        "recommendations": impact_analysis.recommendations,
                    }
                    print(json.dumps(data, indent=2))
                    
                else:
                    # Rich console output
                    console.print(f"[bold]Entity:[/bold] {entity.friendly_name or entity_id}")
                    console.print(f"[bold]Domain:[/bold] {entity.domain}")
                    console.print(f"[bold]Current State:[/bold] {entity.state}")
                    
                    console.print(f"\n[bold yellow]Impact Analysis:[/bold yellow]")
                    console.print(f"[bold]Impact Level:[/bold] {impact_analysis.impact_level}")
                    console.print(f"[bold]Total References:[/bold] {impact_analysis.total_references}")
                    
                    if impact_analysis.automation_references:
                        console.print(f"\n[bold red]Automation References ({len(impact_analysis.automation_references)}):[/bold red]")
                        for ref in impact_analysis.automation_references:
                            console.print(f"  • {ref}")
                    else:
                        console.print(f"\n[green]✓ No automation references found[/green]")
                    
                    if impact_analysis.dashboard_references:
                        console.print(f"\n[bold red]Dashboard References ({len(impact_analysis.dashboard_references)}):[/bold red]")
                        for ref in impact_analysis.dashboard_references:
                            console.print(f"  • {ref}")
                    else:
                        console.print(f"\n[green]✓ No dashboard references found[/green]")
                    
                    if impact_analysis.recommendations:
                        console.print(f"\n[bold blue]Recommendations:[/bold blue]")
                        for rec in impact_analysis.recommendations:
                            console.print(f"  • {rec}")
                    
                    # Safety assessment
                    if impact_analysis.impact_level == "low":
                        console.print(f"\n[green]✓ Renaming this entity should be safe[/green]")
                    elif impact_analysis.impact_level == "medium":
                        console.print(f"\n[yellow]⚠ Moderate impact - review references before renaming[/yellow]")
                    else:
                        console.print(f"\n[red]⚠ High impact - carefully plan rename operation[/red]")
            
            else:
                # Batch analysis - analyze multiple entities based on search/domain filters
                if not search and not domain:
                    console.print("[red]Error:[/red] Must provide either entity_id or search/domain filters for batch analysis")
                    sys.exit(EXIT_USAGE_ERROR)
                
                console.print("[cyan]Finding entities for batch analysis...[/cyan]")
                entities = await service.list_entities(search, domain)
                
                if not entities:
                    console.print("[yellow]No entities found matching the specified criteria[/yellow]")
                    return
                
                console.print(f"[cyan]Analyzing {len(entities)} entities...[/cyan]")
                
                # Analyze impact for each entity
                analysis_results = []
                high_impact_count = 0
                medium_impact_count = 0
                low_impact_count = 0
                total_automation_refs = 0
                total_dashboard_refs = 0
                
                for entity in entities:
                    impact_analysis = await service.analyze_entity_impact(entity.entity_id)
                    analysis_results.append((entity, impact_analysis))
                    
                    # Count impact levels
                    if impact_analysis.impact_level == "high":
                        high_impact_count += 1
                    elif impact_analysis.impact_level == "medium":
                        medium_impact_count += 1
                    else:
                        low_impact_count += 1
                    
                    total_automation_refs += len(impact_analysis.automation_references)
                    total_dashboard_refs += len(impact_analysis.dashboard_references)
                
                if json_output:
                    # JSON output for batch analysis
                    data = {
                        "search_criteria": {
                            "search_pattern": search,
                            "domain_filter": domain
                        },
                        "summary": {
                            "total_entities": len(entities),
                            "high_impact": high_impact_count,
                            "medium_impact": medium_impact_count,
                            "low_impact": low_impact_count,
                            "total_automation_references": total_automation_refs,
                            "total_dashboard_references": total_dashboard_refs
                        },
                        "entities": [
                            {
                                "entity_id": analysis.entity_id,
                                "friendly_name": entity.friendly_name,
                                "domain": entity.domain,
                                "state": entity.state,
                                "automation_references": analysis.automation_references,
                                "dashboard_references": analysis.dashboard_references,
                                "total_references": analysis.total_references,
                                "impact_level": analysis.impact_level,
                                "recommendations": analysis.recommendations,
                            }
                            for entity, analysis in analysis_results
                        ]
                    }
                    print(json.dumps(data, indent=2))
                    
                else:
                    # Rich console output for batch analysis
                    
                    # Summary table
                    console.print(f"\n[bold yellow]Batch Analysis Summary:[/bold yellow]")
                    console.print(f"  Analyzed entities: {len(entities)}")
                    console.print(f"  High impact: [red]{high_impact_count}[/red]")
                    console.print(f"  Medium impact: [yellow]{medium_impact_count}[/yellow]")
                    console.print(f"  Low impact: [green]{low_impact_count}[/green]")
                    console.print(f"  Total automation references: {total_automation_refs}")
                    console.print(f"  Total dashboard references: {total_dashboard_refs}")
                    
                    # Detailed results table
                    console.print(f"\n[cyan]Detailed Impact Analysis:[/cyan]")
                    table = Table()
                    table.add_column("Entity ID", style="cyan")
                    table.add_column("Friendly Name", style="white")
                    table.add_column("Impact", style="yellow")
                    table.add_column("Auto Refs", style="red")
                    table.add_column("Dash Refs", style="red")
                    table.add_column("Total Refs", style="bold red")
                    
                    # Sort by impact level (high first) then by total references
                    impact_order = {"high": 0, "medium": 1, "low": 2}
                    sorted_results = sorted(
                        analysis_results,
                        key=lambda x: (impact_order[x[1].impact_level], -x[1].total_references)
                    )
                    
                    for entity, analysis in sorted_results:
                        impact_color = {
                            "low": "green",
                            "medium": "yellow", 
                            "high": "red"
                        }.get(analysis.impact_level, "white")
                        
                        table.add_row(
                            entity.entity_id,
                            entity.friendly_name or "N/A",
                            f"[{impact_color}]{analysis.impact_level}[/{impact_color}]",
                            str(len(analysis.automation_references)),
                            str(len(analysis.dashboard_references)),
                            str(analysis.total_references) if analysis.total_references > 0 else "[green]0[/green]"
                        )
                    
                    console.print(table)
                    
                    # Show high impact entities with details
                    if high_impact_count > 0:
                        console.print(f"\n[bold red]High Impact Entities ({high_impact_count}):[/bold red]")
                        for entity, analysis in sorted_results:
                            if analysis.impact_level == "high":
                                console.print(f"  • {entity.entity_id} ({entity.friendly_name or 'N/A'})")
                                console.print(f"    Automations: {len(analysis.automation_references)}, Dashboards: {len(analysis.dashboard_references)}")
                                if analysis.recommendations:
                                    console.print(f"    Recommendations: {', '.join(analysis.recommendations[:2])}")
                    
                    # Safety recommendations
                    console.print(f"\n[bold blue]Batch Analysis Recommendations:[/bold blue]")
                    if high_impact_count > 0:
                        console.print(f"  • [red]Caution:[/red] {high_impact_count} entities have high impact - carefully plan any changes")
                    if medium_impact_count > 0:
                        console.print(f"  • [yellow]Review:[/yellow] {medium_impact_count} entities have medium impact - review before changes")
                    if low_impact_count > 0:
                        console.print(f"  • [green]Safe:[/green] {low_impact_count} entities appear safe to modify")
                    
                    if total_automation_refs > 0 or total_dashboard_refs > 0:
                        console.print(f"  • Consider using 'ha-cli entities rename --dry-run' to preview changes before execution")
                        console.print(f"  • Backup configurations before making changes: 'ha-cli entities backup'")
                        console.print(f"  • Test automations after entity changes to ensure they still work correctly")
    
    asyncio.run(run_async_command(_analyze()))


@app.command()
def delete(
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Search pattern (regex) for entities to delete"),
    entity_ids: Optional[List[str]] = typer.Option(None, "--entity-id", "-e", help="Specific entity IDs to delete"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filter by domain"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without doing it"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Delete entities by search pattern or specific IDs.
    
    Examples:
        # Delete specific entities
        ha-cli entities delete --entity-id sensor.rx_10 --entity-id sensor.rx_11
        
        # Delete all sensor.rx* entities  
        ha-cli entities delete --search "^sensor\\.rx" --force
        
        # Delete all unavailable sensors (dry run first)
        ha-cli entities delete --domain sensor --dry-run
    """
    setup_logging(debug)
    
    # Validate mutually exclusive flags
    output_flags = sum([json_output, porcelain])
    if output_flags > 1:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)
    
    # Must provide either search pattern or entity IDs
    if not search and not entity_ids:
        console.print("[red]Error:[/red] Must provide either --search pattern or --entity-id values")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _delete() -> None:
        formatter = PorcelainFormatter("entities delete") if porcelain else None
        
        try:
            url_final, token_final = get_client_config(url, token)
            
            async with HAClient(url_final, token_final, timeout) as client:
                service = EntityService(client)
                
                # Collect entities to delete
                entities_to_delete = []
                
                if entity_ids:
                    # Specific entity IDs provided
                    for entity_id in entity_ids:
                        entity = await service.get_entity(entity_id)
                        if entity:
                            entities_to_delete.append(entity)
                        else:
                            console.print(f"[yellow]Warning:[/yellow] Entity '{entity_id}' not found")
                
                if search:
                    # Search for entities matching pattern
                    matching_entities = await service.list_entities(search, domain)
                    
                    # Filter out any that are already in the list
                    existing_ids = {e.entity_id for e in entities_to_delete}
                    for entity in matching_entities:
                        if entity.entity_id not in existing_ids:
                            entities_to_delete.append(entity)
                
                if not entities_to_delete:
                    if porcelain:
                        output = formatter.success([], {"entities_found": 0}, {"message": "No entities found to delete"})
                        print(output)
                    else:
                        console.print("[yellow]No entities found matching the criteria[/yellow]")
                    return
                
                # Show entities to be deleted
                if porcelain:
                    # Porcelain output for dry-run or pre-confirmation
                    data = [{"entity_id": e.entity_id, "friendly_name": e.friendly_name, "state": e.state} for e in entities_to_delete]
                    metadata = {
                        "total_entities": len(entities_to_delete),
                        "dry_run": dry_run,
                        "search_pattern": search,
                        "domain_filter": domain,
                        "home_assistant": create_home_assistant_metadata(url_final, "websocket")
                    }
                    suggestions = {
                        "common_actions": [
                            "Confirm deletion: ha-cli entities delete --search <pattern> --force",
                            "Backup first: ha-cli entities backup --porcelain"
                        ],
                        "warnings": [
                            "Entity deletion is permanent and cannot be undone",
                            "Deleted entities may be recreated by their integration"
                        ]
                    }
                    
                    if dry_run:
                        output = formatter.success(data, metadata, suggestions)
                        print(output)
                        return
                
                elif json_output:
                    # JSON output
                    data = {
                        "entities_to_delete": [
                            {
                                "entity_id": e.entity_id,
                                "friendly_name": e.friendly_name,
                                "domain": e.domain,
                                "state": e.state
                            } for e in entities_to_delete
                        ],
                        "dry_run": dry_run,
                        "total": len(entities_to_delete)
                    }
                    print(json.dumps(data, indent=2))
                    
                    if dry_run:
                        return
                
                else:
                    # Rich table output
                    console.print(f"[cyan]Found {len(entities_to_delete)} entities to delete:[/cyan]")
                    
                    table = Table()
                    table.add_column("Entity ID", style="red")
                    table.add_column("Friendly Name", style="white")
                    table.add_column("Domain", style="yellow")
                    table.add_column("State", style="cyan")
                    
                    for entity in entities_to_delete:
                        table.add_row(
                            entity.entity_id,
                            entity.friendly_name or "N/A",
                            entity.domain,
                            entity.state
                        )
                    
                    console.print(table)
                    
                    if dry_run:
                        console.print("\n[yellow]Dry run mode - no entities were deleted[/yellow]")
                        return
                
                # Confirm deletion if not forced
                if not force and not porcelain:
                    console.print()
                    console.print("[bold red]⚠ WARNING:[/bold red] Entity deletion is permanent and cannot be undone!")
                    console.print("[yellow]Note:[/yellow] Some entities may be automatically recreated by their integration")
                    
                    confirm = typer.confirm(f"Are you sure you want to delete {len(entities_to_delete)} entities?")
                    if not confirm:
                        console.print("[yellow]Deletion cancelled[/yellow]")
                        return
                
                # Execute deletions
                console.print(f"[cyan]Deleting {len(entities_to_delete)} entities...[/cyan]")
                
                entity_ids_to_delete = [e.entity_id for e in entities_to_delete]
                results = await service.delete_entities(entity_ids_to_delete)
                
                # Process results
                success_count = sum(1 for r in results.values() if r.get("success", False))
                failure_count = len(results) - success_count
                
                if porcelain:
                    # Porcelain output for results
                    data = []
                    for entity_id, result in results.items():
                        data.append({
                            "entity_id": entity_id,
                            "success": result.get("success", False),
                            "error": result.get("error", None)
                        })
                    
                    metadata = {
                        "total_processed": len(results),
                        "successful_deletions": success_count,
                        "failed_deletions": failure_count,
                        "home_assistant": create_home_assistant_metadata(url_final, "websocket")
                    }
                    
                    suggestions = {
                        "common_actions": [],
                        "warnings": []
                    }
                    
                    if success_count > 0:
                        suggestions["common_actions"].append("Reload integrations: ha-cli integrations reload")
                        suggestions["warnings"].append("Some entities may reappear after integration reload")
                    
                    if failure_count > 0:
                        suggestions["common_actions"].append("Check entity states: ha-cli entities list --porcelain")
                        suggestions["warnings"].append("Failed deletions may indicate entities are in use")
                    
                    output = formatter.success(data, metadata, suggestions)
                    print(output)
                    
                elif json_output:
                    # JSON results
                    data = {
                        "results": results,
                        "summary": {
                            "total": len(results),
                            "success": success_count,
                            "failed": failure_count
                        }
                    }
                    print(json.dumps(data, indent=2))
                    
                else:
                    # Rich console output
                    if success_count > 0:
                        console.print(f"[green]✓ Successfully deleted {success_count} entities[/green]")
                    
                    if failure_count > 0:
                        console.print(f"[red]✗ Failed to delete {failure_count} entities:[/red]")
                        for entity_id, result in results.items():
                            if not result.get("success", False):
                                console.print(f"  {entity_id}: {result.get('error', 'Unknown error')}")
                    
                    console.print(f"\n[cyan]Summary:[/cyan] {success_count} deleted, {failure_count} failed")
                    
                    if success_count > 0:
                        console.print("\n[yellow]Note:[/yellow] Some entities may be recreated by their integration on next discovery")
                        
        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                print(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise
    
    asyncio.run(run_async_command(_delete()))


@app.command()
def version() -> None:
    """Show version information."""
    from ... import __version__
    
    console.print(f"ha-cli entities version {__version__}")
"""Dashboard CLI commands for ha-cli."""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, List, Literal

import typer
from rich.console import Console
from rich.table import Table

from ...common.cli_utils import run_async_command, set_porcelain_mode, setup_logging, write_output
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import (
    EXIT_HA_ERROR,
    EXIT_USAGE_ERROR,
)
from ...common.porcelain import (
    PorcelainFormatter,
    analyze_dashboard_performance,
    create_dashboard_suggestions,
    create_home_assistant_metadata,
    create_workflow_recommendations,
    detect_advanced_issues,
    get_home_assistant_health,
)
from .service import DashboardService

# Initialize Typer app
app = typer.Typer(
    name="dashboards",
    help="Manage Home Assistant dashboards",
    add_completion=True,
)

# Console for rich output
console = Console()

# Logging setup
logger = logging.getLogger(__name__)


@app.command()
def list(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all dashboards."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    # Validate mutually exclusive flags
    output_flags = sum([json_output, porcelain])
    if output_flags > 1:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _list() -> None:
        formatter = PorcelainFormatter("dashboards list") if porcelain else None
        
        try:
            url_final, token_final = get_client_config(url, token)
            
            async with HAClient(url_final, token_final, timeout) as client:
                service = DashboardService(client)
                dashboards = await service.list_dashboards()
                
                if porcelain:
                    assert formatter is not None  # Type narrowing for mypy
                    # Convert dashboards to porcelain-friendly format
                    data = []
                    storage_mode_count = {"storage": 0, "yaml": 0}
                    
                    for dashboard in dashboards:
                        dashboard_data = {
                            "id": dashboard.id,
                            "url_path": dashboard.url_path,
                            "title": dashboard.title,
                            "mode": dashboard.mode,
                            "show_in_sidebar": dashboard.show_in_sidebar,
                            "require_admin": dashboard.require_admin,
                            "icon": getattr(dashboard, 'icon', None),
                        }
                        data.append(dashboard_data)
                        
                        # Count storage modes
                        if dashboard.mode == "storage":
                            storage_mode_count["storage"] += 1
                        else:
                            storage_mode_count["yaml"] += 1
                    
                    # Create metadata
                    metadata: dict[str, Any] = {
                        "total_count": len(dashboards),
                        "storage_mode_breakdown": storage_mode_count,
                        "sidebar_count": sum(1 for d in dashboards if d.show_in_sidebar),
                        "admin_only_count": sum(1 for d in dashboards if d.require_admin),
                        "home_assistant": create_home_assistant_metadata(
                            url_final,
                            "rest"
                        )
                    }

                    # Create suggestions
                    suggestions = create_dashboard_suggestions(len(dashboards))
                    
                    # Add specific insights
                    if storage_mode_count["yaml"] > 0 and storage_mode_count["storage"] > 0:
                        suggestions["detected_issues"].append(
                            f"Mixed dashboard modes detected ({storage_mode_count['storage']} storage, {storage_mode_count['yaml']} yaml)"
                        )
                    
                    if sum(1 for d in dashboards if not d.show_in_sidebar) > 0:
                        hidden_count = sum(1 for d in dashboards if not d.show_in_sidebar)
                        suggestions["common_actions"].append(
                            f"Review {hidden_count} dashboard(s) not shown in sidebar"
                        )
                    
                    # Add workflow recommendations
                    workflow_recommendations = create_workflow_recommendations(
                        "dashboards list",
                        {"total_count": len(dashboards), "storage_mode_breakdown": storage_mode_count}
                    )
                    suggestions.update(workflow_recommendations)
                    
                    # Detect advanced issues (get health info from create_home_assistant_metadata call)
                    health_info = metadata.get("home_assistant", {}).get("health", {})
                    advanced_issues = detect_advanced_issues("dashboards list", data, metadata, health_info)
                    if advanced_issues:
                        suggestions.setdefault("detected_issues", []).extend(advanced_issues)
                    
                    porcelain_output = formatter.success(data, metadata, suggestions)
                    write_output(porcelain_output)
                    
                elif json_output:
                    data = [dashboard.model_dump() for dashboard in dashboards]
                    json_str = json.dumps(data, indent=2)
                    write_output(json_str)
                    
                else:
                    # Original table output
                    if not dashboards:
                        console.print("No dashboards found")
                        return
                    
                    # Create table
                    table = Table(title="Home Assistant Dashboards")
                    table.add_column("ID", style="cyan")
                    table.add_column("URL Path", style="white")
                    table.add_column("Title", style="white")
                    table.add_column("Mode", style="yellow")
                    table.add_column("Sidebar", style="green")
                    table.add_column("Admin Only", style="red")
                    
                    for dashboard in dashboards:
                        # For YAML-mode dashboards, use url_path as ID
                        display_id = dashboard.id or dashboard.url_path or "N/A"
                        table.add_row(
                            display_id,
                            dashboard.url_path or "(default)",
                            dashboard.title or "N/A",
                            dashboard.mode,
                            "✓" if dashboard.show_in_sidebar else "✗",
                            "✓" if dashboard.require_admin else "✗",
                        )
                    
                    console.print(table)
                    
        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                write_output(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise
    
    asyncio.run(run_async_command(_list(), command="dashboards list"))


@app.command()
def read(
    url_path: str | None = typer.Argument(None, help="Dashboard URL path (omit for default)"),
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    format: str = typer.Option("yaml", "--format", "-f", help="Output format: yaml or json"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Read dashboard configuration."""
    setup_logging(debug)
    
    async def _read() -> None:
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = DashboardService(client)
            config = await service.get_dashboard(url_path)
            
            # Convert to dict
            config_dict = config.model_dump(exclude_none=True)
            
            # Format output
            if format == "json":
                output_str = json.dumps(config_dict, indent=2)
                if output:
                    Path(output).write_text(output_str)
                    console.print(f"[green]Dashboard saved to {output}[/green]")
                else:
                    write_output(output_str)
            else:  # yaml
                import ruamel.yaml
                yaml = ruamel.yaml.YAML()
                yaml.preserve_quotes = True
                yaml.default_flow_style = False
                yaml.width = 1000
                
                if output:
                    with open(output, "w", encoding="utf-8") as f:
                        yaml.dump(config_dict, f)
                    console.print(f"[green]Dashboard saved to {output}[/green]")
                else:
                    import io
                    stream = io.StringIO()
                    yaml.dump(config_dict, stream)
                    write_output(stream.getvalue(), newline=False)
    
    asyncio.run(run_async_command(_read(), command="dashboards read"))


@app.command()
def backup(
    url_path: str | None = typer.Argument(None, help="Dashboard URL path (omit for default)"),
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (auto-generated if omitted)"),
    format: str = typer.Option("yaml", "--format", "-f", help="Output format: yaml or json"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Backup dashboard to file."""
    setup_logging(debug)

    async def _backup() -> None:
        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final, timeout) as client:
            service = DashboardService(client)

            # Backup dashboard - cast format to literal type
            format_literal: Literal['json', 'yaml'] = 'yaml' if format == 'yaml' else 'json'
            backup_file = await service.backup_dashboard(
                url_path=url_path,
                output_file=output,
                format=format_literal,
            )
            
            console.print(f"[green]✓ Dashboard backed up to: {backup_file}[/green]")
    
    asyncio.run(run_async_command(_backup(), command="dashboards backup"))


@app.command()
def restore(
    input_file: str = typer.Argument(..., help="Backup file to restore from"),
    url_path: str | None = typer.Option(None, "--url-path", "-p", help="Dashboard URL path (omit for default)"),
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    validate_only: bool = typer.Option(False, "--validate-only", help="Only validate without restoring"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Restore dashboard from backup file."""
    setup_logging(debug)
    
    async def _restore() -> None:
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = DashboardService(client)
            
            if validate_only:
                console.print(f"[yellow]Validating {input_file}...[/yellow]")
            else:
                console.print(f"[yellow]Restoring dashboard from {input_file}...[/yellow]")
            
            await service.restore_dashboard(
                input_file=input_file,
                url_path=url_path,
                validate_only=validate_only,
            )
            
            if validate_only:
                console.print("[green]✓ Dashboard configuration is valid[/green]")
            else:
                console.print("[green]✓ Dashboard restored successfully[/green]")
    
    asyncio.run(run_async_command(_restore(), command="dashboards restore"))


@app.command()
def entities(
    url_path: str | None = typer.Argument(None, help="Dashboard URL path (omit for default)"),
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all entities referenced in a dashboard."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    # Validate mutually exclusive flags
    output_flags = sum([json_output, porcelain])
    if output_flags > 1:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _entities() -> None:
        formatter = PorcelainFormatter("dashboards entities") if porcelain else None
        
        try:
            url_final, token_final = get_client_config(url, token)
            
            async with HAClient(url_final, token_final, timeout) as client:
                service = DashboardService(client)
                entities = await service.get_entity_references(url_path)
                
                if porcelain:
                    assert formatter is not None  # Type narrowing for mypy
                    # Group entities by domain for analysis
                    domains_map: dict[str, List[str]] = {}
                    for entity in sorted(entities):
                        domain = entity.split(".", 1)[0]
                        if domain not in domains_map:
                            domains_map[domain] = []
                        domains_map[domain].append(entity)

                    # Create entity data with domain grouping
                    entity_data: List[dict[str, str]] = []
                    for entity in sorted(entities):
                        domain = entity.split(".", 1)[0]
                        entity_data.append({
                            "entity_id": entity,
                            "domain": domain,
                            "friendly_name": entity.replace("_", " ").title(),
                        })

                    # Analyze dashboard performance
                    domain_breakdown = {domain: len(entity_list) for domain, entity_list in domains_map.items()}
                    performance_analysis = analyze_dashboard_performance(len(entities), domain_breakdown)
                    
                    # Get Home Assistant health information
                    health_info = await get_home_assistant_health(client)
                    
                    # Create metadata
                    metadata = {
                        "dashboard_url_path": url_path or "default",
                        "total_entities": len(entities),
                        "unique_domains": len(domains_map),
                        "domain_breakdown": domain_breakdown,
                        "performance": performance_analysis,
                        "home_assistant": create_home_assistant_metadata(
                            url_final,
                            "rest",
                            health_info=health_info
                        )
                    }

                    # Create enhanced suggestions based on performance analysis
                    suggestions: dict[str, Any] = {
                        "common_actions": [
                            f"View dashboard: ha-cli dashboards read {url_path or 'default'} --porcelain",
                            "Check entity states: Use MCP tools for real-time states",
                            "Find missing entities: Compare with available entities",
                        ],
                        "related_commands": [
                            "ha-cli dashboards list --porcelain",
                            "ha-cli automations list --porcelain",
                        ],
                        "detected_issues": [],
                        "performance_optimizations": [],
                        "monitoring_recommendations": []
                    }

                    # Add performance-based suggestions
                    if performance_analysis["issues"]:
                        suggestions["detected_issues"].extend(performance_analysis["issues"])

                    if performance_analysis["optimizations"]:
                        suggestions["performance_optimizations"].extend(performance_analysis["optimizations"])

                    if performance_analysis["monitoring_needed"]:
                        suggestions["monitoring_recommendations"].extend(performance_analysis["monitoring_needed"])

                    # Analyze entity usage patterns
                    if len(entities) == 0:
                        suggestions["detected_issues"].append("No entities found - dashboard may be empty or use only static content")

                    # Add performance score context
                    perf_score = performance_analysis["performance_score"]
                    if perf_score < 70:
                        suggestions["detected_issues"].append(f"Poor performance score ({perf_score}/100) - optimization recommended")
                    elif perf_score < 85:
                        suggestions["performance_optimizations"].append(f"Moderate performance score ({perf_score}/100) - consider optimization")

                    # Domain-specific suggestions
                    if "sensor" in domains_map and len(domains_map["sensor"]) > 20:
                        sensor_count = len(domains_map['sensor'])
                        suggestions["performance_optimizations"].append(f"Many sensors ({sensor_count}) - consider grouping or filtering")

                    if "camera" in domains_map:
                        suggestions["performance_optimizations"].append("Cameras detected - ensure efficient streaming configuration")
                        suggestions["monitoring_recommendations"].append("Monitor bandwidth usage for camera streams")

                    if "automation" in domains_map:
                        suggestions["related_commands"].append("Check automation complexity: ha-cli automations read <id> --porcelain")

                    # Add system-wide insights
                    if health_info and health_info.get("entities", 0) > 1000:
                        suggestions["monitoring_recommendations"].append("Large Home Assistant instance - monitor overall system performance")

                    # Add domain diversity insights
                    if len(domains_map) > 8:
                        suggestions["detected_issues"].append(f"High domain diversity ({len(domains_map)} domains) may indicate dashboard complexity")
                        suggestions["performance_optimizations"].append("Consider organizing by function rather than mixing all domains")
                    
                    # Add workflow recommendations
                    workflow_recommendations = create_workflow_recommendations(
                        "dashboards entities",
                        {
                            "total_entities": len(entities),
                            "domain_breakdown": domain_breakdown,
                            "dashboard_url_path": url_path or "default"
                        },
                        health_info
                    )
                    suggestions.update(workflow_recommendations)
                    
                    # Detect advanced issues
                    advanced_issues = detect_advanced_issues("dashboards entities", entity_data, metadata, health_info)
                    if advanced_issues:
                        suggestions.setdefault("detected_issues", []).extend(advanced_issues)
                    
                    porcelain_output = formatter.success(entity_data, metadata, suggestions)
                    write_output(porcelain_output)
                    
                elif json_output:
                    json_str = json.dumps(entities, indent=2)
                    write_output(json_str)
                    
                else:
                    # Enhanced output with view information
                    if not entities:
                        console.print("No entities found in dashboard")
                        return
                    
                    # Get entity locations to show where each entity appears
                    entity_locations = await service.get_entity_references_with_location(url_path)
                    
                    console.print(f"[cyan]Found {len(entities)} unique entities:[/cyan]")

                    # Group by domain
                    domains: dict[str, List[str]] = {}
                    for entity in sorted(entities):
                        domain = entity.split(".", 1)[0]
                        if domain not in domains:
                            domains[domain] = []
                        domains[domain].append(entity)
                    
                    # Display grouped with location info
                    for domain in sorted(domains.keys()):
                        console.print(f"\n[yellow]{domain}:[/yellow]")
                        for entity in domains[domain]:
                            # Get locations for this entity
                            locations = entity_locations.get(entity, [])
                            dashboard_name = url_path or "default"
                            
                            # Filter to show only views within this dashboard
                            views = []
                            for loc in locations:
                                if loc.startswith(f"{dashboard_name}/"):
                                    view_name = loc.split('/', 1)[1]
                                    views.append(view_name)
                            
                            view_str = f" [dim](views: {', '.join(views)})[/dim]" if views else ""
                            
                            console.print(f"  • {entity}{view_str}")
                            
        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                write_output(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise
    
    asyncio.run(run_async_command(_entities(), command="dashboards entities"))


@app.command()
def create(
    dashboard_id: str = typer.Argument(..., help="Unique dashboard ID"),
    url_path: str = typer.Argument(..., help="URL path for the dashboard"),
    title: str = typer.Argument(..., help="Dashboard title"),
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    icon: str | None = typer.Option(None, "--icon", "-i", help="Icon (e.g., mdi:view-dashboard)"),
    no_sidebar: bool = typer.Option(False, "--no-sidebar", help="Don't show in sidebar"),
    require_admin: bool = typer.Option(False, "--require-admin", help="Require admin access"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Create a new dashboard."""
    setup_logging(debug)
    
    async def _create() -> None:
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = DashboardService(client)
            
            await service.create_dashboard(
                dashboard_id=dashboard_id,
                url_path=url_path,
                title=title,
                icon=icon,
                show_in_sidebar=not no_sidebar,
                require_admin=require_admin,
            )
            
            console.print(f"[green]✓ Dashboard '{dashboard_id}' created successfully[/green]")
            console.print(f"  URL: /lovelace/{url_path}")
    
    asyncio.run(run_async_command(_create(), command="dashboards create"))


@app.command()
def delete(
    dashboard_id: str = typer.Argument(..., help="Dashboard ID to delete"),
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Delete a dashboard."""
    setup_logging(debug)
    
    async def _delete() -> None:
        if not force:
            confirm = typer.confirm(f"Are you sure you want to delete dashboard '{dashboard_id}'?")
            if not confirm:
                console.print("[yellow]Deletion cancelled[/yellow]")
                return
        
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = DashboardService(client)
            await service.delete_dashboard(dashboard_id)
            
            console.print(f"[green]✓ Dashboard '{dashboard_id}' deleted successfully[/green]")
    
    asyncio.run(run_async_command(_delete(), command="dashboards delete"))


@app.command()
def views(
    url_path: str = typer.Argument(None, help="Dashboard URL path (blank for default)"),
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token or env var name"),
    timeout: int = typer.Option(10, "--timeout", help="Request timeout"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all views within a dashboard."""
    setup_logging(debug)
    
    async def _views() -> None:
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = DashboardService(client)
            config = await service.get_dashboard(url_path)
            
            dashboard_name = url_path or "default"
            views: List[dict[str, Any]] = []

            # Extract views from config
            if hasattr(config, 'views') and config.views:
                for view in config.views:
                    view_dict: dict[str, Any] = view.model_dump() if hasattr(view, 'model_dump') else dict(view)
                    view_info: dict[str, Any] = {
                        'title': view_dict.get('title', 'Untitled'),
                        'path': view_dict.get('path', ''),
                        'icon': view_dict.get('icon', ''),
                        'cards': len(view_dict.get('cards', [])),
                        'full_path': f"/lovelace/{view_dict.get('path', '')}" if view_dict.get('path') else f"/lovelace/{dashboard_name}"
                    }

                    # Count entities in view
                    entity_count = 0
                    if 'cards' in view_dict:
                        for card in view_dict['cards']:
                            card_entities = service._extract_entities_from_card(card)
                            entity_count += len(card_entities)
                    view_info['entities'] = entity_count

                    views.append(view_info)
            
            if json_output:
                json_str = json.dumps(views, indent=2)
                write_output(json_str)
            else:
                if not views:
                    console.print(f"No views found in dashboard '{dashboard_name}'")
                    return
                
                # Create table
                table = Table(title=f"Views in {dashboard_name} dashboard")
                table.add_column("Title", style="cyan")
                table.add_column("Path", style="yellow")
                table.add_column("Icon", style="green")
                table.add_column("Cards", style="magenta", justify="right")
                table.add_column("Entities", style="red", justify="right")
                table.add_column("URL", style="blue")
                
                for view_item in views:
                    table.add_row(
                        view_item['title'],
                        view_item['path'] or "(home)",
                        view_item['icon'] or "none",
                        str(view_item['cards']),
                        str(view_item['entities']),
                        view_item['full_path']
                    )

                console.print(table)
                console.print(f"\n[cyan]Total views:[/cyan] {len(views)}")
                console.print(f"[cyan]Total entities:[/cyan] {sum(v['entities'] for v in views)}")
    
    asyncio.run(run_async_command(_views(), command="dashboards views"))


@app.command()
def screenshot(
    dashboard: str = typer.Argument(..., help="Dashboard URL path (e.g., room-lounge, mobile-home)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path (default: /tmp/dashboard-{name}-{timestamp}.png)"),
    width: int = typer.Option(1024, "--width", "-W", help="Viewport width in pixels"),
    height: int = typer.Option(768, "--height", "-H", help="Viewport height in pixels"),
    wait: int = typer.Option(5, "--wait", "-w", help="Seconds to wait for rendering after page load"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Capture a screenshot of a dashboard for visual verification.

    This command navigates to the specified dashboard, waits for it to render,
    and captures a screenshot. Useful for verifying dashboard changes after deployment.

    Examples:
        ha-cli dashboards screenshot room-lounge
        ha-cli dashboards screenshot mobile-home --output /tmp/mobile.png
        ha-cli dashboards screenshot room-office --width 1280 --height 800
    """
    setup_logging(debug)

    from .screenshot import capture_dashboard_screenshot

    async def _screenshot() -> None:
        try:
            output_path = await capture_dashboard_screenshot(
                dashboard_name=dashboard,
                output_path=output,
                viewport_width=width,
                viewport_height=height,
                wait_seconds=wait,
            )
            console.print(f"[green]Screenshot saved:[/green] {output_path}")
            console.print(f"\n[dim]View with: Read tool or 'open {output_path}'[/dim]")
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(EXIT_USAGE_ERROR)
        except Exception as e:
            console.print(f"[red]Screenshot failed:[/red] {e}")
            if debug:
                import traceback
                traceback.print_exc()
            sys.exit(EXIT_HA_ERROR)

    asyncio.run(run_async_command(_screenshot(), command="dashboards screenshot"))


@app.command()
def version() -> None:
    """Show version information."""
    from ... import __version__

    console.print(f"ha-cli dashboards version {__version__}")
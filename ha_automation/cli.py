"""Command-line interface for Home Assistant Automation management using Typer."""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from .client import HAClient
from .exceptions import (
    EXIT_HA_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_USAGE_ERROR,
    HAAutomationError,
)
from .service import AutomationCRUD, AutomationWS
from .utils import (
    get_config_path,
    get_token_from_env,
    load_config,
    save_config,
)

# Initialize Typer app
app = typer.Typer(
    name="ha-automation",
    help="Command-line helper for managing Home Assistant automations",
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


def get_client_config(
    url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: int = 10,
) -> tuple[str, str]:
    """Get client configuration from args, env, config file, or prompt.
    
    Args:
        url: HA URL from command line
        token: Token from command line
        timeout: Request timeout
        
    Returns:
        Tuple of (url, token)
    """
    # 1. Try command line args
    if url and token:
        return url, get_token_from_env(token)
    
    # 2. Try environment variables
    if not url:
        url = os.environ.get("HA_URL", os.environ.get("HOME_ASSISTANT_URL"))
    if not token:
        token = os.environ.get("HA_TOKEN", os.environ.get("HOME_ASSISTANT_TOKEN"))
    
    if url and token:
        return url, get_token_from_env(token)
    
    # 3. Try config file
    config_path = get_config_path()
    if config_path.exists():
        config = load_config(config_path)
        if not url:
            url = config.get("url")
        if not token:
            token = config.get("token")
    
    if url and token:
        return url, get_token_from_env(token)
    
    # 4. Interactive prompt
    if not url:
        url = typer.prompt("Home Assistant URL", default="http://homeassistant.local:8123")
    if not token:
        token = typer.prompt("Access Token", hide_input=True)
    
    # Save to config for next time
    config_path.parent.mkdir(parents=True, exist_ok=True)
    save_config(config_path, {"url": url, "token": token})
    
    return url, get_token_from_env(token)


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
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    storage: Annotated[Optional[str], typer.Option("--storage", help="Filter by storage type: 'ui', 'file', or 'all' (default)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """List all automations."""
    setup_logging(debug)
    
    async def _list():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            from .storage.unified_automation_service import UnifiedAutomationService
            from .storage.automation_type_detector import AutomationTypeDetector, StorageType
            
            service = UnifiedAutomationService(client)
            detector = AutomationTypeDetector()
            
            # Determine filter
            storage_filter = None
            if storage:
                if storage.lower() == "ui":
                    storage_filter = StorageType.UI
                elif storage.lower() == "file":
                    storage_filter = StorageType.FILE
                elif storage.lower() != "all":
                    console.print(f"[red]Error:[/red] Invalid storage filter: {storage}. Use 'ui', 'file', or 'all'")
                    sys.exit(EXIT_USAGE_ERROR)
            
            automations = await service.list_all()
            
            # Filter by storage type if requested
            if storage_filter:
                filtered = []
                for automation in automations:
                    if detector.detect_storage_type(automation) == storage_filter:
                        filtered.append(automation)
                automations = filtered
            
            if json_output:
                data = [automation.to_json_dict() for automation in automations]
                print(json.dumps(data, indent=2))
            else:
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
                
                ui_count = 0
                file_count = 0
                
                for automation in automations:
                    last_triggered = "Never"
                    if automation.last_triggered:
                        last_triggered = automation.last_triggered.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Detect storage type
                    storage_type = detector.detect_storage_type(automation)
                    storage_display = "UI" if storage_type == StorageType.UI else "File"
                    
                    if storage_type == StorageType.UI:
                        ui_count += 1
                    else:
                        file_count += 1
                    
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
    
    asyncio.run(run_async_command(_list()))


@app.command()
def create(
    file: Annotated[Path, typer.Argument(help="YAML or JSON file with automation")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    storage: Annotated[Optional[str], typer.Option("--storage", help="Storage type: 'ui' or 'file' (auto-detect if not specified)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created without actually creating")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Create new automation from file."""
    setup_logging(debug)
    
    if not file.exists():
        console.print(f"[red]Error:[/red] File not found: {file}")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _create():
        # Load and validate the automation first
        from .models import Automation
        from .storage.unified_automation_service import UnifiedAutomationService
        from .storage.automation_type_detector import StorageType
        
        try:
            if file.suffix in [".yaml", ".yml"]:
                automation = Automation.from_yaml_file(str(file))
            else:
                import json
                with open(file, "r") as f:
                    data = json.load(f)
                automation = Automation(**data)
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to parse file: {e}")
            sys.exit(EXIT_USAGE_ERROR)
        
        # Determine storage type
        storage_type = None
        if storage:
            if storage.lower() == "ui":
                storage_type = StorageType.UI
            elif storage.lower() == "file":
                storage_type = StorageType.FILE
            else:
                console.print(f"[red]Error:[/red] Invalid storage type: {storage}. Use 'ui' or 'file'")
                sys.exit(EXIT_USAGE_ERROR)
        
        if dry_run:
            console.print("[yellow]DRY RUN:[/yellow] Would create automation:")
            console.print(f"  Alias: {automation.alias}")
            console.print(f"  Mode: {automation.mode}")
            console.print(f"  Triggers: {len(automation.trigger)}")
            console.print(f"  Actions: {len(automation.action)}")
            if automation.condition:
                console.print(f"  Conditions: {len(automation.condition)}")
            if storage_type:
                console.print(f"  Storage: {storage_type.value}")
            else:
                console.print("  Storage: auto-detect")
            console.print("\n[dim]Full YAML:[/dim]")
            console.print(automation.to_yaml())
            return
        
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = UnifiedAutomationService(client)
            automation_id = await service.create(automation, storage_type=storage_type)
            console.print(f"[green]✓[/green] Created automation with ID: {automation_id}")
    
    asyncio.run(run_async_command(_create()))


@app.command()
def read(
    automation_id: Annotated[str, typer.Argument(help="Automation ID")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Read single automation details."""
    setup_logging(debug)
    
    async def _read():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            crud = AutomationCRUD(client)
            automation = await crud.get_automation(automation_id)
            
            if json_output:
                print(json.dumps(automation.to_json_dict(), indent=2))
            else:
                console.print(f"[bold]Automation: {automation.alias}[/bold]")
                console.print(f"ID: {automation.id}")
                console.print(f"Mode: {automation.mode}")
                if automation.last_triggered:
                    console.print(f"Last Triggered: {automation.last_triggered}")
                
                console.print(f"\nTriggers: {len(automation.trigger)}")
                console.print(f"Conditions: {len(automation.condition or [])}")
                console.print(f"Actions: {len(automation.action)}")
                
                if debug:
                    console.print("\n[dim]Full YAML:[/dim]")
                    console.print(automation.to_yaml())
    
    asyncio.run(run_async_command(_read()))


@app.command()
def update(
    automation_id: Annotated[str, typer.Argument(help="Automation ID")],
    file: Annotated[Path, typer.Argument(help="YAML or JSON file with updated automation")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be updated without actually updating")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Update existing automation from file."""
    setup_logging(debug)
    
    if not file.exists():
        console.print(f"[red]Error:[/red] File not found: {file}")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _update():
        # Load and validate the automation first
        from .models import Automation
        from .storage.unified_automation_service import UnifiedAutomationService
        
        try:
            if file.suffix in [".yaml", ".yml"]:
                automation = Automation.from_yaml_file(str(file))
            else:
                import json
                with open(file, "r") as f:
                    data = json.load(f)
                automation = Automation(**data)
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to parse file: {e}")
            sys.exit(EXIT_USAGE_ERROR)
        
        # Set the ID for the update
        automation.id = automation_id
        
        if dry_run:
            console.print(f"[yellow]DRY RUN:[/yellow] Would update automation {automation_id} with:")
            console.print(f"  Alias: {automation.alias}")
            console.print(f"  Mode: {automation.mode}")
            console.print(f"  Triggers: {len(automation.trigger)}")
            console.print(f"  Actions: {len(automation.action)}")
            if automation.condition:
                console.print(f"  Conditions: {len(automation.condition)}")
            console.print("\n[dim]Full YAML:[/dim]")
            console.print(automation.to_yaml())
            return
        
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = UnifiedAutomationService(client)
            await service.update(automation_id, automation)
            console.print(f"[green]✓[/green] Updated automation {automation_id}")
    
    asyncio.run(run_async_command(_update()))


@app.command()
def delete(
    automation_id: Annotated[str, typer.Argument(help="Automation ID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be deleted without actually deleting")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Delete automation."""
    setup_logging(debug)
    
    async def _delete():
        from .storage.unified_automation_service import UnifiedAutomationService
        from .storage.automation_type_detector import AutomationTypeDetector
        
        if dry_run:
            console.print(f"[yellow]DRY RUN:[/yellow] Would delete automation {automation_id}")
            # Try to get automation details for better dry-run output
            try:
                url_final, token_final = get_client_config(url, token)
                async with HAClient(url_final, token_final, timeout) as client:
                    service = UnifiedAutomationService(client)
                    detector = AutomationTypeDetector()
                    automation = await service.read(automation_id)
                    storage_type = detector.detect_storage_type(automation)
                    console.print(f"  Current alias: {automation.alias}")
                    console.print(f"  Current mode: {automation.mode}")
                    console.print(f"  Storage type: {storage_type.value}")
                    console.print(f"  Components: {len(automation.trigger)} triggers, {len(automation.action)} actions")
            except Exception:
                console.print(f"  (Could not fetch current details for {automation_id})")
            return
        
        if not force:
            confirm = typer.confirm(f"Delete automation {automation_id}?")
            if not confirm:
                console.print("Cancelled")
                return
        
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = UnifiedAutomationService(client)
            await service.delete(automation_id)
            console.print(f"[yellow]✓[/yellow] Deleted automation {automation_id}")
    
    asyncio.run(run_async_command(_delete()))


@app.command()
def enable(
    automation_id: Annotated[str, typer.Argument(help="Automation ID")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Enable automation."""
    setup_logging(debug)
    
    async def _enable():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            ws = AutomationWS(client)
            await ws.enable_automation(automation_id)
            console.print(f"[green]✓[/green] Enabled automation {automation_id}")
    
    asyncio.run(run_async_command(_enable()))


@app.command()
def disable(
    automation_id: Annotated[str, typer.Argument(help="Automation ID")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Disable automation."""
    setup_logging(debug)
    
    async def _disable():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            ws = AutomationWS(client)
            await ws.disable_automation(automation_id)
            console.print(f"[yellow]✓[/yellow] Disabled automation {automation_id}")
    
    asyncio.run(run_async_command(_disable()))


@app.command()
def reload(
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Reload all automations."""
    setup_logging(debug)
    
    async def _reload():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            ws = AutomationWS(client)
            await ws.reload_automations()
            console.print("[green]✓[/green] Reloaded all automations")
    
    asyncio.run(run_async_command(_reload()))


@app.command()
def version() -> None:
    """Show version information."""
    from . import __version__
    
    console.print(f"ha-automation version {__version__}")


@app.command()
def monitor(
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Follow mode - show live updates")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Monitor automation states and executions in real-time."""
    setup_logging(debug)
    
    async def _monitor():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            from .monitor import AutomationMonitor
            
            monitor = AutomationMonitor(client)
            await monitor.start_monitoring()
            
            console.print("[green]✓[/green] Started monitoring automations...")
            
            if follow:
                # Live monitoring mode
                console.print("Press Ctrl+C to stop monitoring\n")
                
                # Track state changes
                def on_state_change(automation_id: str, state):
                    status = "[green]ON[/green]" if state.is_enabled else "[red]OFF[/red]"
                    console.print(f"[yellow]State Change:[/yellow] {automation_id} is now {status}")
                
                # Track executions
                def on_execution(event):
                    console.print(f"[cyan]Execution:[/cyan] {event.automation_id} triggered at {event.timestamp.strftime('%H:%M:%S')}")
                    if debug and event.trigger:
                        console.print(f"  → {event.get_trigger_description()}")
                
                monitor.add_state_listener(on_state_change)
                monitor.add_execution_listener(on_execution)
                
                try:
                    # Keep monitoring until interrupted
                    await asyncio.Event().wait()
                except KeyboardInterrupt:
                    pass
                finally:
                    await monitor.stop_monitoring()
                    console.print("\n[yellow]✓[/yellow] Stopped monitoring")
            else:
                # One-time status display
                await asyncio.sleep(1)  # Give it a moment to collect initial data
                
                states = monitor.get_all_states()
                metrics = monitor.get_all_metrics()
                
                table = Table(title="Automation Status")
                table.add_column("ID", style="cyan")
                table.add_column("Status", style="white")
                table.add_column("Last Triggered", style="green")
                table.add_column("Executions/Hour", style="yellow")
                
                for automation_id, state in states.items():
                    metric = metrics.get(automation_id, {})
                    status = "[green]ON[/green]" if state.is_enabled else "[red]OFF[/red]"
                    last_exec = metric.get("last_execution", "Never")
                    if last_exec != "Never":
                        last_exec = last_exec.split("T")[1].split(".")[0]  # Extract time
                    
                    table.add_row(
                        automation_id,
                        status,
                        last_exec,
                        str(metric.get("executions_per_hour", 0.0)),
                    )
                
                console.print(table)
                await monitor.stop_monitoring()
    
    asyncio.run(run_async_command(_monitor()))


@app.command()
def test_trigger(
    trigger_file: Annotated[Path, typer.Argument(help="YAML file with trigger configuration")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Test timeout in seconds")] = 60,
    max_events: Annotated[int, typer.Option("--max-events", help="Maximum events to collect")] = 10,
    interactive: Annotated[bool, typer.Option("--interactive", "-i", help="Interactive mode")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Test automation triggers interactively."""
    setup_logging(debug)
    
    if not trigger_file.exists():
        console.print(f"[red]Error:[/red] File not found: {trigger_file}")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _test_trigger():
        # Load trigger configuration
        import ruamel.yaml
        yaml = ruamel.yaml.YAML()
        
        try:
            with open(trigger_file, "r") as f:
                trigger_config = yaml.load(f)
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to parse trigger file: {e}")
            sys.exit(EXIT_USAGE_ERROR)
        
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            from .trigger_tester import TriggerTester
            
            tester = TriggerTester(client)
            
            # Validate trigger
            errors = tester.validate_trigger_config(trigger_config)
            if errors:
                console.print("[red]Trigger validation errors:[/red]")
                for error in errors:
                    console.print(f"  • {error}")
                sys.exit(EXIT_USAGE_ERROR)
            
            console.print(f"[green]✓[/green] Testing trigger: {trigger_config.get('platform', 'unknown')}")
            
            if interactive:
                # Interactive mode - show events as they happen
                console.print("Waiting for trigger events... Press Ctrl+C to stop\n")
                
                try:
                    event_count = 0
                    async for event in tester.test_trigger_interactive(trigger_config):
                        event_count += 1
                        console.print(f"[cyan]Event {event_count}:[/cyan] {event.get_trigger_description()}")
                        if debug:
                            console.print(f"  Variables: {json.dumps(event.variables, indent=2)}")
                        
                        if event_count >= max_events:
                            console.print(f"\n[yellow]Reached maximum events ({max_events})[/yellow]")
                            break
                except KeyboardInterrupt:
                    console.print("\n[yellow]Test interrupted[/yellow]")
            else:
                # Batch mode - collect events and show summary
                console.print(f"Collecting trigger events for up to {timeout} seconds...")
                
                result = await tester.test_trigger(trigger_config, timeout=float(timeout), max_events=max_events)
                
                if result.success:
                    console.print(f"\n[green]✓ Test successful![/green]")
                    console.print(f"Collected {len(result.events_received)} events in {result.duration:.1f}s")
                    
                    if result.events_received:
                        console.print("\nEvents received:")
                        for i, event in enumerate(result.events_received, 1):
                            console.print(f"  {i}. {event.get_trigger_description()}")
                else:
                    console.print(f"\n[red]✗ Test failed![/red]")
                    console.print(f"Error: {result.error}")
    
    asyncio.run(run_async_command(_test_trigger()))


@app.command()
def events(
    event_type: Annotated[Optional[str], typer.Argument(help="Event type to filter (e.g., 'state_changed')")] = None,
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    automations_only: Annotated[bool, typer.Option("--automations-only", help="Only show automation events")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Stream Home Assistant events in real-time."""
    setup_logging(debug)
    
    async def _events():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            console.print(f"[green]✓[/green] Connected to Home Assistant")
            console.print("Streaming events... Press Ctrl+C to stop\n")
            
            try:
                if automations_only:
                    # Stream only automation events
                    async for event in client.subscribe_automation_events():
                        data = event.get("data", {})
                        entity_id = data.get("entity_id", "unknown")
                        old_state = data.get("old_state", {}).get("state", "?")
                        new_state = data.get("new_state", {}).get("state", "?")
                        
                        console.print(f"[cyan]{datetime.now().strftime('%H:%M:%S')}[/cyan] {entity_id}: {old_state} → {new_state}")
                else:
                    # Stream all events or filtered by type
                    async for event in client.subscribe_events(event_type):
                        event_type_name = event.get("event_type", "unknown")
                        data = event.get("data", {})
                        
                        console.print(f"[cyan]{datetime.now().strftime('%H:%M:%S')}[/cyan] Event: {event_type_name}")
                        if debug and data:
                            console.print(f"  Data: {json.dumps(data, indent=2)}")
                        elif data:
                            # Show key data fields
                            if "entity_id" in data:
                                console.print(f"  Entity: {data['entity_id']}")
                            if "domain" in data and "service" in data:
                                console.print(f"  Service: {data['domain']}.{data['service']}")
            except KeyboardInterrupt:
                console.print("\n[yellow]✓[/yellow] Stopped streaming events")
    
    asyncio.run(run_async_command(_events()))


@app.command()
def migrate(
    automation_id: Annotated[str, typer.Argument(help="Automation ID to migrate")],
    target: Annotated[str, typer.Argument(help="Target storage: 'ui' or 'file'")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be migrated without actually migrating")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Migrate automation between UI and file-based storage."""
    setup_logging(debug)
    
    # Validate target
    if target.lower() not in ["ui", "file"]:
        console.print(f"[red]Error:[/red] Invalid target storage: {target}. Use 'ui' or 'file'")
        sys.exit(EXIT_USAGE_ERROR)
    
    async def _migrate():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            from .storage.unified_automation_service import UnifiedAutomationService
            from .storage.automation_type_detector import AutomationTypeDetector, StorageType
            
            service = UnifiedAutomationService(client)
            detector = AutomationTypeDetector()
            
            # Get the automation
            try:
                automation = await service.read(automation_id)
            except Exception as e:
                console.print(f"[red]Error:[/red] Failed to read automation {automation_id}: {e}")
                sys.exit(EXIT_HA_ERROR)
            
            # Detect current storage type
            current_storage = detector.detect_storage_type(automation)
            target_storage = StorageType.UI if target.lower() == "ui" else StorageType.FILE
            
            if current_storage == target_storage:
                console.print(f"[yellow]Automation {automation_id} is already in {target} storage[/yellow]")
                return
            
            if dry_run:
                console.print("[yellow]DRY RUN:[/yellow] Would migrate automation:")
                console.print(f"  ID: {automation.id}")
                console.print(f"  Alias: {automation.alias}")
                console.print(f"  Current storage: {current_storage.value}")
                console.print(f"  Target storage: {target_storage.value}")
                return
            
            if not force:
                confirm = typer.confirm(
                    f"Migrate '{automation.alias}' from {current_storage.value} to {target_storage.value} storage?"
                )
                if not confirm:
                    console.print("Cancelled")
                    return
            
            try:
                new_id = await service.migrate(automation_id, target_storage)
                console.print(f"[green]✓[/green] Migrated automation to {target} storage")
                if new_id != automation_id:
                    console.print(f"  New ID: {new_id}")
            except Exception as e:
                console.print(f"[red]Error:[/red] Failed to migrate automation: {e}")
                sys.exit(EXIT_HA_ERROR)
    
    asyncio.run(run_async_command(_migrate()))


@app.command()
def control(
    action: Annotated[str, typer.Argument(help="Action to perform: enable, disable, trigger, toggle")],
    entity_ids: Annotated[str, typer.Argument(help="Comma-separated automation entity IDs")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Control automations via WebSocket (enable/disable/trigger/toggle)."""
    setup_logging(debug)
    
    # Validate action
    valid_actions = ["enable", "disable", "trigger", "toggle"]
    if action not in valid_actions:
        console.print(f"[red]Error:[/red] Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}")
        sys.exit(EXIT_USAGE_ERROR)
    
    # Parse entity IDs
    entity_list = [e.strip() for e in entity_ids.split(",")]
    
    # Map actions to service names
    service_map = {
        "enable": "turn_on",
        "disable": "turn_off",
        "trigger": "trigger",
        "toggle": "toggle",
    }
    
    async def _control():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            service = service_map[action]
            
            # Add automation. prefix if not present
            full_entity_ids = []
            for entity_id in entity_list:
                if not entity_id.startswith("automation."):
                    entity_id = f"automation.{entity_id}"
                full_entity_ids.append(entity_id)
            
            try:
                await client.call_automation_service(service, full_entity_ids)
                
                action_past = {
                    "enable": "enabled",
                    "disable": "disabled",
                    "trigger": "triggered",
                    "toggle": "toggled",
                }[action]
                
                console.print(f"[green]✓[/green] Successfully {action_past} {len(full_entity_ids)} automation(s)")
                for entity_id in full_entity_ids:
                    console.print(f"  • {entity_id}")
            except Exception as e:
                console.print(f"[red]Error:[/red] Failed to {action} automations: {e}")
                sys.exit(EXIT_HA_ERROR)
    
    asyncio.run(run_async_command(_control()))


def main() -> None:
    """Main entry point."""
    app()
"""Command-line interface for Home Assistant Automation management using Typer."""

import asyncio
import json
import logging
import os
import sys
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
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """List all automations."""
    setup_logging(debug)
    
    async def _list():
        url_final, token_final = get_client_config(url, token)
        
        async with HAClient(url_final, token_final, timeout) as client:
            crud = AutomationCRUD(client)
            
            if json_output:
                data = await crud.list_automations(json_output=True)
                print(json.dumps(data, indent=2))
            else:
                automations = await crud.list_automations()
                
                if not automations:
                    console.print("No automations found")
                    return
                
                # Create table
                table = Table(title="Home Assistant Automations")
                table.add_column("ID", style="cyan")
                table.add_column("Alias", style="white")
                table.add_column("Mode", style="yellow")
                table.add_column("Last Triggered", style="green")
                
                for automation in automations:
                    last_triggered = "Never"
                    if automation.last_triggered:
                        last_triggered = automation.last_triggered.strftime("%Y-%m-%d %H:%M:%S")
                    
                    table.add_row(
                        automation.id or "N/A",
                        automation.alias,
                        automation.mode,
                        last_triggered,
                    )
                
                console.print(table)
                console.print(f"\nTotal: {len(automations)} automations")
    
    asyncio.run(run_async_command(_list()))


@app.command()
def create(
    file: Annotated[Path, typer.Argument(help="YAML or JSON file with automation")],
    url: Annotated[Optional[str], typer.Option("--url", "-u", help="Home Assistant URL")] = None,
    token: Annotated[Optional[str], typer.Option("--token", "-t", help="Access token or env var name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout")] = 10,
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
        
        if dry_run:
            console.print("[yellow]DRY RUN:[/yellow] Would create automation:")
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
            crud = AutomationCRUD(client)
            automation_id = await crud.create_automation(str(file))
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
            crud = AutomationCRUD(client)
            await crud.update_automation(automation_id, str(file))
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
        if dry_run:
            console.print(f"[yellow]DRY RUN:[/yellow] Would delete automation {automation_id}")
            # Try to get automation details for better dry-run output
            try:
                url_final, token_final = get_client_config(url, token)
                async with HAClient(url_final, token_final, timeout) as client:
                    crud = AutomationCRUD(client)
                    automation = await crud.get_automation(automation_id)
                    console.print(f"  Current alias: {automation.alias}")
                    console.print(f"  Current mode: {automation.mode}")
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
            crud = AutomationCRUD(client)
            await crud.delete_automation(automation_id)
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


def main() -> None:
    """Main entry point."""
    app()
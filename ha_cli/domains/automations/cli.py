"""Automation CLI commands for ha-cli.

This module provides the main entry point for the automations CLI,
registering commands from the commands/ submodules:
- list_cmd: List automations
- read_cmd: Read automation details
- control_cmd: Enable, disable, reload operations
- crud_cmd: Create, update, delete operations
"""

import typer
from rich.console import Console

from .commands.control_cmd import disable, enable, reload
from .commands.crud_cmd import create, delete, update
from .commands.list_cmd import list_automations
from .commands.read_cmd import read

# Initialize Typer app
app = typer.Typer(
    name="automations",
    help="Manage Home Assistant automations",
    add_completion=True,
)

# Console for rich output
console = Console()

# Register commands from submodules
# Note: Using command decorator to rename 'list_automations' to 'list'
# since 'list' is a Python builtin
app.command(name="list")(list_automations)
app.command(name="read")(read)
app.command(name="enable")(enable)
app.command(name="disable")(disable)
app.command(name="reload")(reload)
app.command(name="create")(create)
app.command(name="update")(update)
app.command(name="delete")(delete)


@app.command()
def version() -> None:
    """Show version information."""
    from ... import __version__

    console.print(f"ha-cli automations version {__version__}")

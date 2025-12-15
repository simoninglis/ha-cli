"""Root CLI definition for ha-cli."""

import typer
from rich import print

app = typer.Typer(
    name="ha-cli",
    help="Multi-domain command-line tool for managing Home Assistant configurations",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show version information."""
    from . import __version__
    print(f"ha-cli version {__version__}")


# Import subcommands
from .domains.areas import cli as areas_cli
from .domains.audit import cli as audit_cli
from .domains.automations import cli as automations_cli
from .domains.dashboards import cli as dashboards_cli
from .domains.deconz import cli as deconz_cli
from .domains.entities import cli as entities_cli
from .domains.system import cli as system_cli

# Add subcommands
app.add_typer(areas_cli.app, name="areas")
app.add_typer(audit_cli.app, name="audit")
app.add_typer(automations_cli.app, name="automations")
app.add_typer(dashboards_cli.app, name="dashboards")
app.add_typer(deconz_cli.app, name="deconz")
app.add_typer(entities_cli.app, name="entities")
app.add_typer(system_cli.app, name="system")
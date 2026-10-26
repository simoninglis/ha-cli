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
from .domains.cloud import cli as cloud_cli
from .domains.dashboards import cli as dashboards_cli
from .domains.deconz import cli as deconz_cli
from .domains.entities import cli as entities_cli
from .domains.events import cli as events_cli
from .domains.hacs import cli as hacs_cli
from .domains.integrations import cli as integrations_cli
from .domains.labels import cli as labels_cli
from .domains.repairs import cli as repairs_cli
from .domains.system import cli as system_cli
from .domains.zones import cli as zones_cli

# Add subcommands
app.add_typer(areas_cli.app, name="areas")
app.add_typer(audit_cli.app, name="audit")
app.add_typer(automations_cli.app, name="automations")
app.add_typer(cloud_cli.app, name="cloud")
app.add_typer(dashboards_cli.app, name="dashboards")
app.add_typer(deconz_cli.app, name="deconz")
app.add_typer(entities_cli.app, name="entities")
app.add_typer(events_cli.app, name="events")
app.add_typer(hacs_cli.app, name="hacs")
app.add_typer(integrations_cli.app, name="integrations")
app.add_typer(labels_cli.app, name="labels")
app.add_typer(repairs_cli.app, name="repairs")
app.add_typer(system_cli.app, name="system")
app.add_typer(zones_cli.app, name="zones")
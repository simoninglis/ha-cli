"""CLI commands for repairs domain."""

import asyncio
import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from ...common.cli_utils import (
    run_async_command,
    set_porcelain_mode,
    setup_logging,
    write_output,
)
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_USAGE_ERROR, NotFoundError
from ...common.porcelain import PorcelainFormatter
from .service import RepairService

app = typer.Typer(
    name="repairs",
    help="View Home Assistant system repair notices",
    no_args_is_help=True,
)

console = Console()

# Severity color mapping
SEVERITY_COLORS = {
    "critical": "red bold",
    "error": "red",
    "warning": "yellow",
}


def _parse_repair_id(repair_id: str) -> tuple[str, str]:
    """Parse domain/issue_id string into components.

    Args:
        repair_id: String in format "domain/issue_id"

    Returns:
        Tuple of (domain, issue_id)

    Raises:
        typer.BadParameter: If format is invalid
    """
    if "/" not in repair_id:
        raise typer.BadParameter(
            f"Invalid repair ID format: '{repair_id}'. Expected format: domain/issue_id"
        )
    parts = repair_id.split("/", 1)
    return parts[0], parts[1]


@app.command("list")
def list_repairs(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    include_ignored: bool = typer.Option(
        False, "--all", "-a", help="Include ignored/dismissed repairs"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List all active repair notices."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _list() -> None:
        formatter = PorcelainFormatter("repairs list") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = RepairService(client)
            repairs = await service.list_repairs(include_ignored=include_ignored)

            if porcelain:
                assert formatter is not None
                data = [r.to_dict() for r in repairs]
                summary = await service.get_summary()
                output = formatter.success(
                    data,
                    metadata={
                        "total_count": len(repairs),
                        **summary,
                    },
                    suggestions={
                        "common_actions": [
                            "View repair details: ha-cli repairs show <domain>/<issue_id>",
                            "Ignore repair: ha-cli repairs ignore <domain>/<issue_id>",
                        ]
                    },
                )
                write_output(output)
            elif json_output:
                data = [r.to_dict() for r in repairs]
                write_output(json.dumps(data, indent=2))
            else:
                if not repairs:
                    console.print("[green]No active repairs found[/green]")
                    return

                table = Table(title="Home Assistant Repairs")
                table.add_column("Severity", style="bold")
                table.add_column("Domain", style="cyan")
                table.add_column("Issue ID")
                table.add_column("Fixable", justify="center")
                table.add_column("Created", justify="right")

                for repair in repairs:
                    severity_style = SEVERITY_COLORS.get(repair.severity, "white")
                    table.add_row(
                        f"[{severity_style}]{repair.severity.upper()}[/{severity_style}]",
                        repair.domain,
                        repair.issue_id,
                        "Yes" if repair.is_fixable else "No",
                        repair.created_display,
                    )

                console.print(table)

                # Summary line
                summary = await service.get_summary()
                parts = []
                if summary["critical_count"]:
                    parts.append(f"{summary['critical_count']} critical")
                if summary["error_count"]:
                    parts.append(f"{summary['error_count']} errors")
                if summary["warning_count"]:
                    parts.append(f"{summary['warning_count']} warnings")

                summary_text = ", ".join(parts) if parts else "0 issues"
                console.print(f"\nTotal: {len(repairs)} repairs ({summary_text})")

    asyncio.run(run_async_command(_list(), command="repairs list"))


@app.command("show")
def show_repair(
    repair_id: str = typer.Argument(
        ..., help="Repair ID in format domain/issue_id"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show details for a specific repair."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    domain, issue_id = _parse_repair_id(repair_id)

    async def _show() -> None:
        formatter = PorcelainFormatter("repairs show") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = RepairService(client)
            repair = await service.get_repair(domain, issue_id)

            if not repair:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(
                        f"Repair '{repair_id}' not found",
                        error_code="NOT_FOUND",
                    )
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] Repair '{repair_id}' not found")
                sys.exit(EXIT_USAGE_ERROR)

            if porcelain:
                assert formatter is not None
                suggestions_list = [
                    "List all repairs: ha-cli repairs list",
                ]
                if repair.active:
                    suggestions_list.insert(
                        0, f"Ignore repair: ha-cli repairs ignore {repair.full_id}"
                    )
                else:
                    suggestions_list.insert(
                        0, f"Unignore repair: ha-cli repairs unignore {repair.full_id}"
                    )
                if repair.learn_more_url:
                    suggestions_list.append(f"Learn more: {repair.learn_more_url}")

                output = formatter.success(
                    repair.to_dict(),
                    metadata={"repair_id": repair.full_id},
                    suggestions={"common_actions": suggestions_list},
                )
                write_output(output)
            elif json_output:
                write_output(json.dumps(repair.to_dict(), indent=2))
            else:
                severity_style = SEVERITY_COLORS.get(repair.severity, "white")
                console.print(f"\n[bold cyan]Repair: {repair.full_id}[/bold cyan]")
                console.print(
                    f"  Severity: [{severity_style}]{repair.severity.upper()}[/{severity_style}]"
                )
                console.print(f"  Domain: {repair.domain}")
                console.print(f"  Issue ID: {repair.issue_id}")
                console.print(f"  Active: {'Yes' if repair.active else 'No (ignored)'}")
                console.print(
                    f"  Fixable: {'Yes' if repair.is_fixable else 'No' if repair.is_fixable is False else 'Unknown'}"
                )
                console.print(f"  Persistent: {'Yes' if repair.is_persistent else 'No'}")
                console.print(f"  Created: {repair.created_display}")

                if repair.breaks_in_ha_version:
                    console.print(
                        f"  [yellow]Breaks in HA version: {repair.breaks_in_ha_version}[/yellow]"
                    )
                if repair.issue_domain:
                    console.print(f"  Issue Domain: {repair.issue_domain}")
                if repair.learn_more_url:
                    console.print(f"\n  [dim]Learn more: {repair.learn_more_url}[/dim]")

    asyncio.run(run_async_command(_show(), command="repairs show"))


@app.command("ignore")
def ignore_repair(
    repair_id: str = typer.Argument(
        ..., help="Repair ID in format domain/issue_id"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Mark a repair as ignored/dismissed."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    domain, issue_id = _parse_repair_id(repair_id)

    async def _ignore() -> None:
        formatter = PorcelainFormatter("repairs ignore") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = RepairService(client)

            try:
                await service.ignore_repair(domain, issue_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {"domain": domain, "issue_id": issue_id, "ignored": True},
                        metadata={"repair_id": f"{domain}/{issue_id}", "action": "ignored"},
                        suggestions={
                            "common_actions": [
                                "List all repairs: ha-cli repairs list",
                                f"Unignore: ha-cli repairs unignore {domain}/{issue_id}",
                            ]
                        },
                    )
                    write_output(output)
                else:
                    console.print(
                        f"[green]Ignored repair '[bold]{domain}/{issue_id}[/bold]'[/green]"
                    )
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {e}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_ignore(), command="repairs ignore"))


@app.command("unignore")
def unignore_repair(
    repair_id: str = typer.Argument(
        ..., help="Repair ID in format domain/issue_id"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Unmark a repair as ignored (make it active again)."""
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    domain, issue_id = _parse_repair_id(repair_id)

    async def _unignore() -> None:
        formatter = PorcelainFormatter("repairs unignore") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = RepairService(client)

            try:
                await service.unignore_repair(domain, issue_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {"domain": domain, "issue_id": issue_id, "ignored": False},
                        metadata={"repair_id": f"{domain}/{issue_id}", "action": "unignored"},
                        suggestions={
                            "common_actions": [
                                "List all repairs: ha-cli repairs list",
                                f"Ignore again: ha-cli repairs ignore {domain}/{issue_id}",
                            ]
                        },
                    )
                    write_output(output)
                else:
                    console.print(
                        f"[green]Unignored repair '[bold]{domain}/{issue_id}[/bold]'[/green]"
                    )
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {e}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_unignore(), command="repairs unignore"))


@app.command("version")
def version() -> None:
    """Show repairs domain version."""
    from ... import __version__

    console.print(f"ha-cli repairs version {__version__}")

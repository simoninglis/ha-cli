"""CLI commands for repairs domain."""

import asyncio
import json
import sys

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ...common.cli_utils import (
    run_async_command,
    set_porcelain_mode,
    setup_logging,
    write_output,
)
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_USAGE_ERROR, NotFoundError, ValidationError
from ...common.porcelain import PorcelainFormatter, create_home_assistant_metadata
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


def _parse_repair_id(repair_id: str) -> tuple[str, str] | None:
    """Parse domain/issue_id string into components.

    Args:
        repair_id: String in format "domain/issue_id"

    Returns:
        Tuple of (domain, issue_id) or None if format is invalid
    """
    repair_id = repair_id.strip()
    if "/" not in repair_id:
        return None
    parts = repair_id.split("/", 1)
    domain = parts[0].strip()
    issue_id = parts[1].strip()
    # Both parts must be non-empty
    if not domain or not issue_id:
        return None
    return domain, issue_id


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
            try:
                repairs = await service.list_repairs(include_ignored=include_ignored)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

            if porcelain:
                assert formatter is not None
                data = [r.to_dict() for r in repairs]
                # Compute summary from displayed repairs for consistency
                critical_count = sum(1 for r in repairs if r.severity == "critical")
                error_count = sum(1 for r in repairs if r.severity == "error")
                warning_count = sum(1 for r in repairs if r.severity == "warning")
                # Use 'is True' for type-strict counting (None != True)
                fixable_count = sum(1 for r in repairs if r.is_fixable is True)
                affected_domains = sorted({r.domain for r in repairs})
                output = formatter.success(
                    data,
                    metadata={
                        "total_count": len(repairs),
                        "critical_count": critical_count,
                        "error_count": error_count,
                        "warning_count": warning_count,
                        "fixable_count": fixable_count,
                        "affected_domains": affected_domains,
                        "include_ignored": include_ignored,
                        "home_assistant": create_home_assistant_metadata(
                            url_final, "websocket"
                        ),
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
                    # Handle None (unknown) separately from False (not fixable)
                    if repair.is_fixable is True:
                        fixable_display = "Yes"
                    elif repair.is_fixable is False:
                        fixable_display = "No"
                    else:
                        fixable_display = "-"
                    table.add_row(
                        f"[{severity_style}]{repair.severity.upper()}[/{severity_style}]",
                        escape(repair.domain),
                        escape(repair.issue_id),
                        fixable_display,
                        repair.created_display,
                    )

                console.print(table)

                # Summary line - compute from displayed repairs, not get_summary()
                critical_count = sum(1 for r in repairs if r.severity == "critical")
                error_count = sum(1 for r in repairs if r.severity == "error")
                warning_count = sum(1 for r in repairs if r.severity == "warning")

                parts = []
                if critical_count:
                    parts.append(f"{critical_count} critical")
                if error_count:
                    parts.append(f"{error_count} errors")
                if warning_count:
                    parts.append(f"{warning_count} warnings")

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

    async def _show() -> None:
        formatter = PorcelainFormatter("repairs show") if porcelain else None

        # Parse repair_id inside async for porcelain error handling
        parsed = _parse_repair_id(repair_id)
        if parsed is None:
            if porcelain:
                assert formatter is not None
                error_msg = f"Invalid repair ID format: '{repair_id}'. Expected: domain/issue_id"
                output = formatter.error(error_msg, error_code="INVALID_FORMAT")
                write_output(output)
            else:
                error_msg = f"Invalid repair ID format: '{escape(repair_id)}'. Expected: domain/issue_id"
                console.print(f"[red]Error:[/red] {error_msg}")
            sys.exit(EXIT_USAGE_ERROR)

        domain, issue_id = parsed
        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = RepairService(client)
            try:
                repair = await service.get_repair(domain, issue_id)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

            if not repair:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(
                        f"Repair '{repair_id}' not found",
                        error_code="NOT_FOUND",
                    )
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] Repair '{escape(repair_id)}' not found")
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
                    metadata={
                        "repair_id": repair.full_id,
                        "home_assistant": create_home_assistant_metadata(
                            url_final, "websocket"
                        ),
                    },
                    suggestions={"common_actions": suggestions_list},
                )
                write_output(output)
            elif json_output:
                write_output(json.dumps(repair.to_dict(), indent=2))
            else:
                severity_style = SEVERITY_COLORS.get(repair.severity, "white")
                console.print(f"\n[bold cyan]Repair: {escape(repair.full_id)}[/bold cyan]")
                console.print(
                    f"  Severity: [{severity_style}]{repair.severity.upper()}[/{severity_style}]"
                )
                console.print(f"  Domain: {escape(repair.domain)}")
                console.print(f"  Issue ID: {escape(repair.issue_id)}")
                console.print(f"  Active: {'Yes' if repair.active else 'No (ignored)'}")
                console.print(
                    f"  Fixable: {'Yes' if repair.is_fixable else 'No' if repair.is_fixable is False else 'Unknown'}"
                )
                console.print(f"  Persistent: {'Yes' if repair.is_persistent else 'No'}")
                console.print(f"  Created: {repair.created_display}")

                if repair.breaks_in_ha_version:
                    console.print(
                        f"  [yellow]Breaks in HA version: {escape(repair.breaks_in_ha_version)}[/yellow]"
                    )
                if repair.issue_domain:
                    console.print(f"  Issue Domain: {escape(repair.issue_domain)}")
                if repair.learn_more_url:
                    console.print(f"\n  [dim]Learn more: {escape(repair.learn_more_url)}[/dim]")

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

    async def _ignore() -> None:
        formatter = PorcelainFormatter("repairs ignore") if porcelain else None

        # Parse repair_id inside async for porcelain error handling
        parsed = _parse_repair_id(repair_id)
        if parsed is None:
            if porcelain:
                assert formatter is not None
                error_msg = f"Invalid repair ID format: '{repair_id}'. Expected: domain/issue_id"
                output = formatter.error(error_msg, error_code="INVALID_FORMAT")
                write_output(output)
            else:
                error_msg = f"Invalid repair ID format: '{escape(repair_id)}'. Expected: domain/issue_id"
                console.print(f"[red]Error:[/red] {error_msg}")
            sys.exit(EXIT_USAGE_ERROR)

        domain, issue_id = parsed
        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = RepairService(client)

            try:
                await service.ignore_repair(domain, issue_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {"domain": domain, "issue_id": issue_id, "ignored": True},
                        metadata={
                            "repair_id": f"{domain}/{issue_id}",
                            "action": "ignored",
                            "home_assistant": create_home_assistant_metadata(
                                url_final, "websocket"
                            ),
                        },
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
                        f"[green]Ignored repair '[bold]{escape(domain)}/{escape(issue_id)}[/bold]'[/green]"
                    )
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
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

    async def _unignore() -> None:
        formatter = PorcelainFormatter("repairs unignore") if porcelain else None

        # Parse repair_id inside async for porcelain error handling
        parsed = _parse_repair_id(repair_id)
        if parsed is None:
            if porcelain:
                assert formatter is not None
                error_msg = f"Invalid repair ID format: '{repair_id}'. Expected: domain/issue_id"
                output = formatter.error(error_msg, error_code="INVALID_FORMAT")
                write_output(output)
            else:
                error_msg = f"Invalid repair ID format: '{escape(repair_id)}'. Expected: domain/issue_id"
                console.print(f"[red]Error:[/red] {error_msg}")
            sys.exit(EXIT_USAGE_ERROR)

        domain, issue_id = parsed
        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = RepairService(client)

            try:
                await service.unignore_repair(domain, issue_id)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {"domain": domain, "issue_id": issue_id, "ignored": False},
                        metadata={
                            "repair_id": f"{domain}/{issue_id}",
                            "action": "unignored",
                            "home_assistant": create_home_assistant_metadata(
                                url_final, "websocket"
                            ),
                        },
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
                        f"[green]Unignored repair '[bold]{escape(domain)}/{escape(issue_id)}[/bold]'[/green]"
                    )
            except NotFoundError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="NOT_FOUND")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)
            except ValidationError as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="VALIDATION_ERROR")
                    write_output(output)
                else:
                    console.print(f"[red]Error:[/red] {escape(str(e))}")
                sys.exit(EXIT_USAGE_ERROR)

    asyncio.run(run_async_command(_unignore(), command="repairs unignore"))


@app.command("version")
def version() -> None:
    """Show repairs domain version."""
    from ... import __version__

    console.print(f"ha-cli repairs version {__version__}")

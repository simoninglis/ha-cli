"""Audit CLI commands for ha-cli."""

import asyncio
import logging
import sys

import typer
from rich.console import Console
from rich.table import Table

from ...common.cli_utils import run_async_command, setup_logging, write_output
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_USAGE_ERROR
from ...common.porcelain import (
    PorcelainFormatter,
    create_home_assistant_metadata,
)
from .models import AuditResult, AuditSeverity
from .service import AuditService

# Initialize Typer app
app = typer.Typer(
    name="audit",
    help="Audit Home Assistant for tech debt and issues",
    add_completion=True,
)

# Console for rich output
console = Console()

# Logging setup
logger = logging.getLogger(__name__)


def _output_result(
    result: AuditResult,
    porcelain: bool,
    formatter: PorcelainFormatter | None,
    url: str,
) -> None:
    """Output audit result in appropriate format.

    Args:
        result: The audit result
        porcelain: Whether to use porcelain format
        formatter: Porcelain formatter instance
        url: Home Assistant URL
    """
    if porcelain and formatter:
        # Porcelain output
        metadata = {
            "check": result.check_name,
            "findings_count": len(result.findings),
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "info_count": result.info_count,
            "execution_time_ms": result.execution_time_ms,
            "exit_code": result.exit_code,
            "home_assistant": create_home_assistant_metadata(url, "websocket"),
        }

        suggestions = {
            "common_actions": [
                f"View full report: ha-cli audit {result.check_name} --porcelain",
                "Filter by severity: ha-cli audit all --severity warning",
            ],
            "troubleshooting": [],
        }

        if result.error_count > 0:
            suggestions["troubleshooting"].append(
                f"Address {result.error_count} errors first - these indicate broken configurations"
            )
        if result.warning_count > 0:
            suggestions["troubleshooting"].append(
                f"Review {result.warning_count} warnings - these may indicate issues"
            )

        porcelain_output = formatter.success(
            data=result.to_dict(),
            metadata=metadata,
            suggestions=suggestions,
        )
        write_output(porcelain_output)
    else:
        # Rich table output
        if result.error:
            console.print(f"[red]Error:[/red] {result.error}")
            return

        if not result.findings:
            console.print(f"[green]✓ No issues found in {result.check_name} check[/green]")
            return

        # Create table
        table = Table(title=f"Audit: {result.check_name}")
        table.add_column("Severity", style="bold")
        table.add_column("Entity/Automation")
        table.add_column("Message")
        table.add_column("Action")

        for finding in result.findings:
            severity_style = {
                AuditSeverity.ERROR: "red",
                AuditSeverity.WARNING: "yellow",
                AuditSeverity.INFO: "blue",
            }.get(finding.severity, "white")

            entity = finding.entity_id or finding.automation_id or "-"
            table.add_row(
                f"[{severity_style}]{finding.severity.value.upper()}[/{severity_style}]",
                entity,
                finding.message,
                finding.suggested_action or "-",
            )

        console.print(table)

        # Summary
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"  Total findings: {len(result.findings)}")
        console.print(f"  Errors: [red]{result.error_count}[/red]")
        console.print(f"  Warnings: [yellow]{result.warning_count}[/yellow]")
        console.print(f"  Info: [blue]{result.info_count}[/blue]")
        console.print(f"  Execution time: {result.execution_time_ms:.0f}ms")


@app.command("dead-entities")
def dead_entities(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token"),
    timeout: int = typer.Option(30, "--timeout", help="Request timeout"),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Filter by domain"),
    integration: str | None = typer.Option(None, "--integration", "-i", help="Filter by integration"),
    ignore_pattern: list[str] | None = typer.Option(None, "--ignore-pattern", help="Regex patterns to ignore"),
    include_disabled: bool = typer.Option(False, "--include-disabled", help="Include disabled entities"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Find dead/unavailable entities."""
    setup_logging(debug)

    async def _check() -> int:
        formatter = PorcelainFormatter("audit dead-entities") if porcelain else None
        url_final, token_final = get_client_config(url, token)

        try:
            async with HAClient(url_final, token_final, timeout) as client:
                service = AuditService(client)
                result = await service.check_dead_entities(
                    domain=domain,
                    integration=integration,
                    ignore_patterns=list(ignore_pattern) if ignore_pattern else None,
                    include_disabled=include_disabled,
                )

                _output_result(result, porcelain, formatter, url_final)
                return result.exit_code

        except Exception as e:
            if formatter:
                error_output = formatter.error(str(e))
                write_output(error_output)
            else:
                console.print(f"[red]Error:[/red] {e}")
            return 2

    exit_code = asyncio.run(run_async_command(_check()))
    sys.exit(exit_code)


@app.command("duplicates")
def duplicates(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token"),
    timeout: int = typer.Option(30, "--timeout", help="Request timeout"),
    show_disabled: bool = typer.Option(False, "--show-disabled", help="Include disabled entities"),
    ignore_pattern: list[str] | None = typer.Option(None, "--ignore-pattern", help="Regex patterns to ignore"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Find duplicate entities with _2, _3 suffixes."""
    setup_logging(debug)

    async def _check() -> int:
        formatter = PorcelainFormatter("audit duplicates") if porcelain else None
        url_final, token_final = get_client_config(url, token)

        try:
            async with HAClient(url_final, token_final, timeout) as client:
                service = AuditService(client)
                result = await service.check_duplicates(
                    show_disabled=show_disabled,
                    ignore_patterns=list(ignore_pattern) if ignore_pattern else None,
                )

                _output_result(result, porcelain, formatter, url_final)
                return result.exit_code

        except Exception as e:
            if formatter:
                error_output = formatter.error(str(e))
                write_output(error_output)
            else:
                console.print(f"[red]Error:[/red] {e}")
            return 2

    exit_code = asyncio.run(run_async_command(_check()))
    sys.exit(exit_code)


@app.command("broken-automations")
def broken_automations(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token"),
    timeout: int = typer.Option(30, "--timeout", help="Request timeout"),
    ignore_pattern: list[str] | None = typer.Option(None, "--ignore-pattern", help="Regex patterns to ignore"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Find automations referencing non-existent entities."""
    setup_logging(debug)

    async def _check() -> int:
        formatter = PorcelainFormatter("audit broken-automations") if porcelain else None
        url_final, token_final = get_client_config(url, token)

        try:
            async with HAClient(url_final, token_final, timeout) as client:
                service = AuditService(client)
                result = await service.check_broken_automations(
                    ignore_patterns=list(ignore_pattern) if ignore_pattern else None,
                )

                _output_result(result, porcelain, formatter, url_final)
                return result.exit_code

        except Exception as e:
            if formatter:
                error_output = formatter.error(str(e))
                write_output(error_output)
            else:
                console.print(f"[red]Error:[/red] {e}")
            return 2

    exit_code = asyncio.run(run_async_command(_check()))
    sys.exit(exit_code)


@app.command("fragile-automations")
def fragile_automations(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token"),
    timeout: int = typer.Option(30, "--timeout", help="Request timeout"),
    ignore_pattern: list[str] | None = typer.Option(None, "--ignore-pattern", help="Regex patterns to ignore"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Find automations referencing unavailable entities."""
    setup_logging(debug)

    async def _check() -> int:
        formatter = PorcelainFormatter("audit fragile-automations") if porcelain else None
        url_final, token_final = get_client_config(url, token)

        try:
            async with HAClient(url_final, token_final, timeout) as client:
                service = AuditService(client)
                result = await service.check_fragile_automations(
                    ignore_patterns=list(ignore_pattern) if ignore_pattern else None,
                )

                _output_result(result, porcelain, formatter, url_final)
                return result.exit_code

        except Exception as e:
            if formatter:
                error_output = formatter.error(str(e))
                write_output(error_output)
            else:
                console.print(f"[red]Error:[/red] {e}")
            return 2

    exit_code = asyncio.run(run_async_command(_check()))
    sys.exit(exit_code)


@app.command("unused-automations")
def unused_automations(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token"),
    timeout: int = typer.Option(30, "--timeout", help="Request timeout"),
    days: int = typer.Option(90, "--days", help="Days threshold for unused"),
    include_disabled: bool = typer.Option(False, "--include-disabled", help="Include disabled automations"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Find automations not triggered in N days."""
    setup_logging(debug)

    async def _check() -> int:
        formatter = PorcelainFormatter("audit unused-automations") if porcelain else None
        url_final, token_final = get_client_config(url, token)

        try:
            async with HAClient(url_final, token_final, timeout) as client:
                service = AuditService(client)
                result = await service.check_unused_automations(
                    days=days,
                    include_disabled=include_disabled,
                )

                _output_result(result, porcelain, formatter, url_final)
                return result.exit_code

        except Exception as e:
            if formatter:
                error_output = formatter.error(str(e))
                write_output(error_output)
            else:
                console.print(f"[red]Error:[/red] {e}")
            return 2

    exit_code = asyncio.run(run_async_command(_check()))
    sys.exit(exit_code)


@app.command("trigger-stats")
def trigger_stats(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token"),
    timeout: int = typer.Option(30, "--timeout", help="Request timeout"),
    top: int = typer.Option(20, "--top", help="Number of results to show"),
    days: int | None = typer.Option(None, "--days", help="Filter to last N days"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show automation trigger statistics."""
    setup_logging(debug)

    async def _check() -> int:
        formatter = PorcelainFormatter("audit trigger-stats") if porcelain else None
        url_final, token_final = get_client_config(url, token)

        try:
            async with HAClient(url_final, token_final, timeout) as client:
                service = AuditService(client)
                result = await service.check_trigger_stats(
                    top=top,
                    days=days,
                )

                _output_result(result, porcelain, formatter, url_final)
                return result.exit_code

        except Exception as e:
            if formatter:
                error_output = formatter.error(str(e))
                write_output(error_output)
            else:
                console.print(f"[red]Error:[/red] {e}")
            return 2

    exit_code = asyncio.run(run_async_command(_check()))
    sys.exit(exit_code)


@app.command("integrations")
def integrations(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token"),
    timeout: int = typer.Option(30, "--timeout", help="Request timeout"),
    ignore_pattern: list[str] | None = typer.Option(None, "--ignore-pattern", help="Regex patterns to ignore"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show health summary per integration."""
    setup_logging(debug)

    async def _check() -> int:
        formatter = PorcelainFormatter("audit integrations") if porcelain else None
        url_final, token_final = get_client_config(url, token)

        try:
            async with HAClient(url_final, token_final, timeout) as client:
                service = AuditService(client)
                result = await service.check_integrations(
                    ignore_patterns=list(ignore_pattern) if ignore_pattern else None,
                )

                if porcelain and formatter:
                    _output_result(result, porcelain, formatter, url_final)
                else:
                    # Custom table output for integrations
                    if result.error:
                        console.print(f"[red]Error:[/red] {result.error}")
                        return 2

                    table = Table(title="Integration Health Summary")
                    table.add_column("Integration")
                    table.add_column("Total", justify="right")
                    table.add_column("Available", justify="right")
                    table.add_column("Unavailable", justify="right")
                    table.add_column("Health %", justify="right")
                    table.add_column("Status")

                    for integration_data in result.summary.get("integrations", []):
                        health = integration_data["health_percentage"]
                        if health >= 90:
                            status = "[green]Healthy[/green]"
                        elif health >= 50:
                            status = "[yellow]Warning[/yellow]"
                        else:
                            status = "[red]Critical[/red]"

                        table.add_row(
                            integration_data["integration"],
                            str(integration_data["total_entities"]),
                            str(integration_data["available_entities"]),
                            str(integration_data["unavailable_entities"]),
                            f"{health:.1f}%",
                            status,
                        )

                    console.print(table)

                    # Show findings for unhealthy integrations
                    if result.findings:
                        console.print(f"\n[bold]Issues found ({len(result.findings)}):[/bold]")
                        for finding in result.findings:
                            console.print(f"  • {finding.message}")

                return result.exit_code

        except Exception as e:
            if formatter:
                error_output = formatter.error(str(e))
                write_output(error_output)
            else:
                console.print(f"[red]Error:[/red] {e}")
            return 2

    exit_code = asyncio.run(run_async_command(_check()))
    sys.exit(exit_code)


@app.command("all")
def all_checks(
    url: str | None = typer.Option(None, "--url", "-u", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="Access token"),
    timeout: int = typer.Option(60, "--timeout", help="Request timeout"),
    severity: str | None = typer.Option(None, "--severity", help="Filter by severity (error, warning, info)"),
    ignore_pattern: list[str] | None = typer.Option(None, "--ignore-pattern", help="Regex patterns to ignore"),
    days: int = typer.Option(90, "--days", help="Days threshold for unused automations"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output in porcelain format"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Run all audit checks."""
    setup_logging(debug)

    # Parse severity filter
    severity_filter: AuditSeverity | None = None
    if severity:
        try:
            severity_filter = AuditSeverity(severity.lower())
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid severity '{severity}'. Use: error, warning, or info")
            sys.exit(EXIT_USAGE_ERROR)

    async def _check() -> int:
        formatter = PorcelainFormatter("audit all") if porcelain else None
        url_final, token_final = get_client_config(url, token)

        try:
            async with HAClient(url_final, token_final, timeout) as client:
                service = AuditService(client)
                result = await service.run_all_checks(
                    severity_filter=severity_filter,
                    ignore_patterns=list(ignore_pattern) if ignore_pattern else None,
                    days_threshold=days,
                )

                if porcelain and formatter:
                    _output_result(result, porcelain, formatter, url_final)
                else:
                    # Group findings by category
                    if result.error:
                        console.print(f"[red]Error:[/red] {result.error}")

                    categories: dict[str, list] = {}
                    for finding in result.findings:
                        cat = finding.category
                        if cat not in categories:
                            categories[cat] = []
                        categories[cat].append(finding)

                    if not categories:
                        console.print("[green]✓ No issues found in any check[/green]")
                        return 0

                    # Output by category
                    for category, findings in sorted(categories.items()):
                        console.print(f"\n[bold]== {category.upper()} ({len(findings)} findings) ==[/bold]")

                        table = Table(show_header=True)
                        table.add_column("Severity")
                        table.add_column("Target")
                        table.add_column("Message")

                        for finding in findings[:10]:  # Limit to 10 per category
                            severity_style = {
                                AuditSeverity.ERROR: "red",
                                AuditSeverity.WARNING: "yellow",
                                AuditSeverity.INFO: "blue",
                            }.get(finding.severity, "white")

                            target = finding.entity_id or finding.automation_id or "-"
                            table.add_row(
                                f"[{severity_style}]{finding.severity.value}[/{severity_style}]",
                                target,
                                finding.message[:60] + "..." if len(finding.message) > 60 else finding.message,
                            )

                        console.print(table)

                        if len(findings) > 10:
                            console.print(f"  ... and {len(findings) - 10} more")

                    # Summary
                    console.print(f"\n[bold]{'='*50}[/bold]")
                    console.print("[bold]AUDIT SUMMARY[/bold]")
                    console.print(f"[bold]{'='*50}[/bold]")
                    console.print(f"  Total findings: {len(result.findings)}")
                    console.print(f"  Errors: [red]{result.error_count}[/red]")
                    console.print(f"  Warnings: [yellow]{result.warning_count}[/yellow]")
                    console.print(f"  Info: [blue]{result.info_count}[/blue]")
                    console.print(f"  Execution time: {result.execution_time_ms:.0f}ms")

                    if result.exit_code == 0:
                        console.print("\n[green]Exit code: 0 (clean)[/green]")
                    elif result.exit_code == 1:
                        console.print("\n[yellow]Exit code: 1 (findings present)[/yellow]")
                    else:
                        console.print("\n[red]Exit code: 2 (error)[/red]")

                return result.exit_code

        except Exception as e:
            if formatter:
                error_output = formatter.error(str(e))
                write_output(error_output)
            else:
                console.print(f"[red]Error:[/red] {e}")
            return 2

    exit_code = asyncio.run(run_async_command(_check()))
    sys.exit(exit_code)

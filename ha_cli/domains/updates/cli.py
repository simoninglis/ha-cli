"""CLI commands for the updates domain."""

import asyncio
import json
import sys
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ...common.cli_utils import run_async_command, set_porcelain_mode, setup_logging, write_output
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_HA_ERROR, EXIT_USAGE_ERROR, NotFoundError, ValidationError
from ...common.porcelain import PorcelainFormatter, create_home_assistant_metadata
from .models import AVAILABLE, CHECK_FAILING, STATUS_LABELS, UpdateInfo
from .service import UpdatesService

app = typer.Typer(
    name="updates",
    help="Update entities: list, check, and install with verification",
    no_args_is_help=True,
)

console = Console()

URL_OPT = typer.Option(None, "--url", help="Home Assistant URL")
TOKEN_OPT = typer.Option(
    None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"
)

STATUS_STYLE = {AVAILABLE: "yellow", CHECK_FAILING: "red", "unavailable": "dim", "installing": "cyan", "current": "green"}


def _fail(formatter: PorcelainFormatter | None, message: str, code: str, exit_code: int = EXIT_USAGE_ERROR) -> None:
    if formatter:
        write_output(formatter.error(message, error_code=code))
    else:
        console.print(f"[red]Error:[/red] {escape(message)}")
    sys.exit(exit_code)


def _check_flags(json_output: bool, porcelain: bool) -> None:
    if json_output and porcelain:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)


def _status_text(u: UpdateInfo) -> str:
    style = STATUS_STYLE.get(u.status, "")
    return f"[{style}]{STATUS_LABELS[u.status]}[/{style}]" if style else STATUS_LABELS[u.status]


@app.command("list")
def list_updates(
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    available: bool = typer.Option(False, "--available", help="Only entities with an update to install"),
    problems: bool = typer.Option(False, "--problems", help="Only entities reporting no version or unavailable"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List update entities: installed -> latest, and whether each is actually reporting.

    "No version reported" is not "up to date". For updates the device checks for
    itself (ESPHome Voice PE), it usually means the device can't reach its
    update server: check DNS and egress from its network.

    Examples:
        ha-cli updates list
        ha-cli updates list --available
        ha-cli updates list --problems
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)

    async def _list() -> None:
        formatter = PorcelainFormatter("updates list") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            try:
                updates = await UpdatesService(client).list_updates()
            except ValidationError as e:
                _fail(formatter, str(e), "VALIDATION_ERROR", EXIT_HA_ERROR)
                return
            shown = [
                u for u in updates
                if (not available or u.status == AVAILABLE)
                and (not problems or u.status in (CHECK_FAILING, "unavailable"))
            ]
            counts: dict[str, int] = {}
            for u in updates:
                counts[u.status] = counts.get(u.status, 0) + 1
            if formatter:
                write_output(formatter.success(
                    [u.to_dict() for u in shown],
                    metadata={"total_count": len(updates), "shown_count": len(shown), "status_counts": counts,
                              "home_assistant": create_home_assistant_metadata(url_final, "websocket")},
                    suggestions={"common_actions": ["Install one: ha-cli updates install <entity> --yes"]},
                ))
            elif json_output:
                write_output(json.dumps([u.to_dict() for u in shown], indent=2))
            else:
                if not shown:
                    console.print("[dim]No matching update entities[/dim]")
                    return
                table = Table(title=f"Update entities ({len(shown)} of {len(updates)})")
                table.add_column("Entity", style="cyan", overflow="fold")
                table.add_column("Installed")
                table.add_column("Latest")
                table.add_column("Status")
                for u in shown:
                    table.add_row(escape(u.entity_id), escape(u.installed_version or "-"),
                                  escape(u.latest_version or "-"), _status_text(u))
                console.print(table)
                if counts.get(CHECK_FAILING):
                    console.print(f"[red]{counts[CHECK_FAILING]} reporting no version[/red] "
                                  "[dim]- try: ha-cli updates check <entity>[/dim]")

    asyncio.run(run_async_command(_list(), command="updates list"))


@app.command("check")
def check(
    entity_id: str = typer.Argument(..., help="update.* entity"),
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    wait: float = typer.Option(20.0, "--wait", help="Seconds to wait for the check to report"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Ask an update entity to check now, and show what it reports.

    Examples:
        ha-cli updates check update.home_assistant_voice_09ebde
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)

    async def _check() -> None:
        formatter = PorcelainFormatter("updates check") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = UpdatesService(client)
            try:
                info = await service.check(entity_id, wait=wait)
            except (ValidationError, NotFoundError) as e:
                _fail(formatter, str(e), "NOT_FOUND" if isinstance(e, NotFoundError) else "VALIDATION_ERROR")
                return
            sw = await service.device_sw_version(entity_id)
            data = {**info.to_dict(), "device_sw_version": sw}
            if formatter:
                write_output(formatter.success(data, metadata={
                    "home_assistant": create_home_assistant_metadata(url_final, "websocket")}))
            elif json_output:
                write_output(json.dumps(data, indent=2))
            else:
                console.print(f"[cyan]{escape(info.entity_id)}[/cyan]  "
                              f"{escape(info.installed_version or '-')} -> {escape(info.latest_version or '-')}  "
                              f"{_status_text(info)}")
                if sw:
                    console.print(f"  device reports: {escape(sw)}")
                if info.status == CHECK_FAILING:
                    console.print("[yellow]  Still no version after the check. If the device checks for itself, "
                                  "look at its own logs (DNS / internet access from its network).[/yellow]")

    asyncio.run(run_async_command(_check(), command="updates check"))


@app.command("install")
def install(
    entity_id: str = typer.Argument(..., help="update.* entity"),
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation (required with --porcelain)"),
    timeout: float = typer.Option(900.0, "--timeout", help="Seconds to wait for the install to finish"),
    verify_wait: float = typer.Option(60.0, "--verify-wait", help="Seconds to wait for the new version to be reported"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Install an update, watch it through, and confirm the device now runs the new version.

    The device may restart. Success means the entity and the device both report
    the target version afterwards, not that the install call returned. Exits 3
    if it can't be confirmed.

    Examples:
        ha-cli updates install update.home_assistant_voice_09ebde
        ha-cli updates install update.home_assistant_voice_09ebde --yes --porcelain
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)
    if porcelain and not yes:
        console.print("[red]Error:[/red] --porcelain needs --yes: an install can restart the device, "
                      "so it never runs unconfirmed")
        sys.exit(EXIT_USAGE_ERROR)

    async def _install() -> None:
        formatter = PorcelainFormatter("updates install") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = UpdatesService(client)
            try:
                info = await service.get(entity_id)
            except (ValidationError, NotFoundError) as e:
                _fail(formatter, str(e), "NOT_FOUND" if isinstance(e, NotFoundError) else "VALIDATION_ERROR")
                return
            if info.status != AVAILABLE:
                _fail(formatter, f"{entity_id} has no update to install ({STATUS_LABELS[info.status]})",
                      "VALIDATION_ERROR")
                return
            if not yes:
                console.print(f"[bold]{escape(info.name)}[/bold] ({escape(entity_id)})")
                console.print(f"  {escape(info.installed_version)} -> [yellow]{escape(info.latest_version)}[/yellow]"
                              + (f"  {escape(info.release_url)}" if info.release_url else ""))
                console.print("  The device may restart.")
                if not typer.confirm("Install it?"):
                    console.print("[yellow]Cancelled[/yellow]")
                    return

            shown_pct: list[int] = [-10]

            def progress(entry: dict[str, Any]) -> None:
                if formatter or json_output:
                    return
                if entry["event"] == "state":
                    pct = entry.get("percentage")
                    if isinstance(pct, int | float) and pct >= shown_pct[0] + 10:
                        shown_pct[0] = int(pct)
                        console.print(f"  [{entry['t']:5.1f}s] {int(pct)}%")
                    return
                extra = {k: v for k, v in entry.items() if k not in ("t", "event")}
                tail = "  " + ", ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
                console.print(f"  [{entry['t']:5.1f}s] {escape(entry['event'])}{escape(tail)}")

            try:
                result = await service.install(entity_id, timeout=timeout, verify_wait=verify_wait,
                                               on_change=progress)
            except ValidationError as e:
                _fail(formatter, str(e), "VALIDATION_ERROR")
                return
            data = result.to_dict()
            if formatter:
                if result.verified:
                    write_output(formatter.success(data, metadata={
                        "action": "installed", "verified": True,
                        "home_assistant": create_home_assistant_metadata(url_final, "websocket")}))
                else:
                    write_output(formatter.error(result.problem or "not verified", error_code="NOT_VERIFIED",
                                                 details=data))
                    sys.exit(EXIT_HA_ERROR)
            elif json_output:
                write_output(json.dumps(data, indent=2))
                if not result.verified:
                    sys.exit(EXIT_HA_ERROR)
            else:
                if result.verified:
                    sw = f" (device: {result.device_sw_version})" if result.device_sw_version else ""
                    console.print(f"[green]Installed and confirmed:[/green] {escape(result.target_version)}"
                                  f"{escape(sw)} in {result.duration_seconds:.0f}s")
                else:
                    console.print(f"[red]Not confirmed:[/red] {escape(result.problem or 'unknown')}")
                    sys.exit(EXIT_HA_ERROR)

    asyncio.run(run_async_command(_install(), command="updates install"))

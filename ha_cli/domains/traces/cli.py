"""CLI commands for the traces domain."""

import asyncio
import json
import sys
from datetime import datetime, tzinfo
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
from .models import DOMAINS, TraceDetail, TraceRun
from .service import TracesService, parse_duration, parse_when

app = typer.Typer(
    name="traces",
    help="Automation and script traces: what ran, when, and which step decided it",
    no_args_is_help=True,
)

console = Console()

URL_OPT = typer.Option(None, "--url", help="Home Assistant URL")
TOKEN_OPT = typer.Option(
    None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"
)
JSON_OPT = typer.Option(False, "--json", help="Output as JSON")
PORCELAIN_OPT = typer.Option(False, "--porcelain", help="Machine-readable output")
DEBUG_OPT = typer.Option(False, "--debug", help="Enable debug logging")

_EXECUTION_STYLE = {"finished": "green", "aborted": "yellow", "failed_conditions": "yellow",
                    "error": "red", "cancelled": "dim", "running": "cyan"}


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


def _code(e: Exception) -> tuple[str, int]:
    return ("NOT_FOUND", EXIT_HA_ERROR) if isinstance(e, NotFoundError) else ("VALIDATION_ERROR", EXIT_USAGE_ERROR)


def _clock(when: datetime | None, tz: tzinfo, date: bool = False) -> str:
    if when is None:
        return "-"
    local = when.astimezone(tz)
    return local.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if date else local.strftime("%H:%M:%S.%f")[:-3]


def _execution(run: TraceRun) -> str:
    text = run.execution or run.state or "?"
    return f"[{_EXECUTION_STYLE.get(text, 'white')}]{escape(text)}[/]"


def _attrs(attributes: dict[str, Any], limit: int = 12) -> str:
    items = [f"{k}={v}" for k, v in attributes.items() if k not in ("friendly_name", "icon")]
    more = f" (+{len(items) - limit})" if len(items) > limit else ""
    return escape(", ".join(items[:limit]) + more)


def _print_detail(d: TraceDetail, tz: tzinfo, indent: str = "") -> None:
    run = d.run
    took = f"{run.duration:.3f}s" if run.duration is not None else "running"
    console.print(f"{indent}[bold cyan]{escape(run.target)}[/bold cyan]"
                  + (f"  [dim]{escape(d.alias)}[/dim]" if d.alias else ""))
    console.print(f"{indent}  {_clock(run.start, tz, date=True)}  {_execution(run)}  {took}  "
                  f"last_step={escape(run.last_step or '-')}  [dim]run {run.run_id}[/dim]")
    if d.trigger:
        t = d.trigger
        hold = f" for {t.for_seconds:g}s" if t.for_seconds else ""
        console.print(f"{indent}  trigger: {escape(t.description or '?')}{hold}")
        for label, st in (("from", t.from_state), ("to", t.to_state)):
            if st:
                when = _clock(datetime.fromisoformat(st["last_changed"]), tz) if st.get("last_changed") else "-"
                console.print(f"{indent}    {label:>4} {escape(str(st.get('state')))}  [dim]since {when}[/dim]")
                if st.get("attributes"):
                    console.print(f"{indent}         [dim]{_attrs(st['attributes'])}[/dim]")
    if d.fields:
        console.print(f"{indent}  called with: {escape(json.dumps(d.fields, default=str))}")
    if d.context_id:
        console.print(f"{indent}  [dim]context {d.context_id}"
                      + (f" parent {d.parent_id}" if d.parent_id else "")
                      + (f" user {d.user_id}" if d.user_id else "") + "[/dim]")
    for step in d.steps:
        offset = f"+{(step.at - run.start).total_seconds():7.3f}s" if step.at and run.start else "        -"
        line = f"{indent}  [dim]{offset}[/dim] {escape(step.path):<34} {escape(step.summary())}"
        console.print(line)
        if step.variables:
            console.print(f"{indent}           [dim]vars {escape(json.dumps(step.variables, default=str))[:300]}[/dim]")
        if step.error:
            console.print(f"{indent}           [red]{escape(str(step.error))}[/red]")


@app.command("list")
def list_runs(
    target: str = typer.Argument(..., help="automation.<entity_id or YAML id>, or script.<id>"),
    since: str | None = typer.Option(None, "--since", help="From this time (HH:MM[:SS] today, or a date and time)"),
    until: str | None = typer.Option(None, "--until", help="Up to this time"),
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    json_output: bool = JSON_OPT,
    porcelain: bool = PORCELAIN_OPT,
    debug: bool = DEBUG_OPT,
) -> None:
    """List the stored runs of one automation or script.

    HA keeps only the last few runs (5 unless the automation sets
    stored_traces), so the header says how many are stored and how far back
    they go: "nothing at 14:18" and "14:18 has rolled off" read differently.
    Times are in HA's time zone.

    Examples:
        ha-cli traces list automation.office_ble_away_signal
        ha-cli traces list automation.office_ble_away_signal --since 14:00 --until 14:30
        ha-cli traces list script.office_pc_lock --json
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)

    async def _list() -> None:
        formatter = PorcelainFormatter("traces list") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = TracesService(client)
            tz = await service.time_zone()
            try:
                lo = parse_when(since, tz) if since else None
                hi = parse_when(until, tz) if until else None
                page = await service.page(target, lo, hi)
            except (ValidationError, NotFoundError) as e:
                code, exit_code = _code(e)
                _fail(formatter, str(e), code, exit_code)
                return
            if formatter:
                write_output(formatter.success(page.to_dict(), metadata={
                    "total_count": len(page.runs), "time_zone": str(tz),
                    "home_assistant": create_home_assistant_metadata(url_final, "websocket")}))
                return
            if json_output:
                write_output(json.dumps(page.to_dict(), indent=2))
                return
            title = page.target + (f" ({page.entity_id})" if page.entity_id and page.entity_id != page.target else "")
            days = {r.start.astimezone(tz).date() for r in page.runs if r.start}
            one_day = len(days) == 1
            if one_day:
                title += f"  {next(iter(days)).isoformat()}"
            table = Table(title=escape(title))
            table.add_column("Start", style="cyan", no_wrap=True)
            table.add_column("Took", justify="right", no_wrap=True)
            table.add_column("Execution")
            table.add_column("Last step")
            table.add_column("Trigger", overflow="fold")
            table.add_column("Run id", style="dim", no_wrap=True)
            for r in page.runs:
                table.add_row(_clock(r.start, tz, date=not one_day), f"{r.duration:.3f}s" if r.duration is not None else "-",
                              _execution(r), escape(r.last_step or "-"), escape(r.trigger or "-"), r.run_id)
            console.print(table)
            oldest = _clock(page.oldest, tz, date=True) if page.oldest else "none"
            console.print(f"[dim]{len(page.runs)} shown; {page.stored} stored by HA, oldest {oldest} ({tz})[/dim]")

    asyncio.run(run_async_command(_list(), command="traces list"))


@app.command("show")
def show(
    target: str = typer.Argument(..., help="automation.<entity_id or YAML id>, or script.<id>"),
    run_id: str | None = typer.Argument(None, help="Run id from 'traces list' (default: the latest run)"),
    at: str | None = typer.Option(None, "--at", help="The run nearest this time instead"),
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    json_output: bool = JSON_OPT,
    porcelain: bool = PORCELAIN_OPT,
    debug: bool = DEBUG_OPT,
) -> None:
    """Show one run step by step: what triggered it and what each step decided.

    The trigger's from/to states include their attributes and when they last
    changed, which is usually where the "why" is.

    Examples:
        ha-cli traces show automation.office_ble_away_signal
        ha-cli traces show automation.office_ble_away_signal --at 14:18:09
        ha-cli traces show script.office_pc_lock 1b8b44a532414b8e15c7b302386e3e66 --json
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)
    if run_id and at:
        console.print("[red]Error:[/red] Give a run id or --at, not both")
        sys.exit(EXIT_USAGE_ERROR)

    async def _show() -> None:
        formatter = PorcelainFormatter("traces show") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = TracesService(client)
            tz = await service.time_zone()
            try:
                detail = await service.get(target, run_id, parse_when(at, tz) if at else None)
            except (ValidationError, NotFoundError) as e:
                code, exit_code = _code(e)
                _fail(formatter, str(e), code, exit_code)
                return
            if formatter:
                write_output(formatter.success(detail.to_dict(), metadata={
                    "time_zone": str(tz), "home_assistant": create_home_assistant_metadata(url_final, "websocket")}))
            elif json_output:
                write_output(json.dumps(detail.to_dict(), indent=2, default=str))
            else:
                _print_detail(detail, tz)

    asyncio.run(run_async_command(_show(), command="traces show"))


@app.command("around")
def around(
    when: str = typer.Argument(..., help="HH:MM[:SS] today, or a date and time"),
    window: str = typer.Option("2m", "--window", "-w", help="Either side of the time: 90s, 2m, 1h"),
    domain: list[str] = typer.Option(None, "--domain", "-d", help="automation and/or script (default: both)"),
    brief: bool = typer.Option(False, "--brief", "-b", help="One line per run, no steps"),
    show_all: bool = typer.Option(False, "--all", "-a",
                                  help="Include runs that stopped at their conditions (hidden by default)"),
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    json_output: bool = JSON_OPT,
    porcelain: bool = PORCELAIN_OPT,
    debug: bool = DEBUG_OPT,
) -> None:
    """Every automation and script run near a time, as one timeline.

    Runs that belong together are grouped: a script started by an automation
    shares its context, so the lock script appears under the automation that
    called it. Runs that stopped at their conditions (time-pattern
    automations, mostly) are counted but hidden unless --all: use --all when
    the question is why something did NOT run. Only stored runs are visible;
    the footer says how far back each domain's history reaches.

    Examples:
        ha-cli traces around 14:18:09
        ha-cli traces around 14:24 --window 5m --brief
        ha-cli traces around "2026-11-13 14:18" --domain automation --json
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)
    domains = tuple(domain or DOMAINS)
    bad = [d for d in domains if d not in DOMAINS]
    if bad:
        console.print(f"[red]Error:[/red] --domain must be automation or script, not {escape(', '.join(bad))}")
        sys.exit(EXIT_USAGE_ERROR)

    async def _around() -> None:
        formatter = PorcelainFormatter("traces around") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = TracesService(client)
            tz = await service.time_zone()
            try:
                center = parse_when(when, tz)
                span = parse_duration(window)
                chains, coverage = await service.around(center, span, domains)
            except (ValidationError, NotFoundError) as e:
                code, exit_code = _code(e)
                _fail(formatter, str(e), code, exit_code)
                return
            hidden = 0
            if not show_all:
                kept = [c for c in chains if not all(d.run.execution == "failed_conditions" for d in c)]
                hidden = sum(len(c) for c in chains) - sum(len(c) for c in kept)
                chains = kept
            data = {"center": center.isoformat(), "window_seconds": span.total_seconds(), "coverage": coverage,
                    "hidden_failed_conditions": hidden,
                    "chains": [[d.to_dict() for d in chain] for chain in chains]}
            if formatter:
                write_output(formatter.success(data, metadata={
                    "total_count": sum(len(c) for c in chains), "time_zone": str(tz),
                    "home_assistant": create_home_assistant_metadata(url_final, "websocket")}))
                return
            if json_output:
                write_output(json.dumps(data, indent=2, default=str))
                return
            console.print(f"[bold]Runs from {_clock(center - span, tz)} to {_clock(center + span, tz)}[/bold] "
                          f"[dim]({tz})[/dim]")
            if not chains:
                console.print("  [yellow]No stored runs in this window[/yellow]")
            for chain in chains:
                console.print()
                for i, d in enumerate(chain):
                    indent = "" if i == 0 else "    ↳ "
                    if brief:
                        console.print(f"{indent}{_clock(d.run.start, tz)}  {_execution(d.run)}  "
                                      f"[cyan]{escape(d.run.target)}[/cyan]  last_step={escape(d.run.last_step or '-')}"
                                      + (f"  [dim]{escape(d.trigger.description or '')}[/dim]" if d.trigger else ""))
                    else:
                        _print_detail(d, tz, indent="" if i == 0 else "    ")
            console.print()
            if hidden:
                console.print(f"[dim]{hidden} run(s) that stopped at their conditions hidden (--all to show)[/dim]")
            for dom, cov in coverage.items():
                if dom == "rolled_off_during_read":
                    continue
                oldest = _clock(datetime.fromisoformat(cov["oldest"]), tz, date=True) if cov["oldest"] else "none"
                console.print(f"[dim]{dom}: {cov['stored']} runs stored, oldest {oldest}[/dim]")
            if coverage.get("rolled_off_during_read"):
                console.print(f"[yellow]{coverage['rolled_off_during_read']} run(s) rolled off while reading[/yellow]")
            console.print("[dim]Oldest is across the whole domain: each automation keeps only its own last "
                          "N runs, so a busy one may have dropped runs this window had.[/dim]")

    asyncio.run(run_async_command(_around(), command="traces around"))

"""CLI commands for the traces domain."""

import asyncio
import json
import sys
from datetime import UTC, datetime, tzinfo
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
from .models import DOMAINS, AroundResult, TraceDetail, TraceRun
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
TARGET_ARG = typer.Argument(..., help="automation.<entity_id or YAML id>, automation:<YAML id>, or script.<id>")

# `show --at`: warn when the nearest stored run is this far from the time asked about
FAR_SECONDS = 300

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


def _zone_label(tz: tzinfo | None) -> str:
    return str(tz) if tz else "UTC: HA's time zone couldn't be read"


def _clock(when: datetime | None, tz: tzinfo | None, date: bool = False) -> str:
    if when is None:
        return "-"
    local = when.astimezone(tz or UTC)
    return local.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if date else local.strftime("%H:%M:%S.%f")[:-3]


def _meta(url: str, tz: tzinfo | None, **extra: Any) -> dict[str, Any]:
    return {"time_zone": str(tz) if tz else None, **extra,
            "home_assistant": create_home_assistant_metadata(url, "websocket")}


def _execution(run: TraceRun) -> str:
    text = run.execution or run.state or "?"
    return f"[{_EXECUTION_STYLE.get(text, 'white')}]{escape(text)}[/]"


def _attrs(attributes: dict[str, Any], limit: int = 12) -> str:
    items = [f"{k}={v}" for k, v in attributes.items() if k not in ("friendly_name", "icon")]
    more = f" (+{len(items) - limit})" if len(items) > limit else ""
    return escape(", ".join(items[:limit]) + more)


def _print_detail(d: TraceDetail, tz: tzinfo | None, indent: str = "") -> None:
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
                changed = st.get("last_changed")
                when = _clock(datetime.fromisoformat(changed), tz) if isinstance(changed, str) and changed else "-"
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
        console.print(f"{indent}  [dim]{offset}[/dim] {escape(step.path):<34} {escape(step.summary())}")
        if step.variables:
            console.print(f"{indent}           [dim]vars {escape(json.dumps(step.variables, default=str))[:300]}[/dim]")
        if step.error:
            console.print(f"{indent}           [red]{escape(str(step.error))}[/red]")


def _relation(d: TraceDetail, head: TraceDetail) -> str:
    """How a group member relates to the group's first run."""
    if d.context_id and d.context_id == head.context_id:
        return "↳ same context"
    return "⇢ caused by the group"


@app.command("list")
def list_runs(
    target: str = TARGET_ARG,
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
    stored_traces), so the footer says how many are stored and how far back
    they go: if the oldest is after the time you care about, runs from then
    may have rolled off. Times are in HA's time zone.

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
                write_output(formatter.success(page.to_dict(), metadata=_meta(
                    url_final, tz, total_count=len(page.runs))))
                return
            if json_output:
                write_output(json.dumps(page.to_dict(), indent=2))
                return
            title = page.target + (f" ({page.entity_id})" if page.entity_id and page.entity_id != page.target else "")
            days = {r.start.astimezone(tz or UTC).date() for r in page.runs if r.start}
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
                table.add_row(_clock(r.start, tz, date=not one_day),
                              f"{r.duration:.3f}s" if r.duration is not None else "-",
                              _execution(r), escape(r.last_step or "-"), escape(r.trigger or "-"), r.run_id)
            console.print(table)
            oldest = _clock(page.oldest, tz, date=True) if page.oldest else "none"
            console.print(f"[dim]{len(page.runs)} shown; {page.stored} stored by HA, oldest {oldest} "
                          f"({escape(_zone_label(tz))})[/dim]")

    asyncio.run(run_async_command(_list(), command="traces list"))


@app.command("show")
def show(
    target: str = TARGET_ARG,
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
    changed, which is usually where the "why" is. With --at, the nearest
    stored run is shown with its distance from the time asked about.

    Examples:
        ha-cli traces show automation.office_ble_away_signal
        ha-cli traces show automation.office_ble_away_signal --at 14:18:09
        ha-cli traces show script.office_pc_lock 1b8b44a532414b8e15c7b302386e3e66 --json
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)
    if run_id and at:
        _fail(PorcelainFormatter("traces show") if porcelain else None,
              "Give a run id or --at, not both", "VALIDATION_ERROR")

    async def _show() -> None:
        formatter = PorcelainFormatter("traces show") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = TracesService(client)
            tz = await service.time_zone()
            try:
                when = parse_when(at, tz) if at else None
                detail = await service.get(target, run_id, when)
            except (ValidationError, NotFoundError) as e:
                code, exit_code = _code(e)
                _fail(formatter, str(e), code, exit_code)
                return
            data = detail.to_dict()
            distance = (detail.run.start - when).total_seconds() if when and detail.run.start else None
            if when:
                data["requested_at"] = when.isoformat()
                data["distance_seconds"] = distance
            if formatter:
                write_output(formatter.success(data, metadata=_meta(url_final, tz)))
            elif json_output:
                write_output(json.dumps(data, indent=2, default=str))
            else:
                console.print(f"[dim]Times in {escape(_zone_label(tz))}[/dim]")
                if when is not None and distance is not None:
                    far = abs(distance) > FAR_SECONDS
                    note = f"nearest stored run to {_clock(when, tz, date=True)}: {distance:+.1f}s"
                    console.print(f"[yellow]{escape(note)} - not that time; it may have rolled off "
                                  "(see 'traces list')[/yellow]" if far else f"[dim]{escape(note)}[/dim]")
                _print_detail(detail, tz)

    asyncio.run(run_async_command(_show(), command="traces show"))


def _print_around(result: AroundResult, tz: tzinfo | None, brief: bool, center: datetime) -> None:
    zone = tz or UTC
    dated = result.lo.astimezone(zone).date() != result.hi.astimezone(zone).date() \
        or center.astimezone(zone).date() != datetime.now(zone).date()
    console.print(f"[bold]Runs from {_clock(result.lo, tz, dated)} to {_clock(result.hi, tz, dated)}[/bold] "
                  f"[dim]({escape(_zone_label(tz))})[/dim]")
    for chain in result.chains:
        console.print()
        head = chain[0]
        if len(chain) > 1:
            console.print(f"[dim]context group of {len(chain)} runs[/dim]")
        for d in chain:
            rel = "" if d is head else f"{_relation(d, head)} "
            if brief:
                console.print(f"{'    ' if rel else ''}{rel}{_clock(d.run.start, tz, dated)}  {_execution(d.run)}  "
                              f"[cyan]{escape(d.run.target)}[/cyan]  last_step={escape(d.run.last_step or '-')}"
                              + (f"  [dim]{escape(d.trigger.description or '')}[/dim]" if d.trigger else ""))
            else:
                if rel:
                    console.print(f"    [dim]{rel}[/dim]")
                _print_detail(d, tz, indent="    " if rel else "")
    console.print()
    unread = len(result.rolled_off) + len(result.unreadable)
    if not result.chains:
        if result.hidden_failed_conditions and unread:
            console.print(f"[yellow]Nothing to show: {result.hidden_failed_conditions} run(s) stopped at their "
                          f"conditions (--all shows them) and {unread} couldn't be read (see below)[/yellow]")
        elif result.hidden_failed_conditions:
            console.print(f"[yellow]Only runs that stopped at their conditions are in this window "
                          f"({result.hidden_failed_conditions}): --all shows them[/yellow]")
        elif unread:
            console.print("[yellow]Runs were in this window, but none could be read (see below)[/yellow]")
        else:
            console.print("[yellow]No stored runs start in this window[/yellow]")
    elif result.hidden_failed_conditions:
        console.print(f"[dim]{result.hidden_failed_conditions} run(s) that stopped at their conditions hidden "
                      "(--all to show)[/dim]")
    for label, refs in (("rolled off while reading", result.rolled_off), ("unreadable", result.unreadable)):
        if refs:
            console.print(f"[yellow]{len(refs)} run(s) {label}: "
                          + escape(", ".join(f"{r['target']} {r['run_id']}" for r in refs)) + "[/yellow]")
    if result.possibly_missing:
        names = ", ".join(m["target"] for m in result.possibly_missing[:8])
        more = f" (+{len(result.possibly_missing) - 8})" if len(result.possibly_missing) > 8 else ""
        console.print(f"[yellow]History starts after this window opened for {len(result.possibly_missing)} "
                      f"item(s), so runs of theirs may be missing: {escape(names + more)}[/yellow]")
    stored = ", ".join(f"{d} {n}" for d, n in result.stored.items())
    console.print(f"[dim]Stored runs: {stored}. Each automation and script keeps only its own last N, "
                  "so this can't prove nothing else ran.[/dim]")


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

    Runs that share a context are grouped: a script started by an automation
    shares its context, so the lock script appears with the automation that
    called it. A group is a shared context, not a call tree. Runs that stopped
    at their conditions (time-pattern automations, mostly) are counted but
    hidden unless --all: use --all when the question is why something did NOT
    run. Only stored runs are visible, and the footer names items whose
    history may not reach back to the window.

    Examples:
        ha-cli traces around 14:18:09
        ha-cli traces around 14:24 --window 5m --brief
        ha-cli traces around "2026-11-13 14:18" --domain automation --json
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)
    domains = tuple(dict.fromkeys(domain or DOMAINS))
    bad = [d for d in domains if d not in DOMAINS]
    if bad:
        _fail(PorcelainFormatter("traces around") if porcelain else None,
              f"--domain must be automation or script, not {', '.join(bad)}", "VALIDATION_ERROR")

    async def _around() -> None:
        formatter = PorcelainFormatter("traces around") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = TracesService(client)
            tz = await service.time_zone()
            try:
                center = parse_when(when, tz)
                result = await service.around(center, parse_duration(window), domains)
            except (ValidationError, NotFoundError) as e:
                code, exit_code = _code(e)
                _fail(formatter, str(e), code, exit_code)
                return
            if not show_all:
                kept = [c for c in result.chains if not all(d.run.execution == "failed_conditions" for d in c)]
                result.hidden_failed_conditions = result.shown - sum(len(c) for c in kept)
                result.chains = kept
            data = {"center": center.isoformat(), **result.to_dict()}
            if formatter:
                write_output(formatter.success(data, metadata=_meta(url_final, tz, total_count=result.shown)))
            elif json_output:
                write_output(json.dumps(data, indent=2, default=str))
            else:
                _print_around(result, tz, brief, center)

    asyncio.run(run_async_command(_around(), command="traces around"))

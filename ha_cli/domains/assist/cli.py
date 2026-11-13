"""CLI commands for the assist domain."""

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ...common.cli_utils import run_async_command, set_porcelain_mode, setup_logging, write_output
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_HA_ERROR, EXIT_USAGE_ERROR, NotFoundError, ValidationError
from ...common.porcelain import PorcelainFormatter, create_home_assistant_metadata
from .models import AGENT, LOCAL, AssistResult
from .service import AssistService

app = typer.Typer(
    name="assist",
    help="Assist pipelines: list them, and see what a pipeline or agent does with a phrase",
    no_args_is_help=True,
)
pipelines_app = typer.Typer(name="pipelines", help="Assist pipelines", no_args_is_help=True)
app.add_typer(pipelines_app, name="pipelines")

console = Console()

URL_OPT = typer.Option(None, "--url", help="Home Assistant URL")
TOKEN_OPT = typer.Option(
    None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"
)
YES_OPT = typer.Option(False, "--yes", "-y", help="Don't ask first (required with --porcelain/--json)")

ACTS_WARNING = "These run for real: a command phrase acts on the house."


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


def _phrases(args: list[str] | None, file: Path | None) -> list[str]:
    phrases = list(args or [])
    if file:
        try:
            lines = file.read_text().splitlines()
        except OSError as e:
            console.print(f"[red]Error:[/red] Cannot read {escape(str(file))}: {escape(str(e))}")
            sys.exit(EXIT_USAGE_ERROR)
        phrases += [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not phrases:
        console.print("[red]Error:[/red] Give a phrase, or --file with one phrase per line")
        sys.exit(EXIT_USAGE_ERROR)
    return phrases


def _confirm(phrases: list[str], target: str, yes: bool, machine: bool) -> None:
    if yes:
        return
    if machine:
        console.print("[red]Error:[/red] --porcelain/--json need --yes: " + ACTS_WARNING)
        sys.exit(EXIT_USAGE_ERROR)
    console.print(f"[bold]{len(phrases)} phrase(s) -> {escape(target)}[/bold]  [yellow]{ACTS_WARNING}[/yellow]")
    for p in phrases[:10]:
        console.print(f"  {escape(p)}")
    if len(phrases) > 10:
        console.print(f"  ... and {len(phrases) - 10} more")
    if not typer.confirm("Run them?"):
        console.print("[yellow]Cancelled[/yellow]")
        sys.exit(0)


def _print_result(r: AssistResult) -> None:
    who = {LOCAL: "[green]LOCAL[/green]", AGENT: "[magenta]AGENT[/magenta]"}.get(r.handled_by, "[dim]?[/dim]")
    secs = f"{r.total_seconds:5.2f}s" if r.total_seconds is not None else "    - "
    parts = []
    if r.intent_seconds is not None:
        parts.append(f"intent {r.intent_seconds:.2f}s")
    split = f"  [dim]({', '.join(parts)})[/dim]" if parts else ""
    console.print(f"{who:>24} {secs}  [cyan]{escape(r.text)}[/cyan]{split}")
    if r.error:
        console.print(f"               [red]{escape(r.error)}[/red]")
    else:
        console.print(f"               {escape(r.speech or '(no speech)')}  [dim]{escape(r.response_type or '')}[/dim]")


def _emit(formatter: PorcelainFormatter | None, json_output: bool, results: list[AssistResult], meta: dict) -> None:
    data = [r.to_dict() for r in results]
    if formatter:
        if all(r.ok for r in results):
            write_output(formatter.success(data, metadata=meta))
        else:
            write_output(formatter.error("Some phrases failed", error_code="ASSIST_ERROR", details={"results": data}))
    elif json_output:
        write_output(json.dumps(data, indent=2))
    if not all(r.ok for r in results):
        sys.exit(EXIT_HA_ERROR)


@pipelines_app.command("list")
def pipelines_list(
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List Assist pipelines; the preferred one is marked.

    Examples:
        ha-cli assist pipelines list
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)

    async def _list() -> None:
        formatter = PorcelainFormatter("assist pipelines list") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            try:
                pipelines = await AssistService(client).list_pipelines()
            except ValidationError as e:
                _fail(formatter, str(e), "VALIDATION_ERROR", EXIT_HA_ERROR)
                return
            data = [p.to_dict() for p in pipelines]
            if formatter:
                write_output(formatter.success(data, metadata={
                    "total_count": len(pipelines),
                    "home_assistant": create_home_assistant_metadata(url_final, "websocket")}))
            elif json_output:
                write_output(json.dumps(data, indent=2))
            else:
                table = Table(title="Assist pipelines")
                table.add_column("", width=1)
                table.add_column("Name", style="cyan")
                table.add_column("Agent", overflow="fold")
                table.add_column("STT", overflow="fold")
                table.add_column("TTS", overflow="fold")
                table.add_column("Local first")
                for p in pipelines:
                    tts = f"{p.tts_engine or '-'}" + (f" ({p.tts_voice})" if p.tts_voice else "")
                    table.add_row("*" if p.preferred else "", escape(p.name), escape(p.conversation_engine),
                                  escape(p.stt_engine or "-"), escape(tts), "yes" if p.prefer_local_intents else "no")
                console.print(table)
                console.print("[dim]* preferred: satellites set to 'preferred' follow it[/dim]")

    asyncio.run(run_async_command(_list(), command="assist pipelines list"))


@app.command("test")
def test_pipeline(
    phrases: list[str] = typer.Argument(None, help="Phrases to run (quote each one)"),
    pipeline: str | None = typer.Option(None, "--pipeline", "-p", help="Pipeline name or id (default: preferred)"),
    file: Path | None = typer.Option(None, "--file", "-f", help="One phrase per line; '#' comments"),
    no_tts: bool = typer.Option(False, "--no-tts", help="Stop after the intent (no TTS generated)"),
    timeout: float = typer.Option(60.0, "--timeout", help="Seconds per phrase"),
    yes: bool = YES_OPT,
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Run phrases through a pipeline: who handled each (LOCAL or AGENT), the reply, timings.

    The pipeline runs for real, so a command phrase acts on the house. With
    "prefer local intents", commands are usually handled locally (and work
    offline) while questions go to the agent even when the built-in agent
    could answer them. Exits 3 if any phrase errors.

    Examples:
        ha-cli assist test "turn off the bedroom pendant" --pipeline "GPT Bedroom"
        ha-cli assist test "is the bedroom pendant on" "what is the capital of Peru" -p "GPT Bedroom" --yes
        ha-cli assist test --file bedroom-phrases.txt --pipeline "GPT Bedroom" --yes --porcelain
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)
    texts = _phrases(phrases, file)

    async def _test() -> None:
        formatter = PorcelainFormatter("assist test") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = AssistService(client)
            try:
                chosen = service.find_pipeline(await service.list_pipelines(), pipeline)
            except (ValidationError, NotFoundError) as e:
                _fail(formatter, str(e), "NOT_FOUND" if isinstance(e, NotFoundError) else "VALIDATION_ERROR")
                return
            _confirm(texts, f"pipeline {chosen.name!r} (agent {chosen.conversation_engine})", yes,
                     bool(formatter or json_output))
            results = []
            for text in texts:
                r = await service.run_text(chosen, text, tts=not no_tts, timeout=timeout)
                results.append(r)
                if not formatter and not json_output:
                    _print_result(r)
            _emit(formatter, json_output, results, {
                "pipeline": chosen.name, "pipeline_id": chosen.id, "agent": chosen.conversation_engine,
                "prefer_local_intents": chosen.prefer_local_intents,
                "handled_local": sum(r.handled_by == LOCAL for r in results),
                "handled_agent": sum(r.handled_by == AGENT for r in results),
                "home_assistant": create_home_assistant_metadata(url_final, "websocket")})

    asyncio.run(run_async_command(_test(), command="assist test"))


@app.command("ask")
def ask(
    phrases: list[str] = typer.Argument(None, help="Phrases to send (quote each one)"),
    agent: str = typer.Option("conversation.home_assistant", "--agent", "-a",
                              help="Conversation agent (default: the built-in one)"),
    language: str | None = typer.Option(None, "--language", help="Language (default: the agent's)"),
    file: Path | None = typer.Option(None, "--file", "-f", help="One phrase per line; '#' comments"),
    yes: bool = YES_OPT,
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Send phrases straight to one conversation agent, skipping the pipeline.

    With the default built-in agent this shows what works offline, e.g. whether
    an alias is recognised. A command phrase acts on the house.

    Examples:
        ha-cli assist ask "is the bedroom pendant on"
        ha-cli assist ask "what's the capital of Peru" --agent conversation.chatgpt --yes
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    _check_flags(json_output, porcelain)
    texts = _phrases(phrases, file)
    _confirm(texts, f"agent {agent}", yes, porcelain or json_output)

    async def _ask() -> None:
        formatter = PorcelainFormatter("assist ask") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = AssistService(client)
            results = []
            for text in texts:
                r = await service.ask_agent(agent, text, language)
                results.append(r)
                if not formatter and not json_output:
                    _print_result(r)
            _emit(formatter, json_output, results, {
                "agent": agent, "home_assistant": create_home_assistant_metadata(url_final, "websocket")})

    asyncio.run(run_async_command(_ask(), command="assist ask"))

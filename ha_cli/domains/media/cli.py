"""CLI commands for the media domain."""

import asyncio
import json
import sys

import typer
from rich.console import Console
from rich.markup import escape

from ...common.cli_utils import run_async_command, set_porcelain_mode, setup_logging, write_output
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_HA_ERROR, EXIT_USAGE_ERROR, NotFoundError, ValidationError
from ...common.porcelain import PorcelainFormatter, create_home_assistant_metadata
from .models import OUTCOME_LABELS, TtsEngine
from .service import MediaService

app = typer.Typer(
    name="media",
    help="Media players: prove a TTS clip actually played",
    no_args_is_help=True,
)

console = Console()


@app.callback()
def _media() -> None:
    """Media players: prove a TTS clip actually played."""
    # A group callback keeps `media <command>` a group while it has one command


URL_OPT = typer.Option(None, "--url", help="Home Assistant URL")
TOKEN_OPT = typer.Option(
    None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"
)


def _fail(formatter: PorcelainFormatter | None, message: str, code: str, exit_code: int = EXIT_USAGE_ERROR) -> None:
    if formatter:
        write_output(formatter.error(message, error_code=code))
    else:
        console.print(f"[red]Error:[/red] {escape(message)}")
    sys.exit(exit_code)


@app.command("tts-test")
def tts_test(
    players: list[str] = typer.Argument(..., help="media_player.* entities, tested one at a time"),
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    engine: str | None = typer.Option(None, "--engine", help="tts.* entity (default: the preferred Assist pipeline's)"),
    language: str | None = typer.Option(None, "--language", help="TTS language (default: the pipeline's)"),
    voice: str | None = typer.Option(None, "--voice", help="TTS voice (default: the pipeline's)"),
    message: str = typer.Option("Testing, one two three.", "--message", "-m", help="What to say"),
    timeout: float = typer.Option(20.0, "--timeout", help="Seconds to wait for each player to start"),
    force: bool = typer.Option(False, "--force", help="Test a player that is already playing (interrupts it)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Speak a short clip on each player and confirm it reached "playing".

    A successful tts.speak call proves nothing: the device has to fetch the audio
    from HA's internal URL itself, and a firewall between them makes it fail
    silently. This watches the player's state instead. It makes a sound in the
    room, so name the players explicitly. Exits 3 unless every clip played.

    Examples:
        ha-cli media tts-test media_player.home_assistant_voice_09f860_media_player
        ha-cli media tts-test media_player.kitchen media_player.office_2 --engine tts.piper --voice en_GB-cori-high
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    if json_output and porcelain:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)

    async def _test() -> None:
        formatter = PorcelainFormatter("media tts-test") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = MediaService(client)
            try:
                tts = (TtsEngine(engine=engine, language=language, voice=voice) if engine
                       else await service.default_engine())
            except ValidationError as e:
                _fail(formatter, str(e), "VALIDATION_ERROR")
                return
            if engine is None:
                tts.language = language or tts.language
                tts.voice = voice or tts.voice
            if not formatter and not json_output:
                console.print(f"[dim]{escape(tts.engine)} ({escape(tts.source)})"
                              f"{' ' + escape(tts.language) if tts.language else ''}"
                              f"{' ' + escape(tts.voice) if tts.voice else ''}[/dim]")
            results = []
            for player in players:
                try:
                    r = await service.tts_test(player, tts, message=message, timeout=timeout, force=force)
                except (ValidationError, NotFoundError) as e:
                    _fail(formatter, str(e), "NOT_FOUND" if isinstance(e, NotFoundError) else "VALIDATION_ERROR")
                    return
                results.append(r)
                if not formatter and not json_output:
                    colour = "green" if r.ok else "red"
                    timing = ""
                    if r.started_after_s is not None:
                        timing = f"  started {r.started_after_s:.1f}s"
                        if r.finished_after_s is not None:
                            timing += f", finished {r.finished_after_s:.1f}s"
                    console.print(f"[cyan]{escape(player)}[/cyan]  [{colour}]{escape(OUTCOME_LABELS[r.outcome])}"
                                  f"[/{colour}]{timing}")
                    if r.problem and not r.ok:
                        console.print(f"  [dim]{escape(r.problem)}[/dim]")
            data = [r.to_dict() for r in results]
            all_ok = all(r.ok for r in results)
            if formatter:
                if all_ok:
                    write_output(formatter.success(data, metadata={
                        "engine": tts.engine, "engine_source": tts.source,
                        "home_assistant": create_home_assistant_metadata(url_final, "websocket")}))
                else:
                    failed = [r.player for r in results if not r.ok]
                    write_output(formatter.error(f"Did not play on: {', '.join(failed)}", error_code="NOT_PLAYED",
                                                 details={"results": data}))
            elif json_output:
                write_output(json.dumps(data, indent=2))
            if not all_ok:
                sys.exit(EXIT_HA_ERROR)

    asyncio.run(run_async_command(_test(), command="media tts-test"))

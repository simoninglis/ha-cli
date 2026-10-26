"""CLI commands for the HACS domain."""

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
from ...common.exceptions import (
    EXIT_HA_ERROR,
    EXIT_USAGE_ERROR,
    HAAutomationError,
    NotFoundError,
    ValidationError,
)
from ...common.porcelain import PorcelainFormatter, create_home_assistant_metadata
from .service import HacsService, summarize

app = typer.Typer(
    name="hacs",
    help="HACS repositories: list, audit against dashboard resources, remove",
    no_args_is_help=True,
)

console = Console()

# Never uninstall HACS through itself
PROTECTED = {"hacs/integration"}

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


@app.command("list")
def list_repositories(
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    category: str | None = typer.Option(None, "--category", "-c", help="plugin, integration, theme, template, ..."),
    updates: bool = typer.Option(False, "--updates", help="Only repositories with an update pending"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List installed HACS repositories.

    Examples:
        ha-cli hacs list
        ha-cli hacs list --category plugin
        ha-cli hacs list --updates
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    if json_output and porcelain:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)

    async def _list() -> None:
        formatter = PorcelainFormatter("hacs list") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = HacsService(client)
            try:
                repos = await service.list_repositories()
            except ValidationError as e:
                _fail(formatter, str(e), "VALIDATION_ERROR")
                return
            shown = [
                r for r in repos
                if r.installed
                and (not category or r.category == category.lower())
                and (not updates or r.pending_upgrade)
            ]
            data = [r.to_dict() for r in shown]
            if formatter:
                write_output(formatter.success(
                    data,
                    metadata={
                        **summarize(repos),
                        "shown_count": len(shown),
                        "home_assistant": create_home_assistant_metadata(url_final, "websocket"),
                    },
                    suggestions={"common_actions": [
                        "Check HACS against dashboard resources: ha-cli hacs audit",
                        "Remove a repository: ha-cli hacs remove <owner/name>",
                    ]},
                ))
            elif json_output:
                write_output(json.dumps(data, indent=2))
            else:
                if not shown:
                    console.print("[dim]No matching installed repositories[/dim]")
                    return
                table = Table(title="HACS repositories (installed)")
                table.add_column("Repository", style="cyan")
                table.add_column("Category")
                table.add_column("Installed")
                table.add_column("Available")
                table.add_column("ID", style="dim")
                for r in shown:
                    available = f"[yellow]{escape(r.available_version)}[/yellow]" if r.pending_upgrade else escape(r.available_version)
                    table.add_row(escape(r.full_name), r.category, escape(r.installed_version), available, r.id)
                console.print(table)
                console.print(
                    "[dim]Only what HACS records as installed. "
                    "Cards it has lost track of show up in: ha-cli hacs audit[/dim]"
                )

    asyncio.run(run_async_command(_list(), command="hacs list"))


@app.command("audit")
def audit(
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Check HACS's records against the dashboard resources.

    Finds cards the dashboards load that HACS no longer tracks as installed (no
    update notices; removing one deletes a card in use), /hacsfiles resources no
    repository owns, and installed cards nothing loads.

    Exit code: 0 clean, 1 findings, 2 error (as `ha-cli audit`).

    Examples:
        ha-cli hacs audit
        ha-cli hacs audit --porcelain
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    if json_output and porcelain:
        console.print("[red]Error:[/red] Cannot use --json and --porcelain together")
        sys.exit(EXIT_USAGE_ERROR)

    async def _audit() -> int:
        formatter = PorcelainFormatter("hacs audit") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            try:
                result = await HacsService(client).audit()
            except HAAutomationError as e:
                # Couldn't read HACS or the resources: an error (2), never "clean" (0)
                _fail(formatter, e.message, "HA_ERROR", exit_code=2)
                return 2
        if formatter:
            write_output(formatter.success(
                result.to_dict(),
                metadata={
                    "finding_count": len(result.findings),
                    "home_assistant": create_home_assistant_metadata(url_final, "websocket"),
                },
            ))
        elif json_output:
            write_output(json.dumps(result.to_dict(), indent=2))
        else:
            for f in result.findings:
                colour = "red" if f.severity == "error" else "yellow"
                console.print(f"[{colour}]{f.severity.upper():7}[/{colour}] [bold]{f.kind}[/bold]  {escape(f.message)}")
            console.print(
                f"\n{len(result.findings)} finding(s); {result.installed_count} installed, "
                f"{result.resource_count} dashboard resources"
            )
        return result.exit_code

    sys.exit(asyncio.run(run_async_command(_audit(), command="hacs audit")))


@app.command("remove")
def remove(
    repository: str = typer.Argument(..., help="owner/name (e.g. custom-cards/bom-radar-card) or repository id"),
    url: str | None = URL_OPT,
    token: str | None = TOKEN_OPT,
    force: bool = typer.Option(False, "--force", "-f", help="Skip the confirmation (required with --porcelain)"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Uninstall a HACS repository: its files and, for a card, its dashboard resource.

    HACS deletes the files even when its records say the repository isn't
    installed, so this shows what will go and asks first. Afterwards it checks the
    repository and its resource are actually gone.

    Examples:
        ha-cli hacs remove custom-cards/bom-radar-card
        ha-cli hacs remove 123456789 --force
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)
    if porcelain and not force:
        console.print("[red]Error:[/red] --porcelain needs --force: removal deletes files, so it never runs unconfirmed")
        sys.exit(EXIT_USAGE_ERROR)

    async def _remove() -> None:
        formatter = PorcelainFormatter("hacs remove") if porcelain else None
        url_final, token_final = get_client_config(url, token)
        async with HAClient(url_final, token_final) as client:
            service = HacsService(client)
            try:
                repos = await service.list_repositories()
                repo = service.find_repository(repos, repository)
            except (ValidationError, NotFoundError) as e:
                _fail(formatter, str(e), "NOT_FOUND" if isinstance(e, NotFoundError) else "VALIDATION_ERROR")
                return
            if repo.full_name.lower() in PROTECTED:
                _fail(formatter, "Refusing to remove HACS itself", "VALIDATION_ERROR")
                return
            blocker = service.removal_blocker(repo)
            if blocker:
                _fail(formatter, f"Refusing to remove: {blocker}", "VALIDATION_ERROR")
                return

            resources = await service.list_resources()  # unreadable: stop before deleting anything
            in_use = service.resources_for(repo, resources)

            if not force:
                console.print(f"[bold]{escape(repo.full_name)}[/bold] ({repo.category}, id {repo.id})")
                state = "installed " + repo.installed_version if repo.installed else "[yellow]NOT tracked as installed by HACS[/yellow]"
                console.print(f"  HACS record: {state}")
                console.print(f"  Deletes:     {escape(repo.local_path)}")
                for r in in_use:
                    console.print(f"  Resource:    {escape(r.url)} (deregistered)")
                if in_use and not repo.installed:
                    console.print(
                        "[yellow]  HACS has lost track of this card but the dashboards still load it. "
                        "If it's still wanted, re-download it in HACS instead.[/yellow]"
                    )
                if not typer.confirm("Remove it?"):
                    console.print("[yellow]Cancelled[/yellow]")
                    return

            await service.remove(repo)
            problems = await service.verify_removed(repo)

            if problems:
                _fail(formatter, f"Removal of {repo.full_name} incomplete: " + "; ".join(problems),
                      "HA_ERROR", exit_code=EXIT_HA_ERROR)
                return
            restart = repo.category in ("integration", "python_script")
            if formatter:
                write_output(formatter.success(
                    {**repo.to_dict(), "removed_resources": [r.url for r in in_use]},
                    metadata={
                        "action": "removed",
                        "verified": True,
                        "restart_required": restart,
                        "home_assistant": create_home_assistant_metadata(url_final, "websocket"),
                    },
                ))
            else:
                console.print(f"[green]Removed {escape(repo.full_name)}[/green] (verified: not installed, no resource left)")
                if restart:
                    console.print("[yellow]Restart Home Assistant to unload it[/yellow]")
                elif in_use:
                    console.print("[dim]Reload open dashboards to drop the card[/dim]")

    asyncio.run(run_async_command(_remove(), command="hacs remove"))

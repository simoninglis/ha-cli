"""Cloud CLI commands for Home Assistant Cloud (Nabu Casa)."""

import asyncio
import sys
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.markup import escape as rich_escape
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
    EXIT_NETWORK_ERROR,
    EXIT_USAGE_ERROR,
    AuthenticationError,
    ConfigurationError,
    ConnectionError,
    EntityFailure,
    NotFoundError,
    ValidationError,
    WebSocketError,
    classify_websocket_error,
    get_most_severe_exit_code,
)
from ...common.porcelain import PorcelainFormatter
from .service import CloudService

app = typer.Typer(
    name="cloud",
    help="Home Assistant Cloud (Nabu Casa) status and Alexa commands",
    no_args_is_help=True,
)

alexa_app = typer.Typer(
    name="alexa",
    help="Alexa-specific cloud commands",
    no_args_is_help=True,
)
app.add_typer(alexa_app, name="alexa")

console = Console()


def _handle_error(
    e: Exception,
    porcelain: bool,
    formatter: PorcelainFormatter | None,
) -> None:
    """Handle errors with appropriate output format and exit code.

    WebSocketError classification uses centralized classify_websocket_error():
    1. Checks HA error code prefix FIRST (prevents "not connected" misclassification)
    2. Only checks transport keywords if no HA code found
    """
    if isinstance(e, NotFoundError):
        error_code = "NOT_FOUND"
        exit_code = EXIT_USAGE_ERROR
    elif isinstance(e, (ValidationError, ConfigurationError)):
        error_code = "VALIDATION_ERROR" if isinstance(e, ValidationError) else "CONFIG_ERROR"
        exit_code = EXIT_USAGE_ERROR
    elif isinstance(e, ConnectionError):
        error_code = "CONNECTION_ERROR"
        exit_code = EXIT_NETWORK_ERROR
    elif isinstance(e, WebSocketError):
        # Use centralized classifier that checks HA error code prefix FIRST
        error_code, exit_code = classify_websocket_error(e)
    elif isinstance(e, AuthenticationError):
        error_code = "AUTH_ERROR"
        exit_code = EXIT_HA_ERROR
    else:
        error_code = "ERROR"
        exit_code = EXIT_HA_ERROR

    if porcelain and formatter:
        output = formatter.error(e, error_code=error_code)
        write_output(output)
    else:
        console.print(f"[red]Error: {rich_escape(str(e))}[/red]")

    sys.exit(exit_code)


@app.command("status")
def cloud_status(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show Home Assistant Cloud connection status.

    Displays:
    - Cloud login state
    - Remote UI status
    - Alexa/Google Assistant enabled state
    - Subscription information
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _status() -> None:
        formatter = PorcelainFormatter("cloud status") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)
                status = await service.get_status()

                if porcelain and formatter:
                    issues = []
                    suggestions = []

                    if not status.logged_in:
                        issues.append("Not logged in to Home Assistant Cloud")
                        suggestions.append("Log in via Settings > Home Assistant Cloud")
                    elif not status.cloud_connected:
                        issues.append("Cloud connection not established")
                        suggestions.append("Check internet connection")
                    else:
                        if not status.alexa_enabled:
                            suggestions.append("Enable Alexa: Settings > Voice Assistants > Alexa")
                        if not status.remote_enabled:
                            suggestions.append("Enable Remote UI: Settings > Home Assistant Cloud")

                    output = formatter.success(
                        data=status.to_dict(),
                        metadata={
                            "issues_count": len(issues),
                        },
                        suggestions={
                            "detected_issues": issues,
                            "next_steps": suggestions,
                            "common_actions": [
                                "ha-cli cloud alexa entities",
                                "ha-cli cloud alexa sync",
                            ],
                        },
                    )
                    write_output(output)
                else:
                    console.print("[bold]Home Assistant Cloud Status[/bold]\n")

                    if not status.logged_in:
                        console.print("[red]✗ Not logged in[/red]")
                        console.print("[dim]Log in via Settings > Home Assistant Cloud[/dim]")
                        return

                    # Account info
                    email = rich_escape(status.email or "unknown")
                    console.print(f"[green]✓ Logged in[/green] as {email}")
                    if status.subscription_expiration:
                        expires = rich_escape(status.subscription_expiration)
                        console.print(f"  Subscription expires: {expires}")

                    # Cloud connection
                    if status.cloud_connected:
                        console.print("[green]✓ Cloud connected[/green]")
                    else:
                        console.print("[red]✗ Cloud disconnected[/red]")

                    # Remote UI
                    if status.remote_enabled:
                        if status.remote_connected:
                            if status.remote_domain:
                                domain = rich_escape(status.remote_domain)
                                console.print(f"[green]✓ Remote UI enabled[/green] ({domain})")
                            else:
                                console.print("[green]✓ Remote UI enabled[/green]")
                        else:
                            console.print("[yellow]⚠ Remote UI enabled but not connected[/yellow]")
                    else:
                        console.print("[dim]- Remote UI disabled[/dim]")

                    # Voice assistants
                    console.print()
                    console.print("[bold]Alexa[/bold]")
                    if status.alexa_enabled:
                        console.print("[green]  ✓ Enabled[/green]")
                    else:
                        console.print("[dim]  - Disabled[/dim]")

                    if status.alexa_registered:
                        console.print("[green]  ✓ Skill linked[/green]")
                    else:
                        console.print("[yellow]  ⚠ Skill not linked[/yellow] - Link in Alexa app")

                    if status.alexa_entity_count > 0:
                        count = status.alexa_entity_count
                        console.print(f"[green]  ✓ {count} entities configured[/green]")
                    else:
                        console.print("[dim]  - No entities in filter[/dim]")

                    console.print()
                    console.print("[bold]Google Assistant[/bold]")
                    if status.google_enabled:
                        console.print("[green]  ✓ Enabled[/green]")
                    else:
                        console.print("[dim]  - Disabled[/dim]")

                    if status.google_registered:
                        console.print("[green]  ✓ Linked[/green]")
                    else:
                        console.print("[dim]  - Not linked[/dim]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_status(), command="cloud status"))


@alexa_app.command("entities")
def alexa_entities(
    exposed_only: bool = typer.Option(False, "--exposed", "-e", help="Show only exposed entities"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List entities available to Alexa.

    Shows all entities that can be exposed to Alexa, their exposure status,
    and Alexa display categories. Use --exposed to filter to only exposed entities.
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _entities() -> None:
        formatter = PorcelainFormatter("cloud alexa entities") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)
                all_entities = await service.get_alexa_entities()
                total_count = len(all_entities)
                # Compute total exposed from unfiltered list
                total_exposed = sum(1 for e in all_entities if e.should_expose)

                # Apply filter if requested (service already sorted by entity_id)
                entities = (
                    [e for e in all_entities if e.should_expose]
                    if exposed_only
                    else all_entities
                )

                if porcelain and formatter:
                    output = formatter.success(
                        data=[e.to_dict() for e in entities],
                        metadata={
                            "total_count": total_count,
                            "total_exposed": total_exposed,
                            "filtered_count": len(entities),
                            "filters_applied": ["exposed_only"] if exposed_only else [],
                        },
                        suggestions={
                            "next_steps": [
                                "ha-cli cloud alexa sync  # Tell Alexa to rediscover",
                                "Say 'Alexa, discover devices'",
                            ],
                        },
                    )
                    write_output(output)
                else:
                    table = Table(title="Alexa Entities")
                    table.add_column("Entity ID", style="cyan")
                    table.add_column("Exposed", justify="center")
                    table.add_column("Categories")

                    for entity in entities:
                        exposed_mark = "[green]✓[/green]" if entity.should_expose else "[dim]-[/dim]"
                        cats = entity.display_categories
                        categories_str = ", ".join(cats) if cats else "-"
                        table.add_row(
                            rich_escape(entity.entity_id),
                            exposed_mark,
                            rich_escape(categories_str),
                        )

                    console.print(table)
                    shown = len(entities)
                    summary = f"\n[dim]Showing: {shown} entities, {total_exposed} exposed"
                    if exposed_only:
                        summary += f" (of {total_count} total)"
                    summary += "[/dim]"
                    console.print(summary)

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_entities(), command="cloud alexa entities"))


@alexa_app.command("sync")
def alexa_sync(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Trigger Alexa to rediscover devices.

    This sends a proactive discovery request to Alexa, telling it to
    refresh its view of your Home Assistant entities.

    Equivalent to saying "Alexa, discover devices" but from the command line.
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _sync() -> None:
        formatter = PorcelainFormatter("cloud alexa sync") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)
                result = await service.sync_alexa()

                if porcelain and formatter:
                    output = formatter.success(
                        data={"sync_triggered": True, "response": result},
                        suggestions={
                            "next_steps": [
                                "Wait 30-60 seconds for Alexa to process",
                                "Check Alexa app for discovered devices",
                                "Try 'Alexa, turn on <device>'",
                            ],
                        },
                    )
                    write_output(output)
                else:
                    console.print("[green]✓ Alexa sync triggered[/green]")
                    console.print("[dim]Alexa should discover devices within 30-60 seconds[/dim]")
                    console.print("[dim]Check the Alexa app to verify devices appear[/dim]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_sync(), command="cloud alexa sync"))


def _parse_entity_list_yaml(file_path: Path) -> list[str]:
    """Parse a YAML file containing a list of entity IDs.

    Supports format like voice_exposure_entities.yaml:
    - light.lounge
    - climate.office_ac
    # Comments are ignored by YAML parser

    Args:
        file_path: Path to the YAML file

    Returns:
        List of entity IDs (stripped of whitespace)

    Raises:
        ValidationError: If file doesn't exist, can't be read, or content is not a list
    """
    if not file_path.exists():
        raise ValidationError(f"File not found: {file_path}")

    try:
        with open(file_path, encoding="utf-8") as f:
            content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValidationError(f"Invalid YAML in {file_path}: {e}") from e
    except OSError as e:
        raise ValidationError(f"Cannot read {file_path}: {e}") from e

    if content is None:
        return []

    if not isinstance(content, list):
        raise ValidationError(
            f"Expected list of entities in {file_path}, got {type(content).__name__}"
        )

    # Filter to only valid non-empty strings and strip whitespace
    return [e.strip() for e in content if isinstance(e, str) and e.strip()]


@alexa_app.command("expose")
def alexa_expose(
    entity_id: str | None = typer.Argument(None, help="Entity ID to expose"),
    from_file: Path | None = typer.Option(
        None, "--from-file", "-f", help="YAML file with entity list"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Enable Alexa exposure for entity(ies).

    Expose a single entity:
        ha-cli cloud alexa expose light.lounge

    Expose multiple entities from a YAML file:
        ha-cli cloud alexa expose --from-file includes/voice_exposure_entities.yaml
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _expose() -> None:
        formatter = PorcelainFormatter("cloud alexa expose") if porcelain else None

        try:
            # Validate input
            if entity_id is None and from_file is None:
                raise ValidationError(
                    "Provide either entity_id or --from-file, not neither"
                )
            if entity_id is not None and from_file is not None:
                raise ValidationError(
                    "Provide either entity_id or --from-file, not both"
                )

            # Get list of entities to expose
            if from_file:
                entity_ids = _parse_entity_list_yaml(from_file)
                if not entity_ids:
                    raise ValidationError(f"No entities found in {from_file}")
            else:
                entity_ids = [entity_id]  # type: ignore[list-item]

            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)
                successful, failed = await service.set_entities_exposure(
                    entity_ids, expose=True
                )

                if porcelain and formatter:
                    output_data = {
                        "successful": successful,
                        "failed": [f.to_dict() for f in failed],
                    }
                    output_metadata = {
                        "total_requested": len(entity_ids),
                        "successful_count": len(successful),
                        "failed_count": len(failed),
                    }
                    output_suggestions = {
                        "next_steps": [
                            "ha-cli cloud alexa sync  # Tell Alexa to rediscover",
                        ] if successful else [],
                    }
                    # Choose status and exit code based on success/failure
                    if failed and not successful:
                        # All operations failed - use most severe exit code
                        output = formatter.error(
                            error="All entity exposure operations failed",
                            error_code="ALL_FAILED",
                            details=output_data,
                        )
                        write_output(output)
                        sys.exit(get_most_severe_exit_code(failed))
                    elif failed:
                        # Some succeeded, some failed - use most severe exit code
                        output = formatter.partial_success(
                            data=output_data,
                            metadata=output_metadata,
                            suggestions=output_suggestions,
                        )
                        write_output(output)
                        sys.exit(get_most_severe_exit_code(failed))
                    else:
                        # All succeeded
                        output = formatter.success(
                            data=output_data,
                            metadata=output_metadata,
                            suggestions=output_suggestions,
                        )
                        write_output(output)
                else:
                    if successful:
                        console.print(
                            f"[green]✓ Exposed {len(successful)} entity(ies) to Alexa[/green]"
                        )
                        for eid in successful:
                            console.print(f"  [dim]{rich_escape(eid)}[/dim]")

                    if failed:
                        console.print(f"\n[red]✗ Failed to expose {len(failed)}:[/red]")
                        for f in failed:
                            console.print(f"  [red]{rich_escape(f.entity_id)}: {rich_escape(f.message)}[/red]")
                        sys.exit(get_most_severe_exit_code(failed))

                    if successful:
                        console.print(
                            "\n[dim]Run 'ha-cli cloud alexa sync' to trigger Alexa discovery[/dim]"
                        )

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_expose(), command="cloud alexa expose"))


@alexa_app.command("hide")
def alexa_hide(
    entity_id: str | None = typer.Argument(None, help="Entity ID to hide"),
    all_except: Path | None = typer.Option(
        None, "--all-except", help="Hide all except entities in YAML file"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Disable Alexa exposure for entity(ies).

    Hide a single entity:
        ha-cli cloud alexa hide light.lounge

    Hide all entities except those in a YAML file:
        ha-cli cloud alexa hide --all-except includes/voice_exposure_entities.yaml
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _hide() -> None:
        formatter = PorcelainFormatter("cloud alexa hide") if porcelain else None

        try:
            # Validate input
            if entity_id is None and all_except is None:
                raise ValidationError(
                    "Provide either entity_id or --all-except, not neither"
                )
            if entity_id is not None and all_except is not None:
                raise ValidationError(
                    "Provide either entity_id or --all-except, not both"
                )

            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)

                if all_except:
                    # Get list of entities to keep exposed
                    keep_exposed = set(_parse_entity_list_yaml(all_except))
                    if not keep_exposed:
                        raise ValidationError(f"No entities found in {all_except}")

                    # Get all currently exposed entities
                    all_entities = await service.get_alexa_entities()
                    currently_exposed = {
                        e.entity_id for e in all_entities if e.should_expose
                    }

                    # Hide entities that are exposed but not in keep list
                    to_hide = list(currently_exposed - keep_exposed)
                    to_hide.sort()  # Deterministic order

                    if not to_hide:
                        if porcelain and formatter:
                            output = formatter.success(
                                data={"successful": [], "failed": []},
                                metadata={
                                    "total_requested": 0,
                                    "successful_count": 0,
                                    "failed_count": 0,
                                    "message": "No entities to hide",
                                },
                            )
                            write_output(output)
                        else:
                            console.print("[dim]No entities to hide[/dim]")
                        return

                    entity_ids = to_hide
                else:
                    entity_ids = [entity_id]  # type: ignore[list-item]

                successful, failed = await service.set_entities_exposure(
                    entity_ids, expose=False
                )

                if porcelain and formatter:
                    output_data = {
                        "successful": successful,
                        "failed": [f.to_dict() for f in failed],
                    }
                    output_metadata = {
                        "total_requested": len(entity_ids),
                        "successful_count": len(successful),
                        "failed_count": len(failed),
                    }
                    output_suggestions = {
                        "next_steps": [
                            "ha-cli cloud alexa sync  # Tell Alexa to rediscover",
                        ] if successful else [],
                    }
                    # Choose status and exit code based on success/failure
                    if failed and not successful:
                        # All operations failed - use most severe exit code
                        output = formatter.error(
                            error="All entity hide operations failed",
                            error_code="ALL_FAILED",
                            details=output_data,
                        )
                        write_output(output)
                        sys.exit(get_most_severe_exit_code(failed))
                    elif failed:
                        # Some succeeded, some failed - use most severe exit code
                        output = formatter.partial_success(
                            data=output_data,
                            metadata=output_metadata,
                            suggestions=output_suggestions,
                        )
                        write_output(output)
                        sys.exit(get_most_severe_exit_code(failed))
                    else:
                        # All succeeded
                        output = formatter.success(
                            data=output_data,
                            metadata=output_metadata,
                            suggestions=output_suggestions,
                        )
                        write_output(output)
                else:
                    if successful:
                        console.print(
                            f"[green]✓ Hidden {len(successful)} entity(ies) from Alexa[/green]"
                        )
                        if len(successful) <= 20:
                            for eid in successful:
                                console.print(f"  [dim]{rich_escape(eid)}[/dim]")
                        else:
                            console.print(f"  [dim]({len(successful)} entities hidden)[/dim]")

                    if failed:
                        console.print(f"\n[red]✗ Failed to hide {len(failed)}:[/red]")
                        for f in failed:
                            console.print(f"  [red]{rich_escape(f.entity_id)}: {rich_escape(f.message)}[/red]")
                        sys.exit(get_most_severe_exit_code(failed))

                    if successful:
                        console.print(
                            "\n[dim]Run 'ha-cli cloud alexa sync' to trigger Alexa discovery[/dim]"
                        )

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_hide(), command="cloud alexa hide"))


@alexa_app.command("sync-filter")
def alexa_sync_filter(
    file: Path = typer.Option(
        ..., "--file", "-f", help="YAML file with entity list (source of truth)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without making changes"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Name of the env var holding the token (default: HA_TOKEN); never the token itself"),
    porcelain: bool = typer.Option(False, "--porcelain", help="Output structured JSON"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Sync entity registry exposure with YAML filter file.

    This is the "magic" command that ensures entity registry matches your YAML file:
    - Enables exposure for all entities IN the YAML file
    - Disables exposure for all entities NOT in the YAML file

    Example:
        ha-cli cloud alexa sync-filter --file includes/voice_exposure_entities.yaml

    Use --dry-run to see what would change without making changes:
        ha-cli cloud alexa sync-filter --file includes/voice_exposure_entities.yaml --dry-run
    """
    setup_logging(debug)
    set_porcelain_mode(porcelain)

    async def _sync_filter() -> None:
        formatter = PorcelainFormatter("cloud alexa sync-filter") if porcelain else None

        try:
            # Parse the YAML file
            desired_exposed = set(_parse_entity_list_yaml(file))
            if not desired_exposed:
                raise ValidationError(f"No entities found in {file}")

            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final) as client:
                service = CloudService(client)

                # Get current state from entity registry
                all_entities = await service.get_alexa_entities()
                currently_exposed = {
                    e.entity_id for e in all_entities if e.should_expose
                }
                all_entity_ids = {e.entity_id for e in all_entities}

                # Identify entities not in Alexa entity list (not compatible)
                not_alexa_compatible = desired_exposed - all_entity_ids

                # Calculate what needs to change (exclude non-compatible entities)
                # Only expose entities that are actually in the Alexa entity list
                to_expose = list((desired_exposed - currently_exposed) - not_alexa_compatible)
                to_hide = list(currently_exposed - desired_exposed)
                already_correct = list(desired_exposed & currently_exposed)

                to_expose.sort()
                to_hide.sort()
                already_correct.sort()
                not_alexa_compatible_list = sorted(not_alexa_compatible)

                if dry_run:
                    # Dry run mode - just report
                    if porcelain and formatter:
                        output = formatter.success(
                            data={
                                "dry_run": True,
                                "to_expose": to_expose,
                                "to_hide": to_hide,
                                "already_correct": already_correct,
                                "not_alexa_compatible": not_alexa_compatible_list,
                            },
                            metadata={
                                "desired_count": len(desired_exposed),
                                "currently_exposed": len(currently_exposed),
                                "to_expose_count": len(to_expose),
                                "to_hide_count": len(to_hide),
                                "already_correct_count": len(already_correct),
                                "not_alexa_compatible_count": len(not_alexa_compatible_list),
                            },
                        )
                        write_output(output)
                    else:
                        console.print("[bold]Dry run - no changes will be made[/bold]\n")
                        console.print(
                            f"Desired: {len(desired_exposed)} entities from {file}"
                        )
                        console.print(
                            f"Currently exposed: {len(currently_exposed)} entities\n"
                        )

                        if to_expose:
                            console.print(f"[green]Would EXPOSE {len(to_expose)}:[/green]")
                            for eid in to_expose:
                                console.print(f"  [green]+ {rich_escape(eid)}[/green]")

                        if to_hide:
                            console.print(f"\n[red]Would HIDE {len(to_hide)}:[/red]")
                            for eid in to_hide[:20]:
                                console.print(f"  [red]- {rich_escape(eid)}[/red]")
                            if len(to_hide) > 20:
                                console.print(
                                    f"  [dim]... and {len(to_hide) - 20} more[/dim]"
                                )

                        if not_alexa_compatible_list:
                            console.print(
                                f"\n[yellow]⚠ Not Alexa-compatible ({len(not_alexa_compatible_list)}):[/yellow]"
                            )
                            for eid in not_alexa_compatible_list:
                                console.print(f"  [yellow]? {rich_escape(eid)}[/yellow]")

                        if already_correct:
                            console.print(
                                f"\n[dim]Already correct: {len(already_correct)}[/dim]"
                            )

                        if not to_expose and not to_hide:
                            console.print("\n[green]✓ Already in sync![/green]")
                    return

                # Actually apply changes
                expose_success: list[str] = []
                expose_failed: list[EntityFailure] = []
                hide_success: list[str] = []
                hide_failed: list[EntityFailure] = []

                if to_expose:
                    expose_success, expose_failed = await service.set_entities_exposure(
                        to_expose, expose=True
                    )

                if to_hide:
                    hide_success, hide_failed = await service.set_entities_exposure(
                        to_hide, expose=False
                    )

                all_failed = expose_failed + hide_failed

                if porcelain and formatter:
                    output_data = {
                        "exposed": expose_success,
                        "hidden": hide_success,
                        "failed": [f.to_dict() for f in all_failed],
                        "not_alexa_compatible": not_alexa_compatible_list,
                    }
                    output_metadata = {
                        "desired_count": len(desired_exposed),
                        "exposed_count": len(expose_success),
                        "hidden_count": len(hide_success),
                        "failed_count": len(all_failed),
                        "not_alexa_compatible_count": len(not_alexa_compatible_list),
                    }
                    output_suggestions = {
                        "next_steps": [
                            "ha-cli cloud alexa sync  # Tell Alexa to rediscover",
                        ],
                    }
                    # Choose status and exit code based on success/failure
                    if all_failed and not expose_success and not hide_success:
                        # All operations failed - use most severe exit code
                        output = formatter.error(
                            error="All sync-filter operations failed",
                            error_code="ALL_FAILED",
                            details=output_data,
                        )
                        write_output(output)
                        sys.exit(get_most_severe_exit_code(all_failed))
                    elif all_failed:
                        # Some succeeded, some failed - use most severe exit code
                        output = formatter.partial_success(
                            data=output_data,
                            metadata=output_metadata,
                            suggestions=output_suggestions,
                        )
                        write_output(output)
                        sys.exit(get_most_severe_exit_code(all_failed))
                    else:
                        # All succeeded
                        output = formatter.success(
                            data=output_data,
                            metadata=output_metadata,
                            suggestions=output_suggestions,
                        )
                        write_output(output)
                else:
                    if expose_success:
                        console.print(
                            f"[green]✓ Exposed {len(expose_success)} entity(ies)[/green]"
                        )

                    if hide_success:
                        console.print(
                            f"[green]✓ Hidden {len(hide_success)} entity(ies)[/green]"
                        )

                    if not_alexa_compatible_list:
                        console.print(
                            f"\n[yellow]⚠ {len(not_alexa_compatible_list)} entities not Alexa-compatible:[/yellow]"
                        )
                        for eid in not_alexa_compatible_list:
                            console.print(f"  [yellow]? {rich_escape(eid)}[/yellow]")

                    if all_failed:
                        console.print(f"\n[red]✗ Failed {len(all_failed)}:[/red]")
                        for f in all_failed:
                            console.print(
                                f"  [red]{rich_escape(f.entity_id)}: {rich_escape(f.message)}[/red]"
                            )
                        sys.exit(get_most_severe_exit_code(all_failed))

                    total_changed = len(expose_success) + len(hide_success)
                    if total_changed > 0:
                        console.print(
                            "\n[dim]Run 'ha-cli cloud alexa sync' to trigger Alexa discovery[/dim]"
                        )
                    else:
                        console.print("\n[green]✓ Already in sync![/green]")

        except Exception as e:
            _handle_error(e, porcelain, formatter)

    asyncio.run(run_async_command(_sync_filter(), command="cloud alexa sync-filter"))

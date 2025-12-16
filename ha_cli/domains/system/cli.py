"""CLI commands for system domain - restart, reload, logs."""

import asyncio
import json
import logging
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from ...common.cli_utils import run_async_command, setup_logging, write_output
from ...common.client import HAClient
from ...common.config import get_client_config
from ...common.exceptions import EXIT_HA_ERROR
from ...common.porcelain import PorcelainFormatter
from .service import SSHError, SystemService

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="system",
    help="Home Assistant system operations (restart, reload, logs)",
    no_args_is_help=True,
)

console = Console()

# Default SSH connection settings
DEFAULT_HOST = "10.0.20.35"
DEFAULT_USER = "root"


@app.command("restart")
def restart(
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    host: str = typer.Option(DEFAULT_HOST, "--host", "-h", help="SSH host (fallback)"),
    user: str = typer.Option(DEFAULT_USER, "--user", "-u", help="SSH user (fallback)"),
    check_first: bool = typer.Option(
        True, "--check/--no-check", help="Check config before restart"
    ),
    use_ssh: bool = typer.Option(False, "--ssh", help="Force SSH instead of API"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Restart Home Assistant core.

    Uses the HA API by default, falls back to SSH if needed.
    By default, it checks the configuration validity before restarting.
    """
    setup_logging(debug)

    async def _restart() -> None:
        formatter = PorcelainFormatter("system restart") if porcelain else None

        # Try to use API client if not forcing SSH
        client = None
        if not use_ssh:
            try:
                url_final, token_final = get_client_config(url, token)
                client = HAClient(url_final, token_final)
                await client.__aenter__()
            except Exception:
                client = None

        service = SystemService(client=client, host=host, user=user)

        try:
            # Check config first if requested (via SSH, as API doesn't have this)
            config_check_skipped = False
            if check_first:
                if not porcelain and not json_output:
                    console.print("[dim]Checking configuration...[/dim]")

                try:
                    is_valid, check_msg = await service.check_config()

                    if not is_valid:
                        if porcelain:
                            assert formatter is not None
                            output = formatter.error(
                                f"Configuration invalid: {check_msg}",
                                error_code="CONFIG_INVALID",
                            )
                            write_output(output)
                        elif json_output:
                            write_output(
                                json.dumps(
                                    {
                                        "success": False,
                                        "error": "Configuration invalid",
                                        "details": check_msg,
                                    },
                                    indent=2,
                                )
                            )
                        else:
                            console.print(f"[red]✗[/red] Configuration invalid: {check_msg}")
                            console.print("[yellow]Restart aborted. Fix configuration first.[/yellow]")
                        sys.exit(EXIT_HA_ERROR)

                    if not porcelain and not json_output:
                        console.print("[green]✓[/green] Configuration valid")
                except SSHError as e:
                    # SSH failed - if we have API client, warn but continue
                    logger.debug(f"SSH config check failed: {e}")
                    if client:
                        config_check_skipped = True
                        if not porcelain and not json_output:
                            console.print(
                                f"[yellow]⚠[/yellow] Config check skipped (SSH unavailable: {e})"
                            )
                            console.print("[dim]Proceeding with restart via API...[/dim]")
                    else:
                        # No API fallback available - fail
                        if porcelain:
                            assert formatter is not None
                            output = formatter.error(
                                f"SSH connection failed: {e}",
                                error_code="SSH_ERROR",
                            )
                            write_output(output)
                        elif json_output:
                            write_output(
                                json.dumps(
                                    {"success": False, "error": "SSH connection failed", "details": str(e)},
                                    indent=2,
                                )
                            )
                        else:
                            console.print(f"[red]✗[/red] SSH connection failed: {e}")
                        sys.exit(EXIT_HA_ERROR)

            # Perform restart
            if not porcelain and not json_output:
                method = "SSH" if use_ssh or not client else "API"
                console.print(f"[dim]Restarting Home Assistant via {method}...[/dim]")

            success, message = await service.restart()

            if porcelain:
                assert formatter is not None
                if success:
                    metadata: dict[str, str | bool] = {"host": host, "message": message}
                    if config_check_skipped:
                        metadata["config_check_skipped"] = True
                    output = formatter.success(
                        {"action": "restart", "success": True},
                        metadata=metadata,
                        suggestions={
                            "common_actions": [
                                "Check logs: ha-cli system logs",
                                "View recent logs: ha-cli system logs --lines 50",
                            ]
                        },
                    )
                else:
                    output = formatter.error(message, error_code="RESTART_FAILED")
                write_output(output)
            elif json_output:
                result = {"success": success, "action": "restart", "message": message}
                if config_check_skipped:
                    result["config_check_skipped"] = True
                write_output(json.dumps(result, indent=2))
            else:
                if success:
                    console.print("[green]✓[/green] Home Assistant restarted successfully")
                else:
                    console.print(f"[red]✗[/red] Restart failed: {message}")
                    sys.exit(EXIT_HA_ERROR)
        finally:
            if client:
                await client.__aexit__(None, None, None)

    asyncio.run(run_async_command(_restart()))


@app.command("reload")
def reload(
    component: str | None = typer.Argument(
        None,
        help="Component to reload (automations, scripts, scenes, groups, etc.)",
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Reload Home Assistant configuration.

    Without arguments, reloads automations, scripts, and scenes.
    With a component name, reloads only that component.

    Examples:
        ha-cli system reload              # Reload automations, scripts, scenes
        ha-cli system reload automations  # Reload only automations
        ha-cli system reload all          # Full restart
    """
    setup_logging(debug)

    async def _reload() -> None:
        formatter = PorcelainFormatter("system reload") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = SystemService(client=client)

            if not porcelain and not json_output:
                target = component or "automations, scripts, scenes"
                console.print(f"[dim]Reloading {target}...[/dim]")

            success, message = await service.reload(component)

            if porcelain:
                assert formatter is not None
                if success:
                    output = formatter.success(
                        {"action": "reload", "component": component, "success": True},
                        metadata={"message": message},
                        suggestions={
                            "common_actions": [
                                "Check logs: ha-cli system logs",
                                "Full restart: ha-cli system restart",
                            ]
                        },
                    )
                else:
                    output = formatter.error(message, error_code="RELOAD_FAILED")
                write_output(output)
            elif json_output:
                write_output(
                    json.dumps(
                        {
                            "success": success,
                            "action": "reload",
                            "component": component,
                            "message": message,
                        },
                        indent=2,
                    )
                )
            else:
                if success:
                    console.print(f"[green]✓[/green] {message}")
                else:
                    console.print(f"[red]✗[/red] {message}")
                    sys.exit(EXIT_HA_ERROR)

    asyncio.run(run_async_command(_reload()))


@app.command("check")
def check_config(
    host: str = typer.Option(DEFAULT_HOST, "--host", "-h", help="Home Assistant host"),
    user: str = typer.Option(DEFAULT_USER, "--user", "-u", help="SSH user"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Check Home Assistant configuration validity.

    Validates the configuration without restarting.
    """
    setup_logging(debug)

    async def _check() -> None:
        formatter = PorcelainFormatter("system check") if porcelain else None
        service = SystemService(host=host, user=user)

        try:
            is_valid, message = await service.check_config()
        except SSHError as e:
            if porcelain:
                assert formatter is not None
                output = formatter.error(f"SSH connection failed: {e}", error_code="SSH_ERROR")
                write_output(output)
            elif json_output:
                write_output(
                    json.dumps({"valid": None, "error": "SSH connection failed", "details": str(e)}, indent=2)
                )
            else:
                console.print(f"[red]✗[/red] SSH connection failed: {e}")
            sys.exit(EXIT_HA_ERROR)

        if porcelain:
            assert formatter is not None
            if is_valid:
                output = formatter.success(
                    {"valid": True, "message": message},
                    metadata={"host": host},
                    suggestions={
                        "common_actions": [
                            "Restart HA: ha-cli system restart",
                            "View logs: ha-cli system logs",
                        ]
                    },
                )
            else:
                output = formatter.error(message, error_code="CONFIG_INVALID")
            write_output(output)
        elif json_output:
            write_output(
                json.dumps({"valid": is_valid, "message": message}, indent=2)
            )
        else:
            if is_valid:
                console.print("[green]✓[/green] Configuration is valid")
            else:
                console.print(f"[red]✗[/red] Configuration invalid: {message}")
                sys.exit(EXIT_HA_ERROR)

    asyncio.run(run_async_command(_check()))


@app.command("logs")
def logs(
    lines: int = typer.Option(100, "--lines", "-n", help="Number of lines to show"),
    filter_pattern: str | None = typer.Option(
        None, "--filter", "-f", help="Filter pattern (grep -i)"
    ),
    errors_only: bool = typer.Option(
        False, "--errors-only", "-e", help="Show only error log via API (no SSH needed)"
    ),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL (for --errors-only)"),
    token: str | None = typer.Option(None, "--token", help="Access token (for --errors-only)"),
    host: str = typer.Option(DEFAULT_HOST, "--host", "-h", help="SSH host (for full logs)"),
    user: str = typer.Option(DEFAULT_USER, "--user", "-u", help="SSH user (for full logs)"),
    raw: bool = typer.Option(False, "--raw", help="Output raw logs without formatting"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """View Home Assistant logs.

    Retrieves recent logs from Home Assistant core.

    Examples:
        ha-cli system logs
        ha-cli system logs --lines 50
        ha-cli system logs --filter "error"
        ha-cli system logs --filter "intent|automation"
        ha-cli system logs --errors-only  # Use API, no SSH needed
    """
    setup_logging(debug)

    async def _logs() -> None:
        formatter = PorcelainFormatter("system logs") if porcelain else None

        # Build client for errors_only mode
        client = None
        if errors_only:
            try:
                url_final, token_final = get_client_config(url, token)
                client = HAClient(url_final, token_final)
                await client.__aenter__()
            except Exception as e:
                logger.debug(f"Failed to connect to API for errors_only: {e}")

        service = SystemService(client=client, host=host, user=user)

        try:
            log_output = await service.get_logs(
                lines=lines,
                filter_pattern=filter_pattern,
                errors_only=errors_only,
            )
        except SSHError as e:
            if porcelain:
                assert formatter is not None
                output = formatter.error(f"SSH connection failed: {e}", error_code="SSH_ERROR")
                write_output(output)
            elif json_output:
                write_output(
                    json.dumps({"error": "SSH connection failed", "details": str(e)}, indent=2)
                )
            else:
                console.print(f"[red]✗[/red] SSH connection failed: {e}")
                console.print("[dim]Tip: Use --errors-only to fetch error log via API (no SSH)[/dim]")
            if client:
                await client.__aexit__(None, None, None)
            sys.exit(EXIT_HA_ERROR)
        finally:
            if client:
                await client.__aexit__(None, None, None)

        if porcelain:
            assert formatter is not None
            # Split into lines for structured output
            log_lines = log_output.strip().split("\n") if log_output.strip() else []
            output = formatter.success(
                {"logs": log_lines},
                metadata={
                    "host": host,
                    "lines_requested": lines,
                    "lines_returned": len(log_lines),
                    "filter": filter_pattern,
                },
                suggestions={
                    "common_actions": [
                        "Filter for errors: ha-cli system logs --filter error",
                        "More lines: ha-cli system logs --lines 200",
                        "Restart HA: ha-cli system restart",
                    ]
                },
            )
            write_output(output)
        elif json_output:
            log_lines = log_output.strip().split("\n") if log_output.strip() else []
            write_output(
                json.dumps(
                    {
                        "logs": log_lines,
                        "lines_requested": lines,
                        "lines_returned": len(log_lines),
                        "filter": filter_pattern,
                    },
                    indent=2,
                )
            )
        elif raw:
            write_output(log_output)
        else:
            # Pretty print with syntax highlighting
            if not log_output.strip():
                console.print("[yellow]No logs found[/yellow]")
                return

            title = f"Home Assistant Logs (last {lines} lines)"
            if filter_pattern:
                title += f" [filter: {filter_pattern}]"

            # Use Panel for nice display
            panel = Panel(
                Syntax(log_output, "log", theme="monokai", word_wrap=True),
                title=title,
                border_style="blue",
            )
            console.print(panel)

    asyncio.run(run_async_command(_logs()))


@app.command("info")
def info(
    host: str = typer.Option(DEFAULT_HOST, "--host", "-h", help="Home Assistant host"),
    user: str = typer.Option(DEFAULT_USER, "--user", "-u", help="SSH user"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Show Home Assistant system information."""
    setup_logging(debug)

    async def _info() -> None:
        formatter = PorcelainFormatter("system info") if porcelain else None
        service = SystemService(host=host, user=user)

        sys_info = await service.get_info()

        if sys_info is None:
            if porcelain:
                assert formatter is not None
                output = formatter.error(
                    "Failed to retrieve system info", error_code="INFO_FAILED"
                )
                write_output(output)
            elif json_output:
                write_output(json.dumps({"error": "Failed to retrieve system info"}, indent=2))
            else:
                console.print("[red]✗[/red] Failed to retrieve system info")
            sys.exit(EXIT_HA_ERROR)

        if porcelain:
            assert formatter is not None
            output = formatter.success(
                sys_info.to_dict(),
                metadata={"host": host},
                suggestions={
                    "common_actions": [
                        "View logs: ha-cli system logs",
                        "Restart: ha-cli system restart",
                        "Check config: ha-cli system check",
                    ]
                },
            )
            write_output(output)
        elif json_output:
            write_output(json.dumps(sys_info.to_dict(), indent=2))
        else:
            console.print("\n[bold cyan]Home Assistant System Info[/bold cyan]")
            console.print(f"  Version: {sys_info.version}")
            console.print(f"  Machine: {sys_info.installation_type}")
            console.print(f"  Host: {sys_info.host}")

    asyncio.run(run_async_command(_info()))


@app.command("call")
def call(
    service_spec: str = typer.Argument(..., help="Service to call (domain.service)"),
    entity: list[str] = typer.Option(
        None, "--entity", "-e", help="Target entity ID(s) - can be repeated"
    ),
    data: str | None = typer.Option(None, "--data", "-d", help="JSON service data"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Call a Home Assistant service.

    Examples:
        ha-cli system call light.turn_on --entity light.office
        ha-cli system call switch.turn_off --entity switch.pump
        ha-cli system call climate.set_temperature --entity climate.lounge --data '{"temperature": 22}'
        ha-cli system call homeassistant.restart
        ha-cli system call notify.mobile_app_iphone --data '{"message": "Hello"}'
    """
    setup_logging(debug)

    # Parse service spec
    if "." not in service_spec:
        console.print(
            f"[red]Error:[/red] Invalid service format: '{service_spec}'. "
            "Expected 'domain.service' (e.g., 'light.turn_on')"
        )
        sys.exit(1)

    domain, service = service_spec.split(".", 1)

    # Parse JSON data if provided
    service_data: dict | None = None
    if data:
        try:
            service_data = json.loads(data)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error:[/red] Invalid JSON in --data: {e}")
            sys.exit(1)

    async def _call() -> None:
        formatter = PorcelainFormatter("system call") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service_obj = SystemService(client=client)

            if not porcelain and not json_output:
                entity_str = f" → {', '.join(entity)}" if entity else ""
                console.print(f"[dim]Calling {domain}.{service}{entity_str}...[/dim]")

            try:
                result = await service_obj.call_service(
                    domain=domain,
                    service=service,
                    entity_ids=list(entity) if entity else None,
                    service_data=service_data,
                )

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {
                            "action": "service_call",
                            "domain": domain,
                            "service": service,
                            "entities": list(entity) if entity else [],
                            "result": result,
                        },
                        metadata={
                            "service_data": service_data,
                        },
                        suggestions={
                            "common_actions": [
                                f"Get state: ha-cli entities state {entity[0]}" if entity else "List entities: ha-cli entities list",
                                f"List {domain} services: ha-cli system services {domain}",
                            ],
                            "related_commands": [
                                "ha-cli system logs",
                            ],
                        },
                    )
                    write_output(output)
                elif json_output:
                    write_output(
                        json.dumps(
                            {
                                "success": True,
                                "domain": domain,
                                "service": service,
                                "entities": list(entity) if entity else [],
                                "result": result,
                            },
                            indent=2,
                        )
                    )
                else:
                    console.print(f"[green]✓[/green] Service {domain}.{service} called successfully")
                    if result and result != {"success": True}:
                        console.print(f"[dim]Result: {result}[/dim]")

            except Exception as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="SERVICE_CALL_FAILED")
                    write_output(output)
                elif json_output:
                    write_output(
                        json.dumps(
                            {"success": False, "error": str(e)},
                            indent=2,
                        )
                    )
                else:
                    console.print(f"[red]✗[/red] Service call failed: {e}")
                sys.exit(EXIT_HA_ERROR)

    asyncio.run(run_async_command(_call()))


@app.command("template")
def template(
    template_str: str | None = typer.Argument(None, help="Jinja2 template to evaluate"),
    file: str | None = typer.Option(None, "--file", "-f", help="Read template from file (- for stdin)"),
    raw: bool = typer.Option(False, "--raw", help="Output without formatting"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Evaluate a Jinja2 template against Home Assistant state.

    Examples:
        ha-cli system template "{{ states('light.office') }}"
        ha-cli system template "{{ now() }}"
        ha-cli system template "{{ states | selectattr('entity_id', 'match', 'light.*') | list | length }} lights"
        echo "{{ now() }}" | ha-cli system template --file -
        ha-cli system template --file template.j2
    """
    setup_logging(debug)

    # Validate input: must provide template_str OR --file, but not both, not neither
    if template_str and file:
        console.print("[red]Error:[/red] Cannot use both template argument and --file")
        sys.exit(1)

    if not template_str and not file:
        console.print("[red]Error:[/red] Must provide template argument or --file")
        sys.exit(1)

    # Read template from file/stdin if needed
    actual_template: str
    if file:
        try:
            if file == "-":
                # Read from stdin
                actual_template = sys.stdin.read()
            else:
                # Read from file
                with open(file) as f:
                    actual_template = f.read()
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to read template: {e}")
            sys.exit(1)
    else:
        actual_template = template_str or ""

    # Remove trailing newline from stdin/file input (common issue)
    actual_template = actual_template.rstrip("\n")

    async def _template() -> None:
        formatter = PorcelainFormatter("system template") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = SystemService(client=client)

            try:
                result = await service.render_template(actual_template)

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {
                            "result": result,
                            "template": actual_template,
                        },
                        metadata={
                            "template_length": len(actual_template),
                            "result_length": len(result),
                        },
                        suggestions={
                            "common_actions": [
                                "Test time: ha-cli system template \"{{ now() }}\"",
                                "Count entities: ha-cli system template \"{{ states | list | length }}\"",
                            ],
                            "related_commands": [
                                "ha-cli entities state <entity_id>",
                            ],
                        },
                    )
                    write_output(output)
                elif json_output:
                    write_output(
                        json.dumps(
                            {
                                "success": True,
                                "template": actual_template,
                                "result": result,
                            },
                            indent=2,
                        )
                    )
                elif raw:
                    # Raw output - just the result, no formatting
                    write_output(result)
                else:
                    # Human-readable output with some formatting
                    console.print(f"[bold]Result:[/bold] {result}")

            except Exception as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="TEMPLATE_ERROR")
                    write_output(output)
                elif json_output:
                    write_output(
                        json.dumps(
                            {"success": False, "error": str(e)},
                            indent=2,
                        )
                    )
                else:
                    console.print(f"[red]✗[/red] Template failed: {e}")
                sys.exit(EXIT_HA_ERROR)

    asyncio.run(run_async_command(_template()))


@app.command("integrations")
def integrations(
    domain: str | None = typer.Option(None, "--domain", "-d", help="Filter by integration domain"),
    unhealthy: bool = typer.Option(False, "--unhealthy", help="Show only non-loaded entries"),
    url: str | None = typer.Option(None, "--url", help="Home Assistant URL"),
    token: str | None = typer.Option(None, "--token", help="Access token"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    porcelain: bool = typer.Option(
        False, "--porcelain", help="Machine-readable output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """List integration (config entry) status.

    Shows all configured integrations with their current state.

    States:
        loaded         - Integration is running normally
        not_loaded     - Integration not loaded (may be disabled)
        setup_error    - Failed during setup
        setup_retry    - Setup failed, will retry
        migration_error - Migration failed
        failed_unload  - Failed to unload

    Examples:
        ha-cli system integrations                     # List all integrations
        ha-cli system integrations --domain sonos     # Filter by domain
        ha-cli system integrations --unhealthy        # Show only unhealthy entries
        ha-cli system integrations --porcelain        # Machine-readable output
    """
    setup_logging(debug)

    async def _integrations() -> None:
        formatter = PorcelainFormatter("system integrations") if porcelain else None

        url_final, token_final = get_client_config(url, token)

        async with HAClient(url_final, token_final) as client:
            service = SystemService(client=client)

            try:
                entries = await service.get_integrations(
                    domain=domain,
                    unhealthy_only=unhealthy,
                )

                # Summarize by state
                state_counts: dict[str, int] = {}
                for entry in entries:
                    state = entry.get("state", "unknown")
                    state_counts[state] = state_counts.get(state, 0) + 1

                if porcelain:
                    assert formatter is not None
                    output = formatter.success(
                        {
                            "integrations": entries,
                            "count": len(entries),
                            "state_summary": state_counts,
                        },
                        metadata={
                            "domain_filter": domain,
                            "unhealthy_filter": unhealthy,
                        },
                        suggestions={
                            "common_actions": [
                                "Filter by domain: ha-cli system integrations --domain <domain>",
                                "Show unhealthy: ha-cli system integrations --unhealthy",
                            ],
                            "related_commands": [
                                "ha-cli system logs",
                                "ha-cli system restart",
                            ],
                        },
                    )
                    write_output(output)
                elif json_output:
                    write_output(
                        json.dumps(
                            {
                                "integrations": entries,
                                "count": len(entries),
                                "state_summary": state_counts,
                            },
                            indent=2,
                        )
                    )
                else:
                    # Human-readable output
                    if not entries:
                        if unhealthy:
                            msg = "No unhealthy integrations found"
                            if domain:
                                msg += f" for domain: {domain}"
                            console.print(f"[green]✓[/green] {msg}")
                        else:
                            msg = "No integrations found"
                            if domain:
                                msg += f" for domain: {domain}"
                            console.print(f"[yellow]{msg}[/yellow]")
                        return

                    # Group by state for display
                    by_state: dict[str, list[dict]] = {}
                    for entry in entries:
                        state = entry.get("state", "unknown")
                        if state not in by_state:
                            by_state[state] = []
                        by_state[state].append(entry)

                    # Display summary
                    console.print(f"\n[bold cyan]Integration Status[/bold cyan] ({len(entries)} entries)")
                    if domain:
                        console.print(f"[dim]Filtered by domain: {domain}[/dim]")

                    # Show unhealthy first if mixed
                    for state in sorted(by_state.keys(), key=lambda s: (s == "loaded", s)):
                        state_entries = by_state[state]
                        if state == "loaded":
                            style = "green"
                            icon = "✓"
                        else:
                            style = "red" if state in ("setup_error", "migration_error") else "yellow"
                            icon = "✗" if style == "red" else "⚠"

                        console.print(f"\n[{style}]{icon} {state}[/{style}] ({len(state_entries)})")
                        for entry in state_entries[:10]:  # Limit displayed per state
                            title = entry.get("title", "")
                            entry_domain = entry.get("domain", "")
                            disabled = entry.get("disabled_by")
                            disabled_note = f" [dim](disabled by: {disabled})[/dim]" if disabled else ""
                            console.print(f"  • {entry_domain}: {title}{disabled_note}")
                        if len(state_entries) > 10:
                            console.print(f"  [dim]... and {len(state_entries) - 10} more[/dim]")

            except Exception as e:
                if porcelain:
                    assert formatter is not None
                    output = formatter.error(str(e), error_code="INTEGRATIONS_ERROR")
                    write_output(output)
                elif json_output:
                    write_output(
                        json.dumps(
                            {"success": False, "error": str(e)},
                            indent=2,
                        )
                    )
                else:
                    console.print(f"[red]✗[/red] Failed to get integrations: {e}")
                sys.exit(EXIT_HA_ERROR)

    asyncio.run(run_async_command(_integrations()))


@app.command("version")
def version() -> None:
    """Show system domain version."""
    from ... import __version__

    console.print(f"ha-cli system version {__version__}")

"""Control commands for automations (enable, disable, reload)."""

import asyncio
import sys

import typer
from rich.console import Console

from ....common.cli_utils import run_async_command, setup_logging, write_output
from ....common.client import HAClient
from ....common.config import get_client_config
from ....common.exceptions import EXIT_HA_ERROR
from ....common.porcelain import PorcelainFormatter
from ..service import AutomationWS

console = Console()


def enable(
    automation_id: str = typer.Argument(..., help="Automation ID to enable"),
    url: str | None = typer.Option(None, "--url", "-u"),
    token: str | None = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Enable an automation."""
    setup_logging(debug)

    async def _enable() -> None:
        formatter = PorcelainFormatter("automations enable") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationWS(client)
                await service.enable_automation(automation_id)

                if porcelain:
                    assert formatter is not None
                    porcelain_output = formatter.success(
                        {"automation_id": automation_id, "state": "enabled"},
                        {"action": "enable", "automation_id": automation_id},
                        {
                            "common_actions": [
                                f"Disable: ha-cli automations disable {automation_id}",
                                f"Read: ha-cli automations read {automation_id}",
                            ]
                        },
                    )
                    write_output(porcelain_output)
                else:
                    console.print(f"[green]✓[/green] Automation '{automation_id}' enabled")

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                write_output(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_enable()))


def disable(
    automation_id: str = typer.Argument(..., help="Automation ID to disable"),
    url: str | None = typer.Option(None, "--url", "-u"),
    token: str | None = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Disable an automation."""
    setup_logging(debug)

    async def _disable() -> None:
        formatter = PorcelainFormatter("automations disable") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationWS(client)
                await service.disable_automation(automation_id)

                if porcelain:
                    assert formatter is not None
                    porcelain_output = formatter.success(
                        {"automation_id": automation_id, "state": "disabled"},
                        {"action": "disable", "automation_id": automation_id},
                        {
                            "common_actions": [
                                f"Enable: ha-cli automations enable {automation_id}",
                                f"Read: ha-cli automations read {automation_id}",
                            ]
                        },
                    )
                    write_output(porcelain_output)
                else:
                    console.print(f"[yellow]○[/yellow] Automation '{automation_id}' disabled")

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                write_output(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_disable()))


def reload(
    url: str | None = typer.Option(None, "--url", "-u"),
    token: str | None = typer.Option(None, "--token", "-t"),
    timeout: int = typer.Option(10, "--timeout"),
    porcelain: bool = typer.Option(False, "--porcelain"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Reload all automations from configuration."""
    setup_logging(debug)

    async def _reload() -> None:
        formatter = PorcelainFormatter("automations reload") if porcelain else None

        try:
            url_final, token_final = get_client_config(url, token)

            async with HAClient(url_final, token_final, timeout) as client:
                service = AutomationWS(client)
                await service.reload_automations()

                if porcelain:
                    assert formatter is not None
                    porcelain_output = formatter.success(
                        {"reloaded": True},
                        {"action": "reload"},
                        {
                            "common_actions": [
                                "ha-cli automations list --porcelain",
                            ]
                        },
                    )
                    write_output(porcelain_output)
                else:
                    console.print("[green]✓[/green] All automations reloaded")

        except Exception as e:
            if porcelain and formatter:
                error_output = formatter.error(e)
                write_output(error_output)
                sys.exit(EXIT_HA_ERROR)
            else:
                raise

    asyncio.run(run_async_command(_reload()))

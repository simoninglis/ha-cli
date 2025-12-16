"""Common CLI utilities shared across domain CLIs."""

import json
import logging
import sys
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import TypeVar

from rich.console import Console

from .exceptions import EXIT_HA_ERROR, EXIT_NETWORK_ERROR, HAAutomationError

# Type variable for async command return type
T = TypeVar('T')

# Shared console instance for rich output
console = Console()

# Thread-local porcelain mode flag (set by commands before calling run_async_command)
_porcelain_mode: bool = False


def set_porcelain_mode(enabled: bool) -> None:
    """Set porcelain mode for error handling.

    Args:
        enabled: If True, errors will be output as JSON instead of Rich format.
    """
    global _porcelain_mode
    _porcelain_mode = enabled


def is_porcelain_mode() -> bool:
    """Check if porcelain mode is enabled."""
    return _porcelain_mode


def _emit_porcelain_error(
    command: str,
    error_type: str,
    message: str,
    details: dict | None = None
) -> None:
    """Emit a structured JSON error for porcelain mode."""
    error_obj: dict[str, str | dict | None] = {
        "type": error_type,
        "message": message,
    }
    if details:
        error_obj["details"] = details

    error_response: dict[str, object] = {
        "command": command,
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "error",
        "error": error_obj,
        "suggestions": {
            "troubleshooting": [
                "Check Home Assistant logs for more details",
                "Verify ha-cli configuration is correct",
                "Try with --debug flag for more information"
            ]
        }
    }
    sys.stdout.write(json.dumps(error_response, indent=2))
    sys.stdout.write('\n')
    sys.stdout.flush()


def write_output(text: str, newline: bool = True, flush: bool = True) -> None:
    """Write text to stdout in a controlled manner.

    This function avoids issues with Python's print() adding unwanted
    newlines in JSON/structured output.

    Args:
        text: The text to write to stdout.
        newline: If True, append a newline after the text.
        flush: If True, flush stdout after writing.
    """
    sys.stdout.write(text)
    if newline:
        sys.stdout.write('\n')
    if flush:
        sys.stdout.flush()


def setup_logging(debug: bool = False) -> None:
    """Configure logging for CLI commands.

    Args:
        debug: If True, set logging level to DEBUG. Otherwise WARNING.
    """
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


async def run_async_command(coro: Awaitable[T], command: str = "unknown") -> T:
    """Run async command and handle exceptions gracefully.

    Args:
        coro: The coroutine to execute.
        command: The command name for error reporting in porcelain mode.

    Returns:
        The result of the coroutine if successful.

    Raises:
        SystemExit: On HAAutomationError (exit code 2) or other exceptions (exit code 3).
    """
    logger = logging.getLogger(__name__)
    try:
        return await coro
    except HAAutomationError as e:
        if _porcelain_mode:
            _emit_porcelain_error(
                command=command,
                error_type=e.__class__.__name__,
                message=e.message,
                details=e.details
            )
        else:
            console.print(f"[red]Error:[/red] {e.message}")
            if e.details:
                logger.debug(f"Error details: {e.details}")
        sys.exit(EXIT_HA_ERROR)
    except Exception as e:
        if _porcelain_mode:
            _emit_porcelain_error(
                command=command,
                error_type=e.__class__.__name__,
                message=str(e)
            )
        else:
            console.print(f"[red]Unexpected error:[/red] {e}")
            logger.exception("Unexpected error")
        sys.exit(EXIT_NETWORK_ERROR)

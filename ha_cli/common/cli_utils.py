"""Common CLI utilities shared across domain CLIs."""

import logging
import sys
from collections.abc import Awaitable
from typing import TypeVar

from rich.console import Console

from .exceptions import EXIT_HA_ERROR, EXIT_NETWORK_ERROR, HAAutomationError

# Type variable for async command return type
T = TypeVar('T')

# Shared console instance for rich output
console = Console()


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


async def run_async_command(coro: Awaitable[T]) -> T:
    """Run async command and handle exceptions gracefully.

    Args:
        coro: The coroutine to execute.

    Returns:
        The result of the coroutine if successful.

    Raises:
        SystemExit: On HAAutomationError (exit code 2) or other exceptions (exit code 3).
    """
    logger = logging.getLogger(__name__)
    try:
        return await coro
    except HAAutomationError as e:
        console.print(f"[red]Error:[/red] {e.message}")
        if e.details:
            logger.debug(f"Error details: {e.details}")
        sys.exit(EXIT_HA_ERROR)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.exception("Unexpected error")
        sys.exit(EXIT_NETWORK_ERROR)

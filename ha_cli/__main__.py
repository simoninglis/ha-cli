"""Entry point for ha-cli."""

import sys

from .cli import app


def main() -> None:
    """Main entry point for ha-cli."""
    app()


def automation_compat() -> None:
    """Backward compatibility entry point for ha-automation command."""
    # Insert 'automations' as the first argument to route to automations subcommand
    sys.argv.insert(1, "automations")
    app()


if __name__ == "__main__":
    main()
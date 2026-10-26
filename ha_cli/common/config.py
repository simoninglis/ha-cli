"""Configuration utilities for ha-cli."""

import logging
import os
import sys

logger = logging.getLogger(__name__)

from .envfile import from_env_file, load_env_file
from .exceptions import MissingCredentialsError
from .utils import get_config_path, load_config, resolve_cli_token, save_config


def get_client_config(
    url: str | None = None,
    token: str | None = None,
    timeout: int = 10,
    interactive: bool = True,
) -> tuple[str, str]:
    """Get client configuration from args, env, config file, or prompt.

    Configuration sources (in order of precedence):
    1. Command line arguments
    2. Environment variables (including .env file)
    3. Config file (~/.config/home-assistant-cli/config.json) - URL only; a token
       there is ignored with a warning
    4. Interactive prompt (if interactive=True and stdin is a terminal); the token
       entered is used for this run and never saved
    
    Args:
        url: Home Assistant URL from command line
        token: Name of the env var holding the token, from --token
        timeout: Request timeout (not used in this function)
        interactive: Whether to prompt for missing values
        
    Returns:
        Tuple of (url, token)
        
    Raises:
        MissingCredentialsError: (a ValueError) If credentials cannot be found and no
            prompt is possible
    """
    # Load .env file if it exists, minus any token in it (tokens: environment only)
    load_env_file()


    # 1. Try command line args. --token names an env var; a literal token is refused,
    #    because argv is readable by every user on the host.
    if token is not None:
        if from_env_file(token):
            import typer

            raise typer.BadParameter(
                f"{token} was set by a .env file: tokens are only taken from the environment",
                param_hint="'--token'",
            )
        try:
            token = resolve_cli_token(token)
        except ValueError as e:
            import typer

            # A usage error, printed by Click without a traceback; `from None` drops the chain.
            raise typer.BadParameter(str(e), param_hint="'--token'") from None
    if url and token:
        return url, token
    
    # 2. Try environment variables (.env values are in os.environ by now, minus tokens).
    #    The token is used exactly as found: never treated as the name of another
    #    variable to look up (that second hop could land on a .env-supplied value).
    if not url:
        url = os.environ.get("HA_URL", os.environ.get("HOME_ASSISTANT_URL"))
    if not token:
        token = os.environ.get("HA_TOKEN", os.environ.get("HOME_ASSISTANT_TOKEN"))
    
    if url and token:
        return url, token
    
    # 3. Try config file - for the URL only. A token is never read from (or written
    #    to) a file: HA tokens live in the environment (e.g. injected by bao-run), and
    #    a token left in an old config file would otherwise be used silently.
    config_path = get_config_path()
    if config_path.exists():
        config = load_config(config_path)
        if not url:
            url = config.get("url")
        if config.get("token"):
            logger.warning(
                "Ignoring the token in %s: ha-cli no longer reads tokens from files. "
                "Set HA_TOKEN in the environment and remove the token from that file.",
                config_path,
            )

    if url and token:
        return url, token

    # 4. Interactive prompt - only with a terminal on stdin. Without one (an agent,
    #    cron, a pipe) typer.prompt would block forever waiting for input, so fail
    #    fast with the usage error below instead.
    if interactive and _stdin_is_tty():
        import typer

        try:
            if not url:
                url = typer.prompt("Home Assistant URL (e.g. http://10.0.0.5:8123)")
            if not token:
                token = typer.prompt("Access Token (used for this run only, never saved)", hide_input=True)
        except (typer.Abort, EOFError, KeyboardInterrupt):
            raise MissingCredentialsError("Cancelled: Home Assistant URL / token not provided.") from None

        # Remember the URL (not a secret) when there's no config file yet. The token
        # is never saved, and an existing file is left alone.
        if url and not config_path.exists():
            try:
                save_config(config_path, {"url": url})
            except OSError as e:
                logger.debug(f"Could not save URL to {config_path}: {e}")

        if url and token:
            return url, token

    # If we get here, we couldn't find credentials
    missing = []
    if not url:
        missing.append("URL")
    if not token:
        missing.append("token")
    
    hints = []
    if not url:
        hints.append("HA_URL (or --url)")
    if not token:
        hints.append("HA_TOKEN in the environment (e.g. via bao-run)")
    raise MissingCredentialsError(
        f"Missing Home Assistant {' and '.join(missing)}. Set {' and '.join(hints)}."
    )


def _stdin_is_tty() -> bool:
    """True when a person could answer a prompt (stdin is a terminal)."""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False
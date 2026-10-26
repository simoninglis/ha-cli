"""The one place ha-cli reads a .env file.

A .env file may set ordinary settings (HA_URL, HA_SSH_HOST, ...) but never a token:
HA tokens come from the process environment (e.g. injected by bao-run), never from
a file on disk. Every module that wants .env values calls load_env_file(); nothing
calls python-dotenv's load_dotenv() directly, because that would put a file's token
into os.environ where it is indistinguishable from a real one.
"""

import logging
import os

from dotenv import dotenv_values, find_dotenv

logger = logging.getLogger(__name__)

# Variables that hold an HA token by default. --token can name others; those are
# refused if a .env file set them (see from_env_file).
TOKEN_ENV_VARS = ("HA_TOKEN", "HOME_ASSISTANT_TOKEN")

# Names this process took from a .env file
_FROM_ENV_FILE: set[str] = set()


def read_env_file() -> dict[str, str | None]:
    """Values from the nearest .env, searching up from the working directory."""
    path = find_dotenv(usecwd=True)
    return dict(dotenv_values(path)) if path else {}


def load_env_file() -> None:
    """Copy .env values into os.environ, except tokens; never override the environment.

    Safe to call repeatedly. A token variable in the file is skipped with a warning
    that names the variable, never its value.
    """
    for name, value in read_env_file().items():
        if value is None or name in os.environ:
            continue
        if name in TOKEN_ENV_VARS:
            logger.warning(
                "Ignoring %s in a .env file: ha-cli only takes tokens from the environment.", name
            )
            continue
        os.environ[name] = value
        _FROM_ENV_FILE.add(name)


def from_env_file(name: str) -> bool:
    """True if `name` got its value from a .env file rather than the real environment."""
    return name in _FROM_ENV_FILE and name in os.environ

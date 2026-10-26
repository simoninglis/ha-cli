"""Default values for ha-cli configuration.

These defaults are extracted to allow the CLI to work as a standalone package
while still supporting environment variable overrides for site-specific values.

Environment variables can be set directly or via a .env file in the working directory.
"""

import os

from .envfile import load_env_file

# Load .env file if present (before reading env vars). Never a token: see envfile.py
load_env_file()

# SSH connection defaults
DEFAULT_SSH_HOST = os.environ.get("HA_SSH_HOST", "homeassistant")
DEFAULT_SSH_USER = os.environ.get("HA_SSH_USER", "root")

# File Editor addon URL (blank by default - must be configured per-site)
DEFAULT_FILE_EDITOR_URL = os.environ.get("HA_FILE_EDITOR_URL", "")

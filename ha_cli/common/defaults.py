"""Default values for ha-cli configuration.

These defaults are extracted to allow the CLI to work as a standalone package
while still supporting environment variable overrides for site-specific values.

Environment variables can be set directly or via a .env file in the working directory.
"""

import os

from dotenv import load_dotenv

# Load .env file if present (before reading env vars)
load_dotenv()

# SSH connection defaults
DEFAULT_SSH_HOST = os.environ.get("HA_SSH_HOST", "homeassistant")
DEFAULT_SSH_USER = os.environ.get("HA_SSH_USER", "root")

# File Editor addon URL (blank by default - must be configured per-site)
DEFAULT_FILE_EDITOR_URL = os.environ.get("HA_FILE_EDITOR_URL", "")

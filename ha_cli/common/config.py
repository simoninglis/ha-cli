"""Configuration utilities for ha-cli."""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

from .utils import get_config_path, get_token_from_env, load_config, save_config


def get_client_config(
    url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: int = 10,
    interactive: bool = True,
) -> Tuple[str, str]:
    """Get client configuration from args, env, config file, or prompt.
    
    Configuration sources (in order of precedence):
    1. Command line arguments
    2. Environment variables (including .env file)
    3. Config file (~/.ha-cli/config.json)
    4. Interactive prompt (if interactive=True)
    
    Args:
        url: Home Assistant URL from command line
        token: Access token from command line
        timeout: Request timeout (not used in this function)
        interactive: Whether to prompt for missing values
        
    Returns:
        Tuple of (url, token)
        
    Raises:
        ValueError: If credentials cannot be found and interactive=False
    """
    # Load .env file if it exists (from current directory or parent directories)
    load_dotenv()
    
    # 1. Try command line args
    if url and token:
        return url, get_token_from_env(token)
    
    # 2. Try environment variables (now includes .env file values)
    if not url:
        url = os.environ.get("HA_URL", os.environ.get("HOME_ASSISTANT_URL"))
    if not token:
        token = os.environ.get("HA_TOKEN", os.environ.get("HOME_ASSISTANT_TOKEN"))
    
    if url and token:
        return url, get_token_from_env(token)
    
    # 3. Try config file
    config_path = get_config_path()
    if config_path.exists():
        config = load_config(config_path)
        if not url:
            url = config.get("url")
        if not token:
            token = config.get("token")
    
    if url and token:
        return url, get_token_from_env(token)
    
    # 4. Interactive prompt (if enabled)
    if interactive:
        try:
            import typer
            
            if not url:
                url = typer.prompt("Home Assistant URL", default="http://homeassistant.local:8123")
            if not token:
                token = typer.prompt("Access Token", hide_input=True)
            
            # Save to config for next time
            config_path.parent.mkdir(parents=True, exist_ok=True)
            save_config(config_path, {"url": url, "token": token})
            
            return url, get_token_from_env(token)
            
        except Exception as e:
            # If typer is not available or prompt fails, fall through to error
            logger.debug(f"Interactive prompt failed: {e}")
    
    # If we get here, we couldn't find credentials
    missing = []
    if not url:
        missing.append("URL")
    if not token:
        missing.append("token")
    
    raise ValueError(
        f"Missing Home Assistant {' and '.join(missing)}. "
        "Please provide via command line, environment variables, or .env file."
    )
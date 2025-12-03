"""Utility functions for Home Assistant Automation CLI."""

import json
import logging
import os
from pathlib import Path
from typing import Any

import ruamel.yaml

logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from JSON file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    if not config_path.exists():
        return {}
    
    with open(config_path) as f:
        return json.load(f)


def save_config(config_path: Path, config: dict[str, Any]) -> None:
    """Save configuration to JSON file.
    
    Args:
        config_path: Path to configuration file
        config: Configuration dictionary
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def load_yaml_file(file_path: str) -> dict[str, Any]:
    """Load YAML file.
    
    Args:
        file_path: Path to YAML file
        
    Returns:
        Parsed YAML data
    """
    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    with open(file_path) as f:
        return yaml.load(f)


def save_yaml_file(file_path: str, data: dict[str, Any]) -> None:
    """Save data to YAML file.
    
    Args:
        file_path: Path to YAML file
        data: Data to save
    """
    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 1000
    with open(file_path, "w") as f:
        yaml.dump(data, f)


def format_timestamp(timestamp: str | None) -> str:
    """Format ISO timestamp for display.
    
    Args:
        timestamp: ISO format timestamp
        
    Returns:
        Formatted timestamp or "Never"
    """
    if not timestamp:
        return "Never"
    
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.debug(f"Failed to parse timestamp '{timestamp}': {e}")
        return timestamp


def sanitize_filename(name: str) -> str:
    """Sanitize string for use as filename.
    
    Args:
        name: String to sanitize
        
    Returns:
        Sanitized filename
    """
    # Replace problematic characters
    replacements = {
        "/": "-",
        "\\": "-",
        ":": "-",
        "*": "-",
        "?": "-",
        '"': "",
        "<": "-",
        ">": "-",
        "|": "-",
        " ": "_",
    }
    
    result = name
    for old, new in replacements.items():
        result = result.replace(old, new)
    
    # Remove leading/trailing dots and spaces
    result = result.strip(". ")
    
    # Limit length
    if len(result) > 100:
        result = result[:100]
    
    return result or "unnamed"


def get_entity_domain(entity_id: str) -> str:
    """Extract domain from entity ID.
    
    Args:
        entity_id: Entity ID (e.g., "light.living_room")
        
    Returns:
        Domain (e.g., "light")
    """
    return entity_id.split(".", 1)[0] if "." in entity_id else ""


def get_entity_name(entity_id: str) -> str:
    """Extract name from entity ID.
    
    Args:
        entity_id: Entity ID (e.g., "light.living_room")
        
    Returns:
        Name (e.g., "living_room")
    """
    return entity_id.split(".", 1)[1] if "." in entity_id else entity_id


def parse_service_call(service: str) -> tuple[str, str]:
    """Parse service call into domain and service.
    
    Args:
        service: Service call (e.g., "light.turn_on")
        
    Returns:
        Tuple of (domain, service)
    """
    parts = service.split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", service


def merge_dicts(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.
    
    Args:
        base: Base dictionary
        update: Dictionary with updates
        
    Returns:
        Merged dictionary
    """
    result = base.copy()
    
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add when truncated
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def format_automation_summary(automation: dict[str, Any]) -> str:
    """Format automation summary for display.
    
    Args:
        automation: Automation data
        
    Returns:
        Formatted summary
    """
    lines = []
    
    # Basic info
    lines.append(f"Name: {automation.get('alias', 'Unnamed')}")
    lines.append(f"ID: {automation.get('id', 'Unknown')}")
    
    # Mode
    mode = automation.get('mode', 'single')
    lines.append(f"Mode: {mode}")
    if mode in ['queued', 'parallel']:
        lines.append(f"Max: {automation.get('max', 'Not set')}")
    
    # Counts
    triggers = automation.get('trigger', [])
    conditions = automation.get('condition', [])
    actions = automation.get('action', [])
    
    lines.append("\nComponents:")
    lines.append(f"  Triggers: {len(triggers)}")
    lines.append(f"  Conditions: {len(conditions)}")
    lines.append(f"  Actions: {len(actions)}")
    
    # Description
    if description := automation.get('description'):
        lines.append("\nDescription:")
        lines.append(f"  {description}")
    
    return "\n".join(lines)


def get_config_path() -> Path:
    """Get path to configuration file.

    Checks locations in order of preference:
    1. ~/.config/home-assistant-cli/config.json (canonical)
    2. ~/.config/ha-automation/config.json (legacy)

    Returns the first existing location, or the canonical path if none exist.
    """
    # Canonical location
    canonical_dir = Path.home() / ".config" / "home-assistant-cli"
    canonical_path = canonical_dir / "config.json"

    # Legacy location
    legacy_dir = Path.home() / ".config" / "ha-automation"
    legacy_path = legacy_dir / "config.json"

    # Return first existing path, or canonical if none exist
    if canonical_path.exists():
        return canonical_path
    if legacy_path.exists():
        return legacy_path

    return canonical_path


def get_token_from_env(token_value: str) -> str:
    """Get token value, checking if it's an env var name.
    
    Args:
        token_value: Token or env var name
        
    Returns:
        Actual token value
    """
    # If token looks like an env var name (all caps with underscores)
    if token_value.isupper() and "_" in token_value:
        # Try to get from environment
        env_value = os.environ.get(token_value)
        if env_value:
            return env_value
    
    # Otherwise return as-is
    return token_value
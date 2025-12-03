"""Utility functions for Home Assistant Automation CLI.

DEPRECATED: This module is a backward-compatibility shim.
Import from ha_cli.common.utils instead.

This module re-exports all utilities from ha_cli.common.utils
for backward compatibility with existing code.
"""

# Re-export all utilities from ha_cli.common.utils
from ha_cli.common.utils import (  # noqa: F401
    RegexValidationError,
    compile_user_regex,
    format_automation_summary,
    format_timestamp,
    get_config_path,
    get_entity_domain,
    get_entity_name,
    get_token_from_env,
    load_config,
    load_yaml_file,
    merge_dicts,
    parse_service_call,
    sanitize_filename,
    save_config,
    save_yaml_file,
    truncate_string,
)

__all__ = [
    "load_config",
    "save_config",
    "load_yaml_file",
    "save_yaml_file",
    "format_timestamp",
    "sanitize_filename",
    "get_entity_domain",
    "get_entity_name",
    "parse_service_call",
    "merge_dicts",
    "truncate_string",
    "format_automation_summary",
    "get_config_path",
    "get_token_from_env",
    "RegexValidationError",
    "compile_user_regex",
]

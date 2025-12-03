"""Tests for utility functions not covered in tests/test_utils.py.

This module tests:
- load_config / save_config (JSON config file operations)
- load_yaml_file / save_yaml_file (YAML file operations)
- format_timestamp (timestamp formatting)
- merge_dicts (deep dictionary merging)
- format_automation_summary (automation display formatting)
"""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from ha_cli.common.utils import (
    load_config,
    save_config,
    load_yaml_file,
    save_yaml_file,
    format_timestamp,
    merge_dicts,
    format_automation_summary,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_existing_config(self, tmp_path: Path) -> None:
        """Test loading an existing config file."""
        config_file = tmp_path / "config.json"
        config_data = {"url": "http://ha.local:8123", "token": "test_token"}
        config_file.write_text(json.dumps(config_data))

        result = load_config(config_file)

        assert result == config_data

    def test_load_nonexistent_config(self, tmp_path: Path) -> None:
        """Test loading a non-existent config file returns empty dict."""
        config_file = tmp_path / "nonexistent.json"

        result = load_config(config_file)

        assert result == {}

    def test_load_config_with_nested_data(self, tmp_path: Path) -> None:
        """Test loading config with nested structures."""
        config_file = tmp_path / "config.json"
        config_data = {
            "url": "http://ha.local:8123",
            "settings": {
                "timeout": 30,
                "retry": True
            },
            "tags": ["production", "primary"]
        }
        config_file.write_text(json.dumps(config_data))

        result = load_config(config_file)

        assert result["settings"]["timeout"] == 30
        assert result["tags"] == ["production", "primary"]


class TestSaveConfig:
    """Tests for save_config function."""

    def test_save_config_basic(self, tmp_path: Path) -> None:
        """Test saving a basic config file."""
        config_file = tmp_path / "config.json"
        config_data = {"url": "http://ha.local:8123", "token": "test_token"}

        save_config(config_file, config_data)

        # Verify file was created and contains correct data
        assert config_file.exists()
        saved_data = json.loads(config_file.read_text())
        assert saved_data == config_data

    def test_save_config_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test that save_config creates parent directories."""
        config_file = tmp_path / "nested" / "dir" / "config.json"
        config_data = {"url": "http://ha.local:8123"}

        save_config(config_file, config_data)

        assert config_file.exists()
        assert config_file.parent.exists()

    def test_save_config_overwrites_existing(self, tmp_path: Path) -> None:
        """Test that save_config overwrites existing file."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"old": "data"}))

        new_data = {"new": "data"}
        save_config(config_file, new_data)

        saved_data = json.loads(config_file.read_text())
        assert saved_data == new_data
        assert "old" not in saved_data

    def test_save_config_preserves_indentation(self, tmp_path: Path) -> None:
        """Test that save_config produces formatted JSON."""
        config_file = tmp_path / "config.json"
        config_data = {"url": "http://ha.local:8123", "token": "test"}

        save_config(config_file, config_data)

        content = config_file.read_text()
        # Should be indented (not a single line)
        assert "\n" in content


class TestLoadYamlFile:
    """Tests for load_yaml_file function."""

    def test_load_yaml_basic(self, tmp_path: Path) -> None:
        """Test loading a basic YAML file."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("key: value\nnumber: 42\n")

        result = load_yaml_file(str(yaml_file))

        assert result["key"] == "value"
        assert result["number"] == 42

    def test_load_yaml_nested(self, tmp_path: Path) -> None:
        """Test loading YAML with nested structures."""
        yaml_file = tmp_path / "test.yaml"
        yaml_content = """
parent:
  child: value
  list:
    - item1
    - item2
"""
        yaml_file.write_text(yaml_content)

        result = load_yaml_file(str(yaml_file))

        assert result["parent"]["child"] == "value"
        assert result["parent"]["list"] == ["item1", "item2"]

    def test_load_yaml_preserves_quotes(self, tmp_path: Path) -> None:
        """Test that quoted strings are preserved."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text('key: "quoted value"\n')

        result = load_yaml_file(str(yaml_file))

        assert result["key"] == "quoted value"


class TestSaveYamlFile:
    """Tests for save_yaml_file function."""

    def test_save_yaml_basic(self, tmp_path: Path) -> None:
        """Test saving a basic YAML file."""
        yaml_file = tmp_path / "test.yaml"
        data = {"key": "value", "number": 42}

        save_yaml_file(str(yaml_file), data)

        assert yaml_file.exists()
        content = yaml_file.read_text()
        assert "key:" in content
        assert "value" in content

    def test_save_yaml_nested(self, tmp_path: Path) -> None:
        """Test saving YAML with nested structures."""
        yaml_file = tmp_path / "test.yaml"
        data = {
            "parent": {
                "child": "value",
                "list": ["item1", "item2"]
            }
        }

        save_yaml_file(str(yaml_file), data)

        # Read back and verify
        result = load_yaml_file(str(yaml_file))
        assert result["parent"]["child"] == "value"
        assert result["parent"]["list"] == ["item1", "item2"]


class TestFormatTimestamp:
    """Tests for format_timestamp function."""

    def test_format_valid_timestamp(self) -> None:
        """Test formatting a valid ISO timestamp."""
        timestamp = "2025-06-14T10:30:00+00:00"

        result = format_timestamp(timestamp)

        assert result == "2025-06-14 10:30:00"

    def test_format_timestamp_with_z(self) -> None:
        """Test formatting timestamp with Z timezone."""
        timestamp = "2025-06-14T10:30:00Z"

        result = format_timestamp(timestamp)

        assert result == "2025-06-14 10:30:00"

    def test_format_none_timestamp(self) -> None:
        """Test formatting None returns 'Never'."""
        result = format_timestamp(None)

        assert result == "Never"

    def test_format_empty_timestamp(self) -> None:
        """Test formatting empty string returns 'Never'."""
        result = format_timestamp("")

        assert result == "Never"

    def test_format_invalid_timestamp_returns_original(self) -> None:
        """Test that invalid timestamps return the original string."""
        timestamp = "not-a-timestamp"

        result = format_timestamp(timestamp)

        assert result == "not-a-timestamp"


class TestMergeDicts:
    """Tests for merge_dicts function."""

    def test_merge_simple_dicts(self) -> None:
        """Test merging simple dictionaries."""
        base = {"a": 1, "b": 2}
        update = {"c": 3}

        result = merge_dicts(base, update)

        assert result == {"a": 1, "b": 2, "c": 3}

    def test_merge_overwrites_values(self) -> None:
        """Test that update values overwrite base values."""
        base = {"a": 1, "b": 2}
        update = {"b": 3}

        result = merge_dicts(base, update)

        assert result == {"a": 1, "b": 3}

    def test_merge_deep_nested(self) -> None:
        """Test deep merging of nested dictionaries."""
        base = {
            "level1": {
                "level2": {
                    "a": 1,
                    "b": 2
                }
            }
        }
        update = {
            "level1": {
                "level2": {
                    "c": 3
                }
            }
        }

        result = merge_dicts(base, update)

        assert result["level1"]["level2"]["a"] == 1
        assert result["level1"]["level2"]["b"] == 2
        assert result["level1"]["level2"]["c"] == 3

    def test_merge_does_not_modify_original(self) -> None:
        """Test that merge doesn't modify the original dictionaries."""
        base = {"a": 1}
        update = {"b": 2}
        original_base = base.copy()
        original_update = update.copy()

        merge_dicts(base, update)

        assert base == original_base
        assert update == original_update

    def test_merge_replaces_non_dict_with_dict(self) -> None:
        """Test that non-dict values are replaced by dict values."""
        base = {"a": "string"}
        update = {"a": {"nested": "value"}}

        result = merge_dicts(base, update)

        assert result["a"] == {"nested": "value"}

    def test_merge_replaces_dict_with_non_dict(self) -> None:
        """Test that dict values are replaced by non-dict values."""
        base = {"a": {"nested": "value"}}
        update = {"a": "string"}

        result = merge_dicts(base, update)

        assert result["a"] == "string"

    def test_merge_empty_base(self) -> None:
        """Test merging into empty base."""
        base = {}
        update = {"a": 1, "b": 2}

        result = merge_dicts(base, update)

        assert result == {"a": 1, "b": 2}

    def test_merge_empty_update(self) -> None:
        """Test merging empty update."""
        base = {"a": 1, "b": 2}
        update = {}

        result = merge_dicts(base, update)

        assert result == {"a": 1, "b": 2}


class TestFormatAutomationSummary:
    """Tests for format_automation_summary function."""

    def test_format_basic_automation(self) -> None:
        """Test formatting a basic automation."""
        automation = {
            "alias": "Test Automation",
            "id": "test_123",
            "mode": "single",
            "trigger": [{"platform": "state"}],
            "condition": [],
            "action": [{"service": "light.turn_on"}]
        }

        result = format_automation_summary(automation)

        assert "Test Automation" in result
        assert "test_123" in result
        assert "single" in result
        assert "Triggers: 1" in result
        assert "Conditions: 0" in result
        assert "Actions: 1" in result

    def test_format_automation_with_description(self) -> None:
        """Test formatting automation with description."""
        automation = {
            "alias": "Test",
            "id": "test_123",
            "description": "This automation does something useful",
            "trigger": [],
            "condition": [],
            "action": []
        }

        result = format_automation_summary(automation)

        assert "Description:" in result
        assert "This automation does something useful" in result

    def test_format_queued_mode_shows_max(self) -> None:
        """Test that queued mode shows max value."""
        automation = {
            "alias": "Test",
            "id": "test_123",
            "mode": "queued",
            "max": 10,
            "trigger": [],
            "condition": [],
            "action": []
        }

        result = format_automation_summary(automation)

        assert "queued" in result
        assert "Max: 10" in result

    def test_format_parallel_mode_shows_max(self) -> None:
        """Test that parallel mode shows max value."""
        automation = {
            "alias": "Test",
            "id": "test_123",
            "mode": "parallel",
            "max": 5,
            "trigger": [],
            "condition": [],
            "action": []
        }

        result = format_automation_summary(automation)

        assert "parallel" in result
        assert "Max: 5" in result

    def test_format_missing_alias(self) -> None:
        """Test formatting automation without alias."""
        automation = {
            "id": "test_123",
            "trigger": [],
            "condition": [],
            "action": []
        }

        result = format_automation_summary(automation)

        assert "Unnamed" in result

    def test_format_missing_id(self) -> None:
        """Test formatting automation without id."""
        automation = {
            "alias": "Test",
            "trigger": [],
            "condition": [],
            "action": []
        }

        result = format_automation_summary(automation)

        assert "Unknown" in result

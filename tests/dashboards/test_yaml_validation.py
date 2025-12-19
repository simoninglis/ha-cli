"""Tests for validating dashboard YAML files against live HA instance.

These tests validate:
1. YAML syntax is valid
2. Entity references exist in Home Assistant
3. Card configurations are properly structured
4. !include references resolve correctly

Run with: poetry run pytest tests/dashboards/test_yaml_validation.py -v
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from ha_cli.common.client import HAClient
from ha_cli.common.config import get_client_config

# Path to dashboards directory (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
DASHBOARDS_DIR = REPO_ROOT / "dashboards"


def get_dashboard_files() -> list[Path]:
    """Get all dashboard YAML files (deduplicated)."""
    if not DASHBOARDS_DIR.exists():
        return []
    # Use **/*.yaml to get all YAML files recursively, which includes root level
    # Sort by path for consistent ordering
    files = set(DASHBOARDS_DIR.glob("**/*.yaml"))
    return sorted(files, key=lambda p: str(p))


def load_yaml_with_includes(file_path: Path) -> dict[str, Any]:
    """Load YAML file, resolving !include directives."""

    class IncludeLoader(yaml.SafeLoader):
        """Custom YAML loader that handles !include."""
        pass

    def include_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
        """Handle !include directive."""
        include_path = loader.construct_scalar(node)
        # Resolve relative to the file being loaded
        full_path = file_path.parent / include_path
        if full_path.exists():
            with open(full_path) as f:
                return yaml.load(f, Loader=IncludeLoader)  # noqa: S506 - IncludeLoader inherits from SafeLoader
        else:
            # Return a placeholder indicating missing include
            return {"_include_error": str(full_path), "_include_missing": True}

    IncludeLoader.add_constructor("!include", include_constructor)

    with open(file_path) as f:
        return yaml.load(f, Loader=IncludeLoader)  # noqa: S506 - IncludeLoader inherits from SafeLoader


def extract_entities_from_config(config: Any, entities: set[str] | None = None) -> set[str]:
    """Recursively extract entity IDs from dashboard config."""
    if entities is None:
        entities = set()

    if isinstance(config, dict):
        # Check common entity reference keys
        for key in ["entity", "entity_id", "entities"]:
            if key in config:
                value = config[key]
                if isinstance(value, str) and "." in value:
                    # Validate entity ID format
                    if re.match(r"^[a-z_]+\.[a-z0-9_]+$", value):
                        entities.add(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and "." in item:
                            if re.match(r"^[a-z_]+\.[a-z0-9_]+$", item):
                                entities.add(item)
                        elif isinstance(item, dict) and "entity" in item:
                            entity = item["entity"]
                            if isinstance(entity, str) and re.match(r"^[a-z_]+\.[a-z0-9_]+$", entity):
                                entities.add(entity)

        # Check target in service calls
        if "target" in config and isinstance(config["target"], dict):
            target = config["target"]
            if "entity_id" in target:
                eid = target["entity_id"]
                if isinstance(eid, str) and "." in eid:
                    entities.add(eid)
                elif isinstance(eid, list):
                    for e in eid:
                        if isinstance(e, str) and "." in e:
                            entities.add(e)

        # Recurse into nested structures
        for value in config.values():
            extract_entities_from_config(value, entities)

    elif isinstance(config, list):
        for item in config:
            extract_entities_from_config(item, entities)

    return entities


def find_include_errors(config: Any, errors: list[str] | None = None) -> list[str]:
    """Find any !include resolution errors in config."""
    if errors is None:
        errors = []

    if isinstance(config, dict):
        if config.get("_include_missing"):
            errors.append(f"Missing include: {config.get('_include_error')}")
        for value in config.values():
            find_include_errors(value, errors)
    elif isinstance(config, list):
        for item in config:
            find_include_errors(item, errors)

    return errors


def validate_card_types(config: Any, issues: list[str] | None = None, path: str = "") -> list[str]:
    """Validate card configurations have required fields."""
    if issues is None:
        issues = []

    if isinstance(config, dict):
        # Check if this is a card (has 'type' field)
        if "type" in config:
            card_type = config["type"]
            current_path = f"{path}/{card_type}" if path else card_type

            # Validate common card types
            if card_type in ["entity", "light"]:
                if "entity" not in config:
                    issues.append(f"Card '{current_path}' missing required 'entity' field")

            # Button cards can have entity OR tap_action
            elif card_type == "button":
                if "entity" not in config and "tap_action" not in config:
                    issues.append(f"Card '{current_path}' missing 'entity' or 'tap_action'")

            elif card_type == "entities":
                if "entities" not in config:
                    issues.append(f"Card '{current_path}' missing required 'entities' field")

            elif card_type.startswith("custom:mushroom-"):
                # Mushroom cards typically need entity
                if card_type not in ["custom:mushroom-chips-card", "custom:mushroom-template-card"]:
                    if "entity" not in config:
                        issues.append(f"Mushroom card '{current_path}' may need 'entity' field")

        # Recurse into cards/views
        if "cards" in config and isinstance(config["cards"], list):
            for i, card in enumerate(config["cards"]):
                validate_card_types(card, issues, f"{path}/cards[{i}]")

        if "views" in config and isinstance(config["views"], list):
            for i, view in enumerate(config["views"]):
                view_path = f"views[{i}]"
                if "title" in view:
                    view_path = f"views/{view['title']}"
                validate_card_types(view, issues, view_path)

    elif isinstance(config, list):
        for i, item in enumerate(config):
            validate_card_types(item, issues, f"{path}[{i}]")

    return issues


def _relative_path(p: Path) -> str:
    """Get path relative to dashboards dir for test IDs."""
    try:
        return str(p.relative_to(DASHBOARDS_DIR))
    except ValueError:
        return p.name


class TestDashboardYAMLSyntax:
    """Test that dashboard YAML files have valid syntax."""

    @pytest.mark.parametrize("dashboard_file", get_dashboard_files(), ids=_relative_path)
    def test_yaml_syntax(self, dashboard_file: Path):
        """Test that YAML file can be parsed."""
        try:
            config = load_yaml_with_includes(dashboard_file)
            assert config is not None, f"Empty config in {dashboard_file}"
        except yaml.YAMLError as e:
            pytest.fail(f"YAML syntax error in {dashboard_file}: {e}")

    @pytest.mark.parametrize("dashboard_file", get_dashboard_files(), ids=_relative_path)
    def test_includes_resolve(self, dashboard_file: Path):
        """Test that all !include directives resolve."""
        config = load_yaml_with_includes(dashboard_file)
        errors = find_include_errors(config)

        if errors:
            pytest.fail(f"Include errors in {dashboard_file}:\n" + "\n".join(errors))

    @pytest.mark.parametrize("dashboard_file", [f for f in get_dashboard_files() if f.name not in ["README.md"]], ids=_relative_path)
    def test_has_views(self, dashboard_file: Path):
        """Test that dashboard files have views defined."""
        # Skip include files
        if "includes" in str(dashboard_file):
            pytest.skip("Include file, not a full dashboard")

        config = load_yaml_with_includes(dashboard_file)

        assert "views" in config, f"Dashboard {dashboard_file} missing 'views' key"
        assert isinstance(config["views"], list), f"'views' should be a list in {dashboard_file}"
        assert len(config["views"]) > 0, f"Dashboard {dashboard_file} has no views"


class TestDashboardCardStructure:
    """Test that dashboard cards are properly structured."""

    @pytest.mark.parametrize("dashboard_file", [f for f in get_dashboard_files() if "includes" not in str(f)], ids=_relative_path)
    def test_card_structure(self, dashboard_file: Path):
        """Test that cards have valid structure."""
        config = load_yaml_with_includes(dashboard_file)
        issues = validate_card_types(config)

        # Filter out warnings vs errors
        errors = [i for i in issues if "missing required" in i]
        warnings = [i for i in issues if "may need" in i]

        if errors:
            pytest.fail(f"Card structure errors in {dashboard_file}:\n" + "\n".join(errors))

        # Log warnings but don't fail (these are suggestions, not errors)
        if warnings:
            for warning in warnings:
                print(f"  Warning: {warning}")


@pytest.mark.integration
class TestDashboardEntityValidation:
    """Integration tests that validate entities against live HA."""

    @pytest.fixture
    def ha_entities(self) -> set[str]:
        """Fetch all entity IDs from Home Assistant."""
        async def _get_entities() -> set[str]:
            url, token = get_client_config()
            async with HAClient(url, token, timeout=30) as client:
                states = await client.get_states()
                return {state["entity_id"] for state in states}

        return asyncio.run(_get_entities())

    @pytest.mark.parametrize("dashboard_file", [f for f in get_dashboard_files() if "includes" not in str(f)], ids=_relative_path)
    def test_entities_exist(self, dashboard_file: Path, ha_entities: set[str]):
        """Test that all entity references exist in Home Assistant."""
        config = load_yaml_with_includes(dashboard_file)
        referenced_entities = extract_entities_from_config(config)

        missing = referenced_entities - ha_entities

        if missing:
            missing_list = sorted(missing)
            pytest.fail(
                f"Missing entities in {dashboard_file.name}:\n" +
                "\n".join(f"  - {e}" for e in missing_list)
            )

    def test_room_office_entities(self, ha_entities: set[str]):
        """Specifically test room-office.yaml entity references."""
        dashboard_file = DASHBOARDS_DIR / "room-office.yaml"
        if not dashboard_file.exists():
            pytest.skip("room-office.yaml not found")

        config = load_yaml_with_includes(dashboard_file)
        referenced_entities = extract_entities_from_config(config)

        missing = referenced_entities - ha_entities

        if missing:
            pytest.fail(
                f"Missing entities in room-office.yaml:\n" +
                "\n".join(f"  - {e}" for e in sorted(missing))
            )

    def test_ops_settings_entities(self, ha_entities: set[str]):
        """Specifically test ops-settings.yaml entity references."""
        dashboard_file = DASHBOARDS_DIR / "ops-settings.yaml"
        if not dashboard_file.exists():
            pytest.skip("ops-settings.yaml not found")

        config = load_yaml_with_includes(dashboard_file)
        referenced_entities = extract_entities_from_config(config)

        missing = referenced_entities - ha_entities

        if missing:
            pytest.fail(
                f"Missing entities in ops-settings.yaml:\n" +
                "\n".join(f"  - {e}" for e in sorted(missing))
            )


@pytest.mark.integration
class TestDashboardCompleteness:
    """Integration tests for dashboard completeness."""

    @pytest.fixture
    def ha_entities(self) -> set[str]:
        """Fetch all entity IDs from Home Assistant."""
        async def _get_entities() -> set[str]:
            url, token = get_client_config()
            async with HAClient(url, token, timeout=30) as client:
                states = await client.get_states()
                return {state["entity_id"] for state in states}

        return asyncio.run(_get_entities())

    def test_kill_switches_in_settings(self, ha_entities: set[str]):
        """Test that all kill switches are in the settings dashboard."""
        dashboard_file = DASHBOARDS_DIR / "ops-settings.yaml"
        if not dashboard_file.exists():
            pytest.skip("ops-settings.yaml not found")

        # Get all kill switches from HA
        kill_switches = {e for e in ha_entities if e.startswith("input_boolean.use_new_")}

        # Get entities in dashboard
        config = load_yaml_with_includes(dashboard_file)
        dashboard_entities = extract_entities_from_config(config)

        missing = kill_switches - dashboard_entities

        if missing:
            pytest.fail(
                f"Kill switches not in ops-settings.yaml:\n" +
                "\n".join(f"  - {e}" for e in sorted(missing))
            )

    def test_office_primary_entities(self, ha_entities: set[str]):
        """Test that office primary entities are in room-office dashboard."""
        dashboard_file = DASHBOARDS_DIR / "room-office.yaml"
        if not dashboard_file.exists():
            pytest.skip("room-office.yaml not found")

        # Expected primary office entities
        expected = {
            "light.office",
            "climate.office_ac",
        }

        # Filter to entities that actually exist
        expected_existing = expected & ha_entities

        # Get entities in dashboard
        config = load_yaml_with_includes(dashboard_file)
        dashboard_entities = extract_entities_from_config(config)

        missing = expected_existing - dashboard_entities

        if missing:
            pytest.fail(
                f"Expected office entities not in room-office.yaml:\n" +
                "\n".join(f"  - {e}" for e in sorted(missing))
            )


# Helper function to run validation from CLI
def validate_dashboards() -> dict[str, list[str]]:
    """Run all dashboard validations and return issues."""
    issues: dict[str, list[str]] = {}

    for dashboard_file in get_dashboard_files():
        if "includes" in str(dashboard_file):
            continue

        file_issues = []

        try:
            config = load_yaml_with_includes(dashboard_file)
        except yaml.YAMLError as e:
            file_issues.append(f"YAML syntax error: {e}")
            issues[dashboard_file.name] = file_issues
            continue

        # Check includes
        include_errors = find_include_errors(config)
        file_issues.extend(include_errors)

        # Check card structure
        card_issues = validate_card_types(config)
        file_issues.extend(card_issues)

        if file_issues:
            issues[dashboard_file.name] = file_issues

    return issues


if __name__ == "__main__":
    # Run quick validation
    issues = validate_dashboards()

    if issues:
        print("Dashboard validation issues found:\n")
        for filename, file_issues in issues.items():
            print(f"{filename}:")
            for issue in file_issues:
                print(f"  - {issue}")
    else:
        print("All dashboards validated successfully!")

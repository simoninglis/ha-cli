"""Tests for integrations CLI flow commands."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.cli import app
from ha_cli.common.exceptions import ValidationError
from ha_cli.domains.integrations.cli import _load_flow_data
from ha_cli.domains.integrations.models import ConfigFlowStep

runner = CliRunner()


def test_integrations_help_lists_flow_commands() -> None:
    """The flow and options commands are discoverable."""
    result = runner.invoke(app, ["integrations", "--help"])

    assert result.exit_code == 0
    assert "flow-show" in result.stdout
    assert "flow-submit" in result.stdout
    assert "subentry-start" in result.stdout
    assert "options-show" in result.stdout
    assert "options-update" in result.stdout


def test_load_flow_data_from_json() -> None:
    """Inline JSON must decode to an object."""
    assert _load_flow_data('{"threshold": 20}', None) == {"threshold": 20}


def test_load_flow_data_from_file(tmp_path: Path) -> None:
    """A JSON file is accepted as an alternative to inline data."""
    data_file = tmp_path / "options.json"
    data_file.write_text('{"enabled": true}', encoding="utf-8")

    assert _load_flow_data(None, data_file) == {"enabled": True}


@pytest.mark.parametrize(
    ("data_json", "data_file"),
    [(None, None), ('{"value": 1}', Path("options.json"))],
)
def test_load_flow_data_requires_exactly_one_source(
    data_json: str | None,
    data_file: Path | None,
) -> None:
    """Ambiguous or absent input is rejected before any API request."""
    with pytest.raises(ValidationError, match="exactly one"):
        _load_flow_data(data_json, data_file)


def test_load_flow_data_rejects_non_object_json() -> None:
    """Flow submissions must be named form fields, not arrays or scalars."""
    with pytest.raises(ValidationError, match="JSON object"):
        _load_flow_data("[]", None)


@patch("ha_cli.domains.integrations.cli.get_client_config")
@patch("ha_cli.domains.integrations.cli.HAClient")
@patch("ha_cli.domains.integrations.cli.IntegrationService")
def test_flow_show_json(
    mock_service_class: MagicMock,
    mock_client_class: MagicMock,
    mock_config: MagicMock,
) -> None:
    """flow-show emits the complete current schema."""
    mock_config.return_value = ("http://test:8123", "test-token")
    mock_client_class.return_value.__aenter__.return_value = AsyncMock()
    mock_service = MagicMock()
    mock_service_class.return_value = mock_service
    mock_service.get_flow = AsyncMock(
        return_value=ConfigFlowStep(
            flow_id="flow123",
            handler="battery_notes",
            step_id="battery",
            type="form",
            data_schema=[{"name": "battery_type", "required": True}],
        )
    )

    result = runner.invoke(
        app,
        ["integrations", "flow-show", "flow123", "--json"],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["flow_id"] == "flow123"
    assert output["data_schema"][0]["name"] == "battery_type"
    mock_service.get_flow.assert_awaited_once_with(
        "flow123",
        options=False,
        subentry=False,
    )


@patch("ha_cli.domains.integrations.cli.get_client_config")
@patch("ha_cli.domains.integrations.cli.HAClient")
@patch("ha_cli.domains.integrations.cli.IntegrationService")
def test_flow_submit_options_json(
    mock_service_class: MagicMock,
    mock_client_class: MagicMock,
    mock_config: MagicMock,
) -> None:
    """flow-submit forwards arbitrary objects to an options flow."""
    mock_config.return_value = ("http://test:8123", "test-token")
    mock_client_class.return_value.__aenter__.return_value = AsyncMock()
    mock_service = MagicMock()
    mock_service_class.return_value = mock_service
    mock_service.submit_flow = AsyncMock(
        return_value=ConfigFlowStep(
            flow_id="options123",
            handler="entry123",
            step_id="",
            type="create_entry",
        )
    )

    result = runner.invoke(
        app,
        [
            "integrations",
            "flow-submit",
            "options123",
            "--options",
            "--data-json",
            '{"threshold":20}',
            "--json",
        ],
    )

    assert result.exit_code == 0
    mock_service.submit_flow.assert_awaited_once_with(
        "options123",
        {"threshold": 20},
        options=True,
        subentry=False,
    )


@patch("ha_cli.domains.integrations.cli.get_client_config")
@patch("ha_cli.domains.integrations.cli.HAClient")
@patch("ha_cli.domains.integrations.cli.IntegrationService")
def test_subentry_start_json(
    mock_service_class: MagicMock,
    mock_client_class: MagicMock,
    mock_config: MagicMock,
) -> None:
    """subentry-start resolves the parent and preserves menu options."""
    mock_config.return_value = ("http://test:8123", "test-token")
    mock_client_class.return_value.__aenter__.return_value = AsyncMock()
    mock_service = MagicMock()
    mock_service_class.return_value = mock_service
    entry = MagicMock(entry_id="entry123")
    mock_service.find_entry = AsyncMock(return_value=entry)
    mock_service.start_subentry_flow = AsyncMock(
        return_value=ConfigFlowStep(
            flow_id="subentry123",
            handler="entry123",
            step_id="user",
            type="menu",
            menu_options=["device", "entity"],
        )
    )

    result = runner.invoke(
        app,
        [
            "integrations",
            "subentry-start",
            "battery_notes",
            "battery_note",
            "--json",
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["menu_options"] == ["device", "entity"]
    mock_service.start_subentry_flow.assert_awaited_once_with(
        "entry123",
        "battery_note",
    )

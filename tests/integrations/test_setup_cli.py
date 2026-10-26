"""CLI tests for `integrations setup`: --data/--data-file, --if-missing, load verification."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.domains.integrations.cli import app
from ha_cli.domains.integrations.models import ConfigEntry, ConfigEntryResult

runner = CliRunner()


def entry(state: str, entry_id: str = "e1", title: str = "Radar", reason: str | None = None) -> ConfigEntry:
    return ConfigEntry.from_dict(
        {"entry_id": entry_id, "domain": "local_file", "title": title, "state": state, "reason": reason}
    )


@pytest.fixture()
def service():
    svc = MagicMock()
    svc.find_by_title = AsyncMock(return_value=[])
    svc.setup_integration = AsyncMock(
        return_value=ConfigEntryResult(entry_id="e1", domain="local_file", title="Radar")
    )
    svc.wait_until_settled = AsyncMock(return_value=entry("loaded"))
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    with patch("ha_cli.domains.integrations.cli.get_client_config", return_value=("http://t:8123", "tok")), \
         patch("ha_cli.domains.integrations.cli.HAClient", return_value=client), \
         patch("ha_cli.domains.integrations.cli.IntegrationService", return_value=svc):
        yield svc


DATA = '{"name": "Radar", "file_path": "/config/r.gif"}'


def flat(result) -> str:
    return " ".join(result.output.split())


def test_created_and_loaded(service):
    result = runner.invoke(app, ["setup", "local_file", "--data", DATA])
    assert result.exit_code == 0, result.output
    assert service.setup_integration.await_args.kwargs["data"] == {"name": "Radar", "file_path": "/config/r.gif"}
    assert "Created" in result.output and "loaded" in result.output


def test_created_but_failed_setup_is_an_error(service):
    service.wait_until_settled.return_value = entry("setup_error", reason="file missing")
    result = runner.invoke(app, ["setup", "local_file", "--data", DATA])
    assert result.exit_code == 3
    assert "setup_error (file missing), not loaded" in flat(result)


def test_still_pending_after_wait_is_an_error(service):
    service.wait_until_settled.return_value = entry("setup_in_progress")
    result = runner.invoke(app, ["setup", "local_file", "--data", DATA, "--wait", "1"])
    assert result.exit_code == 3
    assert service.wait_until_settled.await_args.kwargs["timeout"] == 1


def test_if_missing_skips_existing_loaded_entry(service):
    service.find_by_title.return_value = [entry("loaded")]
    result = runner.invoke(app, ["setup", "local_file", "--data", DATA, "--if-missing", "Radar"])
    assert result.exit_code == 0, result.output
    service.setup_integration.assert_not_awaited()
    service.find_by_title.assert_awaited_once_with("local_file", "Radar")
    assert "Exists" in result.output


def test_if_missing_existing_but_broken_is_an_error(service):
    service.find_by_title.return_value = [entry("setup_error")]
    service.wait_until_settled.return_value = entry("setup_error")
    result = runner.invoke(app, ["setup", "local_file", "--if-missing", "Radar"])
    assert result.exit_code == 3
    assert "already existed" in flat(result)
    service.setup_integration.assert_not_awaited()


def test_if_missing_creates_when_absent(service):
    result = runner.invoke(app, ["setup", "local_file", "--data", DATA, "--if-missing", "Radar"])
    assert result.exit_code == 0, result.output
    service.setup_integration.assert_awaited_once()


def test_if_missing_with_duplicates_refuses(service):
    service.find_by_title.return_value = [entry("loaded", "a"), entry("loaded", "b")]
    result = runner.invoke(app, ["setup", "local_file", "--if-missing", "Radar"])
    assert result.exit_code == 1
    service.setup_integration.assert_not_awaited()


def test_invalid_json_never_echoed(service):
    secret = '{"password": "hunter2-secret"'
    result = runner.invoke(app, ["setup", "x", "--data", secret])
    assert result.exit_code == 1
    assert "not valid JSON" in result.output
    assert "hunter2" not in result.output
    service.setup_integration.assert_not_awaited()


def test_data_must_be_an_object(service):
    result = runner.invoke(app, ["setup", "x", "--data", "[1, 2]"])
    assert result.exit_code == 1
    assert "JSON object" in result.output


def test_data_file_and_stdin(service, tmp_path):
    f = tmp_path / "form.json"
    f.write_text(json.dumps({"password": "s3cret"}))
    result = runner.invoke(app, ["setup", "x", "--data-file", str(f)])
    assert result.exit_code == 0, result.output
    assert service.setup_integration.await_args.kwargs["data"] == {"password": "s3cret"}

    result = runner.invoke(app, ["setup", "x", "--data-file", "-"], input='{"a": 1}')
    assert result.exit_code == 0, result.output
    assert service.setup_integration.await_args.kwargs["data"] == {"a": 1}


def test_data_and_data_file_together_refused(service, tmp_path):
    result = runner.invoke(app, ["setup", "x", "--data", "{}", "--data-file", str(tmp_path / "f")])
    assert result.exit_code == 1


def test_porcelain_reports_action_and_state(service):
    service.find_by_title.return_value = [entry("loaded")]
    result = runner.invoke(app, ["setup", "local_file", "--if-missing", "Radar", "--porcelain"])
    out = json.loads(result.output)
    assert out["metadata"]["action"] == "exists"
    assert out["data"]["state"] == "loaded"


@pytest.mark.parametrize("value", ["inf", "nan", "-1", "601"])
def test_wait_must_be_bounded(service, value):
    result = runner.invoke(app, ["setup", "x", "--wait", value])
    assert result.exit_code in (1, 2), result.output  # usage error, before anything runs
    service.setup_integration.assert_not_awaited()


def test_esphome_host_and_port_still_forwarded(service):
    result = runner.invoke(app, ["setup", "esphome", "--host", "10.0.20.50", "--port", "6053"])
    assert result.exit_code == 0, result.output
    kwargs = service.setup_integration.await_args.kwargs
    assert (kwargs["domain"], kwargs["host"], kwargs["port"], kwargs["data"]) == ("esphome", "10.0.20.50", 6053, None)

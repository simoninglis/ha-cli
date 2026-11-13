"""Tests for the updates domain against a scripted fake HA."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ha_cli.common.entity_watch import EntityTracker
from ha_cli.common.exceptions import NotFoundError, ValidationError, WebSocketError
from ha_cli.domains.updates.cli import app
from ha_cli.domains.updates.models import AVAILABLE, CHECK_FAILING, CURRENT, UNAVAILABLE, UpdateInfo, version_matches
from ha_cli.domains.updates.service import UpdatesService

runner = CliRunner()
EID = "update.home_assistant_voice_09ebde"


def ustate(state: str, installed: str = "25.11.0", latest: str = "26.9.0", in_progress: bool = False,
           pct: int | None = None, eid: str = EID) -> dict[str, Any]:
    return {"entity_id": eid, "state": state, "attributes": {
        "friendly_name": "Home Assistant Voice 09ebde", "installed_version": installed, "latest_version": latest,
        "in_progress": in_progress, "update_percentage": pct, "title": "Voice PE", "release_url": ""}}


class FakeHA:
    """get_states, registry lookups, service calls and a scripted subscribe_entities stream.

    ``script`` is a list of (state dict) the entity passes through after the install
    call; each step is also what get_states returns from then on. ``after_check``
    is what the entity reports once update_entity runs after the install.
    """

    def __init__(self, initial: dict[str, Any], script: list[dict[str, Any]] | None = None,
                 after_check: dict[str, Any] | None = None, sw_version: str | None = "26.9.0 (ESPHome 2026.6.0)",
                 install_error: Exception | None = None) -> None:
        self.current = initial
        self.script = script or []
        self.after_check = after_check
        self.sw_version = sw_version
        self.install_error = install_error
        self.calls: list[tuple[str, str]] = []
        self.installed = asyncio.Event()

    async def _ws_call(self, msg_type: str, **kwargs: Any) -> Any:
        if msg_type == "get_states":
            return [self.current, ustate("off", "1.0", "1.0", eid="update.other")]
        if msg_type == "config/entity_registry/get":
            return {"entity_id": kwargs["entity_id"], "device_id": "dev1"}
        if msg_type == "config/device_registry/list":
            return [{"id": "dev1", "sw_version": self.sw_version}]
        raise AssertionError(msg_type)

    async def call_service_ws(self, domain: str, service: str, **kwargs: Any) -> Any:
        self.calls.append((domain, service))
        if (domain, service) == ("update", "install"):
            if self.install_error:
                raise self.install_error
            self.installed.set()
        if (domain, service) == ("homeassistant", "update_entity") and self.installed.is_set() and self.after_check:
            self.current = self.after_check
        return None

    async def ws_stream(self, msg_type: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        assert msg_type == "subscribe_entities"
        s = self.current
        yield {"a": {EID: {"s": s["state"], "a": s["attributes"]}}}
        await self.installed.wait()
        for step in self.script:
            await asyncio.sleep(0)
            self.current = step
            yield {"c": {EID: {"+": {"s": step["state"], "a": step["attributes"]}}}}
        while True:
            await asyncio.sleep(3600)


VOICE_SCRIPT = [
    ustate("on", in_progress=True),
    ustate("on", in_progress=True, pct=0),
    ustate("on", in_progress=True, pct=50),
    ustate("on", in_progress=True, pct=100),
    ustate("unavailable", in_progress=True, pct=100),
    # Back after the restart: blank installed_version until the next check
    ustate("off", installed="", latest="", in_progress=False),
]


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class TestModels:
    def test_blank_versions_are_check_failing_not_current(self) -> None:
        assert UpdateInfo.from_state(ustate("off", "", "")).status == CHECK_FAILING

    def test_status_order(self) -> None:
        assert UpdateInfo.from_state(ustate("on")).status == AVAILABLE
        assert UpdateInfo.from_state(ustate("off", "26.9.0", "26.9.0")).status == CURRENT
        assert UpdateInfo.from_state(ustate("unavailable")).status == UNAVAILABLE
        assert UpdateInfo.from_state(ustate("on", in_progress=True)).status == "installing"

    @pytest.mark.parametrize(("reported", "version", "ok"), [
        ("26.9.0 (ESPHome 2026.6.0)", "26.9.0", True),
        ("26.9.0", "26.9.0", True),
        ("126.9.0", "26.9.0", False),
        ("26.9.01", "26.9.0", False),
        ("25.11.0 (ESPHome 2025.11.0)", "26.9.0", False),
        ("", "26.9.0", False),
    ])
    def test_version_matches_whole_tokens(self, reported: str, version: str, ok: bool) -> None:
        assert version_matches(reported, version) is ok


class TestTracker:
    def test_applies_add_change_and_removed_attributes(self) -> None:
        t = EntityTracker()
        t.apply({"a": {"x.y": {"s": "on", "a": {"k": 1, "j": 2}}}})
        t.apply({"c": {"x.y": {"+": {"s": "off", "a": {"k": 3}}, "-": {"a": ["j"]}}}})
        assert t.get("x.y").state == "off"
        assert t.get("x.y").attributes == {"k": 3}


class TestService:
    def test_list_rejects_malformed_states(self) -> None:
        class Bad:
            async def _ws_call(self, *a: Any, **k: Any) -> Any:
                return {"not": "a list"}
        with pytest.raises(ValidationError):
            run(UpdatesService(Bad()).list_updates())  # type: ignore[arg-type]

    def test_get_unknown_suggests(self) -> None:
        with pytest.raises(NotFoundError):
            run(UpdatesService(FakeHA(ustate("on"))).get("update.nope"))  # type: ignore[arg-type]

    def test_install_watches_restart_and_verifies(self) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=ustate("off", "26.9.0", "26.9.0"))
        r = run(UpdatesService(fake, poll_seconds=0.01).install(EID, timeout=5, verify_wait=1))  # type: ignore[arg-type]
        assert r.verified, r.problem
        assert r.rebooted
        assert r.installed_version == "26.9.0"
        assert ("update", "install") in fake.calls
        assert ("homeassistant", "update_entity") in fake.calls  # blank version forced a re-check

    def test_install_not_verified_when_device_reports_old_version(self) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=ustate("off", "26.9.0", "26.9.0"),
                      sw_version="25.11.0 (ESPHome 2025.11.0)")
        r = run(UpdatesService(fake, poll_seconds=0.01).install(EID, timeout=5, verify_wait=1))  # type: ignore[arg-type]
        assert not r.verified
        assert "sw_version" in (r.problem or "")

    def test_install_not_verified_when_version_never_reported(self) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=None)  # stays blank
        r = run(UpdatesService(fake, poll_seconds=0.01).install(EID, timeout=5, verify_wait=0.2))  # type: ignore[arg-type]
        assert not r.verified
        assert "no version" in (r.problem or "")

    def test_install_rejection_is_a_failure(self) -> None:
        fake = FakeHA(ustate("on"), [], install_error=WebSocketError("home_assistant_error: nope"))
        r = run(UpdatesService(fake, poll_seconds=0.01).install(EID, timeout=5, verify_wait=0.2))  # type: ignore[arg-type]
        assert not r.verified
        assert "rejected" in (r.problem or "")

    def test_install_call_timeout_is_not_a_failure(self) -> None:
        # The service call can outlast the client's 30 s reply wait; the entity decides
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=ustate("off", "26.9.0", "26.9.0"))
        real = fake.call_service_ws

        async def slow(domain: str, service: str, **kw: Any) -> Any:
            await real(domain, service, **kw)
            if (domain, service) == ("update", "install"):
                raise WebSocketError("WebSocket call timed out after 30s")
        fake.call_service_ws = slow  # type: ignore[method-assign]
        r = run(UpdatesService(fake, poll_seconds=0.01).install(EID, timeout=5, verify_wait=1))  # type: ignore[arg-type]
        assert r.verified, r.problem

    def test_install_refuses_without_update(self) -> None:
        with pytest.raises(ValidationError):
            run(UpdatesService(FakeHA(ustate("off", "1", "1"))).install(EID))  # type: ignore[arg-type]


class TestCLI:
    def _patch(self, fake: FakeHA) -> Any:
        class Ctx:
            def __init__(self, *a: Any, **k: Any) -> None:
                pass

            async def __aenter__(self) -> FakeHA:
                return fake

            async def __aexit__(self, *a: Any) -> None:
                return None
        return patch.multiple("ha_cli.domains.updates.cli", HAClient=Ctx,
                              get_client_config=lambda u, t: ("http://ha", "tok"))

    def test_install_porcelain_requires_yes(self) -> None:
        result = runner.invoke(app, ["install", EID, "--porcelain"])
        assert result.exit_code == 1
        assert "--yes" in result.output

    def test_list_flags_check_failing(self) -> None:
        with self._patch(FakeHA(ustate("off", "", ""))):
            result = runner.invoke(app, ["list", "--porcelain"])
        data = json.loads(result.output)
        assert data["metadata"]["status_counts"].get(CHECK_FAILING) == 1

    def test_install_unverified_exits_3(self) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=None)
        with self._patch(fake), patch("ha_cli.domains.updates.cli.UpdatesService",
                                      lambda c: UpdatesService(c, poll_seconds=0.01)):
            result = runner.invoke(app, ["install", EID, "--yes", "--json", "--timeout", "5", "--verify-wait", "0.2"])
        assert result.exit_code == 3
        assert json.loads(result.output)["verified"] is False

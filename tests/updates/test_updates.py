"""Tests for the updates domain against a scripted fake HA.

The fakes let each review finding be reproduced: event orderings around the
install call, an unreadable or lagging device registry, a changed target, a
refused check and a failing state stream.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ha_cli.common.entity_watch import EntityTracker
from ha_cli.common.exceptions import NotFoundError, ValidationError, WebSocketError
from ha_cli.domains.updates import service as service_mod
from ha_cli.domains.updates.cli import app
from ha_cli.domains.updates.models import AVAILABLE, CHECK_FAILING, CURRENT, UNAVAILABLE, UpdateInfo, version_matches
from ha_cli.domains.updates.service import UpdatesService

runner = CliRunner()
EID = "update.home_assistant_voice_09ebde"


def ustate(state: str, installed: str = "25.11.0", latest: str = "26.9.0", in_progress: bool = False,
           pct: int | None = None, eid: str = EID, features: int = 21) -> dict[str, Any]:
    return {"entity_id": eid, "state": state, "attributes": {
        "friendly_name": "Home Assistant Voice 09ebde", "installed_version": installed, "latest_version": latest,
        "in_progress": in_progress, "update_percentage": pct, "title": "Voice PE", "release_url": "",
        "supported_features": features}}


class FakeHA:
    """get_states, registry lookups, service calls and a scripted subscribe_entities stream.

    After the install call the entity runs through ``script``; get_states follows
    it. Once the install has happened, ``update_entity`` switches the entity to
    ``after_check``. ``device`` controls the registry: a version string, None
    (blank), "NO_DEVICE", or an exception to raise. ``device_lag`` makes the
    device report ``device_before`` for that many reads first.
    """

    def __init__(self, initial: dict[str, Any], script: list[dict[str, Any]] | None = None,
                 after_check: dict[str, Any] | None = None, device: Any = "26.9.0 (ESPHome 2026.6.0)",
                 install_error: Exception | None = None, install_delay: float = 0.0,
                 refresh_error: Exception | None = None, stream_error: Exception | None = None,
                 snapshot: dict[str, Any] | None = None, device_lag: int = 0,
                 device_before: str = "25.11.0 (ESPHome 2025.11.0)") -> None:
        self.current = initial
        self.snapshot = snapshot
        self.script = script or []
        self.after_check = after_check
        self.device = device
        self.install_error = install_error
        self.install_delay = install_delay
        self.refresh_error = refresh_error
        self.stream_error = stream_error
        self.device_lag = device_lag
        self.device_before = device_before
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.installed = asyncio.Event()
        self.unsubscribed = False

    async def _ws_call(self, msg_type: str, **kwargs: Any) -> Any:
        if msg_type == "get_states":
            return [self.current, ustate("off", "1.0", "1.0", eid="update.other")]
        if msg_type == "config/entity_registry/get":
            if isinstance(self.device, Exception):
                raise self.device
            return {"entity_id": kwargs["entity_id"], "device_id": None if self.device == "NO_DEVICE" else "dev1"}
        if msg_type == "config/device_registry/list":
            if self.device_lag > 0:
                self.device_lag -= 1
                return [{"id": "dev1", "sw_version": self.device_before}]
            return [{"id": "dev1", "sw_version": self.device}]
        raise AssertionError(msg_type)

    async def call_service_ws(self, domain: str, service: str, **kwargs: Any) -> Any:
        self.calls.append((domain, service, kwargs))
        if (domain, service) == ("update", "install"):
            self.installed.set()
            if self.install_delay:
                await asyncio.sleep(self.install_delay)
            if self.install_error:
                raise self.install_error
        if (domain, service) == ("homeassistant", "update_entity"):
            if self.refresh_error:
                raise self.refresh_error
            if self.installed.is_set() and self.after_check:
                self.current = self.after_check
        return None

    async def ws_stream(self, msg_type: str, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        assert msg_type == "subscribe_entities"
        try:
            if self.stream_error:
                raise self.stream_error
            s = self.snapshot or self.current
            yield {"a": {EID: {"s": s["state"], "a": s["attributes"]}}}
            await self.installed.wait()
            for step in self.script:
                await asyncio.sleep(0)
                self.current = step
                yield {"c": {EID: {"+": {"s": step["state"], "a": step["attributes"]}}}}
            while True:
                await asyncio.sleep(3600)
        finally:
            self.unsubscribed = True


VOICE_SCRIPT = [
    ustate("on", in_progress=True),
    ustate("on", in_progress=True, pct=0),
    ustate("on", in_progress=True, pct=50),
    ustate("on", in_progress=True, pct=100),
    ustate("unavailable", in_progress=True, pct=100),
    # Back after the restart: blank installed_version until the next check
    ustate("off", installed="", latest="", in_progress=False),
]
DONE = ustate("off", "26.9.0", "26.9.0")


def install(fake: FakeHA, **kw: Any) -> Any:
    kw.setdefault("timeout", 5)
    kw.setdefault("verify_wait", 1)
    return asyncio.run(UpdatesService(fake, poll_seconds=0.01).install(EID, **kw))  # type: ignore[arg-type]


class TestModels:
    def test_blank_versions_are_check_failing_not_current(self) -> None:
        assert UpdateInfo.from_state(ustate("off", "", "")).status == CHECK_FAILING

    def test_status_order(self) -> None:
        assert UpdateInfo.from_state(ustate("on")).status == AVAILABLE
        assert UpdateInfo.from_state(DONE).status == CURRENT
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


class TestListAndCheck:
    def test_list_rejects_malformed_states(self) -> None:
        class Bad:
            async def _ws_call(self, *a: Any, **k: Any) -> Any:
                return {"not": "a list"}
        with pytest.raises(ValidationError):
            asyncio.run(UpdatesService(Bad()).list_updates())  # type: ignore[arg-type]

    def test_get_unknown(self) -> None:
        with pytest.raises(NotFoundError):
            asyncio.run(UpdatesService(FakeHA(ustate("on"))).get("update.nope"))  # type: ignore[arg-type]

    def test_refused_check_is_reported_even_if_old_versions_look_fine(self) -> None:
        fake = FakeHA(ustate("on"), refresh_error=WebSocketError("unauthorized: Unauthorized"))
        r = asyncio.run(UpdatesService(fake, poll_seconds=0.01).check(EID, wait=1))  # type: ignore[arg-type]
        assert not r.conclusive
        assert "unauthorized" in (r.refresh_error or "")

    def test_check_still_blank_is_inconclusive(self) -> None:
        r = asyncio.run(UpdatesService(FakeHA(ustate("off", "", "")), poll_seconds=0.01).check(EID, wait=0.05))  # type: ignore[arg-type]
        assert not r.conclusive
        assert r.refresh_error is None


class TestInstall:
    def test_watches_restart_and_verifies_entity_and_device(self) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE)
        r = install(fake)
        assert r.verified, r.problem
        assert r.rebooted
        assert r.verification == "entity and device"
        assert any(c[:2] == ("homeassistant", "update_entity") for c in fake.calls)  # blank version forced a re-check
        assert fake.unsubscribed

    def test_unreadable_device_registry_is_not_verified(self) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE, device=WebSocketError("unauthorized: no"))
        r = install(fake, verify_wait=0.2)
        assert not r.verified
        assert "couldn't read the device" in (r.problem or "")

    def test_no_device_is_entity_only(self) -> None:
        r = install(FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE, device="NO_DEVICE"))
        assert r.verified
        assert r.verification == "entity only (no device)"

    def test_blank_device_version_is_entity_only(self) -> None:
        r = install(FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE, device=None))
        assert r.verified
        assert r.verification == "entity only (device reports no version)"

    def test_device_old_version_is_not_verified(self) -> None:
        r = install(FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE, device="25.11.0 (ESPHome 2025.11.0)"),
                    verify_wait=0.2)
        assert not r.verified
        assert "sw_version" in (r.problem or "")

    def test_device_registry_lagging_is_waited_for(self) -> None:
        r = install(FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE, device_lag=3))
        assert r.verified, r.problem

    def test_version_never_reported_is_not_verified(self) -> None:
        r = install(FakeHA(ustate("on"), VOICE_SCRIPT, after_check=None), verify_wait=0.2)
        assert not r.verified
        assert "no version" in (r.problem or "")

    def test_immediate_rejection(self) -> None:
        r = install(FakeHA(ustate("on"), [], install_error=WebSocketError("home_assistant_error: nope")))
        assert not r.verified
        assert "rejected" in (r.problem or "")

    def test_rejection_after_progress_is_not_lost(self) -> None:
        # Progress shows, then the call fails: must be reported, not cancelled away
        fake = FakeHA(ustate("on"), [ustate("on", in_progress=True, pct=10), ustate("on", in_progress=False)],
                      install_error=WebSocketError("home_assistant_error: flash failed"), install_delay=0.05)
        r = install(fake, verify_wait=0.2)
        assert not r.verified
        assert "flash failed" in (r.problem or "")

    def test_call_reply_timeout_is_not_a_failure(self) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE,
                      install_error=WebSocketError("WebSocket call timed out after 30s"))
        r = install(fake)
        assert r.verified, r.problem

    def test_still_offering_update_after_call_finished(self) -> None:
        with patch.object(service_mod, "STUCK_GRACE_SECONDS", 0.05):
            r = install(FakeHA(ustate("on"), []))
        assert not r.verified
        assert "still offers" in (r.problem or "")

    def test_confirmed_version_changed_installs_nothing(self) -> None:
        fake = FakeHA(ustate("on"))
        with pytest.raises(ValidationError, match="not the confirmed"):
            install(fake, expected_version="26.6.0")
        assert not any(c[:2] == ("update", "install") for c in fake.calls)

    def test_live_snapshot_changed_installs_nothing(self) -> None:
        fake = FakeHA(ustate("on"), snapshot=ustate("on", latest="27.1.0"))
        with pytest.raises(ValidationError, match="changed before the install"):
            install(fake, expected_version="26.9.0")
        assert not any(c[:2] == ("update", "install") for c in fake.calls)
        assert fake.unsubscribed

    def test_pins_version_when_supported(self) -> None:
        fake = FakeHA(ustate("on", features=21 | 2), VOICE_SCRIPT, after_check=DONE)
        install(fake)
        call = next(c for c in fake.calls if c[:2] == ("update", "install"))
        assert call[2]["service_data"] == {"version": "26.9.0"}

    def test_does_not_pin_when_unsupported(self) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE)
        install(fake)
        call = next(c for c in fake.calls if c[:2] == ("update", "install"))
        assert call[2]["service_data"] is None

    def test_stream_failure_is_reported_at_once(self) -> None:
        fake = FakeHA(ustate("on"), stream_error=WebSocketError("Connection closed: boom"))
        r = install(fake, timeout=30)
        assert not r.verified
        assert "boom" in (r.problem or "")
        assert r.duration_seconds < 5  # not a 30 s queue timeout
        assert not any(c[:2] == ("update", "install") for c in fake.calls)

    def test_refuses_without_update(self) -> None:
        with pytest.raises(ValidationError):
            install(FakeHA(DONE))


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
                              get_client_config=lambda u, t: ("http://ha", "tok"),
                              UpdatesService=lambda c: UpdatesService(c, poll_seconds=0.01))

    @pytest.mark.parametrize("flag", ["--porcelain", "--json"])
    def test_machine_output_requires_yes(self, flag: str) -> None:
        fake = FakeHA(ustate("on"), VOICE_SCRIPT, after_check=DONE)
        with self._patch(fake):
            result = runner.invoke(app, ["install", EID, flag])
        assert result.exit_code == 1
        assert "--yes" in result.output
        assert fake.calls == []

    def test_list_flags_check_failing(self) -> None:
        with self._patch(FakeHA(ustate("off", "", ""))):
            result = runner.invoke(app, ["list", "--porcelain"])
        assert json.loads(result.output)["metadata"]["status_counts"].get(CHECK_FAILING) == 1

    def test_install_unverified_exits_3(self) -> None:
        with self._patch(FakeHA(ustate("on"), VOICE_SCRIPT, after_check=None)):
            result = runner.invoke(app, ["install", EID, "--yes", "--json", "--timeout", "5", "--verify-wait", "0.2"])
        assert result.exit_code == 3
        assert json.loads(result.output)["verified"] is False

    def test_check_refused_exits_3(self) -> None:
        with self._patch(FakeHA(ustate("on"), refresh_error=WebSocketError("unauthorized: no"))):
            result = runner.invoke(app, ["check", EID, "--wait", "1"])
        assert result.exit_code == 3
        assert "refused" in result.output

    def test_check_inconclusive_exits_3(self) -> None:
        with self._patch(FakeHA(ustate("off", "", ""))):
            result = runner.invoke(app, ["check", EID, "--wait", "0.05", "--json"])
        assert result.exit_code == 3
        assert json.loads(result.output)["conclusive"] is False

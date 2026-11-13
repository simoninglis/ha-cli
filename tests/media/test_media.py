"""Tests for media tts-test against a scripted fake HA."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ha_cli.common.exceptions import NotFoundError, ValidationError, WebSocketError
from ha_cli.domains.media.cli import app
from ha_cli.domains.media.models import (
    BUSY,
    DISCONNECTED,
    NOT_PLAYED,
    PLAYED,
    REJECTED,
    UNAVAILABLE,
    WATCH_FAILED,
    TtsEngine,
)
from ha_cli.domains.media.service import MediaService

runner = CliRunner()
P = "media_player.voice"
PIPELINES = {"preferred_pipeline": "p1", "pipelines": [
    {"id": "p0", "name": "Other", "tts_engine": "tts.other"},
    {"id": "p1", "name": "GPT Assist", "tts_engine": "tts.home_assistant_cloud", "tts_language": "en-AU",
     "tts_voice": "AnnetteNeural"},
]}


class FakeHA:
    """A player that runs through ``after_speak`` states once tts.speak is called."""

    def __init__(self, initial: str = "idle", after_speak: list[str] | None = None,
                 speak_error: Exception | None = None, exists: bool = True,
                 snapshot: str | None = None, before_speak: list[str] | None = None,
                 speak_delay: float = 0.0, stream_error: Exception | None = None, gap: float = 0.0) -> None:
        self.initial = initial
        self.snapshot = snapshot or initial          # what the subscription says (may differ from get_states)
        self.before_speak = before_speak or []       # transitions that happen before tts.speak is sent
        self.after_speak = after_speak if after_speak is not None else ["playing", "idle"]
        self.speak_error = speak_error
        self.speak_delay = speak_delay
        self.stream_error = stream_error
        self.gap = gap  # pause between post-speak transitions
        self.exists = exists
        self.spoke = asyncio.Event()
        self.speak_calls: list[dict[str, Any]] = []

    async def _ws_call(self, msg_type: str, **kwargs: Any) -> Any:
        if msg_type == "get_states":
            return [{"entity_id": P, "state": self.initial, "attributes": {}}] if self.exists else []
        if msg_type == "assist_pipeline/pipeline/list":
            return PIPELINES
        raise AssertionError(msg_type)

    async def call_service_ws(self, domain: str, service: str, **kwargs: Any) -> Any:
        assert (domain, service) == ("tts", "speak")
        self.speak_calls.append(kwargs)
        if self.speak_error and not self.speak_delay:
            raise self.speak_error  # refused outright: nothing plays
        self.spoke.set()
        if self.speak_delay:
            await asyncio.sleep(self.speak_delay)
        if self.speak_error:
            raise self.speak_error

    async def ws_stream(self, msg_type: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        if self.stream_error:
            raise self.stream_error
        yield {"a": {P: {"s": self.snapshot, "a": {}}}}
        for s in self.before_speak:
            yield {"c": {P: {"+": {"s": s}}}}
        await self.spoke.wait()
        for s in self.after_speak:
            await asyncio.sleep(self.gap)
            yield {"c": {P: {"+": {"s": s}}}}
        while True:
            await asyncio.sleep(3600)


ENGINE = TtsEngine(engine="tts.piper", language="en_GB", voice="en_GB-cori-high")


def _run(fake: FakeHA, **kw: Any) -> Any:
    return asyncio.run(MediaService(fake, poll_seconds=0.01).tts_test(P, ENGINE, timeout=0.5, **kw))  # type: ignore[arg-type]


def test_played_and_finished() -> None:
    fake = FakeHA()
    r = _run(fake)
    assert r.outcome == PLAYED
    assert r.ok
    assert r.finished_after_s is not None
    call = fake.speak_calls[0]
    assert call["target"] == {"entity_id": "tts.piper"}
    assert call["service_data"]["options"] == {"voice": "en_GB-cori-high"}


def test_accepted_but_never_started_is_not_played() -> None:
    # The ops#974 case: tts.speak succeeds, the device can't fetch the audio
    r = _run(FakeHA(after_speak=[]))
    assert r.outcome == NOT_PLAYED
    assert not r.ok
    assert "never reached playing" in (r.problem or "")


def test_drop_off_mid_test_is_disconnected() -> None:
    r = _run(FakeHA(after_speak=["unavailable"]))
    assert r.outcome == DISCONNECTED


def test_unavailable_before_start_skips_speaking() -> None:
    fake = FakeHA(initial="unavailable")
    assert _run(fake).outcome == UNAVAILABLE
    assert fake.speak_calls == []


def test_busy_unless_forced() -> None:
    fake = FakeHA(initial="playing")
    assert _run(fake).outcome == BUSY
    assert fake.speak_calls == []


def test_playback_that_started_before_the_call_is_not_credited() -> None:
    # Another source starts playing just before we speak; then nothing of ours plays
    fake = FakeHA(before_speak=["playing", "idle"], after_speak=[])
    r = _run(fake)
    assert r.outcome == NOT_PLAYED


def test_subscription_snapshot_overrides_stale_get_states() -> None:
    fake = FakeHA(initial="idle", snapshot="playing")
    assert _run(fake).outcome == BUSY
    assert fake.speak_calls == []


def test_reply_timeout_after_playback_still_counts_as_played() -> None:
    fake = FakeHA(speak_delay=0.05, speak_error=WebSocketError("WebSocket call timed out after 30s"))
    assert _run(fake).outcome == PLAYED


def test_refusal_after_playback_started_still_counts_as_played() -> None:
    fake = FakeHA(speak_delay=0.05, speak_error=WebSocketError("home_assistant_error: late"))
    assert _run(fake).outcome == PLAYED


def test_refusal_arriving_mid_playback_still_played() -> None:
    # The reply lands while the player is still playing (before idle)
    fake = FakeHA(speak_delay=0.15, gap=0.1, speak_error=WebSocketError("home_assistant_error: late"))
    r = _run(fake)
    assert r.outcome == PLAYED
    assert r.finished_after_s is not None


def test_stream_failure_is_watch_failed_not_not_played() -> None:
    r = _run(FakeHA(stream_error=WebSocketError("Connection closed: boom")))
    assert r.outcome == WATCH_FAILED
    assert "boom" in (r.problem or "")


def test_rejected_call() -> None:
    assert _run(FakeHA(speak_error=WebSocketError("not_found: tts.piper"))).outcome == REJECTED


def test_unknown_player() -> None:
    with pytest.raises(NotFoundError):
        _run(FakeHA(exists=False))


def test_not_a_media_player() -> None:
    with pytest.raises(ValidationError):
        asyncio.run(MediaService(FakeHA()).tts_test("light.x", ENGINE))  # type: ignore[arg-type]


def test_default_engine_is_preferred_pipeline() -> None:
    e = asyncio.run(MediaService(FakeHA()).default_engine())  # type: ignore[arg-type]
    assert (e.engine, e.language, e.voice) == ("tts.home_assistant_cloud", "en-AU", "AnnetteNeural")


def _patched(fake: FakeHA) -> Any:
    class Ctx:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def __aenter__(self) -> FakeHA:
            return fake

        async def __aexit__(self, *a: Any) -> None:
            return None
    return patch.multiple("ha_cli.domains.media.cli", HAClient=Ctx, get_client_config=lambda u, t: ("http://ha", "t"),
                          MediaService=lambda c: MediaService(c, poll_seconds=0.01))


def test_cli_exits_3_when_not_played() -> None:
    with _patched(FakeHA(after_speak=[])):
        result = runner.invoke(app, ["tts-test", P, "--json", "--timeout", "0.3"])
    assert result.exit_code == 3
    assert json.loads(result.output)[0]["outcome"] == NOT_PLAYED


def test_cli_ok_exit_0() -> None:
    with _patched(FakeHA()):
        result = runner.invoke(app, ["tts-test", P, "--porcelain", "--timeout", "0.5"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"][0]["ok"] is True

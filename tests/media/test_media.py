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
from ha_cli.domains.media.models import BUSY, DISCONNECTED, NOT_PLAYED, PLAYED, REJECTED, UNAVAILABLE, TtsEngine
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
                 speak_error: Exception | None = None, exists: bool = True) -> None:
        self.initial = initial
        self.after_speak = after_speak if after_speak is not None else ["playing", "idle"]
        self.speak_error = speak_error
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
        if self.speak_error:
            raise self.speak_error
        self.spoke.set()

    async def ws_stream(self, msg_type: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        yield {"a": {P: {"s": self.initial, "a": {}}}}
        await self.spoke.wait()
        for s in self.after_speak:
            await asyncio.sleep(0)
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

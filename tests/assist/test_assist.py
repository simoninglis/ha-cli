"""Tests for the assist domain against a scripted fake HA."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ha_cli.common.exceptions import NotFoundError, ValidationError, WebSocketError
from ha_cli.domains.assist.cli import app
from ha_cli.domains.assist.models import AGENT, LOCAL, UNKNOWN, Pipeline
from ha_cli.domains.assist.service import AssistService

runner = CliRunner()

PIPELINES = {"preferred_pipeline": "p1", "pipelines": [
    {"id": "p1", "name": "GPT Assist", "conversation_engine": "conversation.chatgpt", "language": "en",
     "tts_engine": "tts.cloud", "prefer_local_intents": True},
    {"id": "p2", "name": "GPT Bedroom", "conversation_engine": "conversation.chatgpt", "language": "en",
     "stt_engine": "stt.faster_whisper", "tts_engine": "tts.piper", "prefer_local_intents": True},
]}


def run_events(speech: str, local: bool | None, response_type: str = "action_done",
               error: dict | None = None) -> list[dict[str, Any]]:
    intent_end: dict[str, Any] = {"intent_output": {"response": {
        "response_type": response_type, "speech": {"plain": {"speech": speech}}}}}
    if local is not None:
        intent_end["processed_locally"] = local
    events = [{"type": "run-start", "data": {}}, {"type": "intent-start", "data": {}}]
    if error:
        return [*events, {"type": "error", "data": error}, {"type": "run-end", "data": None}]
    return [*events, {"type": "intent-end", "data": intent_end}, {"type": "tts-start", "data": {}},
            {"type": "tts-end", "data": {"tts_output": {"url": "/api/tts_proxy/x.mp3"}}},
            {"type": "run-end", "data": None}]


class FakeHA:
    def __init__(self, scripts: dict[str, list[dict[str, Any]]] | None = None,
                 conversation: dict[str, Any] | None = None, hang: bool = False) -> None:
        self.scripts = scripts or {}
        self.conversation = conversation
        self.hang = hang
        self.runs: list[dict[str, Any]] = []
        self.asked: list[dict[str, Any]] = []

    async def _ws_call(self, msg_type: str, **kwargs: Any) -> Any:
        if msg_type == "assist_pipeline/pipeline/list":
            return PIPELINES
        if msg_type == "conversation/process":
            self.asked.append(kwargs)
            if self.conversation is None:
                raise WebSocketError("not_found: agent")
            return self.conversation
        raise AssertionError(msg_type)

    async def ws_stream(self, msg_type: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        assert msg_type == "assist_pipeline/run"
        assert kwargs["unsubscribe"] is False
        self.runs.append(kwargs)
        if self.hang:
            await asyncio.sleep(3600)
        for ev in self.scripts[kwargs["input"]["text"]]:
            yield ev


def pipelines() -> list[Pipeline]:
    return asyncio.run(AssistService(FakeHA()).list_pipelines())  # type: ignore[arg-type]


class TestPipelines:
    def test_preferred_marked_and_default(self) -> None:
        ps = pipelines()
        assert [p.preferred for p in ps] == [True, False]
        assert AssistService.find_pipeline(ps, None).name == "GPT Assist"

    def test_find_by_name_case_insensitive_and_id(self) -> None:
        ps = pipelines()
        assert AssistService.find_pipeline(ps, "gpt bedroom").id == "p2"
        assert AssistService.find_pipeline(ps, "p2").name == "GPT Bedroom"

    def test_ambiguous_name_refused(self) -> None:
        ps = [*pipelines(), Pipeline("p3", "GPT Bedroom", "x", None, None, None, "en", False)]
        with pytest.raises(ValidationError):
            AssistService.find_pipeline(ps, "GPT Bedroom")

    def test_unknown(self) -> None:
        with pytest.raises(NotFoundError):
            AssistService.find_pipeline(pipelines(), "nope")


class TestRun:
    def _run(self, fake: FakeHA, text: str, tts: bool = True, timeout: float = 5) -> Any:
        svc = AssistService(fake)  # type: ignore[arg-type]
        return asyncio.run(svc.run_text(svc.find_pipeline(pipelines(), "GPT Bedroom"), text, tts=tts, timeout=timeout))

    def test_local_command(self) -> None:
        fake = FakeHA({"turn off the pendant": run_events("Turned off the light", True)})
        r = self._run(fake, "turn off the pendant")
        assert (r.handled_by, r.speech, r.ok) == (LOCAL, "Turned off the light", True)
        assert r.tts_url == "/api/tts_proxy/x.mp3"
        assert fake.runs[0]["pipeline"] == "p2"
        assert fake.runs[0]["end_stage"] == "tts"

    def test_question_to_agent(self) -> None:
        r = self._run(FakeHA({"is it on": run_events("It is off.", False)}), "is it on")
        assert r.handled_by == AGENT

    def test_missing_processed_locally_is_unknown(self) -> None:
        r = self._run(FakeHA({"x": run_events("ok", None)}), "x")
        assert r.handled_by == UNKNOWN

    def test_no_tts_stops_at_intent(self) -> None:
        fake = FakeHA({"x": run_events("ok", True)})
        self._run(fake, "x", tts=False)
        assert fake.runs[0]["end_stage"] == "intent"

    def test_pipeline_error_event(self) -> None:
        r = self._run(FakeHA({"x": run_events("", None, error={"code": "intent-not-supported",
                                                                "message": "engine not found"})}), "x")
        assert not r.ok
        assert "intent-not-supported" in (r.error or "")

    def test_not_understood_is_not_ok(self) -> None:
        r = self._run(FakeHA({"x": run_events("Sorry, I couldn't understand that", True, "error")}), "x")
        assert not r.ok

    def test_timeout(self) -> None:
        r = self._run(FakeHA(hang=True), "x", timeout=0.1)
        assert "timed out" in (r.error or "")


class TestAsk:
    def test_builtin_agent_is_local(self) -> None:
        fake = FakeHA(conversation={"response": {"response_type": "query_answer", "speech": {"plain": {"speech": "No, off"}}}})
        r = asyncio.run(AssistService(fake).ask_agent("conversation.home_assistant", "is it on"))  # type: ignore[arg-type]
        assert (r.handled_by, r.speech, r.ok) == (LOCAL, "No, off", True)

    def test_error_response(self) -> None:
        fake = FakeHA(conversation={"response": {"response_type": "error", "data": {"code": "no_valid_targets"},
                                                 "speech": {"plain": {"speech": "Sorry, I am not aware of any area called is"}}}})
        r = asyncio.run(AssistService(fake).ask_agent("conversation.home_assistant", "x"))  # type: ignore[arg-type]
        assert not r.ok
        assert "no_valid_targets" in (r.error or "")


def _patched(fake: FakeHA) -> Any:
    class Ctx:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def __aenter__(self) -> FakeHA:
            return fake

        async def __aexit__(self, *a: Any) -> None:
            return None
    return patch.multiple("ha_cli.domains.assist.cli", HAClient=Ctx, get_client_config=lambda u, t: ("http://ha", "t"))


class TestCLI:
    def test_machine_output_needs_yes(self) -> None:
        fake = FakeHA({"x": run_events("ok", True)})
        with _patched(fake):
            result = runner.invoke(app, ["test", "x", "--porcelain"])
        assert result.exit_code == 1
        assert fake.runs == []  # nothing ran

    def test_declining_runs_nothing(self) -> None:
        fake = FakeHA({"x": run_events("ok", True)})
        with _patched(fake):
            result = runner.invoke(app, ["test", "x"], input="n\n")
        assert result.exit_code == 0
        assert fake.runs == []

    def test_file_of_phrases_counts_local_and_agent(self, tmp_path: Any) -> None:
        f = tmp_path / "p.txt"
        f.write_text("# bedroom\nturn off the pendant\n\nis it on\n")
        fake = FakeHA({"turn off the pendant": run_events("Turned off", True), "is it on": run_events("Off", False)})
        with _patched(fake):
            result = runner.invoke(app, ["test", "--file", str(f), "-p", "GPT Bedroom", "--yes", "--porcelain"])
        assert result.exit_code == 0, result.output
        meta = json.loads(result.output)["metadata"]
        assert (meta["handled_local"], meta["handled_agent"]) == (1, 1)

    def test_failure_exits_3(self) -> None:
        fake = FakeHA({"x": run_events("", None, error={"code": "e", "message": "m"})})
        with _patched(fake):
            result = runner.invoke(app, ["test", "x", "--yes", "--json"])
        assert result.exit_code == 3

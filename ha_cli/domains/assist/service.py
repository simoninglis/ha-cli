"""Service layer for the assist domain: pipelines, and what a pipeline does with a phrase."""

import asyncio
from contextlib import aclosing
from typing import Any

from ...common.client import HAClient
from ...common.exceptions import NotFoundError, ValidationError, WebSocketError
from .models import AGENT, LOCAL, UNKNOWN, AssistResult, Pipeline


class AssistService:
    """Read Assist pipelines and run text through them."""

    def __init__(self, client: HAClient) -> None:
        """Initialize.

        Args:
            client: Home Assistant client
        """
        self.client = client

    async def list_pipelines(self) -> list[Pipeline]:
        """Every pipeline, the preferred one marked.

        Raises:
            ValidationError: If the response is malformed
        """
        result = await self.client._ws_call("assist_pipeline/pipeline/list")
        if not isinstance(result, dict) or not isinstance(result.get("pipelines"), list):
            raise ValidationError("Unexpected assist_pipeline/pipeline/list response")
        preferred = result.get("preferred_pipeline")
        return [Pipeline.from_dict(p, preferred) for p in result["pipelines"] if isinstance(p, dict)]

    @staticmethod
    def find_pipeline(pipelines: list[Pipeline], ident: str | None) -> Pipeline:
        """By id, or name (case-insensitive); None means the preferred pipeline.

        Raises:
            NotFoundError: No match
            ValidationError: A name that matches more than one pipeline
        """
        if ident is None:
            for p in pipelines:
                if p.preferred:
                    return p
            raise NotFoundError("No preferred pipeline set: pass --pipeline")
        for p in pipelines:
            if p.id == ident:
                return p
        named = [p for p in pipelines if p.name.lower() == ident.lower()]
        if len(named) > 1:
            raise ValidationError(f"{len(named)} pipelines are named {ident!r}: use the id ({', '.join(p.id for p in named)})")
        if named:
            return named[0]
        names = ", ".join(repr(p.name) for p in pipelines)
        raise NotFoundError(f"No pipeline {ident!r}. Pipelines: {names}")

    async def run_text(self, pipeline: Pipeline, text: str, tts: bool = True, timeout: float = 60.0) -> AssistResult:
        """Run ``text`` through ``pipeline`` from intent to (optionally) TTS.

        This is the real pipeline, so a command phrase **acts on the house**.
        ``handled_by`` comes from HA's ``processed_locally``: with "prefer local
        intents" on, commands are usually local while questions go to the agent
        even when the built-in agent could answer them.
        """
        result = AssistResult(text=text, target=pipeline.name, agent=pipeline.conversation_engine)
        loop = asyncio.get_running_loop()
        start = loop.time()
        marks: dict[str, float] = {}

        async def consume() -> None:
            stream = self.client.ws_stream(
                "assist_pipeline/run", unsubscribe=False,
                start_stage="intent", end_stage="tts" if tts else "intent",
                input={"text": text}, pipeline=pipeline.id,
            )
            # aclosing: returning out of the loop must run the stream's cleanup now,
            # not whenever the generator is garbage-collected
            async with aclosing(stream):
                async for ev in stream:
                    etype = str(ev.get("type"))
                    marks[etype] = loop.time() - start
                    if etype not in ("intent-progress",):
                        result.events.append(etype)
                    data = ev.get("data") or {}
                    if etype == "intent-end":
                        response = ((data.get("intent_output") or {}).get("response")) or {}
                        result.response_type = response.get("response_type")
                        result.speech = str(((response.get("speech") or {}).get("plain") or {}).get("speech") or "")
                        local = data.get("processed_locally")
                        result.handled_by = UNKNOWN if local is None else (LOCAL if local else AGENT)
                        result.intent_seconds = round(marks[etype] - marks.get("intent-start", 0.0), 2)
                    elif etype == "tts-end":
                        result.tts_url = (data.get("tts_output") or {}).get("url")
                        result.tts_seconds = round(marks[etype] - marks.get("tts-start", marks[etype]), 2)
                    elif etype == "error":
                        result.error = f"{data.get('code')}: {data.get('message')}"
                    elif etype == "run-end":
                        return

        try:
            await asyncio.wait_for(consume(), timeout=timeout)
        except asyncio.TimeoutError:
            result.error = f"timed out after {timeout:g}s (last event: {result.events[-1] if result.events else 'none'})"
        except WebSocketError as e:
            result.error = str(e)
        result.total_seconds = round(loop.time() - start, 2)
        return result

    async def ask_agent(self, agent_id: str, text: str, language: str | None = None) -> AssistResult:
        """Send ``text`` straight to one conversation agent (no pipeline, no TTS).

        A command phrase **acts on the house**.
        """
        result = AssistResult(text=text, target=agent_id, agent=agent_id, handled_by=AGENT)
        if agent_id == "conversation.home_assistant":
            result.handled_by = LOCAL
        loop = asyncio.get_running_loop()
        start = loop.time()
        kwargs: dict[str, Any] = {"text": text, "agent_id": agent_id}
        if language:
            kwargs["language"] = language
        try:
            reply = await self.client._ws_call("conversation/process", **kwargs)
        except WebSocketError as e:
            result.error = str(e)
            return result
        response = (reply or {}).get("response") or {}
        result.response_type = response.get("response_type")
        result.speech = str(((response.get("speech") or {}).get("plain") or {}).get("speech") or "")
        if result.response_type == "error":
            result.error = f"{(response.get('data') or {}).get('code', 'error')}: {result.speech}"
        result.total_seconds = round(loop.time() - start, 2)
        return result

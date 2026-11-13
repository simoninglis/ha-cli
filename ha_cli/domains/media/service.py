"""Service layer for the media domain: prove a player actually played a TTS clip."""

import asyncio
import logging
from contextlib import aclosing, suppress
from typing import Any

from ...common.client import HAClient
from ...common.entity_watch import EntityTracker
from ...common.exceptions import NotFoundError, ValidationError, WebSocketError
from .models import BUSY, DISCONNECTED, NOT_PLAYED, PLAYED, REJECTED, UNAVAILABLE, TtsEngine, TtsTestResult

logger = logging.getLogger(__name__)

OFFLINE = ("unavailable", "unknown")
STARTED = ("playing",)
FINISHED = ("idle", "paused", "off", "standby", "on")


class MediaService:
    """TTS delivery checks."""

    def __init__(self, client: HAClient, poll_seconds: float = 0.5) -> None:
        """Initialize.

        Args:
            client: Home Assistant client
            poll_seconds: Wake-up interval while waiting (tests shrink it)
        """
        self.client = client
        self.poll_seconds = poll_seconds

    async def default_engine(self) -> TtsEngine:
        """The preferred Assist pipeline's TTS engine, language and voice.

        That is what a voice satellite speaks with, so it's the honest default.

        Raises:
            ValidationError: If there's no preferred pipeline with a TTS engine
        """
        result = await self.client._ws_call("assist_pipeline/pipeline/list")
        pipelines = result.get("pipelines") if isinstance(result, dict) else None
        preferred = result.get("preferred_pipeline") if isinstance(result, dict) else None
        for p in pipelines if isinstance(pipelines, list) else []:
            if isinstance(p, dict) and p.get("id") == preferred and p.get("tts_engine"):
                return TtsEngine(engine=str(p["tts_engine"]), language=p.get("tts_language"),
                                 voice=p.get("tts_voice"), source=f"preferred pipeline {p.get('name')!r}")
        raise ValidationError("No preferred Assist pipeline with a TTS engine: pass --engine")

    async def _player_state(self, player: str) -> dict[str, Any]:
        states = await self.client._ws_call("get_states")
        if not isinstance(states, list):
            raise ValidationError(f"Unexpected get_states response: {type(states).__name__}")
        for s in states:
            if isinstance(s, dict) and s.get("entity_id") == player:
                return s
        near = [s["entity_id"] for s in states if isinstance(s, dict)
                and str(s.get("entity_id", "")).startswith("media_player.")
                and player.split(".")[-1][:6] in str(s.get("entity_id"))][:5]
        hint = f" Did you mean: {', '.join(near)}?" if near else ""
        raise NotFoundError(f"No media player {player}.{hint}")

    async def tts_test(
        self,
        player: str,
        engine: TtsEngine,
        message: str = "Testing, one two three.",
        timeout: float = 20.0,
        force: bool = False,
    ) -> TtsTestResult:
        """Speak ``message`` on ``player`` and report whether it reached ``playing``.

        ``tts.speak`` succeeds whether or not the device can fetch the audio (a
        Voice PE pulls it from HA's internal URL, which an IoT firewall can block),
        so the only evidence is the player's own state.

        Raises:
            ValidationError / NotFoundError: For a bad player id
        """
        if not player.startswith("media_player."):
            raise ValidationError(f"{player} is not a media player (media_player.*)")
        initial = await self._player_state(player)
        result = TtsTestResult(player=player, outcome=NOT_PLAYED, engine=engine.engine)
        loop = asyncio.get_running_loop()
        start = loop.time()

        def note(what: str, **extra: Any) -> None:
            result.timeline.append({"t": round(loop.time() - start, 2), "event": what, **extra})

        state0 = str(initial.get("state"))
        note("initial", state=state0)
        if state0 in OFFLINE:
            result.outcome = UNAVAILABLE
            return result
        if state0 in STARTED and not force:
            result.outcome = BUSY
            return result

        tracker = EntityTracker()
        events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        stream = self.client.ws_stream("subscribe_entities", entity_ids=[player])

        async def pump() -> None:
            # aclosing: cancelling the pump must close the stream (unsubscribe) even
            # when the cancel lands outside the generator
            async with aclosing(stream):
                async for ev in stream:
                    await events.put(ev)

        pump_task = asyncio.create_task(pump())
        try:
            tracker.apply(await asyncio.wait_for(events.get(), timeout=30))
            data: dict[str, Any] = {"media_player_entity_id": player, "message": message}
            if engine.language:
                data["language"] = engine.language
            if engine.voice:
                data["options"] = {"voice": engine.voice}
            try:
                await self.client.call_service_ws("tts", "speak", target={"entity_id": engine.engine}, service_data=data)
            except WebSocketError as e:
                result.outcome = REJECTED
                result.problem = str(e)
                return result
            note("tts.speak accepted")

            last = tracker.get(player).state
            deadline = loop.time() + timeout
            while loop.time() < deadline:
                try:
                    tracker.apply(await asyncio.wait_for(events.get(), timeout=self.poll_seconds))
                except asyncio.TimeoutError:
                    continue
                state = tracker.get(player).state
                if state == last:
                    continue
                last = state
                note("state", state=state)
                if state in OFFLINE:
                    result.outcome = DISCONNECTED
                    result.problem = "player went unavailable before it finished"
                    return result
                if state in STARTED and result.started_after_s is None:
                    result.started_after_s = round(loop.time() - start, 2)
                    result.outcome = PLAYED
                elif state in FINISHED and result.started_after_s is not None:
                    result.finished_after_s = round(loop.time() - start, 2)
                    return result
            if result.outcome == NOT_PLAYED:
                result.problem = f"never reached playing within {timeout:g}s"
            return result
        finally:
            pump_task.cancel()
            with suppress(asyncio.CancelledError, WebSocketError):
                await pump_task

"""Follow live entity state from a ``subscribe_entities`` stream.

HA sends compressed state: an ``a`` (added) map with the full state, then ``c``
(changed) maps holding ``+`` (set) and ``-`` (removed attribute keys) diffs, and
``r`` for removed entities. ``EntityTracker`` folds those into plain state and
attribute dicts, so a watcher can ask "what is this entity now?".
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing, suppress
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from .exceptions import WebSocketError


@dataclass
class EntityState:
    """Current state of one entity, as far as the stream has told us."""

    state: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    removed: bool = False


class EntityTracker:
    """Apply ``subscribe_entities`` events to a set of entity states."""

    def __init__(self) -> None:
        """Start with nothing known."""
        self.entities: dict[str, EntityState] = {}

    def get(self, entity_id: str) -> EntityState:
        """The entity's current state (empty if nothing has arrived yet)."""
        return self.entities.setdefault(entity_id, EntityState())

    def apply(self, event: dict[str, Any]) -> set[str]:
        """Fold one event in. Returns the entity ids whose state or attributes changed."""
        changed: set[str] = set()
        for eid, full in (event.get("a") or {}).items():
            ent = self.get(eid)
            ent.state = full.get("s")
            ent.attributes = dict(full.get("a") or {})
            ent.removed = False
            changed.add(eid)
        for eid, diff in (event.get("c") or {}).items():
            ent = self.get(eid)
            plus = diff.get("+") or {}
            if "s" in plus:
                ent.state = plus["s"]
            ent.attributes.update(plus.get("a") or {})
            for key in (diff.get("-") or {}).get("a") or []:
                ent.attributes.pop(key, None)
            changed.add(eid)
        for eid in event.get("r") or []:
            self.get(eid).removed = True
            changed.add(eid)
        return changed


class StreamWatcher:
    """Read a stream in the background, without ever hiding why it stopped.

    ``next()`` waits for the next event with a timeout, and raises the stream's
    own error the moment it fails (or ``WebSocketError`` if it simply ends),
    rather than leaving the caller to time out on an empty queue. Use as an
    async context manager: leaving it cancels the reader and closes the stream
    (unsubscribing) straight away.
    """

    def __init__(self, stream: AsyncGenerator[dict[str, Any], None]) -> None:
        """Wrap ``stream``; nothing is read until the context is entered."""
        self._stream = stream
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def _pump(self) -> None:
        async with aclosing(self._stream):
            async for event in self._stream:
                await self._queue.put(event)

    async def __aenter__(self) -> "StreamWatcher":
        """Start reading."""
        self._task = asyncio.create_task(self._pump())
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        """Stop reading and close the stream."""
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError, WebSocketError):
                await self._task

    def _raise_if_stopped(self) -> None:
        if self._task and self._task.done():
            exc = None if self._task.cancelled() else self._task.exception()
            if exc:
                raise exc if isinstance(exc, WebSocketError) else WebSocketError(f"State stream failed: {exc}")
            raise WebSocketError("State stream ended")

    def drain(self) -> list[dict[str, Any]]:
        """Every event already received, without waiting."""
        events = []
        while not self._queue.empty():
            events.append(self._queue.get_nowait())
        return events

    async def next(self, timeout: float) -> dict[str, Any] | None:
        """The next event, or None after ``timeout``.

        Raises:
            WebSocketError: As soon as the stream has failed or ended
        """
        if not self._queue.empty():
            return self._queue.get_nowait()
        self._raise_if_stopped()
        assert self._task is not None, "use StreamWatcher as an async context manager"
        getter = asyncio.ensure_future(self._queue.get())
        try:
            await asyncio.wait({getter, self._task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        finally:
            if not getter.done():
                getter.cancel()
                with suppress(asyncio.CancelledError):
                    await getter
        if getter.done() and not getter.cancelled():
            return getter.result()
        self._raise_if_stopped()
        return None

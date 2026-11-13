"""Tests for StreamWatcher: events, failures surfaced at once, and cleanup."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from ha_cli.common.entity_watch import StreamWatcher
from ha_cli.common.exceptions import WebSocketError


class Probe:
    def __init__(self) -> None:
        self.closed = False

    async def stream(self, events: list[dict[str, Any]], then: str = "block") -> AsyncGenerator[dict[str, Any], None]:
        try:
            for ev in events:
                yield ev
            if then == "fail":
                raise WebSocketError("Connection closed: boom")
            if then == "raw":
                raise ValueError("unexpected")
            if then == "block":
                await asyncio.sleep(3600)
        finally:
            self.closed = True


def test_next_returns_events_then_none_on_timeout() -> None:
    async def go() -> list[Any]:
        p = Probe()
        async with StreamWatcher(p.stream([{"n": 1}, {"n": 2}])) as w:
            got = [await w.next(1), await w.next(1), await w.next(0.05)]
        assert p.closed
        return got
    assert asyncio.run(go()) == [{"n": 1}, {"n": 2}, None]


def test_failure_raises_promptly_not_after_timeout() -> None:
    async def go() -> float:
        p = Probe()
        loop = asyncio.get_running_loop()
        start = loop.time()
        async with StreamWatcher(p.stream([], then="fail")) as w:
            with pytest.raises(WebSocketError, match="boom"):
                await w.next(30)
        return loop.time() - start
    assert asyncio.run(go()) < 1


def test_end_of_stream_raises() -> None:
    async def go() -> None:
        async with StreamWatcher(Probe().stream([{"n": 1}], then="end")) as w:
            assert await w.next(1) == {"n": 1}
            with pytest.raises(WebSocketError, match="ended"):
                await w.next(1)
    asyncio.run(go())


def test_events_before_a_failure_are_still_delivered() -> None:
    async def go() -> None:
        async with StreamWatcher(Probe().stream([{"n": 1}], then="fail")) as w:
            await asyncio.sleep(0.01)
            assert await w.next(1) == {"n": 1}
            with pytest.raises(WebSocketError):
                await w.next(1)
    asyncio.run(go())


def test_drain_and_exit_closes_blocked_stream() -> None:
    async def go() -> Probe:
        p = Probe()
        async with StreamWatcher(p.stream([{"n": 1}, {"n": 2}])) as w:
            await asyncio.sleep(0.01)
            assert w.drain() == [{"n": 1}, {"n": 2}]
            assert w.drain() == []
        return p
    assert asyncio.run(go()).closed


def test_unexpected_error_is_normalised_and_cleanup_does_not_reraise_it() -> None:
    async def go() -> None:
        async with StreamWatcher(Probe().stream([], then="raw")) as w:
            with pytest.raises(WebSocketError, match="unexpected"):
                await w.next(1)
        # leaving the context must not raise the raw ValueError
    asyncio.run(go())

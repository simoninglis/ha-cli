"""Service layer for the updates domain: list, check and install ``update.*`` entities."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import aclosing, suppress
from typing import Any

from ...common.client import HAClient
from ...common.entity_watch import EntityTracker
from ...common.exceptions import NotFoundError, ValidationError, WebSocketError
from .models import AVAILABLE, InstallResult, UpdateInfo, version_matches

logger = logging.getLogger(__name__)

POLL_SECONDS = 2.0
RECHECK_SECONDS = 10.0


class UpdatesService:
    """Read, check and install updates, and confirm what actually got installed."""

    def __init__(self, client: HAClient, poll_seconds: float = POLL_SECONDS) -> None:
        """Initialize.

        Args:
            client: Home Assistant client
            poll_seconds: Gap between state reads while waiting (tests shrink it)
        """
        self.client = client
        self.poll_seconds = poll_seconds

    async def list_updates(self) -> list[UpdateInfo]:
        """Every update entity, sorted by entity id.

        Raises:
            ValidationError: If HA's state list is malformed (never an empty list in
                its place: "no updates" must mean HA said so)
        """
        states = await self.client._ws_call("get_states")
        if not isinstance(states, list):
            raise ValidationError(f"Unexpected get_states response: {type(states).__name__}")
        updates = [
            UpdateInfo.from_state(s) for s in states
            if isinstance(s, dict) and str(s.get("entity_id", "")).startswith("update.")
        ]
        return sorted(updates, key=lambda u: u.entity_id)

    async def get(self, entity_id: str) -> UpdateInfo:
        """One update entity.

        Raises:
            NotFoundError: If it doesn't exist (with near-miss suggestions)
        """
        if not entity_id.startswith("update."):
            raise ValidationError(f"{entity_id} is not an update entity (update.*)")
        updates = await self.list_updates()
        for u in updates:
            if u.entity_id == entity_id:
                return u
        stem = entity_id.split(".", 1)[1]
        near = [u.entity_id for u in updates if stem[:8] and stem[:8] in u.entity_id][:5]
        hint = f" Did you mean: {', '.join(near)}?" if near else ""
        raise NotFoundError(f"No update entity {entity_id}.{hint}")

    async def device_sw_version(self, entity_id: str) -> str | None:
        """The firmware/software version the entity's device reports, if it has one."""
        try:
            entry = await self.client._ws_call("config/entity_registry/get", entity_id=entity_id)
            device_id = entry.get("device_id") if isinstance(entry, dict) else None
            if not device_id:
                return None
            devices = await self.client._ws_call("config/device_registry/list")
        except WebSocketError as e:
            logger.debug(f"Device lookup for {entity_id} failed: {e}")
            return None
        for d in devices if isinstance(devices, list) else []:
            if isinstance(d, dict) and d.get("id") == device_id:
                sw = d.get("sw_version")
                return str(sw) if sw else None
        return None

    async def check(
        self,
        entity_id: str,
        wait: float = 20.0,
        done: Callable[[UpdateInfo], bool] | None = None,
    ) -> UpdateInfo:
        """Ask the entity to check for updates and wait for an answer.

        ``homeassistant.update_entity`` returns before the check has run (for a
        Voice PE the *device* fetches its manifest), so this re-reads the entity
        until ``done`` holds (default: both versions reported) or ``wait`` runs
        out, re-requesting the check every 10 s. Returns the last state seen.
        """
        done = done or (lambda u: bool(u.installed_version and u.latest_version))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait
        next_request = loop.time()
        info = await self.get(entity_id)
        while True:
            if loop.time() >= next_request and info.state not in ("unavailable", "unknown"):
                try:
                    await self.client.call_service_ws(
                        "homeassistant", "update_entity", target={"entity_id": entity_id}
                    )
                except WebSocketError as e:
                    logger.debug(f"update_entity on {entity_id} failed: {e}")
                next_request = loop.time() + RECHECK_SECONDS
            await asyncio.sleep(self.poll_seconds)
            info = await self.get(entity_id)
            if done(info) or loop.time() >= deadline:
                return info

    async def install(
        self,
        entity_id: str,
        timeout: float = 900.0,
        verify_wait: float = 60.0,
        on_change: Callable[[dict[str, Any]], None] | None = None,
    ) -> InstallResult:
        """Install the pending update, watch it through, then confirm the new version.

        Success is not the service call returning: it is the entity *and* (where
        there is one) the device reporting the target version afterwards. A device
        that reboots comes back with a blank installed_version until its next
        check, so verification re-checks rather than trusting the first read.

        Raises:
            ValidationError: If there is no update to install
        """
        info = await self.get(entity_id)
        if info.status != AVAILABLE:
            raise ValidationError(f"{entity_id} has no update to install ({info.status})")

        loop = asyncio.get_running_loop()
        start = loop.time()
        result = InstallResult(entity_id=entity_id, from_version=info.installed_version,
                               target_version=info.latest_version)

        def note(what: str, **extra: Any) -> None:
            entry = {"t": round(loop.time() - start, 1), "event": what, **extra}
            result.timeline.append(entry)
            if on_change:
                on_change(entry)

        tracker = EntityTracker()
        events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        stream = self.client.ws_stream("subscribe_entities", entity_ids=[entity_id])

        async def pump() -> None:
            # aclosing: cancelling the pump must close the stream (unsubscribe) even
            # when the cancel lands outside the generator
            async with aclosing(stream):
                async for ev in stream:
                    await events.put(ev)

        pump_task = asyncio.create_task(pump())
        install_task: asyncio.Task[Any] | None = None
        try:
            # The initial state arrives first; only then is the install requested,
            # so no transition can be missed
            tracker.apply(await asyncio.wait_for(events.get(), timeout=30))
            install_task = asyncio.create_task(
                self.client.call_service_ws("update", "install", target={"entity_id": entity_id})
            )
            note("install requested", version=info.latest_version)

            started = False
            offline_since: float | None = None
            last: tuple[Any, ...] | None = None
            deadline = start + timeout
            while True:
                if loop.time() >= deadline:
                    result.problem = f"timed out after {int(timeout)}s waiting for the install to finish"
                    break
                if install_task.done() and not install_task.cancelled():
                    exc = install_task.exception()
                    # The call can legitimately outlast the client's 30 s reply timeout
                    # (it waits for the install); only a real rejection is a failure
                    if exc and "timed out" not in str(exc):
                        result.problem = f"install rejected: {exc}"
                        break
                if pump_task.done() and not pump_task.cancelled() and pump_task.exception():
                    result.problem = f"lost the state stream: {pump_task.exception()}"
                    break
                with suppress(asyncio.TimeoutError):
                    tracker.apply(await asyncio.wait_for(events.get(), timeout=self.poll_seconds))
                ent = tracker.get(entity_id)
                pct = ent.attributes.get("update_percentage")
                in_progress = bool(ent.attributes.get("in_progress"))
                snap = (ent.state, in_progress, pct)
                if snap != last:
                    last = snap
                    note("state", state=ent.state, in_progress=in_progress, percentage=pct)
                if ent.state in ("unavailable", "unknown"):
                    if offline_since is None:
                        offline_since = loop.time()
                        result.rebooted = True
                        note("went offline (restarting)")
                    started = True
                    continue
                if offline_since is not None:
                    result.offline_seconds = round(loop.time() - offline_since, 1)
                    offline_since = None
                    note("back online", offline_seconds=result.offline_seconds)
                if in_progress:
                    started = True
                    continue
                call_ok = (install_task.done() and not install_task.cancelled()
                           and install_task.exception() is None)
                if started or (call_ok and ent.state == "off"):
                    break
        finally:
            pump_task.cancel()
            with suppress(asyncio.CancelledError, WebSocketError):
                await pump_task
            if install_task and not install_task.done():
                install_task.cancel()

        if result.problem is None:
            note("verifying")
            target = result.target_version
            after = await self.check(entity_id, wait=verify_wait, done=lambda u: u.installed_version == target)
            result.installed_version = after.installed_version
            result.device_sw_version = await self.device_sw_version(entity_id)
            entity_ok = after.installed_version == target
            device_ok = result.device_sw_version is None or version_matches(result.device_sw_version, target)
            result.verified = entity_ok and device_ok
            if not entity_ok:
                result.problem = (f"entity reports {after.installed_version or 'no version'} after the install, "
                                  f"not {target}")
            elif not device_ok:
                result.problem = f"device reports sw_version {result.device_sw_version!r}, not {target}"
        result.duration_seconds = round(loop.time() - start, 1)
        note("done", verified=result.verified)
        return result

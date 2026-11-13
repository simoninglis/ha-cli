"""Service layer for the updates domain: list, check and install ``update.*`` entities."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from ...common.client import HAClient
from ...common.entity_watch import EntityTracker, StreamWatcher
from ...common.exceptions import NotFoundError, ValidationError, WebSocketError
from .models import AVAILABLE, InstallResult, UpdateInfo, version_matches

logger = logging.getLogger(__name__)

POLL_SECONDS = 2.0
RECHECK_SECONDS = 10.0
STUCK_GRACE_SECONDS = 30.0
# The client gives up on any reply after 30 s, so a pending install call always
# resolves (result, rejection or reply timeout) within this
CALL_OUTCOME_SECONDS = 35.0
MIN_VERIFY_SECONDS = 1.0  # verification always gets at least one real attempt
SPECIFIC_VERSION = 2  # UpdateEntityFeature.SPECIFIC_VERSION


def _is_reply_timeout(exc: BaseException) -> bool:
    """The client gave up waiting for a reply: says nothing about the outcome."""
    return "timed out" in str(exc)


@dataclass
class DeviceVersion:
    """What the entity's device says about its software version."""

    status: str  # ok | no_device | no_version | unreadable
    version: str | None = None
    error: str | None = None


@dataclass
class CheckResult:
    """The outcome of asking an update entity to check."""

    info: UpdateInfo
    conclusive: bool
    refresh_error: str | None = None


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

    async def device_version(self, entity_id: str) -> DeviceVersion:
        """The software version the entity's device reports.

        "Couldn't read it" is kept apart from "there's nothing to read": an
        unreadable registry must never count as a passed device check.
        """
        try:
            entry = await self.client._ws_call("config/entity_registry/get", entity_id=entity_id)
        except WebSocketError as e:
            return DeviceVersion("unreadable", error=f"entity registry: {e}")
        if not isinstance(entry, dict) or "device_id" not in entry:
            return DeviceVersion("unreadable", error="entity registry: unexpected response")
        device_id = entry.get("device_id")
        if not device_id:
            return DeviceVersion("no_device")
        try:
            devices = await self.client._ws_call("config/device_registry/list")
        except WebSocketError as e:
            return DeviceVersion("unreadable", error=f"device registry: {e}")
        if not isinstance(devices, list):
            return DeviceVersion("unreadable", error="device registry: unexpected response")
        for d in devices:
            if isinstance(d, dict) and d.get("id") == device_id:
                sw = d.get("sw_version")
                return DeviceVersion("ok", version=str(sw)) if sw else DeviceVersion("no_version")
        return DeviceVersion("unreadable", error=f"device {device_id} not in the device registry")

    async def device_sw_version(self, entity_id: str) -> str | None:
        """The device's sw_version when it has one (display only; verification uses device_version)."""
        dv = await self.device_version(entity_id)
        return dv.version if dv.status == "ok" else None

    async def check(
        self,
        entity_id: str,
        wait: float = 20.0,
        done: Callable[[UpdateInfo], bool] | None = None,
    ) -> CheckResult:
        """Ask the entity to check for updates and wait for an answer.

        ``homeassistant.update_entity`` returns before the check has run (for a
        Voice PE the *device* fetches its manifest), so this re-reads the entity
        until ``done`` holds (default: both versions reported) or ``wait`` runs
        out, re-requesting every 10 s. A refused request ends it at once with
        ``refresh_error`` set: old attributes satisfying ``done`` prove nothing then.
        """
        done = done or (lambda u: bool(u.installed_version and u.latest_version)
                        and u.state not in ("unavailable", "unknown", ""))
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
                    if not _is_reply_timeout(e):
                        return CheckResult(info=info, conclusive=False, refresh_error=str(e))
                    logger.debug(f"update_entity on {entity_id}: {e}")
                next_request = loop.time() + RECHECK_SECONDS
            await asyncio.sleep(self.poll_seconds)
            info = await self.get(entity_id)
            if done(info):
                return CheckResult(info=info, conclusive=True)
            if loop.time() >= deadline:
                return CheckResult(info=info, conclusive=False)

    async def install(
        self,
        entity_id: str,
        expected_version: str | None = None,
        timeout: float = 900.0,
        verify_wait: float = 60.0,
        on_change: Callable[[dict[str, Any]], None] | None = None,
    ) -> InstallResult:
        """Install the pending update, watch it through, then confirm the new version.

        ``expected_version`` is the version the user confirmed: if HA now offers a
        different one, nothing is installed. Success is not the service call
        returning: it is the entity, and the device where it reports a version,
        showing the target afterwards. A device that restarts comes back with a
        blank installed_version until its next check, so verification re-checks.

        Entities supporting SPECIFIC_VERSION are asked for exactly the confirmed
        version. Others install whatever they offer when the call lands; the live
        snapshot is re-checked just before, which narrows (but cannot close) the
        window for a new release to arrive in between, and verification would then
        report the mismatch.

        Raises:
            ValidationError: No update to install, or the offered version changed
        """
        info = await self.get(entity_id)
        if info.status != AVAILABLE:
            raise ValidationError(f"{entity_id} has no update to install ({info.status})")
        target = info.latest_version
        if expected_version and expected_version != target:
            raise ValidationError(f"{entity_id} now offers {target}, not the confirmed {expected_version}: nothing installed")

        loop = asyncio.get_running_loop()
        start = loop.time()
        result = InstallResult(entity_id=entity_id, from_version=info.installed_version, target_version=target)

        def note(what: str, **extra: Any) -> None:
            entry = {"t": round(loop.time() - start, 1), "event": what, **extra}
            result.timeline.append(entry)
            if on_change:
                on_change(entry)

        def rejection() -> str | None:
            if install_task and install_task.done() and not install_task.cancelled():
                exc = install_task.exception()
                if exc and not _is_reply_timeout(exc):
                    return f"install rejected: {exc}"
            return None

        tracker = EntityTracker()
        install_task: asyncio.Task[Any] | None = None
        try:
            try:
                async with StreamWatcher(self.client.ws_stream("subscribe_entities", entity_ids=[entity_id])) as watch:
                    first = await watch.next(timeout=30)
                    if first is None:
                        raise WebSocketError("No initial state from subscribe_entities within 30s")
                    tracker.apply(first)
                    for ev in watch.drain():
                        tracker.apply(ev)
                    # Re-validate on the live snapshot the install will act on
                    ent = tracker.get(entity_id)
                    live_latest = str(ent.attributes.get("latest_version") or "")
                    if ent.state != "on" or live_latest != target:
                        raise ValidationError(
                            f"{entity_id} changed before the install (now {ent.state}, offering {live_latest or 'nothing'}): "
                            "nothing installed")
                    features = ent.attributes.get("supported_features")
                    specific = isinstance(features, int) and bool(features & SPECIFIC_VERSION)
                    install_task = asyncio.create_task(self.client.call_service_ws(
                        "update", "install", target={"entity_id": entity_id},
                        service_data={"version": target} if specific else None))
                    note("install requested", version=target, pinned=specific)

                    started = False
                    offline_since: float | None = None
                    call_done_at: float | None = None
                    last: tuple[Any, ...] | None = None
                    deadline = start + timeout
                    while True:
                        result.problem = rejection()
                        if result.problem:
                            break
                        if loop.time() >= deadline:
                            result.problem = f"timed out after {int(timeout)}s waiting for the install to finish"
                            break
                        event = await watch.next(timeout=self.poll_seconds)
                        if event is not None:
                            tracker.apply(event)
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
                        call_exc = (install_task.exception()
                                    if install_task.done() and not install_task.cancelled() else None)
                        call_ok = install_task.done() and not install_task.cancelled() and (
                            call_exc is None or _is_reply_timeout(call_exc))
                        if call_ok and call_done_at is None:
                            call_done_at = loop.time()
                        if ent.state == "off" and (started or call_ok):
                            break  # finished; whether it's the right version is verification's job
                        if ent.state == "on" and call_done_at is not None and loop.time() - call_done_at > STUCK_GRACE_SECONDS:
                            result.problem = "install call finished but the entity still offers the update"
                            break
            except WebSocketError as e:
                result.problem = result.problem or f"lost the state stream: {e}"

            if result.problem is None:
                result.problem, result.verified = await self._verify(entity_id, target, verify_wait, result, note,
                                                                     rejection)
            if result.verified and install_task and not install_task.done():
                # Never cancel an install call whose outcome is unknown: wait for it
                note("waiting for the install call's reply")
                await asyncio.wait({install_task}, timeout=CALL_OUTCOME_SECONDS)
                if not install_task.done():
                    result.problem, result.verified = "the install call never replied", False
            late = rejection()
            if late:
                result.problem, result.verified = late, False
        finally:
            if install_task:
                if not install_task.done():
                    install_task.cancel()
                with suppress(asyncio.CancelledError, WebSocketError):
                    await install_task
        result.duration_seconds = round(loop.time() - start, 1)
        note("done", verified=result.verified)
        return result

    async def _verify(
        self,
        entity_id: str,
        target: str,
        verify_wait: float,
        result: InstallResult,
        note: Callable[..., None],
        rejection: Callable[[], str | None],
    ) -> tuple[str | None, bool]:
        """Poll the entity and the device until both report ``target`` (or time runs out).

        The entity is re-read on every pass (a device catching up doesn't freeze an
        earlier entity reading). Everything, pauses included, runs against one
        deadline of ``max(verify_wait, MIN_VERIFY_SECONDS)``: there is always one
        real attempt, and nothing seen after the deadline counts.
        """
        note("verifying")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(verify_wait, MIN_VERIFY_SECONDS)

        def left() -> float:
            return deadline - loop.time()

        problem = "not verified"
        entity_ok = False
        refresh_error: str | None = None
        while True:
            rejected = rejection()
            if rejected:
                return rejected, False
            if left() <= 0:
                return problem, False
            try:
                if entity_ok:
                    # Already matched once: pause, then re-read it (no fresh check needed)
                    await asyncio.sleep(min(self.poll_seconds, max(0.0, left())))
                    if left() <= 0:
                        return problem, False
                    after = await asyncio.wait_for(self.get(entity_id), timeout=left())
                else:
                    # The check's own wait ends a little before the outer bound, so it
                    # normally returns its reading (and the specific problem) itself
                    margin = min(0.2, left() / 4)
                    checked = await asyncio.wait_for(
                        self.check(entity_id, wait=min(left() - margin, RECHECK_SECONDS),
                                   done=lambda u: u.installed_version == target),
                        timeout=left())
                    after = checked.info
                    refresh_error = checked.refresh_error
                if left() <= 0:
                    return problem, False
                device = await asyncio.wait_for(self.device_version(entity_id), timeout=left())
            except asyncio.TimeoutError:
                return ("verification ran out of time" if problem == "not verified" else problem), False
            result.installed_version = after.installed_version
            entity_ok = (after.installed_version == target and not after.in_progress
                         and after.state not in ("unavailable", "unknown"))
            result.device_sw_version = device.version
            if device.status == "ok":
                device_ok = version_matches(device.version or "", target)
                result.verification = "entity and device"
            elif device.status in ("no_device", "no_version"):
                device_ok = True
                result.verification = ("entity only (no device)" if device.status == "no_device"
                                       else "entity only (device reports no version)")
            else:
                device_ok = False
                result.verification = None
            if entity_ok and device_ok:
                return None, True
            if not entity_ok:
                problem = (f"entity reports {result.installed_version or 'no version'} after the install, not {target}"
                           + (f" (check refused: {refresh_error})" if refresh_error else ""))
            elif device.status == "unreadable":
                problem = f"couldn't read the device's version: {device.error}"
            else:
                problem = f"device reports sw_version {device.version!r}, not {target}"

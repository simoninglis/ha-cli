"""Service layer for the traces domain: stored automation and script runs."""

import asyncio
import re
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...common.client import HAClient
from ...common.exceptions import NotFoundError, ValidationError, WebSocketError
from .models import DOMAINS, RunsPage, TraceDetail, TraceRun

# `around` fetches every run in its window; past this it asks for a narrower one
MAX_AROUND_RUNS = 60

_CLOCK = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?$")
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)\s*([smh]?)$")


def parse_when(text: str, tz: tzinfo, now: datetime | None = None) -> datetime:
    """A time the way you'd say it: ``14:18``, ``14:18:09``, ``2026-11-13 14:18``, or ISO.

    A bare clock time is today in HA's time zone; a time without a zone is HA's zone.

    Raises:
        ValidationError: Unparseable
    """
    text = text.strip()
    m = _CLOCK.match(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        second = int(m.group(3) or 0)
        micro = int((m.group(4) or "0").ljust(6, "0"))
        if hour > 23 or minute > 59 or second > 59:
            raise ValidationError(f"Not a time: {text!r}")
        today = (now or datetime.now(tz)).astimezone(tz).date()
        return datetime(today.year, today.month, today.day, hour, minute, second, micro, tzinfo=tz)
    try:
        when = datetime.fromisoformat(text)
    except ValueError as e:
        raise ValidationError(f"Not a time: {text!r} (use HH:MM[:SS], 'YYYY-MM-DD HH:MM[:SS]' or ISO)") from e
    return when if when.tzinfo else when.replace(tzinfo=tz)


def parse_duration(text: str) -> timedelta:
    """``90``, ``90s``, ``2m``, ``1h`` (a bare number is seconds).

    Raises:
        ValidationError: Unparseable
    """
    m = _DURATION.match(text.strip())
    if not m:
        raise ValidationError(f"Not a duration: {text!r} (e.g. 90s, 2m, 1h)")
    value = float(m.group(1))
    return timedelta(seconds=value * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)])


def group_chains(details: list[TraceDetail]) -> list[list[TraceDetail]]:
    """Group runs that belong together, earliest first.

    A script started by an automation (``script.turn_on`` or a direct call)
    shares the automation run's ``context.id``. A run whose ``parent_id`` is
    another run's context id (an action that caused it) joins that chain too.
    """
    root: dict[str, str] = {}

    def find(cid: str) -> str:
        while root[cid] != cid:
            root[cid] = root[root[cid]]
            cid = root[cid]
        return cid

    for d in details:
        if d.context_id:
            root.setdefault(d.context_id, d.context_id)
    for d in details:
        if d.context_id and d.parent_id and d.parent_id in root:
            root[find(d.context_id)] = find(d.parent_id)
    chains: dict[str, list[TraceDetail]] = {}
    loose: list[list[TraceDetail]] = []
    for d in details:
        if d.context_id:
            chains.setdefault(find(d.context_id), []).append(d)
        else:
            loose.append([d])
    out = [*chains.values(), *loose]
    for chain in out:
        chain.sort(key=_start_key)
    out.sort(key=lambda c: _start_key(c[0]))
    return out


def _start_key(d: TraceDetail | TraceRun) -> datetime:
    run = d.run if isinstance(d, TraceDetail) else d
    return run.start or datetime.min.replace(tzinfo=UTC)


class TracesService:
    """Read the runs HA stored for automations and scripts (``trace/list``, ``trace/get``)."""

    def __init__(self, client: HAClient) -> None:
        """Initialize.

        Args:
            client: Home Assistant client
        """
        self.client = client

    async def time_zone(self) -> tzinfo:
        """HA's configured time zone (UTC if it can't be read)."""
        try:
            config = await self.client._ws_call("get_config")
            return ZoneInfo(str((config or {}).get("time_zone") or "UTC"))
        except (WebSocketError, ZoneInfoNotFoundError, ValueError):
            return UTC

    async def resolve(self, target: str) -> tuple[str, str, str | None]:
        """``automation.<entity or YAML id>`` or ``script.<id>`` -> (domain, item_id, entity_id).

        Traces are keyed by the automation's YAML ``id:``, which is not the
        entity_id (that comes from the alias). Both are accepted. A target that
        doesn't exist is an error: trace/list answers ``[]`` for any id, so a
        typo would otherwise read as "no runs".

        Raises:
            ValidationError: No domain prefix, or a domain without traces
            NotFoundError: No such automation/script
        """
        domain, sep, name = target.partition(".")
        if not sep or not name:
            raise ValidationError(f"Give automation.<id> or script.<id>, not {target!r}")
        if domain not in DOMAINS:
            raise ValidationError(f"Only automations and scripts have traces, not {domain!r}")
        states = await self.client.get_states()
        mine = [s for s in states if str(s.get("entity_id", "")).startswith(f"{domain}.")]
        if domain == "script":
            if any(s.get("entity_id") == target for s in mine):
                return domain, name, target
            raise NotFoundError(f"No script {target!r}")
        for s in mine:
            if s.get("entity_id") == target:
                item_id = (s.get("attributes") or {}).get("id")
                if not item_id:
                    raise NotFoundError(f"{target} has no id: attribute, so HA keeps no traces for it")
                return domain, str(item_id), target
        for s in mine:
            if str((s.get("attributes") or {}).get("id")) == name:
                return domain, name, str(s.get("entity_id"))
        raise NotFoundError(f"No automation with entity_id or id {name!r}")

    async def list_runs(self, domain: str, item_id: str | None = None) -> list[TraceRun]:
        """Stored runs, earliest first: one item's, or (no item_id) the whole domain's."""
        kwargs: dict[str, Any] = {"domain": domain}
        if item_id is not None:
            kwargs["item_id"] = item_id
        result = await self.client._ws_call("trace/list", **kwargs)
        if not isinstance(result, list):
            raise ValidationError("Unexpected trace/list response")
        runs = [TraceRun.from_dict(r) for r in result if isinstance(r, dict)]
        return sorted(runs, key=_start_key)

    async def page(self, target: str, since: datetime | None = None,
                   until: datetime | None = None) -> RunsPage:
        """``traces list``: one item's runs in [since, until], and what HA kept."""
        domain, item_id, entity_id = await self.resolve(target)
        runs = await self.list_runs(domain, item_id)
        kept = [r for r in runs if _within(r, since, until)]
        return RunsPage(target=f"{domain}.{item_id}", entity_id=entity_id, runs=kept, stored=len(runs),
                        oldest=runs[0].start if runs else None)

    async def get(self, target: str, run_id: str | None = None, at: datetime | None = None) -> TraceDetail:
        """One run in full: by run_id, the one nearest ``at``, or the latest.

        Raises:
            NotFoundError: No such run, or no runs stored
        """
        domain, item_id, _ = await self.resolve(target)
        if run_id is None:
            runs = await self.list_runs(domain, item_id)
            if not runs:
                raise NotFoundError(f"No stored runs for {domain}.{item_id}")
            nearest = runs[-1] if at is None else min(runs, key=lambda r: _distance(r, at))
            run_id = nearest.run_id
        try:
            data = await self.client._ws_call("trace/get", domain=domain, item_id=item_id, run_id=run_id)
        except WebSocketError as e:
            if "not_found" in str(e):
                raise NotFoundError(f"No run {run_id!r} stored for {domain}.{item_id}") from e
            raise
        if not isinstance(data, dict):
            raise ValidationError("Unexpected trace/get response")
        return TraceDetail.from_dict(data)

    async def around(self, center: datetime, window: timedelta,
                     domains: tuple[str, ...] = DOMAINS) -> tuple[list[list[TraceDetail]], dict[str, Any]]:
        """Every stored run starting within ``window`` of ``center``, grouped into chains.

        Returns (chains, coverage). Coverage gives, per domain, how many runs are
        stored and the oldest, so an empty window can be told apart from
        history that has rolled off.

        Raises:
            ValidationError: More runs in the window than MAX_AROUND_RUNS
        """
        lo, hi = center - window, center + window
        lists = await asyncio.gather(*(self.list_runs(d) for d in domains))
        coverage: dict[str, Any] = {}
        hits: list[TraceRun] = []
        for domain, runs in zip(domains, lists, strict=True):
            coverage[domain] = {"stored": len(runs), "oldest": runs[0].start.isoformat() if runs and runs[0].start else None}
            hits += [r for r in runs if _within(r, lo, hi)]
        if len(hits) > MAX_AROUND_RUNS:
            raise ValidationError(f"{len(hits)} runs in that window (limit {MAX_AROUND_RUNS}): narrow --window")
        details = await asyncio.gather(*(
            self.client._ws_call("trace/get", domain=r.domain, item_id=r.item_id, run_id=r.run_id) for r in hits),
            return_exceptions=True)
        parsed: list[TraceDetail] = []
        rolled_off = 0
        for d in details:
            if isinstance(d, WebSocketError) and "not_found" in str(d):
                rolled_off += 1  # dropped between trace/list and trace/get
            elif isinstance(d, BaseException):
                raise d
            elif isinstance(d, dict):
                parsed.append(TraceDetail.from_dict(d))
        coverage["rolled_off_during_read"] = rolled_off
        return group_chains(parsed), coverage


def _distance(run: TraceRun, at: datetime) -> float:
    return abs((run.start - at).total_seconds()) if run.start else float("inf")


def _within(run: TraceRun, lo: datetime | None, hi: datetime | None) -> bool:
    if run.start is None:
        return lo is None and hi is None
    return (lo is None or run.start >= lo) and (hi is None or run.start <= hi)

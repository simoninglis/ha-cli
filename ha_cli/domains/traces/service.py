"""Service layer for the traces domain: stored automation and script runs."""

import asyncio
import re
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...common.client import HAClient
from ...common.exceptions import NotFoundError, ValidationError, WebSocketError
from .models import DOMAINS, AroundResult, RunsPage, TraceDetail, TraceRun

# `around` fetches every run in its window; past this it asks for a narrower one
MAX_AROUND_RUNS = 60
# HA's default stored_traces. An item holding at least this many runs, all newer
# than the window's start, may have dropped runs the window would have shown
DEFAULT_STORED_TRACES = 5

_CLOCK = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?$")
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)\s*([smh]?)$")


def parse_when(text: str, tz: tzinfo | None, now: datetime | None = None) -> datetime:
    """A time the way you'd say it, as an aware UTC datetime.

    ``14:18``, ``14:18:09`` (today), ``2026-11-13 14:18``, or ISO. Without an
    offset the time is in HA's zone ``tz``. A local time that doesn't exist (the
    clocks went forward) or happens twice (they went back) is refused rather
    than guessed: give an offset.

    Raises:
        ValidationError: Unparseable, nonexistent or ambiguous; or no offset and ``tz`` unknown
    """
    text = text.strip()
    m = _CLOCK.match(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        second = int(m.group(3) or 0)
        micro = int((m.group(4) or "0").ljust(6, "0"))
        if hour > 23 or minute > 59 or second > 59:
            raise ValidationError(f"Not a time: {text!r}")
        if tz is None:
            raise _no_zone(text)
        today = (now or datetime.now(UTC)).astimezone(tz).date()
        naive = datetime(today.year, today.month, today.day, hour, minute, second, micro)
        return _localise(naive, tz, text)
    try:
        when = datetime.fromisoformat(text)
    except ValueError as e:
        raise ValidationError(f"Not a time: {text!r} (use HH:MM[:SS], 'YYYY-MM-DD HH:MM[:SS]' or ISO)") from e
    if when.tzinfo is not None:
        return when.astimezone(UTC)
    if tz is None:
        raise _no_zone(text)
    return _localise(when, tz, text)


def _no_zone(text: str) -> ValidationError:
    return ValidationError(f"HA's time zone couldn't be read, so {text!r} has no fixed meaning: "
                           "give an offset, e.g. 2026-11-13T14:18:09+10:00")


def _localise(naive: datetime, tz: tzinfo, text: str) -> datetime:
    early = naive.replace(tzinfo=tz, fold=0)
    if early.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != naive:
        raise ValidationError(f"{text!r} doesn't exist in {tz} (the clocks went forward): give an offset")
    if early.utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset():
        raise ValidationError(f"{text!r} happens twice in {tz} (the clocks went back): give an offset")
    return early.astimezone(UTC)


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
    another run's context id (an action that caused it) joins that group too.
    A group is a shared context, not a call tree: two members can be
    siblings, both started by the first.
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

    async def time_zone(self) -> tzinfo | None:
        """HA's configured time zone, or None if it can't be read.

        None is not UTC: callers must not read a bare ``14:18`` as UTC
        (parse_when refuses it), and should say they are showing UTC.
        """
        try:
            config = await self.client._ws_call("get_config")
            name = (config or {}).get("time_zone")
            return ZoneInfo(str(name)) if name else None
        except (WebSocketError, ZoneInfoNotFoundError, ValueError):
            return None

    async def resolve(self, target: str) -> tuple[str, str, str | None]:
        """A target -> (domain, item_id, entity_id).

        ``automation.<entity_id or YAML id>``, ``automation:<YAML id>`` (the id
        only), or ``script.<id>`` / ``script:<id>``. Traces are keyed by the
        automation's YAML ``id:``, which is not its entity_id (that comes from
        the alias). If ``automation.X`` matches one automation's entity_id and
        another's id, that is refused rather than guessed. A target that
        doesn't exist is an error: trace/list answers ``[]`` for any id, so a
        typo would otherwise read as "no runs".

        Raises:
            ValidationError: Bad form, a domain without traces, or ambiguous
            NotFoundError: No such automation/script
        """
        by_id_only = ":" in target and "." not in target.split(":", 1)[0]
        domain, sep, name = target.partition(":" if by_id_only else ".")
        if not sep or not name:
            raise ValidationError(f"Give automation.<id> or script.<id>, not {target!r}")
        if domain not in DOMAINS:
            raise ValidationError(f"Only automations and scripts have traces, not {domain!r}")
        states = await self.client.get_states()
        mine = [s for s in states if str(s.get("entity_id", "")).startswith(f"{domain}.")]
        if domain == "script":
            if any(s.get("entity_id") == f"script.{name}" for s in mine):
                return domain, name, f"script.{name}"
            raise NotFoundError(f"No script {name!r}")

        def yaml_id(s: dict[str, Any]) -> str | None:
            value = (s.get("attributes") or {}).get("id")
            return str(value) if value not in (None, "") else None

        def unique(item_id: str) -> None:
            # Whichever way it was found, the trace key must name one automation
            holders = [str(s.get("entity_id")) for s in mine if yaml_id(s) == item_id]
            if len(holders) > 1:
                raise ValidationError(f"{len(holders)} automations have id {item_id!r}, so their traces "
                                      f"are mixed: {', '.join(holders)}")

        by_id = [s for s in mine if yaml_id(s) == name]
        if len(by_id) > 1:
            unique(name)
        by_entity = [] if by_id_only else [s for s in mine if s.get("entity_id") == f"automation.{name}"]
        if by_entity and by_id and by_entity[0] is not by_id[0]:
            other = by_entity[0]
            raise ValidationError(
                f"automation.{name} is ambiguous: it is the entity_id of one automation (id "
                f"{yaml_id(other)!r}) and the id of another ({by_id[0].get('entity_id')}). "
                f"Use automation:{name} for the id, or automation:{yaml_id(other)} for the entity")
        if by_id:
            return domain, name, str(by_id[0].get("entity_id"))
        if by_entity:
            item_id = yaml_id(by_entity[0])
            if item_id is None:
                raise NotFoundError(f"automation.{name} has no id: attribute, so HA keeps no traces for it")
            unique(item_id)
            return domain, item_id, f"automation.{name}"
        raise NotFoundError(f"No automation with {'id' if by_id_only else 'entity_id or id'} {name!r}")

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
        """``traces list``: one item's runs in [since, until], and what HA kept.

        Raises:
            ValidationError: ``since`` after ``until``
        """
        if since and until and since > until:
            raise ValidationError("--since is after --until (for a window across midnight, give dates)")
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
        detail = read_detail(data, run_id)
        if detail is None:
            raise ValidationError(f"Unreadable trace/get response for {domain}.{item_id} run {run_id}")
        return detail

    async def around(self, center: datetime, window: timedelta,
                     domains: tuple[str, ...] = DOMAINS) -> AroundResult:
        """Every stored run starting within ``window`` of ``center``, grouped.

        Bounds are computed in UTC, so a window across a DST change spans the
        elapsed time asked for. The result says what it could NOT see:
        items whose retained history starts after the window opened (runs of
        theirs may have rolled off), runs that vanished between list and get,
        and responses that couldn't be read. Completeness is never claimed.

        Raises:
            ValidationError: More runs in the window than MAX_AROUND_RUNS
        """
        domains = tuple(dict.fromkeys(domains))  # a repeated --domain must not fetch twice
        center = center.astimezone(UTC)
        lo, hi = center - window, center + window
        lists = await asyncio.gather(*(self.list_runs(d) for d in domains))
        result = AroundResult(lo=lo, hi=hi, domains=list(domains))
        hits: list[TraceRun] = []
        for domain, runs in zip(domains, lists, strict=True):
            result.stored[domain] = len(runs)
            per_item: dict[str, list[TraceRun]] = {}
            for r in runs:
                per_item.setdefault(r.item_id, []).append(r)
            for item_id, item_runs in per_item.items():
                oldest = item_runs[0].start
                if len(item_runs) >= DEFAULT_STORED_TRACES and oldest is not None and oldest > lo:
                    result.possibly_missing.append({"target": f"{domain}.{item_id}", "stored": len(item_runs),
                                                    "oldest": oldest.isoformat()})
            hits += [r for r in runs if _within(r, lo, hi)]
        if len(hits) > MAX_AROUND_RUNS:
            raise ValidationError(f"{len(hits)} runs in that window (limit {MAX_AROUND_RUNS}): narrow --window")
        details = await asyncio.gather(*(
            self.client._ws_call("trace/get", domain=r.domain, item_id=r.item_id, run_id=r.run_id) for r in hits),
            return_exceptions=True)
        parsed: list[TraceDetail] = []
        for run, d in zip(hits, details, strict=True):
            ref = {"target": run.target, "run_id": run.run_id, "start": run.start.isoformat() if run.start else None}
            if isinstance(d, WebSocketError) and "not_found" in str(d):
                result.rolled_off.append(ref)  # dropped between trace/list and trace/get
            elif isinstance(d, BaseException):
                raise d
            else:
                detail = read_detail(d, run.run_id)
                if detail is None:
                    result.unreadable.append(ref)
                else:
                    parsed.append(detail)
        result.chains = group_chains(parsed)
        return result


def read_detail(data: Any, run_id: str) -> TraceDetail | None:
    """A trace/get payload as a TraceDetail, or None if it isn't one for ``run_id``.

    A payload that parses but lacks the run's identity (``{}`` would show as
    a run of ".") or names a different run is unusable, not a run.
    """
    if not isinstance(data, dict):
        return None
    if data.get("run_id") != run_id or not data.get("domain") or not data.get("item_id"):
        return None
    if not isinstance(data.get("timestamp"), dict) or not isinstance(data.get("trace", {}), dict):
        return None
    try:
        detail = TraceDetail.from_dict(data)
    except (AttributeError, TypeError, ValueError):
        return None
    return detail if detail.run.start is not None else None


def _distance(run: TraceRun, at: datetime) -> float:
    return abs((run.start - at).total_seconds()) if run.start else float("inf")


def _within(run: TraceRun, lo: datetime | None, hi: datetime | None) -> bool:
    if run.start is None:
        return lo is None and hi is None
    return (lo is None or run.start >= lo) and (hi is None or run.start <= hi)

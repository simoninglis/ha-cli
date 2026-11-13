"""Data models for the traces domain."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

DOMAINS = ("automation", "script")

# changed_variables HA adds to every run: shown separately (trigger) or noise (this, context)
_BUILTIN_VARS = {"trigger", "this", "context"}


def parse_ts(value: Any) -> datetime | None:
    """An ISO timestamp from a trace, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass
class TraceRun:
    """One stored run, as trace/list reports it."""

    domain: str
    item_id: str
    run_id: str
    start: datetime | None
    finish: datetime | None
    state: str
    execution: str | None   # HA's script_execution: finished, aborted, failed_conditions, error, ...
    last_step: str | None
    trigger: str | None     # trigger description; automations only

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceRun":
        """From a trace/list item (or the summary fields of trace/get)."""
        ts = data.get("timestamp") or {}
        return cls(
            domain=str(data.get("domain") or ""),
            item_id=str(data.get("item_id") or ""),
            run_id=str(data.get("run_id") or ""),
            start=parse_ts(ts.get("start")),
            finish=parse_ts(ts.get("finish")),
            state=str(data.get("state") or ""),
            execution=data.get("script_execution"),
            last_step=data.get("last_step"),
            trigger=data.get("trigger") or None,
        )

    @property
    def target(self) -> str:
        """``domain.item_id``: what ``traces show`` takes."""
        return f"{self.domain}.{self.item_id}"

    @property
    def duration(self) -> float | None:
        """Seconds from start to finish, if finished."""
        if self.start and self.finish:
            return (self.finish - self.start).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {
            "domain": self.domain, "item_id": self.item_id, "run_id": self.run_id,
            "start": _iso(self.start), "finish": _iso(self.finish), "duration_seconds": self.duration,
            "state": self.state, "execution": self.execution, "last_step": self.last_step,
            "trigger": self.trigger,
        }


@dataclass
class TraceStep:
    """One step of a run: its path, when, what it decided or called."""

    path: str
    at: datetime | None
    result: Any
    error: str | None
    variables: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """A one-line reading of ``result``."""
        return summarise_result(self.result)

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {"path": self.path, "at": _iso(self.at), "result": self.result, "error": self.error,
                "variables": self.variables}


@dataclass
class TriggerInfo:
    """What fired an automation run, from the trace's ``trigger`` variable."""

    description: str | None
    entity_id: str | None
    from_state: dict[str, Any] | None
    to_state: dict[str, Any] | None
    for_seconds: float | None

    @classmethod
    def from_variable(cls, trig: Any) -> "TriggerInfo | None":
        """From changed_variables['trigger']; None if it isn't a mapping."""
        if not isinstance(trig, dict):
            return None
        return cls(
            description=trig.get("description"),
            entity_id=trig.get("entity_id"),
            from_state=_state_view(trig.get("from_state")),
            to_state=_state_view(trig.get("to_state")),
            for_seconds=duration_seconds(trig.get("for")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {"description": self.description, "entity_id": self.entity_id, "from_state": self.from_state,
                "to_state": self.to_state, "for_seconds": self.for_seconds}


@dataclass
class TraceDetail:
    """A whole run, from trace/get."""

    run: TraceRun
    alias: str | None
    steps: list[TraceStep]
    trigger: TriggerInfo | None
    context_id: str | None
    parent_id: str | None
    user_id: str | None
    fields: dict[str, Any] = field(default_factory=dict)  # a script's call variables (e.g. its fields)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceDetail":
        """From a trace/get result."""
        steps: list[TraceStep] = []
        trigger: TriggerInfo | None = None
        fields: dict[str, Any] = {}
        for path, entries in (data.get("trace") or {}).items():
            for entry in entries if isinstance(entries, list) else []:
                cv = entry.get("changed_variables") or {}
                if trigger is None and "trigger" in cv:
                    trigger = TriggerInfo.from_variable(cv.get("trigger"))
                variables = {k: v for k, v in cv.items() if k not in _BUILTIN_VARS}
                # A script's first step carries the variables it was called with
                if not steps and "context" in cv:
                    fields, variables = variables, {}
                steps.append(TraceStep(path=str(path), at=parse_ts(entry.get("timestamp")),
                                       result=entry.get("result"), error=entry.get("error"),
                                       variables=variables))
        steps.sort(key=lambda s: (s.at is None, s.at or datetime.min))
        context = data.get("context") or {}
        config = data.get("config") or {}
        return cls(run=TraceRun.from_dict(data), alias=config.get("alias"), steps=steps, trigger=trigger,
                   context_id=context.get("id"), parent_id=context.get("parent_id"),
                   user_id=context.get("user_id"), fields=fields)

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {**self.run.to_dict(), "alias": self.alias, "context_id": self.context_id,
                "parent_id": self.parent_id, "user_id": self.user_id, "fields": self.fields,
                "trigger_detail": self.trigger.to_dict() if self.trigger else None,
                "steps": [s.to_dict() for s in self.steps]}


@dataclass
class RunsPage:
    """``traces list``: the runs in a window, and how much history HA kept."""

    target: str
    entity_id: str | None
    runs: list[TraceRun]
    stored: int
    oldest: datetime | None

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {"target": self.target, "entity_id": self.entity_id, "stored": self.stored,
                "oldest": _iso(self.oldest), "runs": [r.to_dict() for r in self.runs]}


def duration_seconds(value: Any) -> float | None:
    """A trace's serialised timedelta (``{"__type": ..., "total_seconds": N}``), or a number."""
    if isinstance(value, dict) and isinstance(value.get("total_seconds"), int | float):
        return float(value["total_seconds"])
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _state_view(state: Any) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    return {"state": state.get("state"), "last_changed": state.get("last_changed"),
            "attributes": state.get("attributes") or {}}


def summarise_result(result: Any) -> str:
    """Read a step result the way you would in the trace UI."""
    if not isinstance(result, dict):
        return "" if result is None else _compact(result)
    parts: list[str] = []
    if "choice" in result:
        parts.append(f"choice={result['choice']}")
    if "result" in result:
        parts.append(str(result["result"]).lower())
        if "state" in result or "wanted_state" in result:
            parts.append(f"(state={result.get('state')!r}, wanted={result.get('wanted_state')!r})")
        if result.get("entities"):
            parts.append(f"entities={','.join(map(str, result['entities']))}")
    params = result.get("params")
    if isinstance(params, dict):
        target = params.get("target") or {}
        ids = target.get("entity_id") if isinstance(target, dict) else None
        ids_text = ",".join(ids) if isinstance(ids, list) else (ids or "")
        call = f"{params.get('domain')}.{params.get('service')}"
        data = params.get("service_data") or {}
        data = {k: v for k, v in data.items() if k != "entity_id"} if isinstance(data, dict) else data
        parts.append(f"call {call}" + (f" -> {ids_text}" if ids_text else "") + (f" {_compact(data)}" if data else ""))
    if "stop" in result:
        parts.append(f"stop: {result['stop']}" + (" (error)" if result.get("error") else ""))
    if "wait" in result and isinstance(result["wait"], dict):
        w = result["wait"]
        parts.append(f"wait completed={w.get('completed')} remaining={w.get('remaining')}")
    if "delay" in result:
        parts.append(f"delay {result['delay']}" + (" done" if result.get("done") else ""))
    known = {"choice", "result", "state", "wanted_state", "entities", "params", "stop", "error", "wait",
             "delay", "done", "running_script"}
    rest = {k: v for k, v in result.items() if k not in known}
    if rest:
        parts.append(_compact(rest))
    return " ".join(parts)


def _compact(value: Any, limit: int = 160) -> str:
    text = json.dumps(value, default=str, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class AroundResult:
    """``traces around``: the runs in a window, and what the window could not show."""

    lo: datetime
    hi: datetime
    domains: list[str]
    chains: list[list[TraceDetail]] = field(default_factory=list)
    stored: dict[str, int] = field(default_factory=dict)
    # Items holding a full default history, all of it newer than the window's
    # start: runs of theirs inside the window may already have rolled off
    possibly_missing: list[dict[str, Any]] = field(default_factory=list)
    rolled_off: list[dict[str, Any]] = field(default_factory=list)   # gone between trace/list and trace/get
    unreadable: list[dict[str, Any]] = field(default_factory=list)   # trace/get answered something unusable
    hidden_failed_conditions: int = 0

    @property
    def shown(self) -> int:
        """Runs in the chains."""
        return sum(len(c) for c in self.chains)

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {
            "from": _iso(self.lo), "to": _iso(self.hi), "domains": self.domains,
            "complete": None,  # never claimed: each item keeps only its own last N runs
            "stored": self.stored, "possibly_missing": self.possibly_missing,
            "rolled_off_during_read": self.rolled_off, "unreadable": self.unreadable,
            "hidden_failed_conditions": self.hidden_failed_conditions,
            "chains": [[d.to_dict() for d in chain] for chain in self.chains],
        }

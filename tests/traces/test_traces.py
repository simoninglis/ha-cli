"""Tests for the traces domain, against payloads recorded from a live HA."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from ha_cli.common.exceptions import NotFoundError, ValidationError, WebSocketError
from ha_cli.domains.traces.cli import app
from ha_cli.domains.traces.models import TraceDetail, TraceRun, duration_seconds, summarise_result
from ha_cli.domains.traces.service import MAX_AROUND_RUNS, TracesService, group_chains, parse_duration, parse_when

runner = CliRunner()
FIX = json.loads((Path(__file__).parent / "fixtures.json").read_text())
BNE = ZoneInfo("Australia/Brisbane")

STATES = [
    {"entity_id": "automation.office_ble_away_signal_lock_pc_shorten_timer",
     "attributes": {"id": "office_ble_away_signal"}},
    {"entity_id": "automation.no_id_ui_thing", "attributes": {}},
    {"entity_id": "automation.none_id", "attributes": {"id": None}},
    # A's id is "clash"; B's entity_id is automation.clash
    {"entity_id": "automation.alpha", "attributes": {"id": "clash"}},
    {"entity_id": "automation.clash", "attributes": {"id": "beta_id"}},
    {"entity_id": "automation.dup_a", "attributes": {"id": "dup"}},
    {"entity_id": "automation.dup_b", "attributes": {"id": "dup"}},
    {"entity_id": "script.office_pc_lock", "attributes": {}},
    {"entity_id": "light.office", "attributes": {}},
]


def _run(domain: str, item_id: str, run_id: str, start: str, execution: str = "finished",
         trigger: str | None = None) -> dict[str, Any]:
    return {"domain": domain, "item_id": item_id, "run_id": run_id, "state": "stopped",
            "script_execution": execution, "last_step": "action/0", "trigger": trigger,
            "timestamp": {"start": start, "finish": start}}


def _detail(run: dict[str, Any], context_id: str | None, parent_id: str | None = None) -> dict[str, Any]:
    return {**run, "trace": {}, "config": {"alias": run["item_id"]},
            "context": {"id": context_id, "parent_id": parent_id, "user_id": None}}


class FakeHA:
    """trace/list, trace/get and get_states over a fixed set of runs."""

    def __init__(self, runs: list[dict[str, Any]] | None = None,
                 details: dict[str, dict[str, Any]] | None = None, tz: str = "Australia/Brisbane",
                 gone: set[str] | None = None, broken: set[str] | None = None,
                 junk: set[str] | None = None) -> None:
        self.runs = runs if runs is not None else list(FIX["list_ble"])
        self.details = details if details is not None else {FIX["get_ble"]["run_id"]: FIX["get_ble"]}
        self.tz = tz
        self.gone = gone or set()
        self.broken = broken or set()
        self.junk = junk or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_states(self) -> list[dict[str, Any]]:
        return STATES

    async def _ws_call(self, msg_type: str, **kwargs: Any) -> Any:
        self.calls.append((msg_type, kwargs))
        if msg_type == "get_config":
            return {"time_zone": self.tz}
        if msg_type == "trace/list":
            return [r for r in self.runs if r["domain"] == kwargs["domain"]
                    and ("item_id" not in kwargs or r["item_id"] == kwargs["item_id"])]
        if msg_type == "trace/get":
            rid = kwargs["run_id"]
            if rid in self.broken:
                raise WebSocketError("unknown_error: boom")
            if rid in self.junk:
                return None
            if rid in self.gone or rid not in self.details:
                raise WebSocketError("not_found: The trace could not be found")
            return self.details[rid]
        raise AssertionError(msg_type)


def svc(fake: FakeHA) -> TracesService:
    return TracesService(fake)  # type: ignore[arg-type]


# --- parsing -----------------------------------------------------------------

def test_parse_when_clock_is_today_in_ha_zone() -> None:
    now = datetime(2026, 11, 13, 1, 0, tzinfo=UTC)  # 11:00 in Brisbane
    when = parse_when("14:18:09", BNE, now)
    assert when == datetime(2026, 11, 13, 14, 18, 9, tzinfo=BNE)
    assert parse_when("14:18", BNE, now).second == 0
    assert parse_when("14:18:09.5", BNE, now).microsecond == 500000


def test_parse_when_date_without_zone_is_ha_zone_and_iso_keeps_its_own() -> None:
    assert parse_when("2026-11-13 14:18", BNE) == datetime(2026, 11, 13, 14, 18, tzinfo=BNE)
    iso = parse_when("2026-11-13T04:18:09+00:00", BNE)
    assert iso.utcoffset() == timedelta(0)


@pytest.mark.parametrize("bad", ["25:00", "14:61", "teatime", "", "14"])
def test_parse_when_rejects(bad: str) -> None:
    with pytest.raises(ValidationError):
        parse_when(bad, BNE)


def test_naive_trace_timestamps_are_not_trusted() -> None:
    from ha_cli.domains.traces.models import parse_ts
    assert parse_ts("2026-11-13T04:18:08") is None
    assert parse_ts("2026-11-13T04:18:08+00:00") is not None
    runs = [_run("automation", "a", "r1", "2026-11-13T04:18:08")]   # no offset
    result = asyncio.run(svc(FakeHA(runs=runs, details={})).around(
        parse_when("2026-11-13 14:18:09", BNE), timedelta(seconds=30), ("automation",)))
    assert result.shown == 0                                          # and no TypeError


def test_calendar_edge_times_are_validation_errors() -> None:
    with pytest.raises(ValidationError):
        parse_when("0001-01-01T00:00:00+10:00", BNE)
    with pytest.raises(ValidationError):
        parse_when("0001-01-01 00:00", ZoneInfo("Asia/Tokyo"))   # LMT +09:18 runs before year 1


def test_malformed_list_entries_do_not_abort() -> None:
    bad = {**_run("automation", "a", "r1", "2026-11-13T04:18:08+00:00"), "timestamp": ["bad"]}
    runs = asyncio.run(svc(FakeHA(runs=[bad], details={})).list_runs("automation"))
    assert runs[0].start is None


def test_oversized_windows_are_validation_errors() -> None:
    with pytest.raises(ValidationError):
        parse_duration("1" + "0" * 30 + "h")
    with pytest.raises(ValidationError):
        asyncio.run(svc(FakeHA(runs=[], details={})).around(
            parse_when("2026-11-13 14:18:09", BNE), timedelta(days=999_999_999)))


def test_parse_duration() -> None:
    assert parse_duration("90") == timedelta(seconds=90)
    assert parse_duration("90s") == timedelta(seconds=90)
    assert parse_duration("2m") == timedelta(minutes=2)
    assert parse_duration("1.5h") == timedelta(minutes=90)
    with pytest.raises(ValidationError):
        parse_duration("2 fortnights")


def test_duration_seconds_reads_serialised_timedelta() -> None:
    assert duration_seconds({"__type": "<class 'datetime.timedelta'>", "total_seconds": 120.0}) == 120.0
    assert duration_seconds(5) == 5.0
    assert duration_seconds(True) is None
    assert duration_seconds("2m") is None


# --- resolving targets -------------------------------------------------------

def test_resolve_entity_id_maps_to_yaml_id() -> None:
    got = asyncio.run(svc(FakeHA()).resolve("automation.office_ble_away_signal_lock_pc_shorten_timer"))
    assert got == ("automation", "office_ble_away_signal", "automation.office_ble_away_signal_lock_pc_shorten_timer")


def test_resolve_yaml_id_finds_its_entity() -> None:
    got = asyncio.run(svc(FakeHA()).resolve("automation.office_ble_away_signal"))
    assert got == ("automation", "office_ble_away_signal", "automation.office_ble_away_signal_lock_pc_shorten_timer")


def test_resolve_explicit_id_form_settles_the_clash() -> None:
    assert asyncio.run(svc(FakeHA()).resolve("automation:clash")) == ("automation", "clash", "automation.alpha")
    assert asyncio.run(svc(FakeHA()).resolve("automation:beta_id")) == ("automation", "beta_id", "automation.clash")
    assert asyncio.run(svc(FakeHA()).resolve("script:office_pc_lock"))[1] == "office_pc_lock"


def test_resolve_script() -> None:
    assert asyncio.run(svc(FakeHA()).resolve("script.office_pc_lock")) == ("script", "office_pc_lock",
                                                                           "script.office_pc_lock")


@pytest.mark.parametrize(("target", "error"), [
    ("automation.typo", NotFoundError),       # trace/list would answer [] and look like "no runs"
    ("script.typo", NotFoundError),
    ("automation.no_id_ui_thing", NotFoundError),
    ("automation.None", NotFoundError),       # a missing id must not become the string "None"
    ("automation.clash", ValidationError),    # A's id and B's entity_id: refuse, don't guess
    ("automation.dup", ValidationError),      # two automations share the id
    ("automation.dup_a", ValidationError),    # ...also when found through an entity_id
    ("automation:office_ble_away_signal_lock_pc_shorten_timer", NotFoundError),  # ':' means id only
    ("light.office", ValidationError),
    ("office_pc_lock", ValidationError),
    ("automation.", ValidationError),
])
def test_resolve_refuses(target: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        asyncio.run(svc(FakeHA()).resolve(target))


# --- models from real payloads -----------------------------------------------

def test_detail_from_real_automation_trace() -> None:
    d = TraceDetail.from_dict(FIX["get_ble"])
    assert d.run.target == "automation.office_ble_away_signal"
    assert d.alias
    assert d.alias.startswith("Office: BLE Away")
    assert d.trigger is not None
    assert d.trigger.for_seconds == 120.0
    assert d.trigger.entity_id == "binary_sensor.simon_in_office"
    assert d.trigger.to_state
    assert d.trigger.to_state["state"] == "off"
    assert d.trigger.to_state["attributes"]["phone_room"] == "Master"
    paths = [s.path for s in d.steps]
    assert paths[0] == "trigger/0"
    assert "action/2/then/0" in paths
    assert [s.at for s in d.steps] == sorted(s.at for s in d.steps)  # type: ignore[type-var]
    call = next(s for s in d.steps if s.path == "action/0/then/0")
    assert call.summary() == "call script.turn_on -> script.office_pc_lock"
    gate = next(s for s in d.steps if s.path == "condition/0/entity_id/0")
    assert gate.summary() == "true (state='ready', wanted='ready')"
    assert next(s for s in d.steps if s.path == "action/1").variables == {"shortened_minutes": 2}
    assert d.context_id
    assert d.parent_id


def test_detail_from_real_script_trace_reads_its_call_fields() -> None:
    d = TraceDetail.from_dict(FIX["get_lock_skip"])
    assert d.trigger is None
    assert d.fields.get("automatic") is True
    assert d.steps[0].variables == {}           # the call variables moved to .fields, not repeated
    assert d.run.last_step == "sequence/1/then/1"
    assert "stop: Dippy Bird keep-awake is on" in d.steps[-1].summary()


def test_to_dict_round_trips_through_json() -> None:
    json.dumps(TraceDetail.from_dict(FIX["get_ble"]).to_dict(), default=str)


@pytest.mark.parametrize(("result", "expected"), [
    ({"stop": "done", "error": False}, "stop: done"),
    ({"stop": "bad", "error": True}, "stop: bad (error)"),
    ({"wait": {"completed": False, "remaining": 0}}, "wait completed=False remaining=0"),
    ({"delay": 5.0, "done": True}, "delay 5.0 done"),
    ({"choice": "default"}, "choice=default"),
    (None, ""),
    ({"surprise": 1}, '{"surprise":1}'),
])
def test_summarise_result(result: Any, expected: str) -> None:
    assert summarise_result(result) == expected


# --- list / get ---------------------------------------------------------------

def test_page_filters_window_and_reports_what_is_stored() -> None:
    lo = parse_when("2026-11-13 14:20", BNE)
    page = asyncio.run(svc(FakeHA()).page("automation.office_ble_away_signal", since=lo))
    assert [r.run_id for r in page.runs] == ["85c751e6f01f175ad487d031f880bfd0"]
    assert page.stored == 2
    assert page.oldest == datetime.fromisoformat(FIX["list_ble"][0]["timestamp"]["start"])


def test_page_refuses_reversed_bounds() -> None:
    with pytest.raises(ValidationError):
        asyncio.run(svc(FakeHA()).page("automation.office_ble_away_signal",
                                       since=parse_when("2026-11-13 14:30", BNE),
                                       until=parse_when("2026-11-13 14:00", BNE)))


def test_page_for_an_item_with_no_runs_is_empty_not_an_error() -> None:
    page = asyncio.run(svc(FakeHA(runs=[])).page("script.office_pc_lock"))
    assert page.runs == []
    assert page.stored == 0
    assert page.oldest is None


def test_get_latest_nearest_and_by_id() -> None:
    a, b = FIX["list_ble"]
    details = {a["run_id"]: _detail(a, "c1"), b["run_id"]: _detail(b, "c2")}
    fake = FakeHA(details=details)
    s = svc(fake)
    latest = asyncio.run(s.get("automation.office_ble_away_signal"))
    assert latest.run.run_id == max((a, b), key=lambda r: r["timestamp"]["start"])["run_id"]
    near = asyncio.run(s.get("automation.office_ble_away_signal", at=parse_when("2026-11-13 14:18:09", BNE)))
    assert near.run.run_id == "3e31a971938a313193e7b25ac641d64b"
    by_id = asyncio.run(s.get("automation.office_ble_away_signal", run_id=b["run_id"]))
    assert by_id.run.run_id == b["run_id"]


def test_get_unknown_run_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        asyncio.run(svc(FakeHA()).get("automation.office_ble_away_signal", run_id="nope"))


def test_get_with_nothing_stored_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        asyncio.run(svc(FakeHA(runs=[])).get("script.office_pc_lock"))


def test_time_zone_unknown_is_none_not_utc() -> None:
    assert asyncio.run(svc(FakeHA(tz="Not/AZone")).time_zone()) is None


def test_no_zone_refuses_local_times_but_takes_offsets() -> None:
    for text in ("14:18", "2026-11-13 14:18"):
        with pytest.raises(ValidationError):
            parse_when(text, None)
    assert parse_when("2026-11-13T14:18:00+10:00", None) == datetime(2026, 11, 13, 4, 18, tzinfo=UTC)


SYD = ZoneInfo("Australia/Sydney")


def test_dst_gap_and_repeat_are_refused() -> None:
    with pytest.raises(ValidationError, match="doesn't exist"):
        parse_when("2026-10-04 02:30", SYD)        # clocks go 02:00 -> 03:00
    with pytest.raises(ValidationError, match="happens twice"):
        parse_when("2026-04-05 02:30", SYD)        # clocks go 03:00 -> 02:00
    assert parse_when("2026-04-05T02:30:00+11:00", SYD).utcoffset() == timedelta(0)


def test_parse_when_returns_utc() -> None:
    assert parse_when("2026-11-13 14:18", BNE).tzinfo is UTC


def test_around_window_is_elapsed_time_across_dst() -> None:
    center = parse_when("2026-04-05T02:59:30+11:00", SYD)    # just before the clocks go back
    result = asyncio.run(svc(FakeHA(runs=[], details={})).around(center, timedelta(minutes=2)))
    # Same-zone subtraction is wall-clock, so measure the elapsed span in UTC
    assert result.hi.astimezone(UTC) - result.lo.astimezone(UTC) == timedelta(minutes=4)


# --- chains and around ---------------------------------------------------------

def _d(run_id: str, start: str, ctx: str | None, parent: str | None = None, domain: str = "automation",
       execution: str = "finished") -> TraceDetail:
    return TraceDetail.from_dict(_detail(_run(domain, run_id, run_id, start, execution), ctx, parent))


def test_group_chains_shared_context_and_parent_links() -> None:
    auto = _d("auto", "2026-11-13T04:18:08.795+00:00", "C1", "state-change")
    script = _d("lock", "2026-11-13T04:18:08.796+00:00", "C1", "state-change", domain="script")
    caused = _d("caused", "2026-11-13T04:18:10+00:00", "C2", "C1")      # an action of C1 caused it
    grandchild = _d("gc", "2026-11-13T04:18:11+00:00", "C3", "C2")
    other = _d("other", "2026-11-13T04:18:09+00:00", "C9", "unrelated")
    loose = _d("loose", "2026-11-13T04:18:12+00:00", None)
    chains = group_chains([loose, grandchild, other, caused, script, auto])
    ids = [[d.run.run_id for d in c] for c in chains]
    assert ids == [["auto", "lock", "caused", "gc"], ["other"], ["loose"]]


def test_around_window_gets_each_run_and_groups() -> None:
    inside = [_run("automation", "ble", "r1", "2026-11-13T04:18:08.795+00:00", trigger="state of x"),
              _run("script", "office_pc_lock", "r2", "2026-11-13T04:18:08.796+00:00")]
    outside = [_run("automation", "ble", "r0", "2026-11-13T04:10:00+00:00")]
    details = {"r1": _detail(inside[0], "C1"), "r2": _detail(inside[1], "C1"), "r0": _detail(outside[0], "C0")}
    fake = FakeHA(runs=inside + outside, details=details)
    result = asyncio.run(svc(fake).around(parse_when("2026-11-13 14:18:09", BNE), timedelta(seconds=30)))
    assert [[d.run.run_id for d in c] for c in result.chains] == [["r1", "r2"]]
    assert result.stored == {"automation": 2, "script": 1}
    assert {k["run_id"] for m, k in fake.calls if m == "trace/get"} == {"r1", "r2"}  # nothing outside fetched
    assert all("item_id" not in k for m, k in fake.calls if m == "trace/list")       # whole domain listed


def test_around_tolerates_a_run_rolling_off_but_not_other_errors() -> None:
    runs = [_run("automation", "a", "r1", "2026-11-13T04:18:08+00:00"),
            _run("automation", "a", "r2", "2026-11-13T04:18:09+00:00")]
    details = {r["run_id"]: _detail(r, r["run_id"]) for r in runs}
    center = parse_when("2026-11-13 14:18:09", BNE)
    result = asyncio.run(svc(FakeHA(runs=runs, details=details, gone={"r1"})).around(
        center, timedelta(seconds=30), ("automation",)))
    assert [[d.run.run_id for d in c] for c in result.chains] == [["r2"]]
    assert [r["run_id"] for r in result.rolled_off] == ["r1"]
    with pytest.raises(WebSocketError):
        asyncio.run(svc(FakeHA(runs=runs, details=details, broken={"r1"})).around(
            center, timedelta(seconds=30), ("automation",)))


def test_around_reports_unreadable_responses_instead_of_dropping_them() -> None:
    runs = [_run("automation", "a", "r1", "2026-11-13T04:18:08+00:00")]
    result = asyncio.run(svc(FakeHA(runs=runs, details={}, junk={"r1"})).around(
        parse_when("2026-11-13 14:18:09", BNE), timedelta(seconds=30), ("automation",)))
    assert result.chains == []
    assert [r["run_id"] for r in result.unreadable] == ["r1"]


def malformed(good: dict[str, Any]) -> dict[str, Any]:
    """Ways a trace/get reply for ``good``'s run can fail to be that run."""
    return {
        "empty": {},                                   # would show as a run of "."
        "not a dict": [good["run_id"]],
        "no trace": {k: v for k, v in good.items() if k != "trace"},
        "trace not a mapping": {**good, "trace": ["x"]},
        "no timestamp": {k: v for k, v in good.items() if k != "timestamp"},
        "no start": {**good, "timestamp": {}},
        "start without offset": {**good, "timestamp": {"start": "2026-11-13T04:18:08"}},
        "timestamp not a mapping": {**good, "timestamp": ["2026-11-13T04:18:08+00:00"]},
        "other run": {**good, "run_id": "r9"},
        "other item": {**good, "item_id": "unrelated"},
        "other domain": {**good, "domain": "script"},
        "garbage step": {**good, "trace": {"action/0": [{"changed_variables": "garbage"}]}},
    }


GOOD = {"run_id": "r1", "domain": "automation", "item_id": "a",
        "timestamp": {"start": "2026-11-13T04:18:08+00:00"}, "trace": {}}
GOOD_GET = {**FIX["list_ble"][0], "trace": {}}
CASES = list(malformed(GOOD))


def test_good_payloads_are_runs() -> None:
    runs = [_run("automation", "a", "r1", "2026-11-13T04:18:08+00:00")]
    result = asyncio.run(svc(FakeHA(runs=runs, details={"r1": GOOD})).around(
        parse_when("2026-11-13 14:18:09", BNE), timedelta(seconds=30), ("automation",)))
    assert result.shown == 1
    rid = GOOD_GET["run_id"]
    got = asyncio.run(svc(FakeHA(details={rid: GOOD_GET})).get("automation.office_ble_away_signal", run_id=rid))
    assert got.run.run_id == rid


@pytest.mark.parametrize("case", CASES)
def test_around_treats_malformed_details_as_unreadable(case: str) -> None:
    runs = [_run("automation", "a", "r1", "2026-11-13T04:18:08+00:00")]
    result = asyncio.run(svc(FakeHA(runs=runs, details={"r1": malformed(GOOD)[case]})).around(
        parse_when("2026-11-13 14:18:09", BNE), timedelta(seconds=30), ("automation",)))
    assert result.chains == []
    assert [r["run_id"] for r in result.unreadable] == ["r1"]


@pytest.mark.parametrize("case", CASES)
def test_get_refuses_a_malformed_detail(case: str) -> None:
    rid = GOOD_GET["run_id"]
    with pytest.raises(ValidationError):
        asyncio.run(svc(FakeHA(details={rid: malformed(GOOD_GET)[case]})).get(
            "automation.office_ble_away_signal", run_id=rid))


def test_around_dedupes_domains() -> None:
    runs = [_run("automation", "a", "r1", "2026-11-13T04:18:08+00:00")]
    fake = FakeHA(runs=runs, details={"r1": _detail(runs[0], "C1")})
    result = asyncio.run(svc(fake).around(parse_when("2026-11-13 14:18:09", BNE), timedelta(seconds=30),
                                          ("automation", "automation")))
    assert result.shown == 1
    assert sum(m == "trace/get" for m, _ in fake.calls) == 1


def test_around_flags_items_whose_history_starts_after_the_window() -> None:
    busy = [_run("automation", "busy", f"b{i}", f"2026-11-13T04:2{i}:00+00:00") for i in range(5)]
    idle = [_run("automation", "idle", "i0", "2026-11-12T00:00:00+00:00")]
    few = [_run("automation", "few", f"f{i}", f"2026-11-13T04:2{i}:00+00:00") for i in range(2)]
    result = asyncio.run(svc(FakeHA(runs=busy + idle + few, details={})).around(
        parse_when("2026-11-13 14:18:09", BNE), timedelta(seconds=30), ("automation",)))
    assert [m["target"] for m in result.possibly_missing] == ["automation.busy"]


def test_around_refuses_a_window_that_is_too_busy() -> None:
    runs = [_run("automation", "a", f"r{i}", "2026-11-13T04:18:09+00:00") for i in range(MAX_AROUND_RUNS + 1)]
    with pytest.raises(ValidationError):
        asyncio.run(svc(FakeHA(runs=runs, details={})).around(
            parse_when("2026-11-13 14:18:09", BNE), timedelta(seconds=30), ("automation",)))


# --- CLI ------------------------------------------------------------------------

class _Ctx:
    def __init__(self, fake: FakeHA) -> None:
        self.fake = fake

    async def __aenter__(self) -> FakeHA:
        return self.fake

    async def __aexit__(self, *args: Any) -> None:
        return None


def flat(text: str) -> str:
    """Output with Rich's line wrapping undone."""
    return " ".join(text.split())


def invoke(fake: FakeHA, args: list[str]) -> Any:
    with patch("ha_cli.domains.traces.cli.HAClient", lambda *a, **k: _Ctx(fake)), \
         patch("ha_cli.domains.traces.cli.get_client_config", lambda *a, **k: ("http://ha", "tok")):
        return runner.invoke(app, args)


def test_cli_list_unknown_target_exits_3() -> None:
    result = invoke(FakeHA(), ["list", "automation.typo"])
    assert result.exit_code == 3
    assert "No automation" in result.output


def test_cli_show_json_is_the_detail() -> None:
    result = invoke(FakeHA(), ["show", "automation.office_ble_away_signal", "3e31a971938a313193e7b25ac641d64b",
                               "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["trigger_detail"]["for_seconds"] == 120.0
    assert data["context_id"] == FIX["get_ble"]["context"]["id"]


def test_cli_show_refuses_run_id_and_at_together() -> None:
    result = invoke(FakeHA(), ["show", "automation.office_ble_away_signal", "x", "--at", "14:18"])
    assert result.exit_code == 1


def test_cli_around_hides_condition_stops_unless_all() -> None:
    acted = _run("automation", "a", "r1", "2026-11-13T04:18:08+00:00")
    stopped = _run("automation", "tick", "r2", "2026-11-13T04:18:09+00:00", execution="failed_conditions")
    fake = FakeHA(runs=[acted, stopped], details={"r1": _detail(acted, "C1"), "r2": _detail(stopped, "C2")})
    args = ["around", "2026-11-13 14:18:09", "--window", "30s", "--domain", "automation", "--json"]
    hidden = json.loads(invoke(fake, args).output)
    assert [[d["run_id"] for d in c] for c in hidden["chains"]] == [["r1"]]
    assert hidden["hidden_failed_conditions"] == 1
    assert hidden["complete"] is None
    shown = json.loads(invoke(copy.deepcopy(fake), [*args, "--all"]).output)
    assert len(shown["chains"]) == 2
    assert shown["hidden_failed_conditions"] == 0


def test_cli_around_says_why_the_window_is_empty() -> None:
    stopped = _run("automation", "tick", "r2", "2026-11-13T04:18:09+00:00", execution="failed_conditions")
    gone = _run("automation", "a", "r3", "2026-11-13T04:18:10+00:00")
    args = ["around", "2026-11-13 14:18:09", "--window", "30s", "--domain", "automation"]
    only_hidden = flat(invoke(FakeHA(runs=[stopped], details={"r2": _detail(stopped, "C2")}), args).output)
    assert "Only runs that stopped at their conditions" in only_hidden
    unread = flat(invoke(FakeHA(runs=[gone], details={}), args).output)
    assert "none could be read" in unread
    assert "rolled off while reading" in unread
    nothing = flat(invoke(FakeHA(runs=[], details={}), args).output)
    assert "No stored runs start in this window" in nothing


def test_cli_around_mixed_hidden_and_unreadable_does_not_say_only() -> None:
    stopped = _run("automation", "tick", "r2", "2026-11-13T04:18:09+00:00", execution="failed_conditions")
    gone = _run("automation", "a", "r3", "2026-11-13T04:18:10+00:00")
    out = flat(invoke(FakeHA(runs=[stopped, gone], details={"r2": _detail(stopped, "C2")}),
                      ["around", "2026-11-13 14:18:09", "--window", "30s", "--domain", "automation"]).output)
    assert "Only runs" not in out
    assert "1 run(s) stopped at their conditions" in out
    assert "1 couldn't be read" in out


def test_cli_around_labels_group_members_and_dates_another_day() -> None:
    head = _run("automation", "a", "r1", "2026-11-12T04:18:08+00:00")
    same = _run("script", "s", "r2", "2026-11-12T04:18:09+00:00")
    caused = _run("automation", "b", "r3", "2026-11-12T04:18:10+00:00")
    fake = FakeHA(runs=[head, same, caused], details={
        "r1": _detail(head, "C1"), "r2": _detail(same, "C1"), "r3": _detail(caused, "C3", "C1")})
    out = flat(invoke(fake, ["around", "2026-11-12 14:18:09", "--window", "30s", "--brief"]).output)
    assert "context group of 3 runs" in out
    assert "↳ same context 2026-11-12 14:18:09.000" in out
    assert "⇢ caused by the group 2026-11-12 14:18:10.000" in out


def test_cli_show_survives_bad_trigger_last_changed() -> None:
    detail = copy.deepcopy(FIX["get_ble"])
    for steps in detail["trace"].values():
        for st in steps:
            trig = (st.get("changed_variables") or {}).get("trigger")
            if trig:
                trig["to_state"]["last_changed"] = "yesterday-ish"
                trig["from_state"]["last_changed"] = "2026-11-13T01:28:44"   # no offset
    result = invoke(FakeHA(details={detail["run_id"]: detail}),
                    ["show", "automation.office_ble_away_signal", detail["run_id"]])
    assert result.exit_code == 0, result.output
    assert "since -" in flat(result.output)


def test_cli_show_labels_utc_when_zone_unknown() -> None:
    out = flat(invoke(FakeHA(tz="Not/AZone"), ["show", "automation.office_ble_away_signal",
                                               "3e31a971938a313193e7b25ac641d64b"]).output)
    assert "Times in UTC: HA's time zone couldn't be read" in out


def test_cli_show_at_reports_distance() -> None:
    a, b = FIX["list_ble"]
    fake = FakeHA(details={a["run_id"]: _detail(a, "c1"), b["run_id"]: _detail(b, "c2")})
    out = json.loads(invoke(fake, ["show", "automation.office_ble_away_signal", "--at", "2026-11-13 09:00",
                                   "--json"]).output)
    assert out["run_id"] == "3e31a971938a313193e7b25ac641d64b"
    assert out["distance_seconds"] > 5 * 3600
    far = invoke(fake, ["show", "automation.office_ble_away_signal", "--at", "2026-11-13 09:00"]).output
    assert "may have rolled off" in flat(far)


def test_cli_list_without_ha_zone_says_utc() -> None:
    out = invoke(FakeHA(tz="Not/AZone"), ["list", "automation.office_ble_away_signal"]).output
    assert "HA's time zone couldn't be read" in flat(out)
    refused = invoke(FakeHA(tz="Not/AZone"), ["list", "automation.office_ble_away_signal", "--since", "14:00"])
    assert refused.exit_code == 1


@pytest.mark.parametrize("args", [
    ["show", "automation.office_ble_away_signal", "x", "--at", "14:18", "--porcelain"],
    ["around", "14:18", "--domain", "light", "--porcelain"],
])
def test_cli_early_errors_are_structured_under_porcelain(args: list[str]) -> None:
    result = invoke(FakeHA(), args)
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert body["status"] == "error"
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_cli_around_rejects_other_domains() -> None:
    assert invoke(FakeHA(), ["around", "14:18", "--domain", "light"]).exit_code == 1


def test_trace_run_without_timestamps() -> None:
    run = TraceRun.from_dict({"run_id": "x", "timestamp": {}})
    assert run.start is None
    assert run.duration is None

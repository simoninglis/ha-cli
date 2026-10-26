"""Tests for the HACS domain (service + CLI) against a fake HACS websocket API."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.common.exceptions import NotFoundError, ValidationError, WebSocketError
from ha_cli.domains.hacs.cli import app
from ha_cli.domains.hacs.models import (
    NO_RESOURCE,
    UNKNOWN_RESOURCE,
    UNMAPPED,
    UNTRACKED,
    HacsRepository,
    LovelaceResource,
)
from ha_cli.domains.hacs.service import HacsService, _owner_of

runner = CliRunner()


def repo(rid: str, name: str, installed: bool, category: str = "plugin", path: str | None = None,
         version: str = "v1.0.0", available: str | None = None) -> dict[str, Any]:
    directory = name.split("/")[1]
    return {
        "id": rid,
        "full_name": name,
        "category": category,
        "installed": installed,
        "local_path": path or (
            f"/config/www/community/{directory}" if category == "plugin" else f"/config/custom_components/{directory}"
        ),
        "installed_version": version if installed else "",
        "available_version": available or version,
        "pending_upgrade": bool(available and available != version and installed),
    }


def res(url: str, rid: str = "r") -> dict[str, Any]:
    return {"id": rid, "url": url, "type": "module"}


class FakeHA:
    """Just enough of HA + HACS 2.x: repositories/list, lovelace/resources, repository/remove."""

    def __init__(self, repos: list[dict], resources: list[dict] | None, remove_works: bool = True,
                 resources_fail_after_remove: bool = False) -> None:
        self.repos = repos
        self.resources = resources
        self.remove_works = remove_works
        self.resources_fail_after_remove = resources_fail_after_remove
        self.calls: list[tuple[str, dict]] = []

    async def ws(self, msg_type: str, **kwargs: Any) -> Any:
        self.calls.append((msg_type, kwargs))
        if msg_type == "hacs/repositories/list":
            return [dict(r) if isinstance(r, dict) else r for r in self.repos]
        if msg_type == "lovelace/resources":
            if self.resources is None or (self.resources_fail_after_remove and self.removed):
                raise WebSocketError("unknown_error: resources are in YAML mode")
            return [dict(r) if isinstance(r, dict) else r for r in self.resources]
        if msg_type == "hacs/repository/remove":
            target = next(r for r in self.repos if r["id"] == kwargs["repository"])
            if self.remove_works:
                target["installed"] = False
                directory = target["local_path"].rsplit("/", 1)[-1]
                self.resources = [r for r in self.resources or [] if f"/hacsfiles/{directory}/" not in r["url"]]
            return {}
        raise AssertionError(f"unexpected websocket call {msg_type}")

    def client(self) -> MagicMock:
        c = MagicMock()
        c.url = "http://t:8123"  # what invoke()'s patched get_client_config returns
        c._ws_call = AsyncMock(side_effect=self.ws)
        c.__aenter__ = AsyncMock(return_value=c)
        c.__aexit__ = AsyncMock(return_value=None)
        return c

    @property
    def removed(self) -> list[str]:
        return [k["repository"] for t, k in self.calls if t == "hacs/repository/remove"]


# The live layout that prompted this (2026-10-26): mushroom on disk and loaded, HACS says not installed
LIVE_LIKE = [
    repo("190927524", "thomasloven/lovelace-card-mod", True, version="v4.2.1"),
    repo("444350375", "piitaya/lovelace-mushroom", False),
    repo("172733314", "hacs/integration", True, category="integration", path="/config/custom_components/hacs"),
    repo("228579545", "sebr/bhyve-home-assistant", True, category="integration", path="/config/custom_components/bhyve"),
    repo("555", "custom-cards/bom-radar-card", False),
]
LIVE_RESOURCES = [
    res("/hacsfiles/lovelace-card-mod/card-mod.js?hacstag=190927524421", "a"),
    res("/hacsfiles/lovelace-mushroom/mushroom.js?hacstag=444350375508", "b"),
    res("/hacsfiles/simple-clock-card/simple-clock-card.js?hacstag=34193126618", "c"),
    res("/local/my-own-card.js", "d"),
]


async def run_audit(repos, resources):
    fake = FakeHA(repos, resources)
    return await HacsService(fake.client()).audit()


class TestModels:
    def test_resource_dir_and_hacstag(self):
        r = LovelaceResource.from_dict(res("/hacsfiles/lovelace-mushroom/mushroom.js?hacstag=444350375508"))
        assert r.hacsfiles_dir == "lovelace-mushroom"
        assert r.hacstag == "444350375508"

    def test_non_hacs_resource_has_no_dir(self):
        assert LovelaceResource.from_dict(res("/local/x.js")).hacsfiles_dir is None
        assert LovelaceResource.from_dict(res("https://cdn.example/hacsfiles/x/y.js")).hacsfiles_dir is None

    @pytest.mark.parametrize("url,expected", [
        ("/hacsfiles/card/card.js", "card"),
        ("http://ha:8123/hacsfiles/card/card.js", "card"),
        ("HTTP://HA:8123/hacsfiles/card/card.js?hacstag=1", "card"),
        ("//ha:8123/hacsfiles/card/card.js", "card"),
        ("https://ha:8123/hacsfiles/card/card.js", None),  # other scheme: other origin
        ("http://ha:9999/hacsfiles/card/card.js", None),
        ("http://cdn.example/hacsfiles/card/card.js", None),
        ("/local/card.js", None),
    ])
    def test_resource_dir_resolves_against_the_ha_origin(self, url, expected):
        assert LovelaceResource.from_dict(res(url), "http://ha:8123").hacsfiles_dir == expected

    def test_integration_has_no_hacsfiles_dir(self):
        assert HacsRepository.from_dict(LIVE_LIKE[2]).hacsfiles_dir is None

    def test_installed_must_be_true_not_truthy(self):
        assert HacsRepository.from_dict({**LIVE_LIKE[0], "installed": "false"}).installed is False


class TestAudit:
    @pytest.mark.asyncio
    async def test_untracked_card_in_use_is_an_error(self):
        result = await run_audit(LIVE_LIKE, LIVE_RESOURCES)
        untracked = [f for f in result.findings if f.kind == UNTRACKED]
        assert [f.repository for f in untracked] == ["piitaya/lovelace-mushroom"]
        assert untracked[0].severity == "error"
        assert result.findings[0].kind == UNTRACKED  # errors sort first
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_unowned_hacsfiles_resource_is_flagged(self):
        result = await run_audit(LIVE_LIKE, LIVE_RESOURCES)
        unknown = [f for f in result.findings if f.kind == UNKNOWN_RESOURCE]
        assert [f.resource_url for f in unknown] == [LIVE_RESOURCES[2]["url"]]

    @pytest.mark.asyncio
    async def test_non_hacs_resources_are_ignored(self):
        result = await run_audit(LIVE_LIKE, LIVE_RESOURCES)
        assert not any("/local/" in (f.resource_url or "") for f in result.findings)

    @pytest.mark.asyncio
    async def test_installed_card_without_resource(self):
        result = await run_audit(LIVE_LIKE, [LIVE_RESOURCES[1]])
        missing = [f for f in result.findings if f.kind == NO_RESOURCE]
        assert [f.repository for f in missing] == ["thomasloven/lovelace-card-mod"]

    @pytest.mark.asyncio
    async def test_integrations_never_need_resources(self):
        result = await run_audit(LIVE_LIKE, [])
        assert not any(f.repository == "sebr/bhyve-home-assistant" for f in result.findings)

    @pytest.mark.asyncio
    async def test_installed_card_without_usable_path_is_reported(self):
        """Round-5 probe: an unmappable installed card made a clean audit."""
        repos = [{**repo("9", "x/card", True), "local_path": ""}]
        result = await run_audit(repos, [])
        assert [f.kind for f in result.findings] == [UNMAPPED]
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_clean(self):
        result = await run_audit([LIVE_LIKE[0]], [LIVE_RESOURCES[0]])
        assert result.findings == []
        assert result.exit_code == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [None, {"id": "1"}, {**repo("1", "a/b", True), "installed": "yes"},
                                     {**repo("1", "a/b", True), "full_name": ""}])
    async def test_malformed_repository_is_an_error(self, bad):
        with pytest.raises(ValidationError, match="Malformed HACS repository"):
            await run_audit(LIVE_LIKE + [bad], LIVE_RESOURCES)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [None, {"id": "x"}, {"url": ""}, {"url": 5}])
    async def test_malformed_resource_is_an_error(self, bad):
        with pytest.raises(ValidationError, match="Malformed dashboard resource"):
            await run_audit(LIVE_LIKE, LIVE_RESOURCES + [bad])

    def test_malformed_after_remove_is_unverified(self):
        fake = FakeHA([dict(r) for r in LIVE_LIKE], LIVE_RESOURCES)
        original_ws = fake.ws

        async def ws(msg_type, **kwargs):
            result = await original_ws(msg_type, **kwargs)
            if msg_type == "lovelace/resources" and fake.removed:
                return [None]
            return result

        fake.ws = ws
        result = invoke(fake, ["remove", "custom-cards/bom-radar-card", "--force"])
        assert result.exit_code == 3, result.output
        assert "could not verify" in " ".join(result.output.split())

    @pytest.mark.asyncio
    async def test_unreadable_resources_is_an_error_not_a_clean_audit(self):
        with pytest.raises(WebSocketError):
            await run_audit(LIVE_LIKE, None)

    def test_hacstag_picks_the_owner_among_forks(self):
        fork = HacsRepository.from_dict(repo("999", "someone/lovelace-mushroom", True))
        orig = HacsRepository.from_dict(repo("444350375", "piitaya/lovelace-mushroom", False))
        resource = LovelaceResource.from_dict(LIVE_RESOURCES[1])
        assert _owner_of(resource, [fork, orig]) is orig


class TestFindRepository:
    def test_by_full_name_case_insensitive_and_id(self):
        repos = [HacsRepository.from_dict(r) for r in LIVE_LIKE]
        assert HacsService.find_repository(repos, "Piitaya/Lovelace-Mushroom").id == "444350375"
        assert HacsService.find_repository(repos, "444350375").full_name == "piitaya/lovelace-mushroom"

    def test_no_partial_match_for_a_destructive_target(self):
        repos = [HacsRepository.from_dict(r) for r in LIVE_LIKE]
        with pytest.raises(NotFoundError, match="lovelace-card-mod"):
            HacsService.find_repository(repos, "card-mod")


def invoke(fake: FakeHA, args: list[str], input: str | None = None):
    with patch("ha_cli.domains.hacs.cli.get_client_config", return_value=("http://t:8123", "tok")), \
         patch("ha_cli.domains.hacs.cli.HAClient", return_value=fake.client()):
        return runner.invoke(app, args, input=input)


class TestCli:
    def test_list_shows_installed_only(self):
        result = invoke(FakeHA(LIVE_LIKE, LIVE_RESOURCES), ["list", "--json"])
        assert result.exit_code == 0
        names = [r["full_name"] for r in json.loads(result.output)]
        assert "piitaya/lovelace-mushroom" not in names
        assert "thomasloven/lovelace-card-mod" in names

    def test_list_updates_filter(self):
        repos = LIVE_LIKE + [repo("7", "a/b-card", True, version="1.0", available="1.1")]
        result = invoke(FakeHA(repos, []), ["list", "--updates", "--json"])
        assert [r["full_name"] for r in json.loads(result.output)] == ["a/b-card"]

    def test_audit_exit_codes(self):
        assert invoke(FakeHA(LIVE_LIKE, LIVE_RESOURCES), ["audit"]).exit_code == 1
        clean = invoke(FakeHA([LIVE_LIKE[0]], [LIVE_RESOURCES[0]]), ["audit"])
        assert clean.exit_code == 0, clean.output

    def test_audit_porcelain(self):
        result = invoke(FakeHA(LIVE_LIKE, LIVE_RESOURCES), ["audit", "--porcelain"])
        data = json.loads(result.output)["data"]
        assert {f["kind"] for f in data["findings"]} == {UNTRACKED, UNKNOWN_RESOURCE}

    def test_remove_confirms_and_warns_about_untracked_card_in_use(self):
        fake = FakeHA(LIVE_LIKE, LIVE_RESOURCES)
        result = invoke(fake, ["remove", "piitaya/lovelace-mushroom"], input="n\n")
        output = " ".join(result.output.split())
        assert "NOT tracked" in output
        assert "still load it" in output
        assert "/config/www/community/lovelace-mushroom" in output
        assert "Cancelled" in result.output
        assert fake.removed == []

    def test_remove_confirmed_and_verified(self):
        fake = FakeHA(LIVE_LIKE, LIVE_RESOURCES + [res("/hacsfiles/bom-radar-card/bom-radar-card.js?hacstag=555300", "z")])
        result = invoke(fake, ["remove", "custom-cards/bom-radar-card"], input="y\n")
        assert result.exit_code == 0, result.output
        assert fake.removed == ["555"]
        assert "verified" in result.output

    def test_remove_that_leaves_things_behind_fails(self):
        fake = FakeHA([dict(r) for r in LIVE_LIKE], LIVE_RESOURCES, remove_works=False)
        result = invoke(fake, ["remove", "thomasloven/lovelace-card-mod", "--force"])
        output = " ".join(result.output.split())  # rich wraps long lines
        assert result.exit_code == 3, output
        assert "incomplete" in output
        assert "still lists it as installed" in output
        assert "resource still registered" in output

    def test_audit_that_cannot_read_resources_exits_2(self):
        result = invoke(FakeHA(LIVE_LIKE, None), ["audit"])
        assert result.exit_code == 2, result.output

    def test_remove_stops_if_resources_unreadable_beforehand(self):
        fake = FakeHA(LIVE_LIKE, None)
        result = invoke(fake, ["remove", "custom-cards/bom-radar-card", "--force"])
        assert result.exit_code != 0
        assert fake.removed == []

    def test_absolute_same_origin_resource_left_behind_fails_verification(self):
        """Round-5 probe: an absolute URL on the HA origin was ignored, so this passed."""
        resources = [res("http://t:8123/hacsfiles/lovelace-card-mod/card-mod.js", "abs")]
        fake = FakeHA([dict(r) for r in LIVE_LIKE], resources, remove_works=False)
        result = invoke(fake, ["remove", "thomasloven/lovelace-card-mod", "--force"])
        output = " ".join(result.output.split())
        assert result.exit_code == 3, output
        assert "resource still registered: http://t:8123/hacsfiles/lovelace-card-mod" in output

    def test_remove_unverifiable_afterwards_is_not_success(self):
        fake = FakeHA([dict(r) for r in LIVE_LIKE], LIVE_RESOURCES, resources_fail_after_remove=True)
        result = invoke(fake, ["remove", "custom-cards/bom-radar-card", "--force"])
        output = " ".join(result.output.split())
        assert result.exit_code == 3, output
        assert "could not verify" in output
        assert "verified:" not in output

    def test_porcelain_requires_force(self):
        fake = FakeHA(LIVE_LIKE, LIVE_RESOURCES)
        result = invoke(fake, ["remove", "custom-cards/bom-radar-card", "--porcelain"])
        assert result.exit_code == 1
        assert fake.removed == []
        assert fake.calls == []  # refused before touching HA

    def test_porcelain_with_force(self):
        fake = FakeHA(LIVE_LIKE, LIVE_RESOURCES)
        result = invoke(fake, ["remove", "custom-cards/bom-radar-card", "--porcelain", "--force"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["metadata"]["verified"] is True

    @pytest.mark.parametrize("path", ["", "/config/custom_components/odd"])
    def test_card_without_hacsfiles_mapping_is_not_removed(self, path):
        """Round-3 probe: no local path -> no resource mapping -> a vacuous check."""
        repos = [dict(r) for r in LIVE_LIKE] + [{**repo("77", "x/card", True), "local_path": path}]
        fake = FakeHA(repos, LIVE_RESOURCES + [res("/hacsfiles/card/card.js", "q")])
        result = invoke(fake, ["remove", "x/card", "--force"])
        assert result.exit_code == 1, result.output
        assert "can't tell which dashboard resources" in " ".join(result.output.split())
        assert fake.removed == []

    @pytest.mark.asyncio
    async def test_verify_without_mapping_is_unverified(self):
        fake = FakeHA([{**repo("77", "x/card", False), "local_path": ""}], [])
        problems = await HacsService(fake.client()).verify_removed(
            HacsRepository.from_dict({**repo("77", "x/card", False), "local_path": ""})
        )
        assert problems and "could not verify" in problems[0]

    def test_never_removes_hacs_itself(self):
        fake = FakeHA(LIVE_LIKE, LIVE_RESOURCES)
        result = invoke(fake, ["remove", "hacs/integration", "--force"])
        assert result.exit_code == 1
        assert fake.removed == []

    def test_unknown_repository(self):
        fake = FakeHA(LIVE_LIKE, LIVE_RESOURCES)
        result = invoke(fake, ["remove", "nobody/nothing", "--force"])
        assert result.exit_code == 1
        assert fake.removed == []

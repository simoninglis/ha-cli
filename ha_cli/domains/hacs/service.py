"""Service layer for the HACS domain (HACS 2.x websocket API)."""

from typing import Any

from ...common.client import HAClient
from ...common.exceptions import HAAutomationError, NotFoundError, ValidationError, WebSocketError
from .models import (
    NO_RESOURCE,
    UNKNOWN_RESOURCE,
    UNMAPPED,
    UNTRACKED,
    HacsAuditResult,
    HacsFinding,
    HacsRepository,
    LovelaceResource,
)


class HacsService:
    """Read and manage HACS repositories.

    Needs an admin token: HACS's websocket commands are admin-only.
    """

    def __init__(self, client: HAClient) -> None:
        """Initialize HACS service.

        Args:
            client: Home Assistant client
        """
        self.client = client

    async def list_repositories(self) -> list[HacsRepository]:
        """Every repository HACS knows about (thousands; most not installed).

        Raises:
            ValidationError: If HACS isn't loaded or the response is malformed
        """
        try:
            result = await self.client._ws_call("hacs/repositories/list")
        except WebSocketError as e:
            if "unknown_command" in str(e):
                raise ValidationError("HACS is not installed or not loaded in Home Assistant") from e
            raise
        if not isinstance(result, list):
            raise ValidationError(f"Unexpected hacs/repositories/list response: {type(result).__name__}")
        # Strict: a malformed item dropped or defaulted here would make an audit or a
        # removal check pass while checking nothing
        for i, item in enumerate(result):
            if not isinstance(item, dict) or not all(
                isinstance(item.get(k), str) and item.get(k) for k in ("full_name", "category")
            ) or not item.get("id") or not isinstance(item.get("installed"), bool):
                raise ValidationError(f"Malformed HACS repository at index {i} in hacs/repositories/list")
        repos = [HacsRepository.from_dict(r) for r in result]
        return sorted(repos, key=lambda r: (r.category, r.full_name.lower()))

    async def list_resources(self) -> list[LovelaceResource]:
        """Dashboard resources (lovelace/resources answers in storage and YAML mode).

        Raises:
            WebSocketError / ValidationError: If they can't be read. Never an empty
                list in place of an error: an unread resource list would make an
                audit or a removal check pass while checking nothing.
        """
        result = await self.client._ws_call("lovelace/resources")
        if not isinstance(result, list):
            raise ValidationError(f"Unexpected lovelace/resources response: {type(result).__name__}")
        for i, item in enumerate(result):
            if not isinstance(item, dict) or not isinstance(item.get("url"), str) or not item["url"]:
                raise ValidationError(f"Malformed dashboard resource at index {i} in lovelace/resources")
        ha_url = getattr(self.client, "url", None)
        return [LovelaceResource.from_dict(r, ha_url if isinstance(ha_url, str) else None) for r in result]

    @staticmethod
    def find_repository(repos: list[HacsRepository], ident: str) -> HacsRepository:
        """Match by repository id or exact owner/name (case-insensitive).

        Raises:
            NotFoundError: If nothing matches; suggests installed near-misses
        """
        needle = ident.strip()
        for repo in repos:
            if repo.id == needle or repo.full_name.lower() == needle.lower():
                return repo
        near = [r.full_name for r in repos if r.installed and needle.lower() in r.full_name.lower()]
        hint = f" Installed matches: {', '.join(near[:5])}" if near else ""
        raise NotFoundError(f"No HACS repository '{ident}' (use owner/name or the repository id).{hint}")

    @staticmethod
    def resources_for(repo: HacsRepository, resources: list[LovelaceResource]) -> list[LovelaceResource]:
        """Dashboard resources served from this plugin's /hacsfiles/<dir>/."""
        directory = repo.hacsfiles_dir
        if not directory:
            return []
        return [r for r in resources if r.hacsfiles_dir == directory]

    async def audit(self) -> HacsAuditResult:
        """Cross-check HACS's install records against the dashboard resources.

        Catches the state where HACS has lost track of a card (`installed: false`)
        while its files and resource are still live: no update notices, and
        `hacs remove` on it deletes a card the dashboards depend on.
        """
        repos = await self.list_repositories()
        resources = await self.list_resources()
        installed = [r for r in repos if r.installed]
        findings: list[HacsFinding] = []

        plugins_by_dir: dict[str, list[HacsRepository]] = {}
        for repo in repos:
            if repo.hacsfiles_dir:
                plugins_by_dir.setdefault(repo.hacsfiles_dir, []).append(repo)

        for res in resources:
            directory = res.hacsfiles_dir
            if not directory:
                continue  # not served by HACS (/local/..., a CDN): not ours to judge
            owner = _owner_of(res, plugins_by_dir.get(directory, []))
            if owner is None:
                findings.append(HacsFinding(
                    kind=UNKNOWN_RESOURCE,
                    severity="warning",
                    message=(
                        f"Resource {res.url} is served from /hacsfiles/{directory}/ but no "
                        "HACS repository owns that directory"
                    ),
                    resource_url=res.url,
                ))
            elif not owner.installed:
                findings.append(HacsFinding(
                    kind=UNTRACKED,
                    severity="error",
                    message=(
                        f"{owner.full_name} is loaded by the dashboards but HACS has it as not "
                        "installed: no update notices, and removing it would delete a card in "
                        "use. Re-download it in HACS to adopt it."
                    ),
                    repository=owner.full_name,
                    repository_id=owner.id,
                    resource_url=res.url,
                ))

        for repo in installed:
            if repo.category == "plugin" and not repo.hacsfiles_dir:
                findings.append(HacsFinding(
                    kind=UNMAPPED,
                    severity="warning",
                    message=(
                        f"{repo.full_name} is an installed card but HACS reports no usable local "
                        f"path ({repo.local_path or 'empty'}): its dashboard resources can't be checked"
                    ),
                    repository=repo.full_name,
                    repository_id=repo.id,
                ))
            elif repo.hacsfiles_dir and not self.resources_for(repo, resources):
                findings.append(HacsFinding(
                    kind=NO_RESOURCE,
                    severity="warning",
                    message=(
                        f"{repo.full_name} is installed but no dashboard resource loads "
                        f"/hacsfiles/{repo.hacsfiles_dir}/: its cards won't render"
                    ),
                    repository=repo.full_name,
                    repository_id=repo.id,
                ))

        findings.sort(key=lambda f: (f.severity != "error", f.kind, f.repository or f.resource_url or ""))
        return HacsAuditResult(
            findings=findings,
            installed_count=len(installed),
            resource_count=len(resources),
        )

    async def remove(self, repo: HacsRepository) -> None:
        """Uninstall: HACS deletes the repository's local files and, for a plugin,
        its dashboard resource. It does this even when its records say the repository
        isn't installed.
        """
        await self.client._ws_call("hacs/repository/remove", repository=repo.id)

    @staticmethod
    def removal_blocker(repo: HacsRepository) -> str | None:
        """Why a removal couldn't be checked, or None if it can be.

        A card's resources are found through its /hacsfiles/<dir>; without that
        mapping the post-removal check would find nothing and pass vacuously.
        """
        if repo.category == "plugin" and not repo.hacsfiles_dir:
            return (
                f"HACS reports no usable local path for card {repo.full_name} "
                f"({repo.local_path or 'empty'}): can't tell which dashboard resources it owns"
            )
        return None

    async def verify_removed(self, repo: HacsRepository) -> list[str]:
        """What's left after a removal; empty only when both checks ran and passed."""
        blocker = self.removal_blocker(repo)
        if blocker:
            return [f"could not verify the removal ({blocker})"]
        problems: list[str] = []
        try:
            repos = await self.list_repositories()
            resources = await self.list_resources()
        except HAAutomationError as e:
            return [f"could not verify the removal ({e.message})"]
        current = next((r for r in repos if r.id == repo.id), None)
        if current is not None and current.installed:
            problems.append("HACS still lists it as installed")
        left = self.resources_for(repo, resources)
        problems.extend(f"dashboard resource still registered: {r.url}" for r in left)
        return problems


def _owner_of(resource: LovelaceResource, candidates: list[HacsRepository]) -> HacsRepository | None:
    """The repository that owns a /hacsfiles/<dir>/ resource.

    The hacstag query parameter starts with the repository id, which settles it when
    several repositories (forks) share a directory name.
    """
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    tag = resource.hacstag
    tagged = [r for r in candidates if r.id and tag.startswith(r.id)]
    if tagged:
        return max(tagged, key=lambda r: len(r.id))
    installed = [r for r in candidates if r.installed]
    return installed[0] if installed else candidates[0]


def summarize(repos: list[HacsRepository]) -> dict[str, Any]:
    """Counts for list output."""
    installed = [r for r in repos if r.installed]
    return {
        "installed_count": len(installed),
        "pending_upgrade_count": sum(1 for r in installed if r.pending_upgrade),
        "known_count": len(repos),
    }

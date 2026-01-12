"""Service layer for repairs domain."""

from typing import Any, cast

from ...common.client import HAClient
from ...common.exceptions import NotFoundError
from .models import Repair


class RepairService:
    """Service for retrieving Home Assistant repair notices.

    Repairs represent system issues requiring user intervention, surfaced via
    the Repairs dashboard (Settings > System > Repairs).
    """

    def __init__(self, client: HAClient) -> None:
        """Initialize repair service.

        Args:
            client: Home Assistant client
        """
        self.client = client

    async def list_repairs(self, include_ignored: bool = False) -> list[Repair]:
        """Get all repairs from Home Assistant.

        Args:
            include_ignored: Include dismissed/ignored repairs

        Returns:
            List of repairs sorted by severity (critical > error > warning)
        """
        result = await self.client._ws_call("repairs/list_issues")
        result_dict = cast(dict[str, Any], result)
        issues = result_dict.get("issues", [])

        repairs = []
        for item in issues:
            repair = Repair.from_dict(item)
            # Filter out inactive/ignored unless requested
            if repair.active or include_ignored:
                repairs.append(repair)

        # Sort by severity (critical first), then by domain, then by issue_id
        return sorted(
            repairs,
            key=lambda r: (r.severity_order, r.domain.lower(), r.issue_id.lower()),
        )

    async def get_repair(self, domain: str, issue_id: str) -> Repair | None:
        """Get a specific repair by domain and issue_id.

        Args:
            domain: Integration domain (e.g., "zwave_js")
            issue_id: Unique issue identifier

        Returns:
            Repair if found, None otherwise
        """
        repairs = await self.list_repairs(include_ignored=True)
        for repair in repairs:
            if repair.domain == domain and repair.issue_id == issue_id:
                return repair
        return None

    async def ignore_repair(self, domain: str, issue_id: str) -> None:
        """Mark a repair as ignored/dismissed.

        Args:
            domain: Integration domain
            issue_id: Issue identifier

        Raises:
            NotFoundError: If repair not found
        """
        # Verify repair exists first
        repair = await self.get_repair(domain, issue_id)
        if not repair:
            raise NotFoundError(f"Repair not found: {domain}/{issue_id}")

        await self.client._ws_call(
            "repairs/ignore_issue",
            domain=domain,
            issue_id=issue_id,
            ignore=True,
        )

    async def unignore_repair(self, domain: str, issue_id: str) -> None:
        """Unmark a repair as ignored/dismissed.

        Args:
            domain: Integration domain
            issue_id: Issue identifier

        Raises:
            NotFoundError: If repair not found
        """
        # Verify repair exists first
        repair = await self.get_repair(domain, issue_id)
        if not repair:
            raise NotFoundError(f"Repair not found: {domain}/{issue_id}")

        await self.client._ws_call(
            "repairs/ignore_issue",
            domain=domain,
            issue_id=issue_id,
            ignore=False,
        )

    async def get_summary(self) -> dict[str, Any]:
        """Get summary statistics about repairs.

        Returns:
            Dictionary with repair statistics
        """
        repairs = await self.list_repairs(include_ignored=False)

        # Count by severity
        critical_count = sum(1 for r in repairs if r.severity == "critical")
        error_count = sum(1 for r in repairs if r.severity == "error")
        warning_count = sum(1 for r in repairs if r.severity == "warning")

        # Count fixable (use 'is True' for type-strict counting)
        fixable_count = sum(1 for r in repairs if r.is_fixable is True)

        # Get unique domains
        domains = sorted({r.domain for r in repairs})

        return {
            "total_repairs": len(repairs),
            "critical_count": critical_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "fixable_count": fixable_count,
            "affected_domains": domains,
        }

"""Service layer for repairs domain."""

from typing import Any, cast

from ...common.client import HAClient
from ...common.exceptions import NotFoundError, ValidationError
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

        Raises:
            ValidationError: If response format is unexpected
        """
        result = await self.client._ws_call("repairs/list_issues")

        # Validate response shape
        if result is None:
            result = {}
        if not isinstance(result, dict):
            raise ValidationError(f"Unexpected response type: {type(result).__name__}")

        result_dict = cast(dict[str, Any], result)
        issues = result_dict.get("issues")

        # Handle missing or invalid issues field
        if issues is None:
            issues = []
        if not isinstance(issues, list):
            raise ValidationError(f"Unexpected issues type: {type(issues).__name__}")

        repairs = []
        for item in issues:
            # Validate each item is a dict before parsing
            if not isinstance(item, dict):
                continue  # Skip malformed entries gracefully
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

        Note:
            Matching is case-insensitive for user convenience.
        """
        repairs = await self.list_repairs(include_ignored=True)
        domain_lower = domain.lower()
        issue_id_lower = issue_id.lower()
        for repair in repairs:
            if repair.domain.lower() == domain_lower and repair.issue_id.lower() == issue_id_lower:
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

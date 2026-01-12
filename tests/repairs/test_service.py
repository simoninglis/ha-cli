"""Tests for repairs service layer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_cli.common.exceptions import NotFoundError, ValidationError
from ha_cli.domains.repairs.service import RepairService


@pytest.fixture()
def mock_client() -> MagicMock:
    """Create a mock HAClient."""
    client = MagicMock()
    client._ws_call = AsyncMock()
    return client


class TestListRepairs:
    """Tests for RepairService.list_repairs."""

    @pytest.mark.asyncio()
    async def test_list_repairs_success(self, mock_client: MagicMock) -> None:
        """Test listing repairs successfully."""
        mock_client._ws_call.return_value = {
            "issues": [
                {
                    "domain": "homeassistant",
                    "issue_id": "test_issue",
                    "severity": "warning",
                    "active": True,
                }
            ]
        }

        service = RepairService(mock_client)
        repairs = await service.list_repairs()

        assert len(repairs) == 1
        assert repairs[0].domain == "homeassistant"
        assert repairs[0].issue_id == "test_issue"

    @pytest.mark.asyncio()
    async def test_list_repairs_empty(self, mock_client: MagicMock) -> None:
        """Test listing repairs when none exist."""
        mock_client._ws_call.return_value = {"issues": []}

        service = RepairService(mock_client)
        repairs = await service.list_repairs()

        assert len(repairs) == 0

    @pytest.mark.asyncio()
    async def test_list_repairs_filters_inactive(self, mock_client: MagicMock) -> None:
        """Test that inactive repairs are filtered by default."""
        mock_client._ws_call.return_value = {
            "issues": [
                {"domain": "test", "issue_id": "active", "severity": "warning", "active": True},
                {"domain": "test", "issue_id": "inactive", "severity": "warning", "active": False},
            ]
        }

        service = RepairService(mock_client)
        repairs = await service.list_repairs(include_ignored=False)

        assert len(repairs) == 1
        assert repairs[0].issue_id == "active"

    @pytest.mark.asyncio()
    async def test_list_repairs_includes_ignored(self, mock_client: MagicMock) -> None:
        """Test that include_ignored returns inactive repairs."""
        mock_client._ws_call.return_value = {
            "issues": [
                {"domain": "test", "issue_id": "active", "severity": "warning", "active": True},
                {"domain": "test", "issue_id": "inactive", "severity": "warning", "active": False},
            ]
        }

        service = RepairService(mock_client)
        repairs = await service.list_repairs(include_ignored=True)

        assert len(repairs) == 2

    @pytest.mark.asyncio()
    async def test_list_repairs_sorting(self, mock_client: MagicMock) -> None:
        """Test that repairs are sorted by severity."""
        mock_client._ws_call.return_value = {
            "issues": [
                {"domain": "test", "issue_id": "warn", "severity": "warning", "active": True},
                {"domain": "test", "issue_id": "crit", "severity": "critical", "active": True},
                {"domain": "test", "issue_id": "err", "severity": "error", "active": True},
            ]
        }

        service = RepairService(mock_client)
        repairs = await service.list_repairs()

        assert repairs[0].severity == "critical"
        assert repairs[1].severity == "error"
        assert repairs[2].severity == "warning"

    @pytest.mark.asyncio()
    async def test_list_repairs_none_response(self, mock_client: MagicMock) -> None:
        """Test handling of None response."""
        mock_client._ws_call.return_value = None

        service = RepairService(mock_client)
        repairs = await service.list_repairs()

        assert len(repairs) == 0

    @pytest.mark.asyncio()
    async def test_list_repairs_missing_issues_field(self, mock_client: MagicMock) -> None:
        """Test handling of response without issues field."""
        mock_client._ws_call.return_value = {}

        service = RepairService(mock_client)
        repairs = await service.list_repairs()

        assert len(repairs) == 0

    @pytest.mark.asyncio()
    async def test_list_repairs_invalid_response_type(self, mock_client: MagicMock) -> None:
        """Test that invalid response type raises ValidationError."""
        mock_client._ws_call.return_value = "not a dict"

        service = RepairService(mock_client)
        with pytest.raises(ValidationError, match="Unexpected response type"):
            await service.list_repairs()

    @pytest.mark.asyncio()
    async def test_list_repairs_invalid_issues_type(self, mock_client: MagicMock) -> None:
        """Test that invalid issues type raises ValidationError."""
        mock_client._ws_call.return_value = {"issues": "not a list"}

        service = RepairService(mock_client)
        with pytest.raises(ValidationError, match="Unexpected issues type"):
            await service.list_repairs()

    @pytest.mark.asyncio()
    async def test_list_repairs_skips_non_dict_items(self, mock_client: MagicMock) -> None:
        """Test that non-dict items in issues list are skipped."""
        mock_client._ws_call.return_value = {
            "issues": [
                {"domain": "test", "issue_id": "valid", "severity": "warning", "active": True},
                "not a dict",
                None,
                123,
            ]
        }

        service = RepairService(mock_client)
        repairs = await service.list_repairs()

        assert len(repairs) == 1
        assert repairs[0].issue_id == "valid"


class TestGetRepair:
    """Tests for RepairService.get_repair."""

    @pytest.mark.asyncio()
    async def test_get_repair_found(self, mock_client: MagicMock) -> None:
        """Test getting a specific repair."""
        mock_client._ws_call.return_value = {
            "issues": [
                {"domain": "homeassistant", "issue_id": "test", "severity": "warning", "active": True}
            ]
        }

        service = RepairService(mock_client)
        repair = await service.get_repair("homeassistant", "test")

        assert repair is not None
        assert repair.domain == "homeassistant"
        assert repair.issue_id == "test"

    @pytest.mark.asyncio()
    async def test_get_repair_not_found(self, mock_client: MagicMock) -> None:
        """Test getting a repair that doesn't exist."""
        mock_client._ws_call.return_value = {"issues": []}

        service = RepairService(mock_client)
        repair = await service.get_repair("nonexistent", "repair")

        assert repair is None

    @pytest.mark.asyncio()
    async def test_get_repair_includes_inactive(self, mock_client: MagicMock) -> None:
        """Test that get_repair finds inactive repairs."""
        mock_client._ws_call.return_value = {
            "issues": [
                {"domain": "test", "issue_id": "ignored", "severity": "warning", "active": False}
            ]
        }

        service = RepairService(mock_client)
        repair = await service.get_repair("test", "ignored")

        assert repair is not None
        assert repair.active is False


class TestIgnoreRepair:
    """Tests for RepairService.ignore_repair."""

    @pytest.mark.asyncio()
    async def test_ignore_repair_success(self, mock_client: MagicMock) -> None:
        """Test ignoring a repair successfully."""
        mock_client._ws_call.side_effect = [
            {"issues": [{"domain": "test", "issue_id": "issue", "severity": "warning", "active": True}]},
            None,  # ignore call returns nothing
        ]

        service = RepairService(mock_client)
        await service.ignore_repair("test", "issue")

        # Verify the ignore call was made
        assert mock_client._ws_call.call_count == 2
        mock_client._ws_call.assert_called_with(
            "repairs/ignore_issue", domain="test", issue_id="issue", ignore=True
        )

    @pytest.mark.asyncio()
    async def test_ignore_repair_not_found(self, mock_client: MagicMock) -> None:
        """Test ignoring a repair that doesn't exist raises NotFoundError."""
        mock_client._ws_call.return_value = {"issues": []}

        service = RepairService(mock_client)
        with pytest.raises(NotFoundError, match="not found"):
            await service.ignore_repair("nonexistent", "repair")


class TestUnignoreRepair:
    """Tests for RepairService.unignore_repair."""

    @pytest.mark.asyncio()
    async def test_unignore_repair_success(self, mock_client: MagicMock) -> None:
        """Test unignoring a repair successfully."""
        mock_client._ws_call.side_effect = [
            {"issues": [{"domain": "test", "issue_id": "issue", "severity": "warning", "active": False}]},
            None,  # unignore call returns nothing
        ]

        service = RepairService(mock_client)
        await service.unignore_repair("test", "issue")

        # Verify the unignore call was made
        assert mock_client._ws_call.call_count == 2
        mock_client._ws_call.assert_called_with(
            "repairs/ignore_issue", domain="test", issue_id="issue", ignore=False
        )

    @pytest.mark.asyncio()
    async def test_unignore_repair_not_found(self, mock_client: MagicMock) -> None:
        """Test unignoring a repair that doesn't exist raises NotFoundError."""
        mock_client._ws_call.return_value = {"issues": []}

        service = RepairService(mock_client)
        with pytest.raises(NotFoundError, match="not found"):
            await service.unignore_repair("nonexistent", "repair")

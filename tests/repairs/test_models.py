"""Tests for repairs domain models."""


from ha_cli.domains.repairs.models import Repair


class TestRepair:
    """Tests for Repair model."""

    def test_from_dict_minimal(self) -> None:
        """Test creating repair from minimal dict."""
        data = {
            "domain": "homeassistant",
            "issue_id": "deprecated_yaml",
            "severity": "warning",
        }
        repair = Repair.from_dict(data)

        assert repair.domain == "homeassistant"
        assert repair.issue_id == "deprecated_yaml"
        assert repair.severity == "warning"
        assert repair.active is True  # default
        assert repair.is_fixable is None  # default
        assert repair.is_persistent is False  # default

    def test_from_dict_full(self) -> None:
        """Test creating repair from full dict."""
        data = {
            "domain": "zwave_js",
            "issue_id": "node_5_not_ready",
            "severity": "error",
            "active": True,
            "is_fixable": False,
            "is_persistent": True,
            "breaks_in_ha_version": "2025.1.0",
            "issue_domain": "zwave_js",
            "learn_more_url": "https://example.com/docs",
            "translation_key": "node_not_ready",
            "translation_placeholders": {"node_id": "5"},
            "created": "2026-01-10T08:30:00+00:00",
            "dismissed_version": None,
            "data": {"extra": "info"},
        }
        repair = Repair.from_dict(data)

        assert repair.domain == "zwave_js"
        assert repair.issue_id == "node_5_not_ready"
        assert repair.severity == "error"
        assert repair.active is True
        assert repair.is_fixable is False
        assert repair.is_persistent is True
        assert repair.breaks_in_ha_version == "2025.1.0"
        assert repair.issue_domain == "zwave_js"
        assert repair.learn_more_url == "https://example.com/docs"
        assert repair.translation_key == "node_not_ready"
        assert repair.translation_placeholders == {"node_id": "5"}
        assert repair.dismissed_version is None
        assert repair.data == {"extra": "info"}

    def test_from_dict_inactive(self) -> None:
        """Test creating inactive (ignored) repair."""
        data = {
            "domain": "homeassistant",
            "issue_id": "test_issue",
            "severity": "warning",
            "active": False,
        }
        repair = Repair.from_dict(data)

        assert repair.active is False

    def test_from_dict_fixable_true(self) -> None:
        """Test is_fixable True value."""
        data = {
            "domain": "homeassistant",
            "issue_id": "test_issue",
            "severity": "warning",
            "is_fixable": True,
        }
        repair = Repair.from_dict(data)

        assert repair.is_fixable is True

    def test_from_dict_fixable_none(self) -> None:
        """Test is_fixable None (unknown) value."""
        data = {
            "domain": "homeassistant",
            "issue_id": "test_issue",
            "severity": "warning",
            # is_fixable not present
        }
        repair = Repair.from_dict(data)

        assert repair.is_fixable is None

    def test_to_dict(self) -> None:
        """Test converting repair to dict."""
        data = {
            "domain": "zwave_js",
            "issue_id": "node_not_ready",
            "severity": "error",
            "active": True,
            "is_fixable": False,
            "is_persistent": True,
            "breaks_in_ha_version": "2025.1.0",
        }
        repair = Repair.from_dict(data)
        result = repair.to_dict()

        assert result["domain"] == "zwave_js"
        assert result["issue_id"] == "node_not_ready"
        assert result["severity"] == "error"
        assert result["active"] is True
        assert result["is_fixable"] is False
        assert result["is_persistent"] is True
        assert result["breaks_in_ha_version"] == "2025.1.0"

    def test_full_id(self) -> None:
        """Test full_id property."""
        repair = Repair.from_dict({
            "domain": "homeassistant",
            "issue_id": "deprecated_yaml",
            "severity": "warning",
        })

        assert repair.full_id == "homeassistant/deprecated_yaml"

    def test_severity_order_critical(self) -> None:
        """Test severity ordering for critical."""
        repair = Repair.from_dict({
            "domain": "test",
            "issue_id": "test",
            "severity": "critical",
        })

        assert repair.severity_order == 0

    def test_severity_order_error(self) -> None:
        """Test severity ordering for error."""
        repair = Repair.from_dict({
            "domain": "test",
            "issue_id": "test",
            "severity": "error",
        })

        assert repair.severity_order == 1

    def test_severity_order_warning(self) -> None:
        """Test severity ordering for warning."""
        repair = Repair.from_dict({
            "domain": "test",
            "issue_id": "test",
            "severity": "warning",
        })

        assert repair.severity_order == 2

    def test_severity_order_unknown(self) -> None:
        """Test severity ordering for unknown severity.

        Unknown severities are normalized to 'warning' for consistency.
        """
        repair = Repair.from_dict({
            "domain": "test",
            "issue_id": "test",
            "severity": "info",  # not a standard severity - normalized to warning
        })

        # Unknown severities are normalized to "warning" (severity_order 2)
        assert repair.severity == "warning"
        assert repair.severity_order == 2

    def test_created_display_with_valid_date(self) -> None:
        """Test created_display with valid ISO date."""
        repair = Repair.from_dict({
            "domain": "test",
            "issue_id": "test",
            "severity": "warning",
            "created": "2026-01-10T08:30:00+00:00",
        })

        assert repair.created_display == "2026-01-10"

    def test_created_display_without_date(self) -> None:
        """Test created_display when no date provided."""
        repair = Repair.from_dict({
            "domain": "test",
            "issue_id": "test",
            "severity": "warning",
        })

        assert repair.created_display == "Unknown"

    def test_created_display_with_invalid_date(self) -> None:
        """Test created_display with unparseable date."""
        repair = Repair.from_dict({
            "domain": "test",
            "issue_id": "test",
            "severity": "warning",
            "created": "not-a-date",
        })

        # Invalid dates are suppressed, resulting in None -> "Unknown"
        assert repair.created_display == "Unknown"


class TestRepairSorting:
    """Tests for repair sorting behavior."""

    def test_sorting_by_severity(self) -> None:
        """Test repairs sort by severity (critical first)."""
        warning = Repair.from_dict({
            "domain": "a",
            "issue_id": "warning",
            "severity": "warning",
        })
        error = Repair.from_dict({
            "domain": "a",
            "issue_id": "error",
            "severity": "error",
        })
        critical = Repair.from_dict({
            "domain": "a",
            "issue_id": "critical",
            "severity": "critical",
        })

        repairs = [warning, error, critical]
        sorted_repairs = sorted(
            repairs,
            key=lambda r: (r.severity_order, r.domain.lower(), r.issue_id.lower()),
        )

        assert sorted_repairs[0].severity == "critical"
        assert sorted_repairs[1].severity == "error"
        assert sorted_repairs[2].severity == "warning"

    def test_sorting_by_domain_within_severity(self) -> None:
        """Test repairs sort by domain within same severity."""
        repair_z = Repair.from_dict({
            "domain": "zwave_js",
            "issue_id": "test",
            "severity": "error",
        })
        repair_a = Repair.from_dict({
            "domain": "automation",
            "issue_id": "test",
            "severity": "error",
        })

        repairs = [repair_z, repair_a]
        sorted_repairs = sorted(
            repairs,
            key=lambda r: (r.severity_order, r.domain.lower(), r.issue_id.lower()),
        )

        assert sorted_repairs[0].domain == "automation"
        assert sorted_repairs[1].domain == "zwave_js"

    def test_sorting_by_issue_id_within_domain(self) -> None:
        """Test repairs sort by issue_id within same domain."""
        repair_b = Repair.from_dict({
            "domain": "test",
            "issue_id": "beta",
            "severity": "warning",
        })
        repair_a = Repair.from_dict({
            "domain": "test",
            "issue_id": "alpha",
            "severity": "warning",
        })

        repairs = [repair_b, repair_a]
        sorted_repairs = sorted(
            repairs,
            key=lambda r: (r.severity_order, r.domain.lower(), r.issue_id.lower()),
        )

        assert sorted_repairs[0].issue_id == "alpha"
        assert sorted_repairs[1].issue_id == "beta"

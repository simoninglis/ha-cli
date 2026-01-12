"""Tests for integrations domain models."""


from ha_cli.domains.integrations.models import (
    ConfigEntry,
    ConfigEntryResult,
    ConfigFlowProgress,
    ConfigFlowStep,
)


class TestConfigEntry:
    """Tests for ConfigEntry model."""

    def test_from_dict_minimal(self) -> None:
        """Test creating entry from minimal dict."""
        data = {
            "entry_id": "abc123",
            "domain": "media_extractor",
            "title": "Media extractor",
            "state": "loaded",
            "source": "user",
        }
        entry = ConfigEntry.from_dict(data)

        assert entry.entry_id == "abc123"
        assert entry.domain == "media_extractor"
        assert entry.title == "Media extractor"
        assert entry.state == "loaded"
        assert entry.source == "user"
        assert entry.disabled_by is None

    def test_from_dict_full(self) -> None:
        """Test creating entry from full dict."""
        data = {
            "entry_id": "abc123def456",
            "domain": "esphome",
            "title": "Office Printer",
            "state": "loaded",
            "source": "user",
            "created_at": 1700000000.0,
            "modified_at": 1700001000.0,
            "disabled_by": None,
            "supports_options": True,
            "supports_unload": True,
            "supports_reconfigure": False,
            "supports_remove_device": False,
            "pref_disable_new_entities": False,
            "pref_disable_polling": False,
            "reason": None,
            "error_reason_translation_key": None,
            "num_subentries": 2,
        }
        entry = ConfigEntry.from_dict(data)

        assert entry.entry_id == "abc123def456"
        assert entry.domain == "esphome"
        assert entry.title == "Office Printer"
        assert entry.supports_options is True
        assert entry.supports_unload is True
        assert entry.num_subentries == 2

    def test_from_dict_disabled(self) -> None:
        """Test creating disabled entry."""
        data = {
            "entry_id": "abc123",
            "domain": "test",
            "title": "Test",
            "state": "not_loaded",
            "source": "user",
            "disabled_by": "user",
        }
        entry = ConfigEntry.from_dict(data)

        assert entry.is_disabled is True
        assert entry.disabled_by == "user"

    def test_to_dict(self) -> None:
        """Test converting entry to dict."""
        data = {
            "entry_id": "abc123",
            "domain": "media_extractor",
            "title": "Media extractor",
            "state": "loaded",
            "source": "user",
            "created_at": 1700000000.0,
            "modified_at": 1700001000.0,
            "supports_options": False,
            "supports_unload": False,
            "supports_reconfigure": False,
        }
        entry = ConfigEntry.from_dict(data)
        result = entry.to_dict()

        assert result["entry_id"] == "abc123"
        assert result["domain"] == "media_extractor"
        assert result["title"] == "Media extractor"
        assert result["state"] == "loaded"
        assert "disabled_by" not in result  # None values omitted

    def test_created_display_with_timestamp(self) -> None:
        """Test created_display with valid timestamp."""
        data = {
            "entry_id": "abc123",
            "domain": "test",
            "title": "Test",
            "state": "loaded",
            "source": "user",
            "created_at": 1700000000.0,
        }
        entry = ConfigEntry.from_dict(data)

        # Check format is YYYY-MM-DD (timezone may vary)
        assert len(entry.created_display) == 10
        assert entry.created_display[4] == "-"
        assert entry.created_display[7] == "-"
        assert entry.created_display.startswith("2023-11-")

    def test_created_display_without_timestamp(self) -> None:
        """Test created_display when no timestamp."""
        data = {
            "entry_id": "abc123",
            "domain": "test",
            "title": "Test",
            "state": "loaded",
            "source": "user",
        }
        entry = ConfigEntry.from_dict(data)

        assert entry.created_display == "Unknown"

    def test_state_display_loaded(self) -> None:
        """Test state_display for loaded state."""
        entry = ConfigEntry.from_dict({
            "entry_id": "abc",
            "domain": "test",
            "title": "Test",
            "state": "loaded",
            "source": "user",
        })

        assert entry.state_display == "Loaded"

    def test_state_display_setup_error(self) -> None:
        """Test state_display for setup_error state."""
        entry = ConfigEntry.from_dict({
            "entry_id": "abc",
            "domain": "test",
            "title": "Test",
            "state": "setup_error",
            "source": "user",
        })

        assert entry.state_display == "Setup Error"


class TestConfigFlowStep:
    """Tests for ConfigFlowStep model."""

    def test_from_dict_form(self) -> None:
        """Test creating flow step from form response."""
        data = {
            "type": "form",
            "flow_id": "flow123",
            "handler": "esphome",
            "step_id": "user",
            "data_schema": [
                {"type": "string", "name": "host", "required": True},
                {"type": "integer", "name": "port", "default": 6053},
            ],
        }
        step = ConfigFlowStep.from_dict(data)

        assert step.flow_id == "flow123"
        assert step.handler == "esphome"
        assert step.step_id == "user"
        assert step.type == "form"
        assert len(step.data_schema) == 2
        assert step.requires_input is True
        assert step.is_complete is False

    def test_from_dict_create_entry(self) -> None:
        """Test creating flow step from create_entry response."""
        data = {
            "type": "create_entry",
            "flow_id": "flow123",
            "handler": "media_extractor",
            "title": "Media extractor",
            "result": {
                "entry_id": "abc123",
                "domain": "media_extractor",
                "title": "Media extractor",
            },
        }
        step = ConfigFlowStep.from_dict(data)

        assert step.type == "create_entry"
        assert step.is_complete is True
        assert step.is_aborted is False

    def test_from_dict_abort(self) -> None:
        """Test creating flow step from abort response."""
        data = {
            "type": "abort",
            "flow_id": "flow123",
            "handler": "test",
            "step_id": "already_configured",
        }
        step = ConfigFlowStep.from_dict(data)

        assert step.type == "abort"
        assert step.is_aborted is True
        assert step.is_complete is False

    def test_get_required_fields(self) -> None:
        """Test getting required fields from schema."""
        step = ConfigFlowStep.from_dict({
            "type": "form",
            "flow_id": "flow123",
            "handler": "esphome",
            "step_id": "user",
            "data_schema": [
                {"type": "string", "name": "host", "required": True},
                {"type": "integer", "name": "port", "required": False},
            ],
        })

        required = step.get_required_fields()
        assert required == ["host"]

    def test_get_field_defaults(self) -> None:
        """Test getting default values from schema."""
        step = ConfigFlowStep.from_dict({
            "type": "form",
            "flow_id": "flow123",
            "handler": "esphome",
            "step_id": "user",
            "data_schema": [
                {"type": "string", "name": "host"},
                {"type": "integer", "name": "port", "default": 6053},
            ],
        })

        defaults = step.get_field_defaults()
        assert defaults["port"] == 6053
        assert "host" not in defaults

    def test_to_dict(self) -> None:
        """Test converting flow step to dict."""
        data = {
            "type": "form",
            "flow_id": "flow123",
            "handler": "test",
            "step_id": "user",
            "data_schema": [],
        }
        step = ConfigFlowStep.from_dict(data)
        result = step.to_dict()

        assert result["flow_id"] == "flow123"
        assert result["handler"] == "test"
        assert result["type"] == "form"


class TestConfigFlowProgress:
    """Tests for ConfigFlowProgress model."""

    def test_from_dict(self) -> None:
        """Test creating flow progress from dict."""
        data = {
            "flow_id": "flow123",
            "handler": "zwave_js",
            "step_id": "confirm",
            "context": {
                "source": "usb",
                "title_placeholders": {"name": "Z-Wave Stick"},
            },
        }
        flow = ConfigFlowProgress.from_dict(data)

        assert flow.flow_id == "flow123"
        assert flow.handler == "zwave_js"
        assert flow.step_id == "confirm"
        assert flow.source == "usb"
        assert flow.title == "Z-Wave Stick"

    def test_source_default(self) -> None:
        """Test source defaults to unknown."""
        flow = ConfigFlowProgress.from_dict({
            "flow_id": "flow123",
            "handler": "test",
            "step_id": "user",
        })

        assert flow.source == "unknown"

    def test_title_fallback(self) -> None:
        """Test title falls back to handler."""
        flow = ConfigFlowProgress.from_dict({
            "flow_id": "flow123",
            "handler": "my_integration",
            "step_id": "user",
            "context": {},
        })

        assert flow.title == "my_integration"


class TestConfigEntryResult:
    """Tests for ConfigEntryResult model."""

    def test_from_create_response(self) -> None:
        """Test creating result from create_entry response."""
        data = {
            "type": "create_entry",
            "flow_id": "flow123",
            "handler": "media_extractor",
            "title": "Media extractor",
            "result": {
                "entry_id": "abc123",
                "domain": "media_extractor",
                "title": "Media extractor",
            },
        }
        result = ConfigEntryResult.from_create_response(data)

        assert result.entry_id == "abc123"
        assert result.domain == "media_extractor"
        assert result.title == "Media extractor"
        assert result.require_restart is False

    def test_from_delete_response(self) -> None:
        """Test creating result from delete response."""
        result = ConfigEntryResult.from_delete_response(
            entry_id="abc123",
            domain="test",
            data={"require_restart": True},
        )

        assert result.entry_id == "abc123"
        assert result.domain == "test"
        assert result.require_restart is True

    def test_to_dict(self) -> None:
        """Test converting result to dict."""
        result = ConfigEntryResult(
            entry_id="abc123",
            domain="test",
            title="Test Integration",
            require_restart=True,
        )
        data = result.to_dict()

        assert data["entry_id"] == "abc123"
        assert data["domain"] == "test"
        assert data["title"] == "Test Integration"
        assert data["require_restart"] is True

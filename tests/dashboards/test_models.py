"""Tests for dashboard models."""

import pytest

from ha_cli.domains.dashboards.models import CardConfig, DashboardConfig, DashboardInfo, ViewConfig


class TestDashboardInfo:
    """Test DashboardInfo model."""
    
    def test_dashboard_info_minimal(self):
        """Test creating dashboard info with minimal fields."""
        info = DashboardInfo(
            id="test",
            url_path="test-path",
            require_admin=False,
            show_in_sidebar=True,
        )
        
        assert info.id == "test"
        assert info.url_path == "test-path"
        assert info.require_admin is False
        assert info.show_in_sidebar is True
        assert info.mode == "storage"
        assert info.title is None
        assert info.icon is None
    
    def test_dashboard_info_full(self):
        """Test creating dashboard info with all fields."""
        info = DashboardInfo(
            id="admin",
            url_path="admin-panel",
            require_admin=True,
            show_in_sidebar=True,
            title="Admin Panel",
            icon="mdi:shield",
            mode="yaml",
        )
        
        assert info.id == "admin"
        assert info.url_path == "admin-panel"
        assert info.require_admin is True
        assert info.show_in_sidebar is True
        assert info.title == "Admin Panel"
        assert info.icon == "mdi:shield"
        assert info.mode == "yaml"


class TestCardConfig:
    """Test CardConfig model."""
    
    def test_card_minimal(self):
        """Test creating card with minimal fields."""
        card = CardConfig(type="button")
        
        assert card.type == "button"
        assert card.title is None
        assert card.entity is None
        assert card.entities is None
    
    def test_card_with_entity(self):
        """Test card with single entity."""
        card = CardConfig(
            type="button",
            entity="light.living_room",
            title="Living Room Light",
        )
        
        assert card.type == "button"
        assert card.entity == "light.living_room"
        assert card.title == "Living Room Light"
        
        # Test entity extraction
        entities = card.get_entity_references()
        assert entities == ["light.living_room"]
    
    def test_card_with_entities_list(self):
        """Test card with entities list."""
        card = CardConfig(
            type="entities",
            title="Lights",
            entities=["light.bedroom", "light.kitchen", "switch.porch"],
        )
        
        entities = card.get_entity_references()
        assert len(entities) == 3
        assert "light.bedroom" in entities
        assert "light.kitchen" in entities
        assert "switch.porch" in entities
    
    def test_card_with_tap_action(self):
        """Test card with tap action containing entity."""
        card = CardConfig(
            type="button",
            entity="light.living_room",
            tap_action={
                "action": "call-service",
                "service": "light.toggle",
                "target": {
                    "entity_id": "light.kitchen"
                }
            }
        )
        
        entities = card.get_entity_references()
        assert len(entities) == 2
        assert "light.living_room" in entities
        assert "light.kitchen" in entities
    
    def test_card_with_nested_entities(self):
        """Test card with nested entity references."""
        card = CardConfig(
            type="custom:button-card",
            entity="sensor.temperature",
            custom_fields={
                "info": {
                    "entity": "sensor.humidity"
                },
                "buttons": [
                    {"entity": "switch.fan"},
                    {"entity": "climate.thermostat"}
                ]
            }
        )
        
        entities = card.get_entity_references()
        assert len(entities) == 4
        assert "sensor.temperature" in entities
        assert "sensor.humidity" in entities
        assert "switch.fan" in entities
        assert "climate.thermostat" in entities
    
    def test_entity_validation(self):
        """Test entity ID validation."""
        card = CardConfig(
            type="entities",
            entities=[
                "light.valid",
                "not_an_entity",
                "sensor.temperature",
                "invalid.domain.format",
                "",
            ]
        )
        
        entities = card.get_entity_references()
        # Only valid entity IDs should be returned
        assert entities == ["light.valid", "sensor.temperature"]
    
    def test_duplicate_entity_removal(self):
        """Test that duplicate entities are removed."""
        card = CardConfig(
            type="entities",
            entity="light.living_room",
            entities=["light.living_room", "light.bedroom", "light.living_room"],
            tap_action={
                "target": {"entity_id": "light.bedroom"}
            }
        )
        
        entities = card.get_entity_references()
        # Should have unique entities only
        assert entities == ["light.living_room", "light.bedroom"]


class TestViewConfig:
    """Test ViewConfig model."""
    
    def test_view_minimal(self):
        """Test creating view with minimal fields."""
        view = ViewConfig()
        
        assert view.title is None
        assert view.path is None
        assert view.cards == []
        assert view.badges is None
    
    def test_view_with_cards(self):
        """Test view with multiple cards."""
        view = ViewConfig(
            title="Living Room",
            path="living_room",
            icon="mdi:sofa",
            cards=[
                CardConfig(type="light", entity="light.living_room"),
                CardConfig(type="sensor", entity="sensor.temperature"),
                CardConfig(type="entities", entities=["switch.tv", "switch.fan"]),
            ]
        )
        
        assert view.title == "Living Room"
        assert view.path == "living_room"
        assert len(view.cards) == 3
        
        # Test entity extraction
        entities = view.get_entity_references()
        assert len(entities) == 4
        assert "light.living_room" in entities
        assert "sensor.temperature" in entities
        assert "switch.tv" in entities
        assert "switch.fan" in entities
    
    def test_view_with_badges(self):
        """Test view with legacy badges."""
        view = ViewConfig(
            title="Overview",
            badges=[
                {"entity": "sensor.temperature"},
                {"entity": "sensor.humidity"},
                {"entity": "person.john"},
            ]
        )
        
        entities = view.get_entity_references()
        assert len(entities) == 3
        assert "sensor.temperature" in entities
        assert "sensor.humidity" in entities
        assert "person.john" in entities


class TestDashboardConfig:
    """Test DashboardConfig model."""
    
    def test_dashboard_minimal(self):
        """Test creating dashboard with minimal fields."""
        dashboard = DashboardConfig()
        
        assert dashboard.title is None
        assert dashboard.views == []
        assert dashboard.version is None
    
    def test_dashboard_with_views(self):
        """Test dashboard with multiple views."""
        dashboard = DashboardConfig(
            title="Home Dashboard",
            version=1,
            views=[
                ViewConfig(
                    title="Main",
                    cards=[
                        CardConfig(type="light", entity="light.living_room"),
                        CardConfig(type="sensor", entity="sensor.temperature"),
                    ]
                ),
                ViewConfig(
                    title="Security",
                    cards=[
                        CardConfig(type="alarm-panel", entity="alarm_control_panel.home"),
                        CardConfig(type="entities", entities=["binary_sensor.front_door", "binary_sensor.back_door"]),
                    ]
                )
            ]
        )
        
        assert dashboard.title == "Home Dashboard"
        assert dashboard.version == 1
        assert len(dashboard.views) == 2
        
        # Test entity extraction
        entities = dashboard.get_entity_references()
        assert len(entities) == 5
        assert "light.living_room" in entities
        assert "sensor.temperature" in entities
        assert "alarm_control_panel.home" in entities
        assert "binary_sensor.front_door" in entities
        assert "binary_sensor.back_door" in entities
    
    def test_dashboard_from_dict(self):
        """Test creating dashboard from dictionary."""
        data = {
            "title": "Test Dashboard",
            "views": [
                {
                    "title": "Home",
                    "cards": [
                        {
                            "type": "entities",
                            "entities": ["light.living_room", "switch.fan"]
                        },
                        {
                            "type": "button",
                            "entity": "light.bedroom",
                            "tap_action": {
                                "action": "toggle"
                            }
                        }
                    ]
                }
            ]
        }
        
        dashboard = DashboardConfig.from_dict(data)
        
        assert dashboard.title == "Test Dashboard"
        assert len(dashboard.views) == 1
        assert dashboard.views[0].title == "Home"
        assert len(dashboard.views[0].cards) == 2
        
        # Verify cards were properly instantiated
        card1 = dashboard.views[0].cards[0]
        assert isinstance(card1, CardConfig)
        assert card1.type == "entities"
        
        # Test entity extraction
        entities = dashboard.get_entity_references()
        assert len(entities) == 3
        assert "light.living_room" in entities
        assert "switch.fan" in entities
        assert "light.bedroom" in entities
    
    def test_dashboard_with_extra_fields(self):
        """Test that extra fields are preserved."""
        dashboard = DashboardConfig(
            title="Custom Dashboard",
            custom_field="custom_value",
            views=[
                ViewConfig(
                    title="Custom View",
                    custom_view_field="view_value",
                    cards=[
                        CardConfig(
                            type="custom:special-card",
                            custom_card_field="card_value",
                        )
                    ]
                )
            ]
        )
        
        # Model should accept extra fields
        assert dashboard.title == "Custom Dashboard"
        
        # Convert to dict should include extra fields
        data = dashboard.model_dump()
        assert data["custom_field"] == "custom_value"
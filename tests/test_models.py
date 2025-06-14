"""Tests for Pydantic data models."""

import json
from datetime import datetime

import pytest

from ha_automation.models import Automation, AutomationListResponse, AutomationState


class TestAutomation:
    """Test Automation model."""
    
    def test_automation_minimal(self):
        """Test creating minimal automation."""
        automation = Automation(
            alias="Test Automation",
            trigger=[{"platform": "state", "entity_id": "sensor.test"}],
            action=[{"service": "light.turn_on", "entity_id": "light.test"}],
        )
        
        assert automation.alias == "Test Automation"
        assert automation.mode == "single"  # default
        assert len(automation.trigger) == 1
        assert len(automation.action) == 1
        assert automation.condition is None
        assert automation.id is None
    
    def test_automation_full(self):
        """Test creating full automation."""
        automation = Automation(
            id="test_automation_1",
            alias="Complex Automation",
            trigger=[
                {"platform": "time", "at": "sunset"},
                {"platform": "state", "entity_id": "sensor.motion", "to": "on"},
            ],
            condition=[
                {"condition": "state", "entity_id": "sun.sun", "state": "below_horizon"},
            ],
            action=[
                {"service": "light.turn_on", "entity_id": "light.porch"},
                {"delay": {"minutes": 5}},
                {"service": "light.turn_off", "entity_id": "light.porch"},
            ],
            mode="restart",
            max=10,
            variables={"brightness": 255},
            last_triggered=datetime.fromisoformat("2024-01-01T12:00:00"),
        )
        
        assert automation.id == "test_automation_1"
        assert automation.alias == "Complex Automation"
        assert len(automation.trigger) == 2
        assert len(automation.condition) == 1
        assert len(automation.action) == 3
        assert automation.mode == "restart"
        assert automation.max == 10
        assert automation.variables["brightness"] == 255
    
    def test_automation_normalize_lists(self):
        """Test that single items are normalized to lists."""
        automation = Automation(
            alias="Test",
            trigger={"platform": "time", "at": "10:00"},  # Single dict
            action={"service": "light.turn_on"},  # Single dict
            condition={"condition": "state", "entity_id": "sun.sun", "state": "above_horizon"},  # Single dict
        )
        
        # Should be normalized to lists
        assert isinstance(automation.trigger, list)
        assert len(automation.trigger) == 1
        assert isinstance(automation.action, list)
        assert len(automation.action) == 1
        assert isinstance(automation.condition, list)
        assert len(automation.condition) == 1
    
    def test_automation_to_yaml(self):
        """Test YAML serialization."""
        automation = Automation(
            alias="Sunset Lights",
            trigger=[{"platform": "sun", "event": "sunset", "offset": "-00:30:00"}],
            action=[
                {"service": "light.turn_on", "entity_id": "light.porch", "data": {"brightness": 150}},
            ],
            mode="single",
        )
        
        yaml_str = automation.to_yaml()
        assert "alias: Sunset Lights" in yaml_str
        assert "platform: sun" in yaml_str
        assert "event: sunset" in yaml_str
        assert "service: light.turn_on" in yaml_str
        assert "brightness: 150" in yaml_str
        
        # Should not include None values (check at start of line)
        lines = yaml_str.split('\n')
        assert not any(line.strip().startswith("id:") for line in lines)
        assert not any(line.strip().startswith("last_triggered:") for line in lines)
    
    def test_automation_from_yaml(self):
        """Test creating from YAML."""
        yaml_str = """
alias: Motion Light
trigger:
  platform: state
  entity_id: binary_sensor.motion
  to: 'on'
action:
  - service: light.turn_on
    entity_id: light.hallway
  - delay:
      minutes: 5
  - service: light.turn_off
    entity_id: light.hallway
mode: restart
"""
        
        automation = Automation.from_yaml(yaml_str)
        assert automation.alias == "Motion Light"
        assert automation.trigger[0]["platform"] == "state"
        assert len(automation.action) == 3
        assert automation.mode == "restart"
    
    def test_automation_to_json_dict(self):
        """Test JSON serialization."""
        now = datetime.now()
        automation = Automation(
            id="test_123",
            alias="Test",
            trigger=[{"platform": "time", "at": "10:00"}],
            action=[{"service": "light.turn_on"}],
            last_triggered=now,
        )
        
        json_dict = automation.to_json_dict()
        
        # Should be JSON serializable
        json_str = json.dumps(json_dict)
        assert json_str
        
        # Check datetime is serialized
        assert isinstance(json_dict.get("last_triggered"), str)
    
    def test_automation_validation(self):
        """Test validation of required fields."""
        # Missing alias
        with pytest.raises(ValueError):
            Automation(
                trigger=[{"platform": "time"}],
                action=[{"service": "test"}],
            )
        
        # Missing trigger
        with pytest.raises(ValueError):
            Automation(
                alias="Test",
                action=[{"service": "test"}],
            )
        
        # Missing action
        with pytest.raises(ValueError):
            Automation(
                alias="Test",
                trigger=[{"platform": "time"}],
            )
    
    def test_automation_mode_validation(self):
        """Test mode validation."""
        # Valid modes
        for mode in ["single", "restart", "queued", "parallel"]:
            automation = Automation(
                alias="Test",
                trigger=[{"platform": "time"}],
                action=[{"service": "test"}],
                mode=mode,
            )
            assert automation.mode == mode
        
        # Invalid mode
        with pytest.raises(ValueError):
            Automation(
                alias="Test",
                trigger=[{"platform": "time"}],
                action=[{"service": "test"}],
                mode="invalid",
            )
    
    def test_automation_triggers_format(self):
        """Test handling of triggers (plural) format."""
        # Create automation with plural format
        automation = Automation(
            alias="Test Plural Triggers",
            triggers=[  # Using 'triggers' instead of 'trigger'
                {"platform": "state", "entity_id": "sensor.test"},
                {"platform": "time", "at": "10:00"},
            ],
            action=[{"service": "light.turn_on"}],
        )
        
        # Should be normalized to 'trigger'
        assert hasattr(automation, "trigger")
        assert len(automation.trigger) == 2
        assert automation.trigger[0]["platform"] == "state"
        assert automation.trigger[1]["platform"] == "time"
    
    def test_automation_conditions_format(self):
        """Test handling of conditions (plural) format."""
        automation = Automation(
            alias="Test Plural Conditions",
            trigger=[{"platform": "state"}],
            conditions=[  # Using 'conditions' instead of 'condition'
                {"condition": "state", "entity_id": "sun.sun", "state": "above_horizon"},
                {"condition": "time", "after": "08:00", "before": "20:00"},
            ],
            action=[{"service": "light.turn_on"}],
        )
        
        # Should be normalized to 'condition'
        assert hasattr(automation, "condition")
        assert len(automation.condition) == 2
        assert automation.condition[0]["condition"] == "state"
        assert automation.condition[1]["condition"] == "time"
    
    def test_automation_actions_format(self):
        """Test handling of actions (plural) format."""
        automation = Automation(
            alias="Test Plural Actions",
            trigger=[{"platform": "state"}],
            actions=[  # Using 'actions' instead of 'action'
                {"service": "light.turn_on", "entity_id": "light.test"},
                {"delay": {"seconds": 10}},
                {"service": "light.turn_off", "entity_id": "light.test"},
            ],
        )
        
        # Should be normalized to 'action'
        assert hasattr(automation, "action")
        assert len(automation.action) == 3
        assert automation.action[0]["service"] == "light.turn_on"
        assert automation.action[1]["delay"]["seconds"] == 10
    
    def test_automation_mixed_formats(self):
        """Test handling of mixed singular/plural formats."""
        automation = Automation(
            alias="Test Mixed Formats",
            triggers={"platform": "state", "entity_id": "sensor.test"},  # Plural + single dict
            conditions={"condition": "state", "entity_id": "sun.sun", "state": "above_horizon"},  # Plural + single dict
            actions={"service": "light.turn_on"},  # Plural + single dict
        )
        
        # All should be normalized to singular form as lists
        assert isinstance(automation.trigger, list)
        assert len(automation.trigger) == 1
        assert isinstance(automation.condition, list)
        assert len(automation.condition) == 1
        assert isinstance(automation.action, list)
        assert len(automation.action) == 1
    
    def test_automation_yaml_preserves_format(self):
        """Test that YAML serialization uses correct singular format."""
        automation = Automation(
            alias="Test YAML Format",
            triggers=[{"platform": "state"}],  # Input with plural
            conditions=[{"condition": "state"}],  # Input with plural
            actions=[{"service": "test"}],  # Input with plural
        )
        
        yaml_str = automation.to_yaml()
        
        # Should use singular forms in YAML
        assert "trigger:" in yaml_str
        assert "triggers:" not in yaml_str
        assert "condition:" in yaml_str
        assert "conditions:" not in yaml_str
        assert "action:" in yaml_str
        assert "actions:" not in yaml_str


class TestAutomationListResponse:
    """Test AutomationListResponse model."""
    
    def test_list_response_empty(self):
        """Test empty list response."""
        response = AutomationListResponse(result=[])
        automations = response.to_automations()
        assert automations == []
    
    def test_list_response_with_automations(self):
        """Test list response with automations."""
        response_data = {
            "result": [
                {
                    "id": "sunset_lights",
                    "alias": "Sunset Lights",
                    "trigger": [{"platform": "sun", "event": "sunset"}],
                    "action": [{"service": "light.turn_on"}],
                    "mode": "single",
                },
                {
                    "id": "morning_routine",
                    "alias": "Morning Routine",
                    "trigger": [{"platform": "time", "at": "07:00:00"}],
                    "action": [{"service": "script.morning"}],
                    "mode": "single",
                    "last_triggered": "2024-01-15T07:00:00",
                },
            ]
        }
        
        response = AutomationListResponse(**response_data)
        automations = response.to_automations()
        
        assert len(automations) == 2
        assert automations[0].id == "sunset_lights"
        assert automations[0].alias == "Sunset Lights"
        assert automations[1].id == "morning_routine"
        assert automations[1].last_triggered is not None
    
    def test_list_response_with_invalid_automation(self):
        """Test list response handles invalid automations gracefully."""
        response_data = {
            "result": [
                {
                    "id": "valid",
                    "alias": "Valid Automation",
                    "trigger": [{"platform": "time"}],
                    "action": [{"service": "test"}],
                },
                {
                    "id": "invalid",
                    # Missing required fields
                },
                {
                    "id": "also_valid",
                    "alias": "Also Valid",
                    "trigger": [{"platform": "state"}],
                    "action": [{"service": "test2"}],
                },
            ]
        }
        
        response = AutomationListResponse(**response_data)
        automations = response.to_automations()
        
        # Should skip invalid automation
        assert len(automations) == 2
        assert automations[0].id == "valid"
        assert automations[1].id == "also_valid"


class TestAutomationState:
    """Test AutomationState model."""
    
    def test_automation_state_enabled(self):
        """Test enabled automation state."""
        state = AutomationState(
            entity_id="automation.sunset_lights",
            state="on",
            attributes={
                "friendly_name": "Sunset Lights Automation",
                "last_triggered": "2024-01-15T18:30:00",
            },
        )
        
        assert state.automation_id == "sunset_lights"
        assert state.is_enabled is True
        assert state.friendly_name == "Sunset Lights Automation"
    
    def test_automation_state_disabled(self):
        """Test disabled automation state."""
        state = AutomationState(
            entity_id="automation.test_automation",
            state="off",
        )
        
        assert state.automation_id == "test_automation"
        assert state.is_enabled is False
        assert state.friendly_name == "test_automation"  # Falls back to ID
    
    def test_automation_state_unavailable(self):
        """Test unavailable automation state."""
        state = AutomationState(
            entity_id="automation.broken",
            state="unavailable",
        )
        
        assert state.is_enabled is False
        assert state.state == "unavailable"
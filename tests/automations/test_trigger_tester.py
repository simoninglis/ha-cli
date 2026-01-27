"""Tests for trigger testing service."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_cli.common.client import HAClient
from ha_cli.domains.automations.trigger_tester import TriggerEvent, TriggerTester, TriggerTestResult


class TestTriggerEvent:
    """Test TriggerEvent class."""
    
    def test_state_trigger_description(self):
        """Test state trigger description."""
        event = TriggerEvent(
            timestamp=datetime.now(),
            trigger_data={"platform": "state"},
            variables={
                "trigger": {
                    "platform": "state",
                    "entity_id": "sensor.temperature",
                    "from_state": {"state": "20"},
                    "to_state": {"state": "25"},
                }
            },
        )
        
        desc = event.get_trigger_description()
        assert "sensor.temperature" in desc
        assert "20" in desc
        assert "25" in desc
    
    def test_time_trigger_description(self):
        """Test time trigger description."""
        event = TriggerEvent(
            timestamp=datetime.now(),
            trigger_data={"platform": "time"},
            variables={
                "trigger": {
                    "platform": "time",
                    "at": "10:00:00",
                }
            },
        )
        
        desc = event.get_trigger_description()
        assert "10:00:00" in desc
    
    def test_event_trigger_description(self):
        """Test event trigger description."""
        event = TriggerEvent(
            timestamp=datetime.now(),
            trigger_data={"platform": "event"},
            variables={
                "trigger": {
                    "platform": "event",
                    "event_type": "custom_event",
                    "event_data": {"key": "value"},
                }
            },
        )
        
        desc = event.get_trigger_description()
        assert "custom_event" in desc
        assert "key" in desc


class TestTriggerTestResult:
    """Test TriggerTestResult class."""
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        result = TriggerTestResult(
            trigger_config={"platform": "time"},
            start_time=datetime(2025, 6, 14, 10, 0, 0),
            end_time=datetime(2025, 6, 14, 10, 0, 30),
        )
        
        assert result.duration == 30.0
    
    def test_success_with_events(self):
        """Test success property with events."""
        result = TriggerTestResult(
            trigger_config={"platform": "time"},
            events_received=[
                TriggerEvent(
                    timestamp=datetime.now(),
                    trigger_data={},
                    variables={},
                )
            ],
        )
        
        assert result.success is True
    
    def test_success_with_error(self):
        """Test success property with error."""
        result = TriggerTestResult(
            trigger_config={"platform": "time"},
            error="Test error",
        )
        
        assert result.success is False


class TestTriggerTester:
    """Test TriggerTester service."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock HAClient."""
        client = MagicMock(spec=HAClient)
        # Don't use AsyncMock here, we'll set the return value manually
        client.subscribe_trigger = MagicMock()
        return client
    
    @pytest.fixture
    def tester(self, mock_client):
        """Create TriggerTester instance."""
        return TriggerTester(client=mock_client)
    
    @pytest.mark.asyncio
    async def test_test_trigger_success(self, tester, mock_client):
        """Test successful trigger test."""
        trigger_config = {"platform": "time", "at": "10:00:00"}
        
        # Mock trigger events
        async def mock_trigger_events():
            yield {
                "variables": {
                    "trigger": {
                        "platform": "time",
                        "at": "10:00:00",
                        "now": "2025-06-14T10:00:00",
                    }
                },
                "context": {"id": "test-context"},
            }
        
        mock_client.subscribe_trigger.return_value = mock_trigger_events()
        
        # Run test
        result = await tester.test_trigger(trigger_config, timeout=1.0)
        
        assert result.success is True
        assert len(result.events_received) == 1
        assert result.error is None
        assert result.duration is not None
    
    @pytest.mark.asyncio
    async def test_test_trigger_timeout(self, tester, mock_client):
        """Test trigger test timeout."""
        trigger_config = {"platform": "time", "at": "10:00:00"}
        
        # Mock no events
        async def mock_no_events():
            # Wait forever
            await asyncio.Event().wait()
            yield  # Never reached
        
        mock_client.subscribe_trigger.return_value = mock_no_events()
        
        # Run test with short timeout
        result = await tester.test_trigger(trigger_config, timeout=0.1)
        
        assert result.success is False
        assert len(result.events_received) == 0
        assert "No trigger events received" in result.error
    
    @pytest.mark.asyncio
    async def test_test_trigger_max_events(self, tester, mock_client):
        """Test trigger test with max events limit."""
        trigger_config = {"platform": "time_pattern", "seconds": "*"}
        
        # Mock many trigger events
        async def mock_many_events():
            for i in range(20):
                yield {
                    "variables": {
                        "trigger": {
                            "platform": "time_pattern",
                            "seconds": str(i),
                        }
                    }
                }
        
        mock_client.subscribe_trigger.return_value = mock_many_events()
        
        # Run test with max events limit
        result = await tester.test_trigger(trigger_config, max_events=5)
        
        assert result.success is True
        assert len(result.events_received) == 5
    
    @pytest.mark.asyncio
    async def test_test_trigger_interactive(self, tester, mock_client):
        """Test interactive trigger testing."""
        trigger_config = {"platform": "state", "entity_id": "sensor.test"}
        
        # Mock events
        async def mock_events():
            for i in range(3):
                yield {
                    "variables": {
                        "trigger": {
                            "platform": "state",
                            "entity_id": "sensor.test",
                            "to_state": {"state": str(i)},
                        }
                    }
                }
        
        mock_client.subscribe_trigger.return_value = mock_events()
        
        # Collect events
        events = []
        callback = MagicMock(side_effect=lambda e: events.append(e))
        
        collected = []
        async for event in tester.test_trigger_interactive(trigger_config, callback):
            collected.append(event)
        
        assert len(collected) == 3
        assert len(events) == 3
        assert callback.call_count == 3
    
    def test_validate_trigger_config(self, tester):
        """Test trigger configuration validation."""
        # Valid state trigger
        errors = tester.validate_trigger_config({
            "platform": "state",
            "entity_id": "sensor.test",
        })
        assert len(errors) == 0
        
        # Missing platform
        errors = tester.validate_trigger_config({
            "entity_id": "sensor.test",
        })
        assert "Missing required field: platform" in errors
        
        # State trigger missing entity_id
        errors = tester.validate_trigger_config({
            "platform": "state",
        })
        assert "State trigger requires entity_id" in errors
        
        # Time trigger missing at
        errors = tester.validate_trigger_config({
            "platform": "time",
        })
        assert "Time trigger requires 'at' field" in errors
        
        # Numeric state missing thresholds
        errors = tester.validate_trigger_config({
            "platform": "numeric_state",
            "entity_id": "sensor.temp",
        })
        assert any("above" in e or "below" in e for e in errors)
    
    @pytest.mark.asyncio
    async def test_background_test(self, tester, mock_client):
        """Test background trigger testing."""
        trigger_config = {"platform": "state", "entity_id": "sensor.test"}
        
        # Mock events
        event_count = 0
        async def mock_events():
            nonlocal event_count
            while event_count < 3:
                yield {
                    "variables": {
                        "trigger": {
                            "platform": "state",
                            "entity_id": "sensor.test",
                        }
                    }
                }
                event_count += 1
                await asyncio.sleep(0.05)
        
        mock_client.subscribe_trigger.return_value = mock_events()
        
        # Start background test
        events = []
        callback = lambda e: events.append(e)
        
        tester.start_background_test("test1", trigger_config, callback)
        
        # Verify test is running
        assert "test1" in tester.get_active_tests()
        
        # Wait for some events
        await asyncio.sleep(0.2)
        
        # Stop test
        assert tester.stop_background_test("test1") is True
        assert "test1" not in tester.get_active_tests()
        
        # Should have received some events
        assert len(events) > 0
    
    @pytest.mark.asyncio
    async def test_stop_all_tests(self, tester, mock_client):
        """Test stopping all background tests."""
        # Mock infinite event stream
        async def mock_infinite_events():
            while True:
                yield {"variables": {}}
                await asyncio.sleep(0.1)
        
        mock_client.subscribe_trigger.return_value = mock_infinite_events()
        
        # Start multiple background tests
        for i in range(3):
            tester.start_background_test(f"test{i}", {"platform": "time"})
        
        assert len(tester.get_active_tests()) == 3
        
        # Stop all
        await tester.stop_all_tests()
        
        assert len(tester.get_active_tests()) == 0
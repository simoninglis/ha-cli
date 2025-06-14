"""Tests for automation monitoring service."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_automation.client import HAClient
from ha_automation.models import AutomationState
from ha_automation.monitor import AutomationExecutionEvent, AutomationMonitor


class TestAutomationMonitor:
    """Test AutomationMonitor service."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock HAClient."""
        client = MagicMock(spec=HAClient)
        client.get_automation_states = AsyncMock()
        client.subscribe_automation_events = AsyncMock()
        return client
    
    @pytest.fixture
    def monitor(self, mock_client):
        """Create AutomationMonitor instance."""
        return AutomationMonitor(client=mock_client)
    
    @pytest.mark.asyncio
    async def test_start_monitoring(self, monitor, mock_client):
        """Test starting monitoring loads initial states."""
        # Mock initial states
        mock_client.get_automation_states.return_value = [
            {
                "entity_id": "automation.test1",
                "state": "on",
                "attributes": {"friendly_name": "Test 1"},
            },
            {
                "entity_id": "automation.test2",
                "state": "off",
                "attributes": {"friendly_name": "Test 2"},
            },
        ]
        
        # Mock event stream
        async def mock_events():
            # Yield one event then stop
            yield {
                "data": {
                    "entity_id": "automation.test1",
                    "old_state": {"state": "on"},
                    "new_state": {"state": "on"},
                }
            }
            # Allow task to be cancelled
            await asyncio.Event().wait()
        
        mock_client.subscribe_automation_events.return_value = mock_events()
        
        # Start monitoring
        await monitor.start_monitoring()
        
        # Give it a moment to load states
        await asyncio.sleep(0.1)
        
        # Verify initial states loaded
        assert len(monitor._automation_states) == 2
        assert "test1" in monitor._automation_states
        assert "test2" in monitor._automation_states
        assert monitor._automation_states["test1"].is_enabled is True
        assert monitor._automation_states["test2"].is_enabled is False
        
        # Cleanup
        await monitor.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_process_state_change_event(self, monitor):
        """Test processing state change events."""
        # Set initial state
        monitor._automation_states["test"] = AutomationState(
            entity_id="automation.test",
            state="on",
            attributes={},
        )
        
        # Create state change event
        event = {
            "data": {
                "entity_id": "automation.test",
                "old_state": {
                    "state": "on",
                    "attributes": {"last_triggered": None},
                },
                "new_state": {
                    "state": "off",
                    "attributes": {"last_triggered": None},
                },
            }
        }
        
        # Add state listener
        state_changes = []
        monitor.add_state_listener(lambda id, state: state_changes.append((id, state)))
        
        # Process event
        await monitor._process_event(event)
        
        # Verify state updated
        assert monitor._automation_states["test"].state == "off"
        assert len(state_changes) == 1
        assert state_changes[0][0] == "test"
        assert state_changes[0][1].state == "off"
    
    @pytest.mark.asyncio
    async def test_process_execution_event(self, monitor):
        """Test processing automation execution events."""
        # Create execution event (last_triggered changed)
        event = {
            "data": {
                "entity_id": "automation.test",
                "old_state": {
                    "state": "on",
                    "attributes": {"last_triggered": None},
                },
                "new_state": {
                    "state": "on",
                    "attributes": {"last_triggered": "2025-06-14T10:00:00Z"},
                },
            },
            "context": {"id": "test-context"},
        }
        
        # Add execution listener
        executions = []
        monitor.add_execution_listener(lambda event: executions.append(event))
        
        # Process event
        await monitor._process_event(event)
        
        # Verify execution recorded
        assert len(monitor._execution_history.get("test", [])) == 1
        assert len(executions) == 1
        
        execution = executions[0]
        assert execution.automation_id == "test"
        assert execution.timestamp == datetime.fromisoformat("2025-06-14T10:00:00+00:00")
        assert execution.context["id"] == "test-context"
    
    def test_get_automation_metrics_no_history(self, monitor):
        """Test getting metrics with no execution history."""
        metrics = monitor.get_automation_metrics("test")
        
        assert metrics["total_executions"] == 0
        assert metrics["last_execution"] is None
        assert metrics["executions_per_hour"] == 0.0
    
    def test_get_automation_metrics_with_history(self, monitor):
        """Test getting metrics with execution history."""
        # Add some execution history
        now = datetime.now()
        monitor._execution_history["test"] = [
            AutomationExecutionEvent(
                automation_id="test",
                timestamp=now.replace(hour=now.hour-2),
            ),
            AutomationExecutionEvent(
                automation_id="test",
                timestamp=now.replace(hour=now.hour-1),
            ),
            AutomationExecutionEvent(
                automation_id="test",
                timestamp=now,
            ),
        ]
        
        metrics = monitor.get_automation_metrics("test")
        
        assert metrics["total_executions"] == 3
        assert metrics["last_execution"] == now.isoformat()
        assert metrics["executions_per_hour"] > 0  # Should be ~1.5
        assert metrics["history_size"] == 3
    
    @pytest.mark.asyncio
    async def test_track_executions_stream(self, monitor):
        """Test streaming execution events."""
        # Start tracking in background
        events = []
        track_task = asyncio.create_task(
            self._collect_events(monitor.track_executions(), events)
        )
        
        # Give it a moment to set up
        await asyncio.sleep(0.1)
        
        # Simulate some executions
        for i in range(3):
            event = AutomationExecutionEvent(
                automation_id=f"test{i}",
                timestamp=datetime.now(),
            )
            for listener in monitor._execution_listeners:
                listener(event)
            await asyncio.sleep(0.05)
        
        # Cancel tracking
        track_task.cancel()
        try:
            await track_task
        except asyncio.CancelledError:
            pass
        
        # Verify events received
        assert len(events) == 3
        assert events[0].automation_id == "test0"
        assert events[1].automation_id == "test1"
        assert events[2].automation_id == "test2"
    
    async def _collect_events(self, iterator, collection):
        """Helper to collect events from async iterator."""
        try:
            async for event in iterator:
                collection.append(event)
        except asyncio.CancelledError:
            pass
    
    def test_listener_management(self, monitor):
        """Test adding and removing listeners."""
        # State listeners
        state_listener = MagicMock()
        monitor.add_state_listener(state_listener)
        assert state_listener in monitor._state_listeners
        
        monitor.remove_state_listener(state_listener)
        assert state_listener not in monitor._state_listeners
        
        # Execution listeners
        exec_listener = MagicMock()
        monitor.add_execution_listener(exec_listener)
        assert exec_listener in monitor._execution_listeners
        
        monitor.remove_execution_listener(exec_listener)
        assert exec_listener not in monitor._execution_listeners
    
    def test_get_all_states(self, monitor):
        """Test getting all automation states."""
        # Add some states
        monitor._automation_states = {
            "test1": AutomationState(
                entity_id="automation.test1",
                state="on",
            ),
            "test2": AutomationState(
                entity_id="automation.test2",
                state="off",
            ),
        }
        
        states = monitor.get_all_states()
        
        assert len(states) == 2
        assert "test1" in states
        assert "test2" in states
        # Should be a copy
        assert states is not monitor._automation_states
    
    def test_execution_history_limit(self, monitor):
        """Test execution history is limited to 100 entries."""
        # Add 150 executions
        monitor._execution_history["test"] = []
        for i in range(150):
            event = AutomationExecutionEvent(
                automation_id="test",
                timestamp=datetime.now(),
            )
            monitor._execution_history["test"].append(event)
        
        # Process one more event to trigger cleanup
        event = {
            "data": {
                "entity_id": "automation.test",
                "old_state": {"attributes": {"last_triggered": None}},
                "new_state": {"attributes": {"last_triggered": "2025-06-14T10:00:00Z"}},
            }
        }
        
        asyncio.run(monitor._process_event(event))
        
        # Should be limited to 100
        assert len(monitor._execution_history["test"]) == 100
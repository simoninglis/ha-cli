"""Real-time automation monitoring service."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .client import HAClient
from .models import AutomationState

logger = logging.getLogger(__name__)


@dataclass
class AutomationExecutionEvent:
    """Represents an automation execution event."""
    
    automation_id: str
    timestamp: datetime
    trigger: dict[str, Any] | None = None
    old_state: str | None = None
    new_state: str | None = None
    context: dict[str, Any] | None = None


@dataclass
class AutomationMonitor:
    """Real-time automation monitoring service.
    
    Tracks automation states, executions, and provides analysis.
    """
    
    client: HAClient
    _automation_states: dict[str, AutomationState] = field(default_factory=dict)
    _execution_history: dict[str, list[AutomationExecutionEvent]] = field(default_factory=dict)
    _state_listeners: list[Callable[[str, AutomationState], None]] = field(default_factory=list)
    _execution_listeners: list[Callable[[AutomationExecutionEvent], None]] = field(default_factory=list)
    _monitoring_task: asyncio.Task | None = None
    
    async def start_monitoring(self) -> None:
        """Start monitoring automation states and executions."""
        if self._monitoring_task and not self._monitoring_task.done():
            logger.warning("Monitoring already active")
            return
        
        # Load initial states
        await self._load_initial_states()
        
        # Start monitoring task
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info("Automation monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        logger.info("Automation monitoring stopped")
    
    async def _load_initial_states(self) -> None:
        """Load initial automation states."""
        try:
            states = await self.client.get_automation_states()
            for state_data in states:
                state = AutomationState(
                    entity_id=state_data["entity_id"],
                    state=state_data.get("state", "unknown"),
                    attributes=state_data.get("attributes", {}),
                )
                self._automation_states[state.automation_id] = state
            logger.info(f"Loaded {len(self._automation_states)} automation states")
        except Exception as e:
            logger.error(f"Failed to load initial states: {e}")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        try:
            async for event in self.client.subscribe_automation_events():
                await self._process_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
            # Attempt to restart monitoring after a delay
            await asyncio.sleep(5)
            if self._monitoring_task and not self._monitoring_task.done():
                asyncio.create_task(self.start_monitoring())
    
    async def _process_event(self, event: dict[str, Any]) -> None:
        """Process a state change event."""
        try:
            data = event.get("data", {})
            entity_id = data.get("entity_id", "")
            
            if not entity_id.startswith("automation."):
                return
            
            # Extract automation ID
            automation_id = entity_id.replace("automation.", "")
            
            # Create state from event data
            new_state_data = data.get("new_state", {})
            old_state_data = data.get("old_state", {})
            
            new_state = AutomationState(
                entity_id=entity_id,
                state=new_state_data.get("state", "unknown"),
                attributes=new_state_data.get("attributes", {}),
            )
            
            # Check if this is an execution event
            old_last_triggered = old_state_data.get("attributes", {}).get("last_triggered")
            new_last_triggered = new_state_data.get("attributes", {}).get("last_triggered")
            
            if old_last_triggered != new_last_triggered and new_last_triggered:
                # Automation was triggered
                execution_event = AutomationExecutionEvent(
                    automation_id=automation_id,
                    timestamp=datetime.fromisoformat(new_last_triggered.replace("Z", "+00:00")),
                    old_state=old_state_data.get("state"),
                    new_state=new_state_data.get("state"),
                    context=event.get("context"),
                )
                
                # Add to history
                if automation_id not in self._execution_history:
                    self._execution_history[automation_id] = []
                self._execution_history[automation_id].append(execution_event)
                
                # Keep only last 100 executions per automation
                if len(self._execution_history[automation_id]) > 100:
                    self._execution_history[automation_id] = self._execution_history[automation_id][-100:]
                
                # Notify listeners
                for listener in self._execution_listeners:
                    try:
                        listener(execution_event)
                    except Exception as e:
                        logger.error(f"Execution listener error: {e}")
            
            # Update state
            old_state = self._automation_states.get(automation_id)
            self._automation_states[automation_id] = new_state
            
            # Notify state listeners if state changed
            if old_state != new_state:
                for listener in self._state_listeners:
                    try:
                        listener(automation_id, new_state)
                    except Exception as e:
                        logger.error(f"State listener error: {e}")
                        
        except Exception as e:
            logger.error(f"Error processing event: {e}")
    
    def get_automation_state(self, automation_id: str) -> AutomationState | None:
        """Get current state of an automation."""
        return self._automation_states.get(automation_id)
    
    def get_all_states(self) -> dict[str, AutomationState]:
        """Get all automation states."""
        return self._automation_states.copy()
    
    def get_execution_history(self, automation_id: str) -> list[AutomationExecutionEvent]:
        """Get execution history for an automation."""
        return self._execution_history.get(automation_id, []).copy()
    
    def add_state_listener(self, listener: Callable[[str, AutomationState], None]) -> None:
        """Add a state change listener."""
        self._state_listeners.append(listener)
    
    def remove_state_listener(self, listener: Callable[[str, AutomationState], None]) -> None:
        """Remove a state change listener."""
        if listener in self._state_listeners:
            self._state_listeners.remove(listener)
    
    def add_execution_listener(self, listener: Callable[[AutomationExecutionEvent], None]) -> None:
        """Add an execution event listener."""
        self._execution_listeners.append(listener)
    
    def remove_execution_listener(self, listener: Callable[[AutomationExecutionEvent], None]) -> None:
        """Remove an execution event listener."""
        if listener in self._execution_listeners:
            self._execution_listeners.remove(listener)
    
    async def track_executions(self) -> AsyncIterator[AutomationExecutionEvent]:
        """Stream automation execution events in real-time."""
        # Create a queue for this iterator
        queue: asyncio.Queue[AutomationExecutionEvent] = asyncio.Queue()
        
        def queue_listener(event: AutomationExecutionEvent) -> None:
            """Put events in the queue."""
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest event if queue is full
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
        
        # Add listener
        self.add_execution_listener(queue_listener)
        
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            # Remove listener on exit
            self.remove_execution_listener(queue_listener)
    
    def get_automation_metrics(self, automation_id: str) -> dict[str, Any]:
        """Get execution metrics for an automation."""
        history = self._execution_history.get(automation_id, [])
        
        if not history:
            return {
                "total_executions": 0,
                "last_execution": None,
                "executions_per_hour": 0.0,
            }
        
        # Calculate metrics
        total = len(history)
        last_execution = history[-1].timestamp
        
        # Calculate rate (executions per hour) over the history period
        if total > 1:
            first_execution = history[0].timestamp
            time_span = (last_execution - first_execution).total_seconds() / 3600  # hours
            rate = total / time_span if time_span > 0 else 0.0
        else:
            rate = 0.0
        
        return {
            "total_executions": total,
            "last_execution": last_execution.isoformat(),
            "executions_per_hour": round(rate, 2),
            "history_size": len(history),
        }
    
    def get_all_metrics(self) -> dict[str, dict[str, Any]]:
        """Get metrics for all monitored automations."""
        return {
            automation_id: self.get_automation_metrics(automation_id)
            for automation_id in self._automation_states
        }
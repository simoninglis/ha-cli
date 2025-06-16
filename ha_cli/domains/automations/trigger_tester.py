"""Interactive trigger testing service."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ...common.client import HAClient

logger = logging.getLogger(__name__)


@dataclass
class TriggerEvent:
    """Represents a trigger event."""
    
    timestamp: datetime
    trigger_data: dict[str, Any]
    variables: dict[str, Any]
    context: dict[str, Any] | None = None
    
    def get_trigger_description(self) -> str:
        """Get a human-readable description of the trigger."""
        trigger = self.variables.get("trigger", {})
        platform = trigger.get("platform", "unknown")
        
        descriptions = {
            "state": self._describe_state_trigger,
            "time": self._describe_time_trigger,
            "time_pattern": self._describe_time_pattern_trigger,
            "event": self._describe_event_trigger,
            "numeric_state": self._describe_numeric_state_trigger,
            "sun": self._describe_sun_trigger,
            "zone": self._describe_zone_trigger,
            "webhook": self._describe_webhook_trigger,
            "mqtt": self._describe_mqtt_trigger,
        }
        
        describe_func = descriptions.get(platform, self._describe_generic_trigger)
        return describe_func(trigger)
    
    def _describe_state_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe a state trigger."""
        entity = trigger.get("entity_id", "unknown")
        from_state = trigger.get("from_state", {})
        to_state = trigger.get("to_state", {})
        
        if from_state and to_state:
            return f"State: {entity} changed from {from_state.get('state')} to {to_state.get('state')}"
        elif to_state:
            return f"State: {entity} changed to {to_state.get('state')}"
        else:
            return f"State: {entity} changed"
    
    def _describe_time_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe a time trigger."""
        at = trigger.get("at", trigger.get("now", "unknown"))
        return f"Time: Triggered at {at}"
    
    def _describe_time_pattern_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe a time pattern trigger."""
        parts = []
        if "hours" in trigger:
            parts.append(f"hours={trigger['hours']}")
        if "minutes" in trigger:
            parts.append(f"minutes={trigger['minutes']}")
        if "seconds" in trigger:
            parts.append(f"seconds={trigger['seconds']}")
        return f"Time Pattern: {', '.join(parts) or 'every interval'}"
    
    def _describe_event_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe an event trigger."""
        event_type = trigger.get("event_type", "unknown")
        event_data = trigger.get("event_data", {})
        if event_data:
            return f"Event: {event_type} with data {event_data}"
        return f"Event: {event_type}"
    
    def _describe_numeric_state_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe a numeric state trigger."""
        entity = trigger.get("entity_id", "unknown")
        above = trigger.get("above")
        below = trigger.get("below")
        
        if above is not None and below is not None:
            return f"Numeric State: {entity} between {above} and {below}"
        elif above is not None:
            return f"Numeric State: {entity} above {above}"
        elif below is not None:
            return f"Numeric State: {entity} below {below}"
        else:
            return f"Numeric State: {entity}"
    
    def _describe_sun_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe a sun trigger."""
        event = trigger.get("event", "unknown")
        offset = trigger.get("offset", "")
        if offset:
            return f"Sun: {event} with offset {offset}"
        return f"Sun: {event}"
    
    def _describe_zone_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe a zone trigger."""
        entity = trigger.get("entity_id", "unknown")
        zone = trigger.get("zone", "unknown")
        event = trigger.get("event", "enter/leave")
        return f"Zone: {entity} {event} {zone}"
    
    def _describe_webhook_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe a webhook trigger."""
        webhook_id = trigger.get("webhook_id", "unknown")
        return f"Webhook: {webhook_id}"
    
    def _describe_mqtt_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe an MQTT trigger."""
        topic = trigger.get("topic", "unknown")
        payload = trigger.get("payload")
        if payload:
            return f"MQTT: {topic} = {payload}"
        return f"MQTT: {topic}"
    
    def _describe_generic_trigger(self, trigger: dict[str, Any]) -> str:
        """Describe a generic trigger."""
        platform = trigger.get("platform", "unknown")
        return f"{platform.title()} trigger"


@dataclass
class TriggerTestResult:
    """Result of a trigger test."""
    
    trigger_config: dict[str, Any]
    events_received: list[TriggerEvent] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    error: str | None = None
    
    @property
    def duration(self) -> float | None:
        """Get test duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def success(self) -> bool:
        """Check if test was successful."""
        return self.error is None and len(self.events_received) > 0


@dataclass
class TriggerTester:
    """Service for testing automation triggers interactively."""
    
    client: HAClient
    _active_tests: dict[str, asyncio.Task] = field(default_factory=dict)
    
    async def test_trigger(
        self,
        trigger_config: dict[str, Any],
        timeout: float = 60.0,
        max_events: int = 10,
    ) -> TriggerTestResult:
        """Test a trigger configuration.
        
        Args:
            trigger_config: Trigger configuration to test
            timeout: Maximum time to wait for trigger events
            max_events: Maximum number of events to collect
            
        Returns:
            Test result with collected events
        """
        result = TriggerTestResult(
            trigger_config=trigger_config,
            start_time=datetime.now(),
        )
        
        try:
            logger.info(f"Starting trigger test for: {trigger_config}")
            
            # Collect events with timeout
            async with asyncio.timeout(timeout):
                event_count = 0
                async for event in self.client.subscribe_trigger(trigger_config):
                    trigger_event = TriggerEvent(
                        timestamp=datetime.now(),
                        trigger_data=trigger_config,
                        variables=event.get("variables", {}),
                        context=event.get("context"),
                    )
                    result.events_received.append(trigger_event)
                    event_count += 1
                    
                    logger.info(f"Trigger fired: {trigger_event.get_trigger_description()}")
                    
                    if event_count >= max_events:
                        logger.info(f"Reached maximum event count ({max_events})")
                        break
                        
        except asyncio.TimeoutError:
            logger.info(f"Trigger test timed out after {timeout}s")
            if not result.events_received:
                result.error = f"No trigger events received within {timeout}s"
        except Exception as e:
            logger.error(f"Trigger test error: {e}")
            result.error = str(e)
        finally:
            result.end_time = datetime.now()
        
        return result
    
    async def test_trigger_interactive(
        self,
        trigger_config: dict[str, Any],
        callback: Callable[[TriggerEvent], None] | None = None,
    ) -> AsyncIterator[TriggerEvent]:
        """Test a trigger interactively, yielding events as they occur.
        
        Args:
            trigger_config: Trigger configuration to test
            callback: Optional callback for each event
            
        Yields:
            Trigger events as they occur
        """
        logger.info(f"Starting interactive trigger test for: {trigger_config}")
        
        try:
            async for event in self.client.subscribe_trigger(trigger_config):
                trigger_event = TriggerEvent(
                    timestamp=datetime.now(),
                    trigger_data=trigger_config,
                    variables=event.get("variables", {}),
                    context=event.get("context"),
                )
                
                logger.debug(f"Trigger fired: {trigger_event.get_trigger_description()}")
                
                if callback:
                    try:
                        callback(trigger_event)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
                
                yield trigger_event
                
        except Exception as e:
            logger.error(f"Interactive trigger test error: {e}")
            raise
    
    def start_background_test(
        self,
        test_id: str,
        trigger_config: dict[str, Any],
        callback: Callable[[TriggerEvent], None] | None = None,
    ) -> None:
        """Start a background trigger test.
        
        Args:
            test_id: Unique identifier for this test
            trigger_config: Trigger configuration to test
            callback: Optional callback for each event
        """
        if test_id in self._active_tests:
            raise ValueError(f"Test {test_id} is already running")
        
        async def run_test():
            """Run the test in background."""
            try:
                async for event in self.test_trigger_interactive(trigger_config, callback):
                    pass  # Events are handled by callback
            except asyncio.CancelledError:
                logger.info(f"Background test {test_id} cancelled")
                raise
            except Exception as e:
                logger.error(f"Background test {test_id} error: {e}")
        
        task = asyncio.create_task(run_test())
        self._active_tests[test_id] = task
        logger.info(f"Started background test: {test_id}")
    
    def stop_background_test(self, test_id: str) -> bool:
        """Stop a background trigger test.
        
        Args:
            test_id: Test identifier
            
        Returns:
            True if test was stopped, False if not found
        """
        if test_id not in self._active_tests:
            return False
        
        task = self._active_tests[test_id]
        task.cancel()
        del self._active_tests[test_id]
        logger.info(f"Stopped background test: {test_id}")
        return True
    
    def get_active_tests(self) -> list[str]:
        """Get list of active test IDs."""
        # Clean up completed tasks
        completed = [
            test_id for test_id, task in self._active_tests.items()
            if task.done()
        ]
        for test_id in completed:
            del self._active_tests[test_id]
        
        return list(self._active_tests.keys())
    
    async def stop_all_tests(self) -> None:
        """Stop all active tests."""
        tasks = list(self._active_tests.values())
        test_ids = list(self._active_tests.keys())
        
        for task in tasks:
            task.cancel()
        
        # Wait for all to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._active_tests.clear()
        logger.info(f"Stopped {len(test_ids)} background tests")
    
    def validate_trigger_config(self, trigger_config: dict[str, Any]) -> list[str]:
        """Validate a trigger configuration.
        
        Args:
            trigger_config: Trigger configuration to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check required fields
        if not isinstance(trigger_config, dict):
            errors.append("Trigger configuration must be a dictionary")
            return errors
        
        if "platform" not in trigger_config:
            errors.append("Missing required field: platform")
        
        platform = trigger_config.get("platform", "")
        
        # Platform-specific validation
        if platform == "state":
            if "entity_id" not in trigger_config:
                errors.append("State trigger requires entity_id")
        elif platform == "time":
            if "at" not in trigger_config:
                errors.append("Time trigger requires 'at' field")
        elif platform == "time_pattern":
            if not any(k in trigger_config for k in ["hours", "minutes", "seconds"]):
                errors.append("Time pattern trigger requires at least one of: hours, minutes, seconds")
        elif platform == "numeric_state":
            if "entity_id" not in trigger_config:
                errors.append("Numeric state trigger requires entity_id")
            if not any(k in trigger_config for k in ["above", "below"]):
                errors.append("Numeric state trigger requires 'above' or 'below'")
        elif platform == "sun":
            if "event" not in trigger_config:
                errors.append("Sun trigger requires 'event' (sunrise or sunset)")
        elif platform == "zone":
            if "entity_id" not in trigger_config:
                errors.append("Zone trigger requires entity_id")
            if "zone" not in trigger_config:
                errors.append("Zone trigger requires zone")
        elif platform == "event":
            if "event_type" not in trigger_config:
                errors.append("Event trigger requires event_type")
        elif platform == "webhook":
            if "webhook_id" not in trigger_config:
                errors.append("Webhook trigger requires webhook_id")
        elif platform == "mqtt":
            if "topic" not in trigger_config:
                errors.append("MQTT trigger requires topic")
        
        return errors
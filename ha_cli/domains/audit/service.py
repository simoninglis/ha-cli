"""Service layer for audit operations."""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from ...common.client import HAClient
from ...common.utils import compile_user_regex
from ..automations.storage.unified_automation_service import UnifiedAutomationService
from ..entities.service import EntityService
from .models import (
    AuditFinding,
    AuditResult,
    AuditSeverity,
    BrokenAutomationFinding,
    DeadEntityFinding,
    DuplicateEntityFinding,
    IntegrationHealthSummary,
    TriggerStatsFinding,
    UnusedAutomationFinding,
)

logger = logging.getLogger(__name__)

# States that indicate an entity is not functioning
DEAD_STATES = {"unavailable", "unknown"}

# Transient domains where unavailable state may be normal
TRANSIENT_DOMAINS = {
    "device_tracker",  # Users may be away
    "person",  # Users may be away
    "binary_sensor",  # Battery-powered sensors sleep
    "sensor",  # Battery-powered sensors sleep
}

# Integrations known for normal unavailable states
SLEEPER_INTEGRATIONS = {"zha", "zwave", "zwave_js", "mqtt"}

# Default days threshold for unused automations
DEFAULT_UNUSED_DAYS = 90

# Duplicate suffix pattern
DUPLICATE_SUFFIX_PATTERN = re.compile(r"^(.+)_(\d+)$")


class AuditService:
    """Service for auditing Home Assistant configuration."""

    def __init__(self, client: HAClient) -> None:
        """Initialize audit service.

        Args:
            client: Home Assistant client
        """
        self.client = client
        self._entity_service = EntityService(client)
        self._automation_service = UnifiedAutomationService(client)

    async def check_dead_entities(
        self,
        domain: str | None = None,
        integration: str | None = None,
        ignore_patterns: list[str] | None = None,
        include_disabled: bool = False,
    ) -> AuditResult:
        """Check for dead/unavailable entities.

        Args:
            domain: Optional domain filter (e.g., "sensor", "light")
            integration: Optional integration filter
            ignore_patterns: Regex patterns for entities to ignore
            include_disabled: Include entities disabled by user

        Returns:
            AuditResult with findings
        """
        start_time = time.time()
        result = AuditResult(check_name="dead-entities")

        try:
            # Get all entities
            entities = await self._entity_service.list_entities(domain_filter=domain)

            # Compile ignore patterns
            ignore_regexes = []
            if ignore_patterns:
                for pattern in ignore_patterns:
                    try:
                        ignore_regexes.append(compile_user_regex(pattern))
                    except Exception as e:
                        logger.warning(f"Invalid ignore pattern '{pattern}': {e}")

            # Track integration stats
            integration_stats: dict[str, dict[str, int]] = {}

            for entity in entities:
                # Skip if ignored by pattern
                if any(r.search(entity.entity_id) for r in ignore_regexes):
                    continue

                # Skip disabled entities unless requested
                if not include_disabled:
                    disabled_by = entity.attributes.get("disabled_by")
                    if disabled_by:
                        continue

                # Check if dead
                state = entity.state.lower() if entity.state else "unknown"
                if state in DEAD_STATES:
                    # Extract integration from entity attributes
                    entity_integration = entity.attributes.get("integration")
                    if not entity_integration:
                        # Try to infer from entity_id pattern
                        entity_integration = self._infer_integration(entity.entity_id)

                    # Filter by integration if specified
                    if integration and entity_integration != integration:
                        continue

                    # Track stats
                    if entity_integration:
                        if entity_integration not in integration_stats:
                            integration_stats[entity_integration] = {
                                "unavailable": 0,
                                "unknown": 0,
                                "total": 0,
                            }
                        integration_stats[entity_integration][state] += 1
                        integration_stats[entity_integration]["total"] += 1

                    # Determine severity
                    severity = AuditSeverity.WARNING
                    if state == "unavailable":
                        severity = AuditSeverity.ERROR

                    finding = DeadEntityFinding(
                        severity=severity,
                        category="dead-entities",
                        message=f"Entity '{entity.entity_id}' is {state}",
                        entity_id=entity.entity_id,
                        suggested_action=self._suggest_dead_entity_action(
                            entity.entity_id, state, entity_integration
                        ),
                        state=state,
                        integration=entity_integration,
                        last_changed=entity.last_changed,
                    )
                    result.findings.append(finding)

            # Build summary
            result.summary = {
                "total_checked": len(entities),
                "dead_count": len(result.findings),
                "by_integration": integration_stats,
                "filters": {
                    "domain": domain,
                    "integration": integration,
                    "ignore_patterns": ignore_patterns,
                },
            }

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error checking dead entities: {e}")

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    async def check_duplicates(
        self,
        show_disabled: bool = False,
        ignore_patterns: list[str] | None = None,
    ) -> AuditResult:
        """Check for duplicate entities with _2, _3, etc suffixes.

        Args:
            show_disabled: Include disabled entities
            ignore_patterns: Regex patterns for entities to ignore

        Returns:
            AuditResult with findings
        """
        start_time = time.time()
        result = AuditResult(check_name="duplicates")

        try:
            entities = await self._entity_service.list_entities()

            # Compile ignore patterns
            ignore_regexes = []
            if ignore_patterns:
                for pattern in ignore_patterns:
                    try:
                        ignore_regexes.append(compile_user_regex(pattern))
                    except Exception as e:
                        logger.warning(f"Invalid ignore pattern '{pattern}': {e}")

            # Group entities by base name
            entity_groups: dict[str, list[str]] = {}
            for entity in entities:
                # Skip if ignored
                if any(r.search(entity.entity_id) for r in ignore_regexes):
                    continue

                # Skip disabled unless requested
                if not show_disabled:
                    disabled_by = entity.attributes.get("disabled_by")
                    if disabled_by:
                        continue

                # Check for duplicate suffix
                match = DUPLICATE_SUFFIX_PATTERN.match(entity.entity_id)
                if match:
                    base_id = match.group(1)
                    if base_id not in entity_groups:
                        entity_groups[base_id] = []
                    entity_groups[base_id].append(entity.entity_id)

            # Create findings for duplicates
            for base_id, duplicates in entity_groups.items():
                if len(duplicates) >= 1:  # At least one duplicate suffix found
                    # Check if base entity also exists
                    all_related = [base_id] + duplicates
                    entity_ids = {e.entity_id for e in entities}
                    existing = [eid for eid in all_related if eid in entity_ids]

                    if len(existing) > 1:
                        for dup_id in duplicates:
                            match = DUPLICATE_SUFFIX_PATTERN.match(dup_id)
                            suffix = match.group(2) if match else ""

                            finding = DuplicateEntityFinding(
                                severity=AuditSeverity.WARNING,
                                category="duplicates",
                                message=f"Entity '{dup_id}' appears to be a duplicate of '{base_id}'",
                                entity_id=dup_id,
                                suggested_action=(
                                    f"Review if '{dup_id}' is needed or if '{base_id}' "
                                    f"should be used instead. Consider deleting duplicates."
                                ),
                                base_entity_id=base_id,
                                suffix=suffix,
                                all_duplicates=existing,
                            )
                            result.findings.append(finding)

            # Build summary
            result.summary = {
                "total_checked": len(entities),
                "duplicate_groups": len(entity_groups),
                "duplicate_entities": len(result.findings),
            }

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error checking duplicates: {e}")

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    async def check_broken_automations(
        self,
        ignore_patterns: list[str] | None = None,
    ) -> AuditResult:
        """Check for automations referencing non-existent entities.

        Args:
            ignore_patterns: Regex patterns for entities to ignore

        Returns:
            AuditResult with findings
        """
        start_time = time.time()
        result = AuditResult(check_name="broken-automations")

        try:
            # Get all automations and entities
            automations = await self._automation_service.list_all()
            entities = await self._entity_service.list_entities()
            entity_ids = {e.entity_id for e in entities}

            # Compile ignore patterns
            ignore_regexes = []
            if ignore_patterns:
                for pattern in ignore_patterns:
                    try:
                        ignore_regexes.append(compile_user_regex(pattern))
                    except Exception as e:
                        logger.warning(f"Invalid ignore pattern '{pattern}': {e}")

            for automation in automations:
                # Extract entity references from automation config
                refs = self._extract_entity_references(automation)

                for ref_entity, location in refs:
                    # Skip if ignored
                    if any(r.search(ref_entity) for r in ignore_regexes):
                        continue

                    # Check if entity exists
                    if ref_entity not in entity_ids:
                        finding = BrokenAutomationFinding(
                            severity=AuditSeverity.ERROR,
                            category="broken-automations",
                            message=(
                                f"Automation '{automation.alias or automation.id}' "
                                f"references non-existent entity '{ref_entity}'"
                            ),
                            automation_id=automation.id,
                            suggested_action=(
                                f"Update automation to use a valid entity or remove "
                                f"the reference to '{ref_entity}'"
                            ),
                            referenced_entity=ref_entity,
                            entity_exists=False,
                            entity_available=False,
                            reference_location=location,
                        )
                        result.findings.append(finding)

            # Build summary
            result.summary = {
                "automations_checked": len(automations),
                "broken_count": len(result.findings),
                "unique_missing_entities": len(
                    {f.referenced_entity for f in result.findings if isinstance(f, BrokenAutomationFinding)}
                ),
            }

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error checking broken automations: {e}")

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    async def check_fragile_automations(
        self,
        ignore_patterns: list[str] | None = None,
    ) -> AuditResult:
        """Check for automations referencing unavailable entities.

        Args:
            ignore_patterns: Regex patterns for entities to ignore

        Returns:
            AuditResult with findings
        """
        start_time = time.time()
        result = AuditResult(check_name="fragile-automations")

        try:
            # Get all automations and entities
            automations = await self._automation_service.list_all()
            entities = await self._entity_service.list_entities()
            entity_map = {e.entity_id: e for e in entities}

            # Compile ignore patterns
            ignore_regexes = []
            if ignore_patterns:
                for pattern in ignore_patterns:
                    try:
                        ignore_regexes.append(compile_user_regex(pattern))
                    except Exception as e:
                        logger.warning(f"Invalid ignore pattern '{pattern}': {e}")

            for automation in automations:
                # Extract entity references from automation config
                refs = self._extract_entity_references(automation)

                for ref_entity, location in refs:
                    # Skip if ignored
                    if any(r.search(ref_entity) for r in ignore_regexes):
                        continue

                    # Check if entity exists and is unavailable
                    entity = entity_map.get(ref_entity)
                    if entity:
                        state = entity.state.lower() if entity.state else ""
                        if state in DEAD_STATES:
                            finding = BrokenAutomationFinding(
                                severity=AuditSeverity.WARNING,
                                category="fragile-automations",
                                message=(
                                    f"Automation '{automation.alias or automation.id}' "
                                    f"references {state} entity '{ref_entity}'"
                                ),
                                automation_id=automation.id,
                                suggested_action=(
                                    f"Check why '{ref_entity}' is {state}. "
                                    f"The automation may not work correctly."
                                ),
                                referenced_entity=ref_entity,
                                entity_exists=True,
                                entity_available=False,
                                reference_location=location,
                            )
                            result.findings.append(finding)

            # Build summary
            result.summary = {
                "automations_checked": len(automations),
                "fragile_count": len(result.findings),
                "unique_unavailable_entities": len(
                    {f.referenced_entity for f in result.findings if isinstance(f, BrokenAutomationFinding)}
                ),
            }

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error checking fragile automations: {e}")

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    async def check_unused_automations(
        self,
        days: int = DEFAULT_UNUSED_DAYS,
        include_disabled: bool = False,
    ) -> AuditResult:
        """Check for automations that haven't triggered recently.

        Args:
            days: Number of days to consider as unused threshold
            include_disabled: Include disabled automations

        Returns:
            AuditResult with findings
        """
        start_time = time.time()
        result = AuditResult(check_name="unused-automations")

        try:
            automations = await self._automation_service.list_all()
            now = datetime.now(timezone.utc)

            never_triggered = 0
            old_triggered = 0

            for automation in automations:
                # Skip disabled automations unless requested
                # Check enabled attribute (set by UnifiedAutomationService) or assume enabled
                is_enabled = getattr(automation, "enabled", True)
                if not include_disabled and not is_enabled:
                    continue

                days_since: int | None = None
                if automation.last_triggered:
                    # Make sure last_triggered is timezone-aware
                    last_triggered = automation.last_triggered
                    if last_triggered.tzinfo is None:
                        last_triggered = last_triggered.replace(tzinfo=timezone.utc)
                    delta = now - last_triggered
                    days_since = delta.days
                else:
                    days_since = None  # Never triggered

                # Check if unused
                if days_since is None or days_since >= days:
                    severity = AuditSeverity.INFO
                    if days_since is None:
                        severity = AuditSeverity.WARNING
                        never_triggered += 1
                        message = f"Automation '{automation.alias or automation.id}' has never been triggered"
                        suggested = "Review if this automation is configured correctly or if it's needed"
                    else:
                        old_triggered += 1
                        message = (
                            f"Automation '{automation.alias or automation.id}' "
                            f"hasn't triggered in {days_since} days"
                        )
                        suggested = (
                            f"Review if this automation is still needed. "
                            f"Last triggered: {automation.last_triggered.strftime('%Y-%m-%d') if automation.last_triggered else 'never'}"
                        )

                    finding = UnusedAutomationFinding(
                        severity=severity,
                        category="unused-automations",
                        message=message,
                        automation_id=automation.id,
                        suggested_action=suggested,
                        last_triggered=automation.last_triggered,
                        days_since_trigger=days_since,
                        automation_name=automation.alias or automation.id,
                        is_enabled=is_enabled,
                    )
                    result.findings.append(finding)

            # Build summary
            result.summary = {
                "automations_checked": len(automations),
                "unused_count": len(result.findings),
                "never_triggered": never_triggered,
                "not_triggered_in_threshold": old_triggered,
                "threshold_days": days,
            }

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error checking unused automations: {e}")

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    async def check_trigger_stats(
        self,
        top: int = 20,
        days: int | None = None,
    ) -> AuditResult:
        """Get trigger statistics for automations.

        Args:
            top: Number of top/bottom results to show
            days: Optional filter for automations triggered in last N days

        Returns:
            AuditResult with findings
        """
        start_time = time.time()
        result = AuditResult(check_name="trigger-stats")

        try:
            automations = await self._automation_service.list_all()
            now = datetime.now(timezone.utc)

            # Build stats list
            stats: list[dict[str, Any]] = []
            for automation in automations:
                # Check enabled attribute (set by UnifiedAutomationService) or assume enabled
                is_enabled = getattr(automation, "enabled", True)

                days_since: int | None = None
                if automation.last_triggered:
                    last_triggered = automation.last_triggered
                    if last_triggered.tzinfo is None:
                        last_triggered = last_triggered.replace(tzinfo=timezone.utc)
                    delta = now - last_triggered
                    days_since = delta.days

                # Filter by days if specified
                if days is not None:
                    if days_since is None or days_since > days:
                        continue

                stats.append({
                    "automation_id": automation.id,
                    "automation_name": automation.alias or automation.id,
                    "last_triggered": automation.last_triggered,
                    "days_since_trigger": days_since,
                    "is_enabled": is_enabled,
                    "trigger_count": len(automation.trigger) if automation.trigger else 0,
                })

            # Sort by last_triggered (most recent first), None values last
            stats.sort(
                key=lambda x: (
                    x["last_triggered"] is None,
                    x["last_triggered"] or datetime.min.replace(tzinfo=timezone.utc),
                ),
                reverse=True,
            )

            # Create findings for most recently triggered
            most_active = stats[:top]
            for stat in most_active:
                if stat["last_triggered"] is None:
                    message = f"Automation '{stat['automation_name']}' has never been triggered"
                else:
                    days_ago = stat["days_since_trigger"]
                    message = f"Automation '{stat['automation_name']}' last triggered {days_ago} days ago"

                finding = TriggerStatsFinding(
                    severity=AuditSeverity.INFO,
                    category="trigger-stats",
                    message=message,
                    automation_id=stat["automation_id"],
                    automation_name=stat["automation_name"],
                    trigger_count=stat["trigger_count"],
                    last_triggered=stat["last_triggered"],
                    is_enabled=stat["is_enabled"],
                )
                result.findings.append(finding)

            # Build summary
            triggered_count = len([s for s in stats if s["last_triggered"]])
            result.summary = {
                "total_automations": len(automations),
                "shown": len(result.findings),
                "with_triggers": triggered_count,
                "never_triggered": len(stats) - triggered_count,
            }

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error getting trigger stats: {e}")

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    async def check_integrations(
        self,
        ignore_patterns: list[str] | None = None,
    ) -> AuditResult:
        """Get health summary per integration.

        Args:
            ignore_patterns: Regex patterns for entities to ignore

        Returns:
            AuditResult with integration health summaries
        """
        start_time = time.time()
        result = AuditResult(check_name="integrations")

        try:
            entities = await self._entity_service.list_entities()

            # Compile ignore patterns
            ignore_regexes = []
            if ignore_patterns:
                for pattern in ignore_patterns:
                    try:
                        ignore_regexes.append(compile_user_regex(pattern))
                    except Exception as e:
                        logger.warning(f"Invalid ignore pattern '{pattern}': {e}")

            # Group by integration
            integration_data: dict[str, dict[str, Any]] = {}

            for entity in entities:
                # Skip if ignored
                if any(r.search(entity.entity_id) for r in ignore_regexes):
                    continue

                # Get integration
                integration = entity.attributes.get("integration")
                if not integration:
                    integration = self._infer_integration(entity.entity_id)
                if not integration:
                    integration = "unknown"

                if integration not in integration_data:
                    integration_data[integration] = {
                        "total": 0,
                        "available": 0,
                        "unavailable": 0,
                        "unknown": 0,
                        "domains": {},
                        "unavailable_samples": [],
                    }

                data = integration_data[integration]
                data["total"] += 1

                # Track domain
                domain = entity.domain
                data["domains"][domain] = data["domains"].get(domain, 0) + 1

                # Check state
                state = entity.state.lower() if entity.state else "unknown"
                if state == "unavailable":
                    data["unavailable"] += 1
                    if len(data["unavailable_samples"]) < 5:
                        data["unavailable_samples"].append(entity.entity_id)
                elif state == "unknown":
                    data["unknown"] += 1
                else:
                    data["available"] += 1

            # Create health summaries
            summaries: list[IntegrationHealthSummary] = []
            for integration, data in integration_data.items():
                total = data["total"]
                available = data["available"]
                health_pct = (available / total * 100) if total > 0 else 0

                summary = IntegrationHealthSummary(
                    integration=integration,
                    total_entities=total,
                    available_entities=available,
                    unavailable_entities=data["unavailable"],
                    unknown_entities=data["unknown"],
                    health_percentage=health_pct,
                    domains=data["domains"],
                    sample_unavailable=data["unavailable_samples"],
                )
                summaries.append(summary)

                # Create finding if health is poor
                if health_pct < 50 and total >= 5:
                    finding = AuditFinding(
                        severity=AuditSeverity.ERROR if health_pct < 25 else AuditSeverity.WARNING,
                        category="integrations",
                        message=(
                            f"Integration '{integration}' has {health_pct:.1f}% health "
                            f"({available}/{total} entities available)"
                        ),
                        suggested_action=(
                            f"Check the '{integration}' integration configuration. "
                            f"Sample unavailable: {', '.join(data['unavailable_samples'][:3])}"
                        ),
                        details=summary.to_dict(),
                    )
                    result.findings.append(finding)

            # Sort summaries by health (worst first)
            summaries.sort(key=lambda x: x.health_percentage)

            # Build summary
            result.summary = {
                "total_integrations": len(summaries),
                "unhealthy_integrations": len(result.findings),
                "integrations": [s.to_dict() for s in summaries],
            }

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error checking integrations: {e}")

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    async def run_all_checks(
        self,
        severity_filter: AuditSeverity | None = None,
        ignore_patterns: list[str] | None = None,
        days_threshold: int = DEFAULT_UNUSED_DAYS,
    ) -> AuditResult:
        """Run all audit checks and combine results.

        Args:
            severity_filter: Only include findings at or above this severity
            ignore_patterns: Regex patterns for entities to ignore
            days_threshold: Days threshold for unused automations

        Returns:
            Combined AuditResult
        """
        start_time = time.time()
        result = AuditResult(check_name="all")

        try:
            # Run all checks
            dead_result = await self.check_dead_entities(ignore_patterns=ignore_patterns)
            duplicates_result = await self.check_duplicates(ignore_patterns=ignore_patterns)
            broken_result = await self.check_broken_automations(ignore_patterns=ignore_patterns)
            fragile_result = await self.check_fragile_automations(ignore_patterns=ignore_patterns)
            unused_result = await self.check_unused_automations(days=days_threshold)
            integrations_result = await self.check_integrations(ignore_patterns=ignore_patterns)

            # Combine findings
            all_findings = (
                dead_result.findings
                + duplicates_result.findings
                + broken_result.findings
                + fragile_result.findings
                + unused_result.findings
                + integrations_result.findings
            )

            # Apply severity filter
            if severity_filter:
                severity_order = {
                    AuditSeverity.ERROR: 0,
                    AuditSeverity.WARNING: 1,
                    AuditSeverity.INFO: 2,
                }
                filter_level = severity_order.get(severity_filter, 2)
                all_findings = [
                    f for f in all_findings
                    if severity_order.get(f.severity, 2) <= filter_level
                ]

            result.findings = all_findings

            # Build combined summary
            result.summary = {
                "checks_run": [
                    "dead-entities",
                    "duplicates",
                    "broken-automations",
                    "fragile-automations",
                    "unused-automations",
                    "integrations",
                ],
                "check_results": {
                    "dead-entities": {
                        "findings": len(dead_result.findings),
                        "error": dead_result.error,
                    },
                    "duplicates": {
                        "findings": len(duplicates_result.findings),
                        "error": duplicates_result.error,
                    },
                    "broken-automations": {
                        "findings": len(broken_result.findings),
                        "error": broken_result.error,
                    },
                    "fragile-automations": {
                        "findings": len(fragile_result.findings),
                        "error": fragile_result.error,
                    },
                    "unused-automations": {
                        "findings": len(unused_result.findings),
                        "error": unused_result.error,
                    },
                    "integrations": {
                        "findings": len(integrations_result.findings),
                        "error": integrations_result.error,
                    },
                },
            }

            # Check for any errors
            errors = [
                r.error for r in [
                    dead_result, duplicates_result, broken_result,
                    fragile_result, unused_result, integrations_result
                ]
                if r.error
            ]
            if errors:
                result.error = "; ".join(errors)

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error running all checks: {e}")

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    def _extract_entity_references(
        self,
        automation: Any,
    ) -> list[tuple[str, str]]:
        """Extract entity references from an automation config.

        Args:
            automation: Automation object

        Returns:
            List of (entity_id, location) tuples
        """
        refs: list[tuple[str, str]] = []

        def search_dict(obj: Any, location: str) -> None:
            """Recursively search for entity references."""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ["entity_id", "entity_ids"]:
                        if isinstance(value, str):
                            refs.append((value, location))
                        elif isinstance(value, list):
                            for v in value:
                                if isinstance(v, str):
                                    refs.append((v, location))
                    elif key == "target" and isinstance(value, dict):
                        for target_key, target_value in value.items():
                            if target_key in ["entity_id", "entity_ids"]:
                                if isinstance(target_value, str):
                                    refs.append((target_value, location))
                                elif isinstance(target_value, list):
                                    for v in target_value:
                                        if isinstance(v, str):
                                            refs.append((v, location))
                    elif isinstance(value, (dict, list)):
                        search_dict(value, location)
            elif isinstance(obj, list):
                for item in obj:
                    search_dict(item, location)

        # Search triggers
        if hasattr(automation, "trigger") and automation.trigger:
            search_dict(automation.trigger, "trigger")

        # Search conditions
        if hasattr(automation, "condition") and automation.condition:
            search_dict(automation.condition, "condition")

        # Search actions
        if hasattr(automation, "action") and automation.action:
            search_dict(automation.action, "action")

        return refs

    def _infer_integration(self, entity_id: str) -> str | None:
        """Try to infer integration from entity ID patterns.

        Args:
            entity_id: Entity ID

        Returns:
            Integration name or None
        """
        # Common patterns
        patterns = {
            r"^(sensor|switch|binary_sensor)\.unifi_": "unifi",
            r"^(light|sensor|binary_sensor)\.hue_": "hue",
            r"^(climate|sensor)\.climate_": "climate",
            r"^(sensor|switch)\.mqtt_": "mqtt",
            r"^device_tracker\.": "device_tracker",
            r"^(light|switch|sensor)\.zha_": "zha",
            r"^(light|switch|sensor)\.zwave_": "zwave_js",
        }

        for pattern, integration in patterns.items():
            if re.match(pattern, entity_id):
                return integration

        return None

    def _suggest_dead_entity_action(
        self,
        entity_id: str,
        state: str,
        integration: str | None,
    ) -> str:
        """Generate suggested action for a dead entity.

        Args:
            entity_id: Entity ID
            state: Current state
            integration: Integration name

        Returns:
            Suggested action string
        """
        domain = entity_id.split(".")[0]

        # Check for known transient domains
        if domain in TRANSIENT_DOMAINS:
            return (
                f"Entity may be temporarily {state} (normal for {domain}). "
                f"Check if the device/sensor is reachable."
            )

        # Check for known sleeper integrations
        if integration in SLEEPER_INTEGRATIONS:
            return (
                f"Entity from '{integration}' may be a battery device in sleep mode. "
                f"Verify device is powered and within range."
            )

        # Default suggestion
        if state == "unavailable":
            return (
                f"Entity is unavailable. Check if the device is online, "
                f"the integration is configured correctly, or consider removing "
                f"the entity if it's no longer needed."
            )
        else:
            return (
                f"Entity state is {state}. Review the entity configuration "
                f"and check if it's receiving data correctly."
            )

"""Service layer for entity management operations."""

import asyncio
import json
import logging
import re
import ssl
from datetime import datetime
from json import JSONDecodeError
from typing import Any

import websockets

from ...common.client import HAClient
from ...common.exceptions import HAAutomationError
from ...common.utils import compile_user_regex
from .models import (
    Entity,
    EntityImpactAnalysis,
    RenameOperation,
    RenamePreview,
    RenameResult,
)

logger = logging.getLogger(__name__)

# Default WebSocket timeout in seconds
WS_RECV_TIMEOUT = 30


def _search_dict_for_entity(obj: Any, entity_id: str) -> bool:
    """Recursively search for entity references in dict/list structures.

    Args:
        obj: The object to search (dict, list, or other)
        entity_id: The entity ID to search for

    Returns:
        True if the entity_id is found, False otherwise
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            # Direct entity_id references
            if key in ['entity_id', 'entity_ids']:
                if isinstance(value, str) and value == entity_id or isinstance(value, list) and entity_id in value:
                    return True
            # Service call targets (target.entity_id, target.entity_ids)
            elif key == 'target' and isinstance(value, dict):
                for target_key, target_value in value.items():
                    if target_key in ['entity_id', 'entity_ids']:
                        is_str_match = isinstance(target_value, str) and target_value == entity_id
                        is_list_match = isinstance(target_value, list) and entity_id in target_value
                        if is_str_match or is_list_match:
                            return True
            # Device/area targets that might contain entities - skip these
            elif key in ['device_id', 'device_ids', 'area_id', 'area_ids']:
                continue
            # Check nested structures
            elif isinstance(value, dict | list) and _search_dict_for_entity(value, entity_id):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _search_dict_for_entity(item, entity_id):
                return True
    return False


async def recv_with_timeout(ws: Any, timeout: float = WS_RECV_TIMEOUT) -> str:
    """Receive a WebSocket message with timeout.

    Args:
        ws: WebSocket connection
        timeout: Timeout in seconds (default: 30)

    Returns:
        Received message as string

    Raises:
        TimeoutError: If no message received within timeout
    """
    return await asyncio.wait_for(ws.recv(), timeout=timeout)


def parse_ws_message(raw_message: str, context: str = "WebSocket") -> dict:
    """Parse and validate a WebSocket message.

    Args:
        raw_message: Raw message string from WebSocket
        context: Description for error messages

    Returns:
        Parsed JSON as dictionary

    Raises:
        HAAutomationError: If message is not valid JSON or not a dict
    """
    if not isinstance(raw_message, str):
        raise HAAutomationError(
            f"{context}: Expected string message, got {type(raw_message).__name__}"
        )

    try:
        parsed = json.loads(raw_message)
    except JSONDecodeError as e:
        logger.warning(
            "%s: Failed to parse JSON: %s (message: %.100s...)", context, e, raw_message
        )
        raise HAAutomationError(f"{context}: Invalid JSON response: {e}") from e

    if not isinstance(parsed, dict):
        raise HAAutomationError(
            f"{context}: Expected dict message, got {type(parsed).__name__}"
        )

    return parsed


class EntityService:
    """Service for managing Home Assistant entities."""
    
    def __init__(self, client: HAClient):
        self.client = client
    
    async def list_entities(
        self, 
        search_pattern: str | None = None,
        domain_filter: str | None = None
    ) -> list[Entity]:
        """List entities with optional filtering.
        
        Args:
            search_pattern: Regex pattern to filter entity IDs
            domain_filter: Filter by specific domain (e.g., 'light', 'sensor')
            
        Returns:
            List of Entity objects
        """
        try:
            # Get all states from Home Assistant
            response = await self.client.get_states()
            
            entities = []
            pattern = compile_user_regex(search_pattern, "search pattern") if search_pattern else None
            
            for state_data in response:
                entity = Entity.from_ha_state(state_data)
                
                # Apply domain filter
                if domain_filter and entity.domain != domain_filter:
                    continue
                
                # Apply search pattern filter
                if pattern and not pattern.search(entity.entity_id):
                    continue
                
                entities.append(entity)
            
            # Sort by entity_id for consistent ordering
            return sorted(entities, key=lambda e: e.entity_id)
            
        except Exception as e:
            raise HAAutomationError(f"Failed to list entities: {e}") from e

    async def get_entity(self, entity_id: str) -> Entity | None:
        """Get a specific entity by ID.

        Args:
            entity_id: The entity ID to retrieve

        Returns:
            Entity object or None if not found
        """
        try:
            # Get all states and find the specific entity
            all_states = await self.client.get_states()
            for state_data in all_states:
                if state_data["entity_id"] == entity_id:
                    return Entity.from_ha_state(state_data)
            return None
        except Exception as e:
            logger.debug("Failed to get entity %s: %s", entity_id, e)
            return None

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """Get current state of an entity via REST API.

        Uses REST API GET /api/states/<entity_id> which is more efficient
        than scanning all states via WebSocket.

        Args:
            entity_id: The entity ID to query

        Returns:
            State data dict with entity_id, state, attributes, etc.

        Raises:
            HAAutomationError: If entity not found or API error
        """
        endpoint = f"/api/states/{entity_id}"
        result = await self.client._rest("GET", endpoint)
        return dict(result) if isinstance(result, dict) else {}
    
    def preview_rename(
        self, 
        search_pattern: str, 
        replace_pattern: str, 
        entities: list[Entity]
    ) -> RenamePreview:
        """Preview rename operations without executing them.
        
        Args:
            search_pattern: Regex pattern to search for
            replace_pattern: Replacement pattern
            entities: List of entities to process
            
        Returns:
            RenamePreview with validation results
        """
        operations = []
        pattern = compile_user_regex(search_pattern, "search pattern")
        
        for entity in entities:
            if pattern.search(entity.entity_id):
                new_id = re.sub(search_pattern, replace_pattern, entity.entity_id)
                if new_id != entity.entity_id:
                    operation = RenameOperation(
                        old_entity_id=entity.entity_id,
                        new_entity_id=new_id,
                        friendly_name=entity.friendly_name
                    )
                    operations.append(operation)
        
        return RenamePreview.from_operations(operations)
    
    async def execute_rename_operations(self, operations: list[RenameOperation]) -> list[RenameResult]:
        """Execute rename operations via WebSocket API.
        
        Args:
            operations: List of rename operations to execute
            
        Returns:
            List of RenameResult objects
        """
        if not operations:
            return []
        
        results = []
        
        # Create WebSocket connection URL
        ws_url = self.client.url.replace("http", "ws") + "/api/websocket"
        
        # Handle SSL context for HTTPS
        ssl_context = None
        if ws_url.startswith("wss://") and not getattr(self.client, 'verify_ssl', True):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            # Connect to WebSocket
            async with websockets.connect(ws_url, ssl=ssl_context) as websocket:

                # Wait for auth request (with timeout)
                try:
                    auth_req = await recv_with_timeout(websocket)
                    logger.debug("Received auth request: %.100s...", auth_req)
                except TimeoutError as e:
                    raise HAAutomationError(
                        "WebSocket auth request timeout after 30s"
                    ) from e

                # Authenticate
                auth_msg = {
                    "type": "auth",
                    "access_token": self.client.token
                }
                await websocket.send(json.dumps(auth_msg))

                # Wait for auth result (with timeout and validation)
                try:
                    auth_raw = await recv_with_timeout(websocket)
                    auth_result = parse_ws_message(auth_raw, "Auth response")
                except TimeoutError as e:
                    raise HAAutomationError(
                        "WebSocket auth response timeout after 30s"
                    ) from e

                if auth_result.get("type") != "auth_ok":
                    raise HAAutomationError(
                        f"WebSocket authentication failed: {auth_result}"
                    )

                # Execute rename operations
                for i, operation in enumerate(operations, start=1):
                    try:
                        rename_msg = {
                            "id": i,
                            "type": "config/entity_registry/update",
                            "entity_id": operation.old_entity_id,
                            "new_entity_id": operation.new_entity_id
                        }
                        await websocket.send(json.dumps(rename_msg))

                        # Wait for response (with timeout and validation)
                        try:
                            response_raw = await recv_with_timeout(websocket)
                            response = parse_ws_message(
                                response_raw,
                                f"Rename response for {operation.old_entity_id}"
                            )
                        except TimeoutError:
                            logger.warning(
                                "Timeout waiting for rename response: %s",
                                operation.old_entity_id
                            )
                            result = RenameResult(
                                operation=operation,
                                success=False,
                                error_message="Timeout waiting for response after 30s",
                                timestamp=datetime.now()
                            )
                            results.append(result)
                            continue

                        if response.get("success", False):
                            result = RenameResult(
                                operation=operation,
                                success=True,
                                error_message=None,
                                timestamp=datetime.now()
                            )
                        else:
                            error_msg = response.get("error", {}).get("message", "Unknown error")
                            result = RenameResult(
                                operation=operation,
                                success=False,
                                error_message=error_msg,
                                timestamp=datetime.now()
                            )

                        results.append(result)

                    except HAAutomationError as e:
                        # Re-raise HAAutomationError from parse_ws_message
                        result = RenameResult(
                            operation=operation,
                            success=False,
                            error_message=str(e),
                            timestamp=datetime.now()
                        )
                        results.append(result)
                    except Exception as e:
                        logger.warning(
                            "Unexpected error during rename of %s: %s",
                            operation.old_entity_id, e
                        )
                        result = RenameResult(
                            operation=operation,
                            success=False,
                            error_message=str(e),
                            timestamp=datetime.now()
                        )
                        results.append(result)

        except HAAutomationError:
            # Re-raise HAAutomationError (auth failures, parse errors)
            raise
        except TimeoutError as e:
            logger.error("WebSocket timeout during rename operations: %s", e)
            # Create failure results for all remaining operations
            for operation in operations:
                already_processed = any(
                    r.operation.old_entity_id == operation.old_entity_id
                    for r in results
                )
                if not already_processed:
                    result = RenameResult(
                        operation=operation,
                        success=False,
                        error_message=f"WebSocket timeout: {e}",
                        timestamp=datetime.now()
                    )
                    results.append(result)
        except Exception as e:
            logger.error("WebSocket connection failed: %s", e)
            # Create failure results for all remaining operations
            for operation in operations:
                already_processed = any(
                    r.operation.old_entity_id == operation.old_entity_id
                    for r in results
                )
                if not already_processed:
                    result = RenameResult(
                        operation=operation,
                        success=False,
                        error_message=f"WebSocket connection failed: {e}",
                        timestamp=datetime.now()
                    )
                    results.append(result)

        return results
    
    async def analyze_entity_impact(self, entity_id: str) -> EntityImpactAnalysis:
        """Analyze the impact of changing an entity on automations and dashboards.
        
        Args:
            entity_id: The entity ID to analyze
            
        Returns:
            EntityImpactAnalysis with reference information
        """
        automation_refs = []
        dashboard_refs = []
        
        try:
            # Import the automation and dashboard services
            from ..automations.storage.unified_automation_service import (
                UnifiedAutomationService,
            )
            from ..dashboards.service import DashboardService
            
            # Check automation references
            automation_service = UnifiedAutomationService(self.client)
            try:
                automations = await automation_service.list_all()
                
                for automation in automations:
                    # Check if entity is referenced in automation configuration
                    if self._entity_referenced_in_automation(entity_id, automation):
                        automation_refs.append(automation.id or automation.alias)
                    # Also check for potential references based on naming patterns
                    elif self._entity_likely_referenced_in_automation(entity_id, automation):
                        automation_refs.append(f"{automation.id or automation.alias} (likely)")
            except Exception:
                # If automation service fails, try alternative methods
                automation_refs = await self._analyze_automation_references_alternative(entity_id)
                pass
            
            # Check dashboard references
            dashboard_service = DashboardService(self.client)
            try:
                dashboards = await dashboard_service.list_dashboards()
                
                for dashboard in dashboards:
                    try:
                        # Get entity references with their locations (including views)
                        entity_locations = await dashboard_service.get_entity_references_with_location(dashboard.url_path)
                        
                        # Check if our entity is referenced anywhere in this dashboard
                        if entity_id in entity_locations:
                            # Add all locations where this entity appears
                            for location in entity_locations[entity_id]:
                                if location not in dashboard_refs:
                                    dashboard_refs.append(location)
                    except Exception as e:
                        # Skip this dashboard if we can't get its config
                        logger.debug("Skipping dashboard %s: %s", dashboard.url_path, e)
                        continue
            except Exception as e:
                # If dashboard service fails, continue with empty list
                logger.debug("Dashboard service failed for entity %s: %s", entity_id, e)
            
            return EntityImpactAnalysis.create(entity_id, automation_refs, dashboard_refs)
            
        except Exception:
            # Return empty analysis on error
            return EntityImpactAnalysis.create(entity_id, [], [])
    
    def _entity_referenced_in_automation(self, entity_id: str, automation: Any) -> bool:
        """Check if an entity is referenced in an automation configuration."""
        # Check triggers, conditions, and actions using consolidated helper
        for section in [automation.trigger, automation.condition, automation.action]:
            if section and _search_dict_for_entity(section, entity_id):
                return True

        return False

    def _entity_referenced_in_dashboard(self, entity_id: str, dashboard_config: Any) -> bool:
        """Check if an entity is referenced in a dashboard configuration."""
        def search_dashboard_structure(obj: Any) -> bool:
            """Recursively search for entity references in dashboard structure."""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == 'entity' and value == entity_id or key == 'entities' and isinstance(value, list) and entity_id in value:
                        return True
                    elif key in ['entity_id', 'entity_ids']:
                        if isinstance(value, str) and value == entity_id or isinstance(value, list) and entity_id in value:
                            return True
                    elif isinstance(value, dict | list) and search_dashboard_structure(value):
                        return True
            elif isinstance(obj, list):
                for item in obj:
                    if search_dashboard_structure(item):
                        return True
            return False

        # Check the dashboard configuration structure
        config_dict = dashboard_config.model_dump() if hasattr(dashboard_config, 'model_dump') else dashboard_config

        return bool(search_dashboard_structure(config_dict))
    
    def export_entities_to_csv(self, entities: list[Entity], output_file: str) -> None:
        """Export entities to CSV file.
        
        Args:
            entities: List of entities to export
            output_file: Path to output CSV file
        """
        import csv
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['entity_id', 'friendly_name', 'domain', 'state']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for entity in entities:
                writer.writerow({
                    'entity_id': entity.entity_id,
                    'friendly_name': entity.friendly_name,
                    'domain': entity.domain,
                    'state': entity.state
                })
    
    def import_operations_from_csv(self, csv_file: str) -> list[RenameOperation]:
        """Import rename operations from CSV file.
        
        Args:
            csv_file: Path to CSV file containing rename operations
            
        Returns:
            List of RenameOperation objects
        """
        import csv
        
        operations = []
        
        with open(csv_file, encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                if 'old_entity_id' in row and 'new_entity_id' in row:
                    operation = RenameOperation(
                        old_entity_id=row['old_entity_id'],
                        new_entity_id=row['new_entity_id'],
                        friendly_name=row.get('friendly_name', '')
                    )
                    operations.append(operation)
        
        return operations

    def _entity_likely_referenced_in_automation(self, entity_id: str, automation: Any) -> bool:
        """Check if an entity is likely referenced in an automation based on naming patterns.
        
        This is used when full automation configuration is not available (WebSocket mode).
        Uses heuristic analysis of automation names and entity patterns.
        """
        if not automation.alias and not automation.id:
            return False
            
        automation_name = (automation.alias or automation.id or "").lower()
        entity_domain = entity_id.split('.')[0]
        entity_name = entity_id.split('.')[1] if '.' in entity_id else ""
        
        # Climate entity specific patterns
        if entity_domain == "climate":
            import re
            
            # Only match automations with strong climate/AC indicators using word boundaries
            ac_pattern = r'\bac\b'  # Match "ac" as whole word
            climate_pattern = r'\bclimate\b'
            
            has_ac = bool(re.search(ac_pattern, automation_name))
            has_climate = bool(re.search(climate_pattern, automation_name))
            
            if has_ac or has_climate:
                # For specific entity locations, require exact matching
                location_matches = (
                    (entity_name == "master_bedroom" and "master" in automation_name)
                    or (entity_name == "bedroom_2" and "bed" in automation_name)
                    or (entity_name == "office_ac" and "office" in automation_name)
                    or (entity_name == "lounge" and "lounge" in automation_name)
                    or (entity_name == "office_store" and "office" in automation_name)
                    or (has_ac and not any(loc in automation_name for loc in ["master", "bed", "office", "lounge"]))
                )
                if location_matches:
                    return True
            return False
                    
        # General domain matching - only for non-climate entities since climate is handled above
        if entity_domain != "climate":
            domain_automation_patterns = {
                "light": ["light", "lamp", "bright", "dim", "illuminate"],
                "switch": ["switch", "toggle", "turn", "power"],
                "sensor": ["sensor", "temperature", "humidity", "motion"],
                "binary_sensor": ["motion", "door", "window", "alarm"],
                "media_player": ["media", "music", "tv", "volume", "play"],
                "cover": ["blind", "shade", "curtain", "cover", "window"],
                "vacuum": ["vacuum", "clean", "sweep", "mop"],
            }
            
            if entity_domain in domain_automation_patterns:
                patterns = domain_automation_patterns[entity_domain]
                # Require at least one pattern match AND some location/context matching
                if any(pattern in automation_name for pattern in patterns):
                    # Extract entity location and check for context matching
                    entity_parts = entity_name.split('_')
                    for part in entity_parts:
                        if len(part) > 2 and part in automation_name:  # Avoid short words
                            return True
                
        return False
    
    async def _analyze_automation_references_alternative(self, entity_id: str) -> list[str]:
        """Alternative method to analyze automation references when full config is not available.
        
        This method tries multiple approaches to access automation configurations.
        """
        references = []
        
        try:
            # Method 1: Try File Editor API if available
            references = await self._try_file_editor_api(entity_id)
            if references:
                return references
                
            # Method 2: Try python script approach
            references = await self._try_python_script_analysis(entity_id)
            if references:
                return references
                
            # Method 3: Fall back to pattern-based analysis
            references = await self._try_pattern_based_analysis(entity_id)
            
        except Exception as e:
            # If all methods fail, return empty list
            logger.debug(f"Error getting entity references for {entity_id}: {e}")

        return references

    async def _try_file_editor_api(self, entity_id: str) -> list[str]:
        """Try to access automation files via File Editor API.

        Uses httpx for HTTP requests (consistent with rest of codebase).
        """
        references = []

        try:
            import httpx
            import yaml

            # Try multiple access methods for File Editor
            token = getattr(self.client, '_token', '')
            access_methods = [
                # Method 1: Direct access on port 3218 (if enabled)
                {"base_url": "http://10.0.20.35:3218", "headers": {}},
                # Method 2: Through Home Assistant API proxy (if ingress available)
                {"base_url": "http://10.0.20.35:8123/api/hassio_ingress", "headers": {"Authorization": f"Bearer {token}"}},
                # Method 3: Try without authentication first (some configurations don't require it)
                {"base_url": "http://10.0.20.35:3218", "headers": {"User-Agent": "ha-cli/1.0"}},
            ]

            # Common automation file locations
            automation_files = [
                "/config/automations.yaml",
                "/config/automations/climate.yaml",
                "/config/automations/master_bedroom.yaml",
                "/config/automations/bedroom.yaml",
                "/config/automations/office.yaml",
                "/config/automations/general.yaml"
            ]

            for method in access_methods:
                base_url = str(method["base_url"])
                headers: dict[str, str] = dict(method["headers"])  # type: ignore[arg-type]

                try:
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        for file_path in automation_files:
                            try:
                                url = f"{base_url}/api/file?filename={file_path}"

                                response = await client.get(url, headers=headers)
                                if response.status_code == 200:
                                    content = response.text

                                    # Handle both single automation and list of automations
                                    try:
                                        automations_data = yaml.safe_load(content)
                                        if not automations_data:
                                            continue

                                        # If it's a single automation dict, wrap in list
                                        if isinstance(automations_data, dict):
                                            automations_data = [automations_data]

                                        for automation in automations_data:
                                            if isinstance(automation, dict) and self._entity_in_automation_config(entity_id, automation):
                                                alias = automation.get('alias', automation.get('id', f'automation from {file_path}'))
                                                references.append(f"{alias} (confirmed)")

                                    except yaml.YAMLError as e:
                                        # Skip files with YAML errors
                                        logger.debug("YAML error in %s: %s", file_path, e)
                                        continue

                            except Exception as e:
                                # Skip inaccessible files
                                logger.debug("Cannot access file %s: %s", file_path, e)
                                continue

                    # If we found references with this method, return them
                    if references:
                        return references

                except Exception as e:
                    # Try next access method
                    logger.debug("File Editor access method failed: %s", e)
                    continue

        except ImportError:
            # httpx not available (shouldn't happen as it's a core dependency)
            logger.debug("httpx not available for File Editor API access")
        except Exception as e:
            logger.debug("File Editor API access failed: %s", e)

        return references

    async def _try_python_script_analysis(self, entity_id: str) -> list[str]:
        """Try to use python scripts to analyze automation files."""
        # This would require creating a custom python script
        # For now, return empty list - no try/except needed for stub
        return []
    
    async def _try_pattern_based_analysis(self, entity_id: str) -> list[str]:
        """Fall back to pattern-based analysis using WebSocket data."""
        references = []
        
        try:
            # Get all automation states via WebSocket
            states = await self.client.get_automation_states()
            
            for state in states:
                automation_entity_id = state.get("entity_id", "")
                automation_id = automation_entity_id.replace("automation.", "")
                attributes = state.get("attributes", {})
                automation_name = attributes.get("friendly_name", automation_id)
                
                # Create a minimal automation object for pattern matching
                class AutomationInfo:
                    def __init__(self, id: str, alias: str) -> None:
                        self.id = id
                        self.alias = alias
                
                automation_info = AutomationInfo(automation_id, automation_name)
                
                # Check using naming patterns
                if self._entity_likely_referenced_in_automation(entity_id, automation_info):
                    references.append(f"{automation_name} (pattern match)")
                    
        except Exception as e:
            # If all methods fail, return empty list with explanation
            logger.debug(f"Error in pattern-based analysis for {entity_id}: {e}")

        return references

    def _entity_in_automation_config(self, entity_id: str, automation_config: dict) -> bool:
        """Check if an entity is referenced in a full automation configuration."""
        # Check triggers, conditions, and actions using consolidated helper
        for section in ['trigger', 'condition', 'action']:
            if section in automation_config and _search_dict_for_entity(automation_config[section], entity_id):
                return True

        return False
    
    async def delete_entities(self, entity_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Delete entities via WebSocket API.
        
        Args:
            entity_ids: List of entity IDs to delete
            
        Returns:
            Dict mapping entity_id to result dict with 'success' and optional 'error' keys
        """
        if not entity_ids:
            return {}
        
        results = {}
        
        # Create WebSocket connection URL
        ws_url = self.client.url.replace("http", "ws") + "/api/websocket"
        
        # Handle SSL context for HTTPS
        ssl_context = None
        if ws_url.startswith("wss://") and not getattr(self.client, 'verify_ssl', True):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            # Connect to WebSocket
            async with websockets.connect(ws_url, ssl=ssl_context) as websocket:

                # Wait for auth request (with timeout)
                try:
                    auth_req = await recv_with_timeout(websocket)
                    logger.debug("Received auth request: %.100s...", auth_req)
                except TimeoutError as e:
                    raise HAAutomationError(
                        "WebSocket auth request timeout after 30s"
                    ) from e

                # Authenticate
                auth_msg = {
                    "type": "auth",
                    "access_token": self.client.token
                }
                await websocket.send(json.dumps(auth_msg))

                # Wait for auth result (with timeout and validation)
                try:
                    auth_raw = await recv_with_timeout(websocket)
                    auth_result = parse_ws_message(auth_raw, "Auth response")
                except TimeoutError as e:
                    raise HAAutomationError(
                        "WebSocket auth response timeout after 30s"
                    ) from e

                if auth_result.get("type") != "auth_ok":
                    raise HAAutomationError(
                        f"WebSocket authentication failed: {auth_result}"
                    )

                # Execute delete operations
                for i, entity_id in enumerate(entity_ids, start=1):
                    try:
                        delete_msg = {
                            "id": i,
                            "type": "config/entity_registry/remove",
                            "entity_id": entity_id
                        }
                        await websocket.send(json.dumps(delete_msg))

                        # Wait for response (with timeout and validation)
                        try:
                            response_raw = await recv_with_timeout(websocket)
                            response = parse_ws_message(
                                response_raw, f"Delete response for {entity_id}"
                            )
                        except TimeoutError:
                            logger.warning(
                                "Timeout waiting for delete response: %s", entity_id
                            )
                            results[entity_id] = {
                                "success": False,
                                "error": "Timeout waiting for response after 30s"
                            }
                            continue

                        if response.get("success", False):
                            results[entity_id] = {"success": True}
                        else:
                            error_msg = response.get("error", {}).get(
                                "message", "Unknown error"
                            )
                            results[entity_id] = {"success": False, "error": error_msg}

                    except HAAutomationError as e:
                        results[entity_id] = {"success": False, "error": str(e)}
                    except Exception as e:
                        logger.warning(
                            "Unexpected error during delete of %s: %s", entity_id, e
                        )
                        results[entity_id] = {"success": False, "error": str(e)}

        except HAAutomationError:
            # Re-raise HAAutomationError (auth failures, parse errors)
            raise
        except TimeoutError as e:
            logger.error("WebSocket timeout during delete operations: %s", e)
            # Create failure results for all remaining entities
            for entity_id in entity_ids:
                if entity_id not in results:
                    results[entity_id] = {
                        "success": False, "error": f"WebSocket timeout: {e}"
                    }
        except Exception as e:
            logger.error("WebSocket connection failed: %s", e)
            # Create failure results for all remaining entities
            for entity_id in entity_ids:
                if entity_id not in results:
                    results[entity_id] = {
                        "success": False, "error": f"WebSocket connection failed: {e}"
                    }

        return results
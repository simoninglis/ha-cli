#!/usr/bin/env python3
"""Test direct JSON output"""

import json

# Create test data that exactly matches the problematic entity
test_entity = {
    "entity_id": "button.office_downlights_idle_power_management_load_error_status",
    "friendly_name": "Office Downlights Idle Power Management Load error status",
    "domain": "button",
    "state": "unknown",
    "attributes": {
        "friendly_name": "Office Downlights Idle Power Management Load error status"
    },
    "last_changed": "2025-06-13T01:14:08.151317+00:00",
    "last_updated": "2025-06-13T01:14:08.151317+00:00"
}

print("Direct json.dumps output:")
print(json.dumps([test_entity], indent=2))
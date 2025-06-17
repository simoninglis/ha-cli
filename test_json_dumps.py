#!/usr/bin/env python3
"""Test json.dumps behavior"""

import json

# Test data that matches what we're seeing
test_data = {
    "entity_id": "button.office_downlights_idle_power_management_load_error_status",
    "friendly_name": "Office Downlights Idle Power Management Load error status"
}

print("Test 1: Normal json.dumps with indent=2")
print(json.dumps(test_data, indent=2))
print()

# Test with embedded newline (what we're seeing in output)
test_data_with_newline = {
    "entity_id": "button.office_downlights_idle_power_management_load_error\nstatus",
    "friendly_name": "Office Downlights Idle Power Management Load error \nstatus"
}

print("Test 2: json.dumps with actual newlines in strings")
try:
    output = json.dumps(test_data_with_newline, indent=2)
    print(output)
    print()
    print("Output is valid JSON")
except Exception as e:
    print(f"Error: {e}")

# Check what the output looks like
print("\nTest 3: Checking the raw output bytes")
output = json.dumps(test_data_with_newline, indent=2)
for i, line in enumerate(output.split('\n')):
    print(f"Line {i}: {repr(line)}")
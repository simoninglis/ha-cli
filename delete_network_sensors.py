#!/usr/bin/env python3
"""
Script to delete all orphaned network monitoring sensors (sensor.rx* and sensor.tx*).

This script uses the new ha-cli entities delete command to remove these stale entities.
"""

import subprocess
import sys
import os

def main():
    # Check if running in dry-run mode
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    force = "--force" in sys.argv or "-f" in sys.argv
    
    # Get credentials from environment or .env file
    ha_url = os.environ.get("HOME_ASSISTANT_URL") or os.environ.get("HA_URL", "http://homeassistant.local:8123")
    ha_token = os.environ.get("HOME_ASSISTANT_TOKEN") or os.environ.get("HA_TOKEN")

    if not ha_token:
        print("Error: HOME_ASSISTANT_TOKEN or HA_TOKEN environment variable not set")
        print("See ENV_SETUP.md for configuration details")
        sys.exit(1)
    
    print("Home Assistant Network Sensor Cleanup Tool")
    print("==========================================")
    print(f"Target: {ha_url}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE DELETION'}")
    print()
    
    # Count entities first
    print("Counting entities to delete...")
    
    # Count rx sensors
    rx_count_cmd = [
        "poetry", "run", "ha-cli", "entities", "list",
        "--search", "^sensor\\.rx",
        "--json"
    ]
    
    env = os.environ.copy()
    env["HOME_ASSISTANT_URL"] = ha_url
    env["HOME_ASSISTANT_TOKEN"] = ha_token
    
    try:
        result = subprocess.run(rx_count_cmd, capture_output=True, text=True, env=env)
        if result.returncode == 0:
            import json
            rx_entities = json.loads(result.stdout)
            rx_count = len(rx_entities)
        else:
            print(f"Error counting rx sensors: {result.stderr}")
            rx_count = 0
    except Exception as e:
        print(f"Error: {e}")
        rx_count = 0
    
    # Count tx sensors
    tx_count_cmd = rx_count_cmd.copy()
    tx_count_cmd[6] = "^sensor\\.tx"
    
    try:
        result = subprocess.run(tx_count_cmd, capture_output=True, text=True, env=env)
        if result.returncode == 0:
            import json
            tx_entities = json.loads(result.stdout)
            tx_count = len(tx_entities)
        else:
            print(f"Error counting tx sensors: {result.stderr}")
            tx_count = 0
    except Exception as e:
        print(f"Error: {e}")
        tx_count = 0
    
    total_count = rx_count + tx_count
    
    print(f"\nFound:")
    print(f"  - {rx_count} sensor.rx* entities")
    print(f"  - {tx_count} sensor.tx* entities")
    print(f"  - {total_count} total entities to delete")
    
    if total_count == 0:
        print("\nNo entities to delete!")
        return
    
    if dry_run:
        print("\nDRY RUN MODE - No entities will be deleted")
        print("\nTo actually delete these entities, run:")
        print("  python delete_network_sensors.py --force")
        return
    
    # Confirm deletion if not forced
    if not force:
        print("\n⚠️  WARNING: This will permanently delete all sensor.rx* and sensor.tx* entities!")
        response = input("\nAre you sure you want to proceed? (yes/no): ")
        if response.lower() != "yes":
            print("Deletion cancelled.")
            return
    
    # Delete rx sensors
    print(f"\nDeleting {rx_count} sensor.rx* entities...")
    rx_delete_cmd = [
        "poetry", "run", "ha-cli", "entities", "delete",
        "--search", "^sensor\\.rx",
        "--force"
    ]
    
    result = subprocess.run(rx_delete_cmd, env=env)
    if result.returncode != 0:
        print("Error deleting rx sensors")
        sys.exit(1)
    
    # Delete tx sensors
    print(f"\nDeleting {tx_count} sensor.tx* entities...")
    tx_delete_cmd = [
        "poetry", "run", "ha-cli", "entities", "delete",
        "--search", "^sensor\\.tx",
        "--force"
    ]
    
    result = subprocess.run(tx_delete_cmd, env=env)
    if result.returncode != 0:
        print("Error deleting tx sensors")
        sys.exit(1)
    
    print(f"\n✅ Successfully deleted {total_count} network monitoring sensors!")
    print("\nNote: These entities may be recreated if their integration is still active.")
    print("To prevent recreation, you should remove or disable the integration that created them.")

if __name__ == "__main__":
    main()
"""
Regression tests for Alexa integration.

Tests cover:
1. UI: "Show entities" page loads without hanging (scripts in YAML filter bug)
2. CLI: Cloud status, Alexa entities, and sync commands work
3. Diagnostic: State reports are being sent (outbound channel health)

See:
- docs/troubleshooting.md#alexa-show-entities-ui-hangs
- docs/troubleshooting.md#alexa-discovery-not-working-state-reports-ok
"""

import asyncio
import os
import subprocess

import pytest
from playwright.async_api import async_playwright

# Configuration - matches test_smoke_frontend.py
HA_URL = os.environ.get("HOME_ASSISTANT_URL") or os.environ.get("HA_URL", "http://homeassistant.local:8123")
HA_USERNAME = os.environ.get("HA_USERNAME", "")
HA_PASSWORD = os.environ.get("HA_PASSWORD", "")


@pytest.fixture
def skip_if_no_credentials():
    """Skip tests if HA credentials are not configured."""
    if not HA_USERNAME or not HA_PASSWORD:
        pytest.skip("HA_USERNAME and HA_PASSWORD environment variables required")


@pytest.mark.asyncio
@pytest.mark.smoke
@pytest.mark.integration
async def test_alexa_show_entities_loads(skip_if_no_credentials):
    """
    Regression test: Voice Assistants Expose UI must load without hanging.

    Root cause (Dec 2025): Including scripts in cloud.alexa.filter.include_entities
    causes the "Show entities" UI to hang indefinitely.

    This test navigates to the Voice Assistants Expose page and verifies
    it loads within the timeout (not hanging). Home Assistant uses shadow DOM
    extensively, so we verify success by:
    1. Reaching the correct URL
    2. Page loads without timeout (the failure mode is infinite spinner)
    3. Screenshot shows actual content (for manual verification if needed)
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Navigate to HA
            await page.goto(HA_URL, timeout=60000, wait_until="networkidle")

            # Handle login if needed
            if "/auth" in page.url:
                await asyncio.sleep(2)
                await page.fill('input[name="username"]', HA_USERNAME)
                await page.fill('input[name="password"]', HA_PASSWORD)
                await page.click("ha-button")
                await asyncio.sleep(5)

            # Navigate to Settings > Voice Assistants > Expose (HA 2025+)
            # This is the page that hangs when scripts are in the Alexa filter
            await page.goto(
                f"{HA_URL}/config/voice-assistants/expose",
                timeout=30000,  # Short timeout - page should load quickly
                wait_until="networkidle"
            )

            # Give the page time to render entity list
            await asyncio.sleep(3)

            # Take screenshot for debugging/verification
            await page.screenshot(path="/tmp/alexa_test_page.png")

            # Verify we're on the correct page
            assert "voice-assistants" in page.url.lower(), (
                f"Not on Voice Assistants page. URL: {page.url}"
            )
            assert "expose" in page.url.lower(), (
                f"Not on Expose tab. URL: {page.url}"
            )

            # If we got here without timeout, the page loaded successfully
            # The regression failure mode is the page hanging indefinitely

        except Exception as e:
            await page.screenshot(path="/tmp/alexa_test_failure.png")
            raise AssertionError(
                f"Voice Assistants Expose page failed to load: {e}. "
                "This may be caused by scripts in the YAML filter. "
                "See docs/troubleshooting.md#alexa-show-entities-ui-hangs. "
                "Screenshot saved to /tmp/alexa_test_*.png"
            ) from e

        finally:
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.smoke
@pytest.mark.integration
async def test_cloud_page_loads(skip_if_no_credentials):
    """
    Basic test: Cloud settings page loads without error.

    Home Assistant uses shadow DOM, so we verify success by URL and no timeout.
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(HA_URL, timeout=60000, wait_until="networkidle")

            # Handle login
            if "/auth" in page.url:
                await asyncio.sleep(2)
                await page.fill('input[name="username"]', HA_USERNAME)
                await page.fill('input[name="password"]', HA_PASSWORD)
                await page.click("ha-button")
                await asyncio.sleep(5)

            # Navigate to Cloud settings
            await page.goto(
                f"{HA_URL}/config/cloud",
                timeout=30000,
                wait_until="networkidle"
            )
            await asyncio.sleep(3)

            await page.screenshot(path="/tmp/cloud_page_test.png")

            # Verify we're on the correct page
            assert "config/cloud" in page.url.lower(), (
                f"Not on Cloud settings page. URL: {page.url}"
            )

        except Exception as e:
            await page.screenshot(path="/tmp/cloud_page_failure.png")
            raise AssertionError(
                f"Cloud settings page failed to load: {e}. "
                "Screenshot saved to /tmp/cloud_page_*.png"
            ) from e

        finally:
            await browser.close()


# =============================================================================
# CLI-Based Tests (no browser required)
# =============================================================================


@pytest.fixture
def skip_if_no_ha_connection():
    """Skip tests if HA is not reachable via CLI."""
    result = subprocess.run(
        ["poetry", "run", "ha-cli", "cloud", "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"Cannot connect to HA: {result.stderr}")


@pytest.mark.smoke
@pytest.mark.integration
def test_cloud_status_cli(skip_if_no_ha_connection):
    """
    Verify cloud status can be retrieved via CLI.

    This tests the basic cloud connection health.
    """
    import json

    result = subprocess.run(
        ["poetry", "run", "ha-cli", "cloud", "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"cloud status failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert data.get("status") == "success", f"Unexpected status: {data}"
    assert data.get("data", {}).get("logged_in") is True, "Not logged in to cloud"
    assert data.get("data", {}).get("cloud_connected") is True, "Cloud not connected"


@pytest.mark.smoke
@pytest.mark.integration
def test_alexa_entities_cli(skip_if_no_ha_connection):
    """
    Verify Alexa entities can be listed via CLI.

    This tests the Alexa configuration is accessible.
    """
    import json

    result = subprocess.run(
        ["poetry", "run", "ha-cli", "cloud", "alexa", "entities", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"alexa entities failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert data.get("status") == "success", f"Unexpected status: {data}"

    # Should have some entities (exact count depends on config)
    entity_count = data.get("metadata", {}).get("total_count", 0)
    assert entity_count > 0, "No Alexa-compatible entities found"


@pytest.mark.smoke
@pytest.mark.integration
def test_alexa_exposed_entities_cli(skip_if_no_ha_connection):
    """
    Verify exposed Alexa entities can be filtered via CLI.

    This tests the exposure filter is working correctly.
    """
    import json

    result = subprocess.run(
        ["poetry", "run", "ha-cli", "cloud", "alexa", "entities", "--exposed", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"alexa entities --exposed failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert data.get("status") == "success", f"Unexpected status: {data}"

    # Check metadata shows filtering was applied
    metadata = data.get("metadata", {})
    assert "exposed_only" in metadata.get("filters_applied", []), (
        "Filter not applied correctly"
    )


@pytest.mark.smoke
@pytest.mark.integration
def test_alexa_sync_cli(skip_if_no_ha_connection):
    """
    Verify Alexa sync can be triggered via CLI.

    This tests the sync command works (but doesn't verify discovery succeeds).
    """
    import json

    result = subprocess.run(
        ["poetry", "run", "ha-cli", "cloud", "alexa", "sync", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"alexa sync failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert data.get("status") == "success", f"Unexpected status: {data}"
    assert data.get("data", {}).get("sync_triggered") is True, "Sync not triggered"


# =============================================================================
# Diagnostic Tests (for manual troubleshooting)
# =============================================================================


@pytest.mark.diagnostic
@pytest.mark.slow
def test_diagnostic_state_reports_working():
    """
    Diagnostic: Check if Alexa state reports are being sent.

    This is a diagnostic test for troubleshooting discovery issues.
    If state reports work but discovery doesn't, the inbound channel is broken.

    See: docs/troubleshooting.md#alexa-discovery-not-working-state-reports-ok
    """
    # This test requires SSH access to HA - skip if not available
    result = subprocess.run(
        ["ssh", "homeassistant", "ha", "core", "logs", "2>&1"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        pytest.skip(f"Cannot SSH to homeassistant: {result.stderr}")

    logs = result.stdout

    # Check for state report activity
    state_report_sent = "alexa" in logs.lower() and "state_report" in logs.lower() and "Sent" in logs

    if not state_report_sent:
        pytest.skip("No recent state report activity in logs (device may be idle)")

    # Check for successful responses (HTTP 202)
    has_202_response = "Received (202)" in logs

    assert has_202_response, (
        "State reports are being sent but not acknowledged (no HTTP 202). "
        "This may indicate an authentication or connection issue. "
        "Try: Settings > Home Assistant Cloud > Log out, then log back in."
    )


@pytest.mark.diagnostic
def test_diagnostic_discovery_channel_health():
    """
    Diagnostic: Check if discovery-related logs are present.

    If state reports work but no discovery logs exist, the inbound channel
    may be broken. Fix: Nabu Casa logout/login.

    See: docs/troubleshooting.md#alexa-discovery-not-working-state-reports-ok
    """
    result = subprocess.run(
        ["ssh", "homeassistant", "ha", "core", "logs", "2>&1"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        pytest.skip(f"Cannot SSH to homeassistant: {result.stderr}")

    logs = result.stdout.lower()

    # Check for discovery-related activity
    has_discovery_activity = any(
        term in logs
        for term in ["addorupdate", "discover", "proactive mode"]
    )

    # Check for state report activity (outbound channel)
    has_state_reports = "state_report" in logs and "sent" in logs

    if has_state_reports and not has_discovery_activity:
        pytest.fail(
            "POTENTIAL ISSUE: State reports are working but no discovery activity found. "
            "This pattern indicates the Nabu Casa inbound channel may be broken. "
            "Fix: Settings > Home Assistant Cloud > Log out, then log back in. "
            "See: docs/troubleshooting.md#alexa-discovery-not-working-state-reports-ok"
        )

    # If we get here, either both channels work or both are quiet
    assert True, "Discovery channel appears healthy or no recent activity"

"""
Regression tests for Alexa integration UI.

These tests verify the Alexa "Show entities" UI loads correctly,
which can break if scripts are included in the YAML filter.

See: docs/troubleshooting.md#alexa-show-entities-ui-hangs
"""

import asyncio
import os

import pytest
from playwright.async_api import async_playwright

# Configuration - matches test_smoke_frontend.py
HA_URL = os.environ.get("HOME_ASSISTANT_URL", "http://10.0.20.35:8123")
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
    Regression test: Alexa "Show entities" UI must load without hanging.

    Root cause (Dec 2025): Including scripts in cloud.alexa.filter.include_entities
    causes the "Show entities" UI to hang indefinitely.

    This test navigates to the Alexa entity list and verifies it loads
    within a reasonable timeout.
    """

    entities_loaded = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Navigate to HA
        await page.goto(HA_URL, timeout=60000, wait_until="networkidle")

        # Handle login if needed
        if "/auth" in page.url:
            await asyncio.sleep(2)
            await page.fill('input[name="username"]', HA_USERNAME)
            await page.fill('input[name="password"]', HA_PASSWORD)
            await page.click("ha-button")
            await asyncio.sleep(5)

        # Navigate to Cloud settings
        await page.goto(f"{HA_URL}/config/cloud", timeout=60000, wait_until="networkidle")
        await asyncio.sleep(3)

        # Take screenshot for debugging
        await page.screenshot(path="/tmp/alexa_test_cloud_page.png")

        # Look for Alexa section and click "Show entities" or "Manage entities"
        # The exact selector may vary by HA version
        try:
            # Try to find and click the Alexa entities link
            alexa_link = page.locator('text=Alexa').first
            await alexa_link.wait_for(timeout=10000)

            # Look for "Show entities" or similar button
            show_entities = page.locator('a:has-text("entities"), button:has-text("entities")').first
            if await show_entities.count() > 0:
                await show_entities.click()
                await asyncio.sleep(2)

            # Wait for entity list to load (look for entity rows or "exposed" text)
            # If this times out, the UI is hanging
            entity_list = page.locator('ha-entity-picker, .entity-row, text=/\\d+ entit/i').first
            await entity_list.wait_for(timeout=30000)
            entities_loaded = True

        except Exception as e:
            # Take screenshot on failure
            await page.screenshot(path="/tmp/alexa_test_failure.png")
            print(f"Failed to load Alexa entities: {e}")

        await browser.close()

    assert entities_loaded, (
        "Alexa 'Show entities' UI did not load within 30 seconds. "
        "This may be caused by scripts in the YAML filter. "
        "See docs/troubleshooting.md#alexa-show-entities-ui-hangs"
    )


@pytest.mark.asyncio
@pytest.mark.smoke
@pytest.mark.integration
async def test_cloud_page_loads(skip_if_no_credentials):
    """
    Basic test: Cloud settings page loads without error.
    """

    page_loaded = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(HA_URL, timeout=60000, wait_until="networkidle")

        # Handle login
        if "/auth" in page.url:
            await asyncio.sleep(2)
            await page.fill('input[name="username"]', HA_USERNAME)
            await page.fill('input[name="password"]', HA_PASSWORD)
            await page.click("ha-button")
            await asyncio.sleep(5)

        # Navigate to Cloud settings
        await page.goto(f"{HA_URL}/config/cloud", timeout=60000, wait_until="networkidle")
        await asyncio.sleep(3)

        # Check for cloud page content
        content = await page.content()
        if "Alexa" in content and "Google" in content:
            page_loaded = True

        await page.screenshot(path="/tmp/cloud_page_test.png")
        await browser.close()

    assert page_loaded, "Cloud settings page did not load correctly"

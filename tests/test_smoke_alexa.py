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

"""Playwright-based dashboard screenshot capture.

Captures screenshots of Home Assistant dashboards for visual verification.
Reuses credential and browser patterns from test_smoke_frontend.py.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright


def get_credentials() -> tuple[str, str, str]:
    """Get Home Assistant credentials from environment.

    Loads from .env file if present, then checks environment variables.
    Supports both HA_URL and HOME_ASSISTANT_URL for the base URL.

    Returns:
        Tuple of (url, username, password)

    Raises:
        ValueError: If required credentials are missing
    """
    # Use python-dotenv for proper .env parsing (handles quotes, exports, comments)
    load_dotenv()

    # Support both HA_URL and HOME_ASSISTANT_URL for consistency with other CLI commands
    url = os.environ.get("HOME_ASSISTANT_URL") or os.environ.get("HA_URL", "http://homeassistant.local:8123")
    username = os.environ.get("HA_USERNAME", "")
    password = os.environ.get("HA_PASSWORD", "")

    if not username or not password:
        raise ValueError(
            "HA_USERNAME and HA_PASSWORD environment variables are required. "
            "Set them in .env file or export them."
        )

    return url, username, password


async def capture_dashboard_screenshot(
    dashboard_name: str,
    output_path: Optional[str] = None,
    viewport_width: int = 1024,
    viewport_height: int = 768,
    wait_seconds: int = 5,
) -> str:
    """Capture a screenshot of a Home Assistant dashboard.

    Args:
        dashboard_name: Dashboard URL path (e.g., 'room-lounge', 'mobile-home')
        output_path: Where to save the screenshot. If None, uses /tmp/dashboard-{name}-{timestamp}.png
        viewport_width: Browser viewport width (default: 1024 for tablets)
        viewport_height: Browser viewport height (default: 768 for tablets)
        wait_seconds: Seconds to wait after page load for rendering (default: 5)

    Returns:
        Path to the saved screenshot file

    Raises:
        ValueError: If credentials are missing
        playwright.async_api.Error: If browser operations fail
    """
    url, username, password = get_credentials()

    # Normalize URL and dashboard name (strip trailing/leading slashes)
    url = url.rstrip("/")
    dashboard_name = dashboard_name.strip("/") if dashboard_name else ""

    # Build dashboard URL
    dashboard_url = f"{url}/{dashboard_name}" if dashboard_name else url

    # Generate output path if not provided
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = dashboard_name.replace("/", "-") if dashboard_name else "default"
        output_path = f"/tmp/dashboard-{safe_name}-{timestamp}.png"

    # Ensure output directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height}
        )
        page = await context.new_page()

        try:
            # Navigate to dashboard
            await page.goto(dashboard_url, timeout=60000, wait_until="networkidle")

            # Handle login if needed
            if "/auth" in page.url:
                await asyncio.sleep(2)
                await page.fill('input[name="username"]', username)
                await page.fill('input[name="password"]', password)
                await page.click("ha-button")

                # Wait for redirect after login - use flexible pattern
                await page.wait_for_url(f"**/{dashboard_name}*" if dashboard_name else "**", timeout=30000)
                await page.wait_for_load_state("networkidle")

            # Wait for dashboard to fully render
            await asyncio.sleep(wait_seconds)

            # Capture screenshot
            await page.screenshot(path=output_path, full_page=True)
        finally:
            await browser.close()

    return output_path


def list_available_dashboards() -> list[str]:
    """List dashboard names that can be screenshotted.

    Note: This is a convenience function that returns common dashboard patterns.
    For a complete list, use `ha-cli dashboards list`.

    Returns:
        List of common dashboard URL paths
    """
    # These are the known dashboard URL paths from configuration.yaml
    return [
        "mobile-home",
        "room-office",
        "room-lounge",
        "room-master",
        "room-kitchen",
        "room-bed2",
        "room-laundry",
        "room-garage",
        "domain-climate",
        "domain-irrigation",
        "ops-settings",
    ]

"""Playwright-based dashboard screenshot capture.

Captures screenshots of Home Assistant dashboards for visual verification.
Logs in with HA_TOKEN when set (no password needed), else HA_USERNAME/HA_PASSWORD:
see common/frontend_auth.py.
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from ...common.frontend_auth import (
    FrontendAuth,
    assert_logged_in,
    ensure_logged_in,
    prepare_context,
    resolve_frontend_auth,
    settle,
)


async def capture_dashboard_screenshot(
    dashboard_name: str,
    output_path: str | None = None,
    viewport_width: int = 1024,
    viewport_height: int = 768,
    wait_seconds: int = 5,
    auth: FrontendAuth | None = None,
) -> str:
    """Capture a screenshot of a Home Assistant dashboard.

    Args:
        dashboard_name: Dashboard URL path (e.g., 'room-lounge', 'mobile-home')
        output_path: Where to save the screenshot. If None, uses /tmp/dashboard-{name}-{timestamp}.png
        viewport_width: Browser viewport width (default: 1024 for tablets)
        viewport_height: Browser viewport height (default: 768 for tablets)
        wait_seconds: Seconds to wait after page load for rendering (default: 5)
        auth: Credentials; resolved from the environment when omitted

    Returns:
        Path to the saved screenshot file

    Raises:
        FrontendAuthError: (a ValueError) If credentials are missing or rejected
        playwright.async_api.Error: If browser operations fail
    """
    if auth is None:
        auth = resolve_frontend_auth()
    url = auth.url.rstrip("/")

    # Normalize dashboard name (strip trailing/leading slashes)
    dashboard_name = dashboard_name.strip("/") if dashboard_name else ""

    # Build dashboard URL
    dashboard_url = f"{url}/{dashboard_name}" if dashboard_name else url

    # Generate output path if not provided
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = dashboard_name.replace("/", "-") if dashboard_name else "default"
        output_path = str(Path(tempfile.gettempdir()) / f"dashboard-{safe_name}-{timestamp}.png")

    # Ensure output directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height}
            )
            # Blocks navigation off the HA origin; seeds the token if there is one
            await prepare_context(context, auth)
            page = await context.new_page()

            # Navigate to dashboard. "load", then a bounded wait for network idle:
            # dashboards with live cameras or streams never go idle, and waiting
            # for that outright timed out on mobile-home.
            await page.goto(dashboard_url, timeout=60000, wait_until="load")
            await settle(page)

            # Log in if the frontend asked (password auth). With a token, a login
            # page means the token was rejected: raise rather than capture it.
            await ensure_logged_in(page, auth)

            # Wait for dashboard to fully render
            await asyncio.sleep(wait_seconds)

            # The frontend can still bounce to /auth once its websocket auth fails
            assert_logged_in(page, auth, f"instead of /{dashboard_name}")

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

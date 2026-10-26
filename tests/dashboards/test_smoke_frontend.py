"""
Smoke tests for Home Assistant frontend using Playwright.

These tests verify that the HA frontend loads correctly after deployment.
They check for critical issues like:
- recorder/info WebSocket responding (prevents "Loading data" hang)
- All bootstrap WebSocket requests receiving responses
- No critical HTTP failures for frontend assets

## Running Tests

From repository root (recommended):
    just smoke-test

Or directly with pytest:
    poetry run pytest tests/test_smoke_frontend.py -v -m smoke

Skip during regular unit test runs:
    just test  # Automatically excludes smoke tests

## Requirements

- HA_TOKEN in the environment (e.g. via bao-run), or HA_USERNAME and HA_PASSWORD
  in .env / the environment
- Home Assistant at HOME_ASSISTANT_URL or HA_URL (default: http://homeassistant.local:8123)
- Playwright browsers: poetry run playwright install chromium

## Integration

Run after deployment to verify frontend health:
    just deploy && just smoke-test

See docs/troubleshooting.md#frontend-loading-data-spinner for diagnosis.
"""

import asyncio
import json
import re
from typing import Any
from urllib.parse import urlparse

import pytest
from playwright.async_api import async_playwright, Page, WebSocket

from ha_cli.common.frontend_auth import (
    FrontendAuth,
    FrontendAuthError,
    assert_logged_in,
    ensure_logged_in,
    prepare_context,
    resolve_frontend_auth,
    resolve_frontend_url,
    settle,
)

# HA_TOKEN (e.g. via bao-run) or HA_USERNAME/HA_PASSWORD; see ha_cli/common/frontend_auth.py
try:
    AUTH: FrontendAuth | None = resolve_frontend_auth()
except FrontendAuthError:
    AUTH = None
HA_URL = AUTH.url if AUTH else resolve_frontend_url()

# Critical WebSocket requests that must respond for frontend to load
CRITICAL_WS_TYPES = [
    "recorder/info",  # If this hangs, frontend shows "Loading data" forever
    "lovelace/config",
    "config/entity_registry/list_for_display",
    "get_config",
    "auth/current_user",
]


@pytest.fixture
def skip_if_no_credentials():
    """Skip tests if HA credentials are not configured."""
    if AUTH is None:
        pytest.skip("HA_TOKEN, or HA_USERNAME and HA_PASSWORD, required")


async def wait_for_success(tracker: "WebSocketTracker", msg_type: str, timeout_s: float = 30) -> bool:
    """Poll until `msg_type` has succeeded, or give up after `timeout_s`."""
    for _ in range(int(timeout_s * 2)):
        if tracker.succeeded(msg_type):
            return True
        await asyncio.sleep(0.5)
    return tracker.succeeded(msg_type)


class WebSocketTracker:
    """Track WebSocket messages for analysis."""

    def __init__(self):
        self.sent: dict[int, dict[str, Any]] = {}
        self.received: dict[int, dict[str, Any]] = {}
        self.failed_http: list[dict[str, str]] = []

    def handle_frame_sent(self, payload: str):
        try:
            data = json.loads(payload)
            msg_id = data.get("id")
            msg_type = data.get("type", "unknown")
            if msg_id:
                # Type only: never keep frame contents (the auth frame carries the token)
                self.sent[msg_id] = {"type": msg_type}
        except (json.JSONDecodeError, TypeError):
            pass

    def handle_frame_received(self, payload: str):
        try:
            messages = json.loads(payload) if payload.startswith("[") else [json.loads(payload)]
            for data in messages:
                msg_id = data.get("id")
                msg_type = data.get("type", "unknown")
                success = data.get("success")
                if msg_id:
                    self.received[msg_id] = {
                        "type": msg_type,
                        "success": success,
                        "size": len(json.dumps(data)),
                    }
        except (json.JSONDecodeError, TypeError):
            pass

    def succeeded(self, msg_type: str) -> bool:
        """True once a request of this type got a successful response."""
        return any(
            req["type"] == msg_type and self.received.get(mid, {}).get("success") is True
            for mid, req in self.sent.items()
        )

    def get_unanswered_requests(self) -> dict[int, dict[str, Any]]:
        """Return requests that never received responses."""
        unanswered_ids = set(self.sent.keys()) - set(self.received.keys())
        return {mid: self.sent[mid] for mid in unanswered_ids}

    def get_critical_unanswered(self) -> list[str]:
        """Return list of critical request types that didn't receive responses."""
        unanswered = self.get_unanswered_requests()
        return [
            req["type"]
            for req in unanswered.values()
            if req["type"] in CRITICAL_WS_TYPES
        ]


@pytest.mark.asyncio
@pytest.mark.smoke
@pytest.mark.integration
async def test_frontend_loads(skip_if_no_credentials):
    """
    Verify Home Assistant frontend loads without hanging.

    This is the critical smoke test - if this fails, the frontend is broken.
    """
    tracker = WebSocketTracker()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await prepare_context(context, AUTH)
        page = await context.new_page()

        # Track failed HTTP requests
        page.on("requestfailed", lambda req: tracker.failed_http.append({
            "url": req.url,
            "failure": str(req.failure),
        }))

        # Track WebSocket messages
        def handle_ws(ws: WebSocket):
            ws.on("framesent", lambda payload: tracker.handle_frame_sent(payload))
            ws.on("framereceived", lambda payload: tracker.handle_frame_received(payload))

        page.on("websocket", handle_ws)

        # Navigate to HA
        await page.goto(HA_URL, timeout=60000, wait_until="load")
        await settle(page)

        # Log in if needed (no-op with a token; a rejected token fails here)
        await ensure_logged_in(page, AUTH)

        # The frontend must actually come up: config and dashboard loaded over an
        # authenticated websocket. An empty trace is a failure, not a pass.
        ready = await wait_for_success(tracker, "lovelace/config")

        # Wait for remaining WebSocket activity to settle
        await asyncio.sleep(10)

        # Take screenshot for debugging
        await page.screenshot(path="/tmp/ha_smoke_test.png")

        # Still logged in after everything settled (a late auth failure lands on /auth)
        assert_logged_in(page, AUTH, "after the frontend loaded")

        await browser.close()

    # Assertions
    assert ready and tracker.succeeded("get_config"), (
        "The frontend never finished loading: no successful get_config / lovelace/config. "
        f"Requests seen: {sorted({r['type'] for r in tracker.sent.values()})}"
    )
    critical_unanswered = tracker.get_critical_unanswered()
    assert len(critical_unanswered) == 0, (
        f"Critical WebSocket requests did not receive responses: {critical_unanswered}. "
        "This likely means the frontend is showing 'Loading data' spinner. "
        "See docs/troubleshooting.md#frontend-loading-data-spinner"
    )

    # Check recorder specifically (the most common cause of frontend hang)
    assert tracker.succeeded("recorder/info"), (
        "recorder/info WebSocket request did not receive a response. "
        "This is the most common cause of the 'Loading data' spinner. "
        "Check recorder configuration - avoid restrictive include: filters."
    )


@pytest.mark.asyncio
@pytest.mark.smoke
@pytest.mark.integration
async def test_recorder_info_responds(skip_if_no_credentials):
    """
    Specifically test that recorder/info WebSocket responds.

    This is the most critical check - if recorder/info hangs, the frontend hangs.
    """
    tracker = WebSocketTracker()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await prepare_context(context, AUTH)
        page = await context.new_page()

        def handle_ws(ws: WebSocket):
            ws.on("framesent", lambda payload: tracker.handle_frame_sent(payload))
            ws.on("framereceived", lambda payload: tracker.handle_frame_received(payload))

        page.on("websocket", handle_ws)

        await page.goto(HA_URL, timeout=60000, wait_until="load")
        await settle(page)

        await ensure_logged_in(page, AUTH)

        # Wait (bounded) for a SUCCESSFUL recorder/info - an error response is not health -
        # and for the dashboard config, so an empty trace can't pass
        recorder_responded = await wait_for_success(tracker, "recorder/info")
        dashboard_loaded = await wait_for_success(tracker, "lovelace/config")

        assert_logged_in(page, AUTH)
        await browser.close()

    assert dashboard_loaded, "The dashboard never loaded (no successful lovelace/config)"
    assert recorder_responded, (
        "recorder/info never succeeded within 30 seconds. "
        "The recorder integration may be blocked. "
        "See docs/troubleshooting.md#frontend-loading-data-spinner"
    )


@pytest.mark.asyncio
@pytest.mark.smoke
@pytest.mark.integration
async def test_no_critical_http_failures(skip_if_no_credentials):
    """
    Verify no critical frontend JavaScript files fail to load.

    ERR_ABORTED on JS chunks can prevent the frontend from rendering.
    """
    failed_requests: list[dict[str, str]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await prepare_context(context, AUTH)
        page = await context.new_page()

        page.on("requestfailed", lambda req: failed_requests.append({
            "url": req.url,
            "failure": str(req.failure),
        }))

        tracker = WebSocketTracker()

        def handle_ws(ws: WebSocket):
            ws.on("framesent", lambda payload: tracker.handle_frame_sent(payload))
            ws.on("framereceived", lambda payload: tracker.handle_frame_received(payload))

        page.on("websocket", handle_ws)

        await page.goto(HA_URL, timeout=60000, wait_until="load")
        await settle(page)

        await ensure_logged_in(page, AUTH)

        # Let the dashboard load its resources before judging what failed: closing
        # straight after login would see no requests at all and pass.
        ready = await wait_for_success(tracker, "lovelace/config")
        await settle(page)
        assert_logged_in(page, AUTH)

        await browser.close()

    assert ready, "The dashboard never loaded (no successful lovelace/config): nothing was checked"

    def is_critical_failure(url: str) -> bool:
        """Determine if a failed request is critical (should fail the test).

        Critical failures:
        - Core JS files (in /frontend_latest/) that aren't numbered chunks
        - API calls except: camera_proxy, websocket, HLS streams

        Non-critical (expected to fail sometimes):
        - Numbered JS chunks (e.g., 1234.js) - lazy-loaded, may not exist
        - Camera proxy/stream requests - network-dependent
        - WebSocket connections - handled separately
        - HLS streams (.m3u8, .ts) - camera streams may be offline
        """
        parsed = urlparse(url)
        path = parsed.path
        filename = path.rsplit("/", 1)[-1] if "/" in path else path

        # JS file handling
        if path.endswith(".js"):
            # Only check JS files in /frontend_latest/ (framework files)
            if "/frontend_latest/" in path:
                # Core framework JS IS critical (e.g., core-xxx.js, app-xxx.js)
                if re.match(r"^(core|app)[.-]", filename):
                    return True
                # Numbered chunks (e.g., "1234.js", "1234.abcdef.js") are lazy-loaded, OK to fail
                if re.match(r"^\d+[.-]", filename):
                    return False
                # Other frontend_latest files - likely critical
                return True
            # Other JS files outside frontend_latest are likely custom/external, less critical
            return False

        # API call handling
        if "/api/" in path:
            # Camera proxies and streams are network-dependent
            if "camera_proxy" in path:
                return False
            # WebSocket handled separately
            if "websocket" in path:
                return False
            # HLS streams (parse path to handle query strings)
            if path.startswith("/api/hls/") or path.endswith((".m3u8", ".ts")):
                return False
            # Other API failures are critical
            return True

        return False

    critical_failures = [f for f in failed_requests if is_critical_failure(f["url"])]

    # Only fail if core framework JS fails (e.g., core-xxx.js, app-xxx.js)
    if critical_failures:
        pytest.fail(
            f"Critical HTTP requests failed: {json.dumps(critical_failures, indent=2)}. "
            "This may cause frontend rendering issues."
        )

    # Log non-critical failures for awareness (don't fail)
    non_critical = [f for f in failed_requests if f not in critical_failures]
    if non_critical:
        # These are expected and acceptable
        pass  # Could log these if needed for debugging


@pytest.mark.asyncio
@pytest.mark.smoke
@pytest.mark.integration
async def test_lovelace_config_loads(skip_if_no_credentials):
    """
    Verify Lovelace dashboard configuration loads successfully.
    """
    tracker = WebSocketTracker()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await prepare_context(context, AUTH)
        page = await context.new_page()

        def handle_ws(ws: WebSocket):
            ws.on("framesent", lambda payload: tracker.handle_frame_sent(payload))
            ws.on("framereceived", lambda payload: tracker.handle_frame_received(payload))

        page.on("websocket", handle_ws)

        await page.goto(HA_URL, timeout=60000, wait_until="load")
        await settle(page)

        await ensure_logged_in(page, AUTH)

        # Wait (bounded) for the dashboard config, rather than closing straight away
        lovelace_loaded = await wait_for_success(tracker, "lovelace/config")
        assert_logged_in(page, AUTH)

        await browser.close()

    assert lovelace_loaded, (
        "Lovelace configuration did not load successfully. "
        "Check lovelace storage file for corruption."
    )

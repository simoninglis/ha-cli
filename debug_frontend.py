#!/usr/bin/env python3
"""Debug Home Assistant frontend loading issues using Playwright."""

import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

# Load .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                # Don't override existing env vars, skip variable references
                if key not in os.environ and not value.startswith("${"):
                    os.environ[key] = value

HA_URL = os.environ.get("HOME_ASSISTANT_URL", "http://10.0.20.35:8123")
HA_USERNAME = os.environ.get("HA_USERNAME", "")
HA_PASSWORD = os.environ.get("HA_PASSWORD", "")

async def debug_frontend():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        ws_sent = {}  # id -> request details
        ws_recv = {}  # id -> response details
        console_logs = []
        failed_requests = []

        # Capture console logs
        page.on("console", lambda msg: console_logs.append({
            "type": msg.type,
            "text": msg.text[:500]
        }))

        # Capture failed requests
        page.on("requestfailed", lambda req: failed_requests.append({
            "url": req.url,
            "failure": str(req.failure)
        }))

        # Capture WebSocket frames
        def handle_ws(ws):
            print(f"\n[WS] Connected: {ws.url}")

            def on_frame_sent(payload):
                try:
                    data = json.loads(payload)
                    msg_id = data.get("id")
                    msg_type = data.get("type", "unknown")
                    if msg_id:
                        ws_sent[msg_id] = {"type": msg_type, "data": data}
                    print(f"[→ SENT] id={msg_id} type={msg_type}")
                except:
                    pass

            def on_frame_received(payload):
                try:
                    # Handle batched messages
                    if payload.startswith("["):
                        messages = json.loads(payload)
                    else:
                        messages = [json.loads(payload)]

                    for data in messages:
                        msg_id = data.get("id")
                        msg_type = data.get("type", "unknown")
                        success = data.get("success")
                        size = len(json.dumps(data))

                        if msg_id:
                            ws_recv[msg_id] = {
                                "type": msg_type,
                                "success": success,
                                "size": size,
                                "has_result": "result" in data
                            }

                        # Print notable responses
                        if msg_type == "result":
                            req_type = ws_sent.get(msg_id, {}).get("type", "?")
                            status = "✓" if success else "✗"
                            print(f"[← RECV] id={msg_id} {status} {req_type} ({size:,} bytes)")
                        elif msg_type == "event":
                            pass  # Skip event spam
                        else:
                            print(f"[← RECV] id={msg_id} type={msg_type}")
                except Exception as e:
                    print(f"[← RECV] parse error: {e}")

            ws.on("framesent", on_frame_sent)
            ws.on("framereceived", on_frame_received)

        page.on("websocket", handle_ws)

        print(f"Navigating to {HA_URL}...")

        try:
            await page.goto(HA_URL, timeout=60000, wait_until="networkidle")
            print(f"Page URL: {page.url}")

            # Handle login
            if "/auth" in page.url:
                print("\nLogging in...")
                if not HA_PASSWORD:
                    print("ERROR: Set HA_PASSWORD")
                    return

                await asyncio.sleep(2)

                try:
                    await page.fill('input[name="username"]', HA_USERNAME)
                    await page.fill('input[name="password"]', HA_PASSWORD)
                    await page.click('ha-button')
                    print("Login submitted")
                except Exception as e:
                    print(f"Login error: {e}")
                    return

                await asyncio.sleep(5)
                print(f"After login: {page.url}")

            # Wait for WebSocket activity
            print("\nWaiting 45 seconds for WebSocket responses...")
            for i in range(45):
                await asyncio.sleep(1)
                if i % 10 == 9:
                    print(f"  {i+1}s: {len(ws_recv)}/{len(ws_sent)} responses received")

            # Take final screenshot
            await page.screenshot(path="/tmp/ha_final.png")
            print("\nScreenshot saved to /tmp/ha_final.png")

        except Exception as e:
            print(f"Error: {e}")

        # Analysis
        print("\n" + "="*70)
        print("ANALYSIS")
        print("="*70)

        # Find unanswered requests
        unanswered_ids = set(ws_sent.keys()) - set(ws_recv.keys())
        if unanswered_ids:
            print(f"\n⚠️  UNANSWERED REQUESTS ({len(unanswered_ids)}):")
            for mid in sorted(unanswered_ids):
                req = ws_sent[mid]
                print(f"   id={mid}: {req['type']}")
        else:
            print("\n✓ All WebSocket requests received responses")

        # Check for failed responses
        failed_ws = {k: v for k, v in ws_recv.items() if v.get("success") == False}
        if failed_ws:
            print(f"\n⚠️  FAILED RESPONSES ({len(failed_ws)}):")
            for mid, resp in failed_ws.items():
                req_type = ws_sent.get(mid, {}).get("type", "?")
                print(f"   id={mid}: {req_type}")

        # Show largest responses
        sorted_recv = sorted(ws_recv.items(), key=lambda x: x[1].get("size", 0), reverse=True)
        print(f"\nLargest responses:")
        for mid, resp in sorted_recv[:5]:
            req_type = ws_sent.get(mid, {}).get("type", "?")
            print(f"   id={mid}: {req_type} = {resp['size']:,} bytes")

        # HTTP failures
        if failed_requests:
            print(f"\n⚠️  FAILED HTTP REQUESTS ({len(failed_requests)}):")
            for req in failed_requests:
                print(f"   {req['url']}: {req['failure']}")

        # Console errors
        errors = [l for l in console_logs if l["type"] == "error"]
        if errors:
            print(f"\n⚠️  CONSOLE ERRORS ({len(errors)}):")
            for e in errors[:10]:
                print(f"   {e['text'][:200]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_frontend())

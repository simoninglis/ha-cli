"""Log a headless browser into the Home Assistant frontend.

Two ways in, tried in this order:

1. A long-lived access token (HA_TOKEN / HOME_ASSISTANT_TOKEN in the environment).
   The frontend keeps its auth in localStorage under ``hassTokens``; seeding that
   before the first page load makes it use the token directly, with no login form.
   This is what lets agent sessions (token via bao-run, no HA password) screenshot
   and smoke-test dashboards.
2. The HA login form, with HA_USERNAME / HA_PASSWORD.

The token never touches argv or disk: it goes to the browser over Playwright's
pipe as an init script, into a throwaway in-memory browser context, and the script
only writes it for the Home Assistant origin. Credentials are only typed into a
login form on that origin, and a browser that ends up anywhere else is an error.
A token is never read from a .env file (see config.load_env_file).
"""

import contextlib
import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

from .envfile import load_env_file

DEFAULT_URL = "http://homeassistant.local:8123"

# How long the frontend should consider the token valid. A long-lived token has no
# refresh token, so the frontend must never decide it has expired and try to refresh
# (that fails and drops it on the login page). Year ~2286, in ms.
_FAR_FUTURE_MS = 9_999_999_999_999


class FrontendAuthError(ValueError):
    """No usable credentials, or Home Assistant rejected the ones we used."""


@dataclass
class FrontendAuth:
    """How to get a browser past the HA login. Secrets are kept out of repr()."""

    url: str
    token: str | None = field(default=None, repr=False)
    username: str | None = None
    password: str | None = field(default=None, repr=False)

    @property
    def method(self) -> str:
        """'token' or 'login'."""
        return "token" if self.token else "login"

    @property
    def origin(self) -> str:
        """The browser-normalized origin of `url`."""
        return canonical_origin(self.url)


def canonical_origin(url: str) -> str:
    """scheme://host[:port] as a browser reports window.location.origin.

    Lowercases the host and drops a default port, so http://HA:80 and http://ha
    compare equal.

    Raises:
        FrontendAuthError: If the URL isn't http(s)://host, or carries user:pass@
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as e:
        raise FrontendAuthError(f"Not a valid Home Assistant URL: {e}") from None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise FrontendAuthError("The Home Assistant URL must look like http(s)://host[:port]")
    if parts.username is not None or parts.password is not None:
        raise FrontendAuthError("The Home Assistant URL must not contain user:password@")
    host = parts.hostname  # urlsplit lowercases it
    if ":" in host:
        host = f"[{host}]"  # IPv6 literal
    default_port = 443 if scheme == "https" else 80
    return f"{scheme}://{host}" if port in (None, default_port) else f"{scheme}://{host}:{port}"


def _origin_or_none(url: str) -> str | None:
    try:
        return canonical_origin(url)
    except FrontendAuthError:
        return None  # about:blank, data:, chrome-error://, ...


def _page_origin(page: Any) -> str | None:
    return _origin_or_none(page.url)


def resolve_frontend_url() -> str:
    """HOME_ASSISTANT_URL, then HA_URL, then the homeassistant.local default."""
    url = os.environ.get("HOME_ASSISTANT_URL") or os.environ.get("HA_URL") or DEFAULT_URL
    return url.rstrip("/")


def resolve_frontend_auth() -> FrontendAuth:
    """Pick the token if there is one, else the username/password login.

    Raises:
        FrontendAuthError: If neither is available. The message names the variables,
            never their values.
    """
    load_env_file()
    url = resolve_frontend_url()
    canonical_origin(url)  # fail early on a malformed URL
    token = os.environ.get("HA_TOKEN") or os.environ.get("HOME_ASSISTANT_TOKEN")
    if token:
        return FrontendAuth(url=url, token=token)
    username = os.environ.get("HA_USERNAME", "")
    password = os.environ.get("HA_PASSWORD", "")
    if username and password:
        return FrontendAuth(url=url, username=username, password=password)
    raise FrontendAuthError(
        "No Home Assistant credentials for the browser: set HA_TOKEN (a long-lived "
        "access token, e.g. via bao-run) or HA_USERNAME and HA_PASSWORD."
    )


def token_init_script(auth: FrontendAuth) -> str:
    """JavaScript that seeds the frontend's stored auth with the token.

    Runs before any page script on every navigation, but only writes when the page
    is the Home Assistant origin, so a redirect elsewhere never receives the token.
    """
    if not auth.token:
        raise FrontendAuthError("token_init_script needs a token")
    origin = auth.origin
    tokens = {
        "access_token": auth.token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": origin,
        "clientId": origin + "/",
        "expires": _FAR_FUTURE_MS,
        "refresh_token": "",
    }
    # json.dumps twice: once for the stored JSON string, once to make it a JS literal.
    return (
        "(() => { try {"
        f" if (window.location.origin !== {json.dumps(origin)}) return;"
        f" window.localStorage.setItem('hassTokens', {json.dumps(json.dumps(tokens))});"
        " } catch (e) {} })();"
    )


async def prepare_context(context: Any, auth: FrontendAuth) -> None:
    """Call on a fresh browser context, before opening any page.

    Keeps the session on the Home Assistant origin:

    - Every top-level navigation to another origin is blocked, so no page can carry
      the login somewhere else - in particular not between typing the username and
      the password (a check before each fill can't close that window).
    - Same-origin requests with a body - anything but GET/HEAD/OPTIONS, i.e. where a
      typed password travels - are fetched with redirects disabled, and a redirect to
      another origin is refused before the browser could re-send the body there. GETs
      pass straight through: they carry no credentials, a landing elsewhere is caught
      by the origin checks, and a document Playwright fulfils counts as "public" to
      Chromium's local-network checks, which then block its requests to a LAN-hosted
      Home Assistant.
    - Off-origin requests with a body are blocked from every frame.
    - With password auth, EVERY off-origin request is blocked, for the life of the
      browser: once a password is in a page, any later GET (a form aimed at an
      iframe, an image URL) could carry it, and no time window closes that. Such
      screenshots show off-origin iframes and images blank.
    - With token auth (no password ever in the page), iframes and images from other
      origins (camera and webpage cards) load as usual.

    Then seeds the token, if there is one.
    """
    origin = auth.origin

    async def guard(route: Any) -> None:
        request = route.request
        top_level = request.is_navigation_request() and request.frame.parent_frame is None
        has_body = request.method not in ("GET", "HEAD", "OPTIONS")
        if _origin_or_none(request.url) != origin:
            # Off-origin: never a top-level navigation, never a request carrying a body
            # (a form posted into a frame), and nothing at all with password auth
            if top_level or has_body or not auth.token:
                await route.abort("blockedbyclient")
            else:
                await route.fallback()
            return
        if not has_body:
            await route.fallback()
            return
        try:
            response = await route.fetch(max_redirects=0)
        except Exception:
            await route.abort("failed")
            return
        try:
            if 300 <= response.status < 400:
                location = response.headers.get("location")
                target = urljoin(request.url, location) if location else None
                if target is None or _origin_or_none(target) != origin:
                    await route.abort("blockedbyclient")
                    return
            await route.fulfill(response=response)
        finally:
            await response.dispose()  # fulfil copies the body; don't keep every POST's

    await context.route("**/*", guard)
    if auth.token:
        await context.add_init_script(script=token_init_script(auth))


async def ensure_logged_in(page: Any, auth: FrontendAuth) -> None:
    """Get past the login page if the frontend showed it.

    With a token, landing on /auth means HA rejected it (revoked, wrong instance):
    that is an error, never a screenshot of the login form. With a username and
    password, fill the form - only on the Home Assistant origin - and wait to be
    sent back off /auth, still on that origin.
    """
    _require_ha_origin(page, auth)
    if "/auth" not in page.url:
        return
    if auth.token:
        raise FrontendAuthError(
            "Home Assistant rejected the access token (the frontend showed its login "
            "page). Check HA_TOKEN is current for this instance."
        )
    await page.wait_for_selector('input[name="username"]', timeout=15000)
    _require_ha_origin(page, auth)  # never type the password into another site
    # With password auth nothing leaves the HA origin at all (prepare_context)
    try:
        await page.fill('input[name="username"]', auth.username or "", timeout=10000)
        # The context blocks navigation off the HA origin (prepare_context). A page that
        # tries anyway is left on an error page, or mid-navigation: either way the
        # password fill below finds no form and times out, rather than typing elsewhere.
        _require_ha_origin(page, auth)
        await page.fill('input[name="password"]', auth.password or "", timeout=10000)
        _require_ha_origin(page, auth)
        await page.click("ha-button", timeout=10000)
    except FrontendAuthError:
        raise
    except Exception:  # playwright errors; not imported here
        raise FrontendAuthError(
            f"Login form stopped responding on {_page_origin(page) or 'a non-web page'}: "
            "the page may have tried to leave Home Assistant"
        ) from None  # Playwright's message quotes the fill: it would echo the password
    try:
        await page.wait_for_url(lambda u: "/auth" not in u, timeout=30000)
    except Exception:  # playwright TimeoutError; not imported here
        raise FrontendAuthError("Login failed: check HA_USERNAME / HA_PASSWORD.") from None
    await page.wait_for_load_state("load")
    _require_ha_origin(page, auth)


def assert_logged_in(page: Any, auth: FrontendAuth, context: str = "") -> None:
    """Fail unless the page is on Home Assistant and off the login page.

    Call after waiting for a page to render: the frontend can drop back to /auth
    once its websocket authentication fails, well after the first load.
    """
    _require_ha_origin(page, auth)
    if "/auth" in page.url:
        where = f" {context}" if context else ""
        raise FrontendAuthError(
            f"Ended on the login page{where} ({auth.method} auth was not accepted)"
        )


def _require_ha_origin(page: Any, auth: FrontendAuth) -> None:
    origin = _page_origin(page)
    if origin != auth.origin:
        raise FrontendAuthError(
            f"The browser left Home Assistant ({auth.origin}): now on {origin or 'a non-web page'}"
        )


async def settle(page: Any, timeout_ms: int = 15000) -> None:
    """Wait for network idle, but don't fail on pages that never go idle.

    Dashboards with live cameras or streams keep the network busy forever, so
    navigate with wait_until="load" and call this, rather than wait_until="networkidle".
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    with contextlib.suppress(PlaywrightTimeoutError):
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)

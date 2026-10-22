"""HESTIA sign-in for MulAn.

The HESTIA portal owns accounts and sign-in. MulAn sends the browser to the
portal's login page and reads the resulting refresh-token cookie, which it
forwards to HESTIA to learn who the user is and what they may do.
"""

from __future__ import annotations

import hashlib
import threading
import time
from urllib.parse import urlencode

from flask import Blueprint, current_app, g, jsonify, redirect, request

from .errors import ApiError
from .hestia import HestiaClient


# HESTIA is asked again after this long, so permission changes and portal
# sign-outs reach MulAn quickly without one HESTIA call per brush stroke.
SESSION_CACHE_SECONDS = 15

CAPABILITIES = ("images_read", "images_create", "annotations_read", "annotations_create", "annotations_update")

auth_api = Blueprint("auth_api", __name__)


class SessionCache:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self._entries: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def get(self, token: str) -> dict | None:
        with self._lock:
            entry = self._entries.get(self._key(token))
            if entry is None or entry[0] < time.monotonic():
                return None
            return entry[1]

    def put(self, token: str, session: dict) -> None:
        with self._lock:
            now = time.monotonic()
            self._entries = {key: value for key, value in self._entries.items() if value[0] >= now}
            self._entries[self._key(token)] = (now + self.ttl, session)

    def drop(self, token: str) -> None:
        with self._lock:
            self._entries.pop(self._key(token), None)


def hestia() -> HestiaClient:
    return current_app.extensions["hestia"]


def hestia_token() -> str | None:
    return request.cookies.get(current_app.config["HESTIA_COOKIE_NAME"]) or None


def _anonymous() -> dict:
    return {"authenticated": False, "user": None, "capabilities": {cap: False for cap in CAPABILITIES}}


def current_session(*, fresh: bool = False) -> dict:
    """The caller's HESTIA session: authentication state, user, and capabilities."""
    if "hestia_session" in g and not fresh:
        return g.hestia_session
    token = hestia_token()
    cache: SessionCache = current_app.extensions["hestia_sessions"]
    session = None if token is None or fresh else cache.get(token)
    if session is None:
        session = hestia().session(token) if token else _anonymous()
        if token:
            cache.put(token, session)
    g.hestia_session = session
    return session


def require_session() -> dict:
    session = current_session()
    if not session.get("authenticated"):
        raise ApiError("unauthenticated", "A HESTIA login is required.", 401)
    return session


def require_login() -> None:
    """``before_request`` hook: rejects callers without a HESTIA session."""
    require_session()


def require_capabilities(*capabilities: str) -> dict:
    session = require_session()
    if not all(session["capabilities"].get(cap) for cap in capabilities):
        raise ApiError("forbidden", "You do not have permission for this action.", 403)
    return session


def require_token() -> str:
    """The caller's HESTIA credential, for calls HESTIA authorizes itself."""
    token = hestia_token()
    if token is None:
        raise ApiError("unauthenticated", "A HESTIA login is required.", 401)
    return token


def _front_page_url() -> str:
    configured = current_app.config["MULAN_PUBLIC_URL"]
    if configured:
        return configured.rstrip("/") + "/"
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    host = request.headers.get("X-Forwarded-Host", request.host).split(",")[0].strip()
    return f"{scheme}://{host}/"


def _portal_url(path: str) -> str:
    portal = current_app.config["HESTIA_PORTAL_URL"].rstrip("/")
    return f"{portal}{path}?{urlencode({'redirect_url': _front_page_url()})}"


@auth_api.get("/api/v1/session")
def session():
    state = current_session(fresh=True)
    body = {
        "authenticated": bool(state.get("authenticated")),
        "user": state.get("user"),
        "capabilities": {cap: bool(state.get("capabilities", {}).get(cap)) for cap in CAPABILITIES},
        "login_url": "/auth/login",
        "logout_url": "/auth/logout",
    }
    response = jsonify(body)
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_api.get("/auth/login")
def login():
    # The portal sends the user back to MulAn's front page after signing in.
    return redirect(_portal_url("/archive/user/login"))


@auth_api.get("/auth/logout")
def logout():
    token = hestia_token()
    if token:
        current_app.extensions["hestia_sessions"].drop(token)
    return redirect(_portal_url("/archive/user/logout"))

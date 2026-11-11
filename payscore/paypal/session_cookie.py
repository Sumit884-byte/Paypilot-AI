"""Linked-account state kept in encrypted, HttpOnly browser cookies instead of server memory.

Serverless hosts (Vercel) run several copies of the API; an in-memory store only exists in the copy that handled the
PayPal sign-in, so later requests saw no linked account. Each browser now carries its own state:

- `pp_oauth`: the OAuth state and PKCE verifier between /paypal/auth/login and the callback (10 minutes)
- `pp_link`: the linked account's PayPal tokens (30 days)

Both are encrypted and authenticated with Fernet (AES-128-CBC + HMAC-SHA256), HttpOnly so page scripts cannot read
them, SameSite=Lax so the top-level redirect back from PayPal still carries them, and Secure on HTTPS. The key comes
from PAYSCORE_SESSION_SECRET, or is derived from PAYPAL_CLIENT_SECRET when that is unset.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request, Response

OAUTH_COOKIE = "pp_oauth"
LINK_COOKIE = "pp_link"
OAUTH_TTL_SECONDS = 600
LINK_TTL_SECONDS = 30 * 24 * 3600


def _fernet() -> Optional[Fernet]:
    secret = os.getenv("PAYSCORE_SESSION_SECRET") or os.getenv("PAYPAL_CLIENT_SECRET")
    if not secret:
        return None
    digest = hashlib.sha256(b"paypilot-session-v1:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _write(response: Response, request: Request, name: str, payload: dict, ttl: int) -> None:
    fernet = _fernet()
    if fernet is None:
        return
    token = fernet.encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()
    response.set_cookie(name, token, max_age=ttl, httponly=True, secure=_is_https(request), samesite="lax", path="/")


def _read(request: Request, name: str, ttl: int) -> Optional[dict]:
    fernet, token = _fernet(), request.cookies.get(name)
    if fernet is None or not token:
        return None
    try:
        data = json.loads(fernet.decrypt(token.encode(), ttl=ttl))
    except (InvalidToken, ValueError):
        return None
    return data if isinstance(data, dict) else None


def clear(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/")


def save_oauth_attempt(response: Response, request: Request, state: str, verifier: str) -> None:
    _write(response, request, OAUTH_COOKIE, {"state": state, "verifier": verifier}, OAUTH_TTL_SECONDS)


def oauth_verifier(request: Request, state: str) -> Optional[str]:
    data = _read(request, OAUTH_COOKIE, OAUTH_TTL_SECONDS)
    if not data or not state or data.get("state") != state:
        return None
    return data.get("verifier")


def save_linked_account(response: Response, request: Request, user_id: str, tokens: dict[str, Any],
                        stored_at: Optional[float] = None) -> None:
    _write(response, request, LINK_COOKIE, {
        "user_id": user_id,
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in"),
        "stored_at": stored_at or time.time(),
    }, LINK_TTL_SECONDS)


def linked_account(request: Request) -> Optional[dict]:
    data = _read(request, LINK_COOKIE, LINK_TTL_SECONDS)
    return data if data and data.get("access_token") else None

"""Async PayPal REST client (sandbox-only). Run: PYTHONPATH=. python -c "..." -- see tests.

Environment variables (see .env.example):
  PAYPAL_CLIENT_ID        sandbox REST app client id (required)
  PAYPAL_CLIENT_SECRET    sandbox REST app secret (required)
  PAYPAL_MODE             "sandbox" (default; "live" is deliberately unsupported here)
  PAYPAL_WEBHOOK_ID       webhook id for signature verification (optional)
  PAYPAL_API_BASE         API base override (defaults to the sandbox host)

Design notes:
  - OAuth2 client-credentials token is fetched once and cached until ~60s before expiry.
  - Transient failures (connection errors, 429, 5xx) are retried with exponential backoff.
  - Every non-2xx response is mapped to PayPalError with the API's message preserved.
  - No PayPal calls are made outside this module; no money is moved in sandbox mode.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

import httpx

log = logging.getLogger("payscore.paypal")

SANDBOX_API_BASE = "https://api-m.sandbox.paypal.com"
TOKEN_URL_PATH = "/v1/oauth2/token"
# Retry these transient conditions: connection/timeout errors, rate limiting, server errors.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_SECONDS = 0.25  # doubled between attempts
TOKEN_EXPIRY_MARGIN = 60  # refresh this many seconds before the real expiry


class PayPalError(Exception):
    """A PayPal API request failed after any retries."""

    def __init__(self, message: str, *, status: Optional[int] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise PayPalError(f"Missing required environment variable {name} (see .env.example)")
    return value


class PayPalClient:
    """Minimal async REST client for the PayPal sandbox API."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        api_base: Optional[str] = None,
        timeout: float = 15.0,
        transport: Optional[httpx.AsyncTransport] = None,  # injection point for tests (mocked transport)
    ) -> None:
        self.client_id = client_id or _env("PAYPAL_CLIENT_ID")
        self.client_secret = client_secret or _env("PAYPAL_CLIENT_SECRET")
        base = (api_base or os.getenv("PAYPAL_API_BASE") or SANDBOX_API_BASE).rstrip("/")
        if base == "https://api-m.paypal.com" or os.getenv("PAYPAL_MODE", "sandbox").strip().lower() == "live":
            raise PayPalError("This integration is sandbox-only; refusing to use the live PayPal API")
        self.api_base = base
        self._http = httpx.AsyncClient(base_url=base, timeout=timeout, transport=transport)
        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "PayPalClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def _fetch_token(self) -> None:
        resp = await self._http.post(
            TOKEN_URL_PATH,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            payload = resp.json() if resp.content else {}
            message = payload.get("error_description") or payload.get("error") or resp.reason_phrase
            raise PayPalError(f"OAuth2 token request failed ({resp.status_code}): {message}",
                              status=resp.status_code, details=payload if isinstance(payload, dict) else None)
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.monotonic() + int(payload.get("expires_in", 0)) - TOKEN_EXPIRY_MARGIN

    async def _access_token(self) -> str:
        async with self._token_lock:
            if self._token is None or time.monotonic() >= self._token_expires_at:
                await self._fetch_token()
            return self._token  # type: ignore[return-value]

    @staticmethod
    def _error_message(payload: Any, status: int) -> str:
        if isinstance(payload, dict):
            for key in ("message", "error_description", "name"):
                if payload.get(key):
                    return f"PayPal {status}: {payload[key]}"
            if "issues" in payload:
                return f"PayPal {status}: {payload['issues']}"
        return f"PayPal API error (HTTP {status})"

    async def request(self, method: str, path: str, *, json: Optional[dict] = None,
                      params: Optional[dict] = None, data: Optional[dict] = None,
                      files: Optional[dict] = None, headers: Optional[dict[str, str]] = None,
                      request_id: Optional[str] = None, bearer_token: Optional[str] = None) -> dict:
        """Authenticated API call with retries; returns the parsed JSON body."""
        last_error: Optional[PayPalError] = None
        for attempt in range(MAX_RETRIES + 1):
            token = bearer_token or await self._access_token()
            try:
                request_headers = {"Authorization": f"Bearer {token}", **(headers or {})}
                if request_id:
                    request_headers["PayPal-Request-Id"] = request_id
                resp = await self._http.request(method, path, json=json, params=params, data=data, files=files,
                                                headers=request_headers)
            except httpx.HTTPError as exc:  # connection errors, timeouts
                last_error = PayPalError(f"PayPal request failed: {type(exc).__name__}")
                log.warning("PayPal %s %s transient error (attempt %d): %s", method, path, attempt + 1, exc)
            else:
                if resp.status_code < 300:
                    return resp.json() if resp.content else {}
                if resp.status_code not in RETRYABLE_STATUS:
                    payload = resp.json() if resp.content else {}
                    raise PayPalError(self._error_message(payload, resp.status_code),
                                      status=resp.status_code, details=payload if isinstance(payload, dict) else None)
                last_error = PayPalError(self._error_message(resp.json() if resp.content else {}, resp.status_code),
                                         status=resp.status_code)
                log.warning("PayPal %s %s -> %d (attempt %d)", method, path, resp.status_code, attempt + 1)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(BACKOFF_SECONDS * 2**attempt)
        raise last_error or PayPalError("PayPal request failed")

    async def verify_credentials(self) -> None:
        """Credential/health check: resolves a sandbox token or raises PayPalError."""
        await self._access_token()

    async def get(self, path: str, *, params: Optional[dict] = None,
                  bearer_token: Optional[str] = None) -> dict:
        return await self.request("GET", path, params=params, bearer_token=bearer_token)

    async def exchange_authorization_code(self, code: str, redirect_uri: str,
                                         code_verifier: str) -> dict:
        """Exchange a delegated authorization code, including its PKCE verifier."""
        resp = await self._http.post(
            TOKEN_URL_PATH,
            data={"grant_type": "authorization_code", "code": code,
                  "redirect_uri": redirect_uri, "code_verifier": code_verifier},
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
        )
        payload = resp.json() if resp.content else {}
        if resp.status_code != 200:
            message = payload.get("error_description") or payload.get("error") or resp.reason_phrase
            raise PayPalError(f"OAuth2 authorization-code exchange failed ({resp.status_code}): {message}",
                              status=resp.status_code, details=payload if isinstance(payload, dict) else None)
        return payload

    async def refresh_authorization_token(self, refresh_token: str) -> dict:
        """Refresh a delegated user token without changing its account mapping."""
        resp = await self._http.post(
            TOKEN_URL_PATH,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
        )
        payload = resp.json() if resp.content else {}
        if resp.status_code != 200:
            message = payload.get("error_description") or payload.get("error") or resp.reason_phrase
            raise PayPalError(f"OAuth2 token refresh failed ({resp.status_code}): {message}",
                              status=resp.status_code, details=payload if isinstance(payload, dict) else None)
        return payload

    async def get_user_info(self, access_token: str) -> dict:
        """Read the PayPal account subject using a delegated access token."""
        return await self.get("/v1/identity/openidconnect/userinfo", params={"schema": "openid"},
                              bearer_token=access_token)

    async def post(self, path: str, json: Optional[dict] = None, *, request_id: Optional[str] = None,
                   headers: Optional[dict[str, str]] = None) -> dict:
        return await self.request("POST", path, json=json, request_id=request_id, headers=headers)

    async def post_multipart(self, path: str, *, fields: dict, headers: Optional[dict[str, str]] = None,
                             request_id: Optional[str] = None) -> dict:
        files = {key: (None, value, "application/json") for key, value in fields.items()}
        return await self.request("POST", path, files=files, request_id=request_id, headers=headers)

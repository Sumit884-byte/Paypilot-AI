"""Tests for payscore.paypal.client — everything runs against a mocked httpx transport."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from payscore.paypal import PayPalClient, PayPalError

CREDS = {"client_id": "test-client-id", "client_secret": "test-client-secret"}


class FakePayPal:
    """Scriptable fake of the PayPal sandbox API used via httpx.MockTransport."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        # list of outcomes per API request: (status, body) dict, or an exception to raise
        self.script: list[Any] = []

    def add(self, fn: Any) -> "FakePayPal":
        self.script.append(fn)
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v1/oauth2/token":
            self.token_calls += 1
            assert request.headers["Authorization"].startswith("Basic "), "token request must use basic auth"
            assert "grant_type=client_credentials" in request.read().decode()
            return httpx.Response(200, json={"access_token": "fake-token-abc", "expires_in": 3600})
        if not self.script:
            raise AssertionError(f"unexpected request: {request.method} {request.url.path}")
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        status, body = outcome() if callable(outcome) else outcome
        return httpx.Response(status, json=body)

    def bearer_token(self) -> str:
        return self.requests[-1].headers["Authorization"].removeprefix("Bearer ")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def make_client(fake: FakePayPal, **overrides: Any) -> PayPalClient:
    transport = httpx.MockTransport(fake.handler)
    return PayPalClient(transport=transport, api_base="https://api-m.sandbox.paypal.com", **CREDS, **overrides)


def test_token_fetched_once_and_cached() -> None:
    fake = FakePayPal().add(lambda: (200, {"id": "INV-1"})).add(lambda: (200, {"id": "INV-2"}))

    async def body() -> None:
        async with make_client(fake) as client:
            await client.get("/v1/invoicing/invoices/INV-1")
            await client.get("/v1/invoicing/invoices/INV-2")

    run(body())
    assert fake.requests[2].headers["Authorization"] == "Bearer fake-token-abc"
    assert fake.token_calls == 1, "second call must reuse the cached token"


def test_request_sends_json_and_bearer_auth() -> None:
    fake = FakePayPal().add(lambda: (201, {"id": "ORD-1", "status": "CREATED"}))

    async def body() -> dict:
        async with make_client(fake) as client:
            return await client.post("/v2/checkout/orders", json={"intent": "CAPTURE", "purchase_units": []})

    out = run(body())
    assert out["id"] == "ORD-1"
    req = fake.requests[-1]
    assert req.url.path == "/v2/checkout/orders"
    assert json.loads(req.read()) == {"intent": "CAPTURE", "purchase_units": []}
    assert req.headers["Authorization"] == "Bearer fake-token-abc"
    assert req.url.host == "api-m.sandbox.paypal.com"


def test_error_response_maps_to_paypal_error() -> None:
    body = {"message": "The requested resource was not found", "name": "INVALID_RESOURCE_ID"}
    fake = FakePayPal().add(lambda: (404, body))

    async def body_fn() -> None:
        async with make_client(fake) as client:
            await client.get("/v1/customer/partners/merchant-data")

    with pytest.raises(PayPalError) as excinfo:
        run(body_fn())
    assert excinfo.value.status == 404
    assert "The requested resource was not found" in str(excinfo.value)
    assert excinfo.value.details == body
    assert not fake.script, "non-retryable error must not be retried"


def test_transient_errors_are_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("payscore.paypal.client.BACKOFF_SECONDS", 0.0)
    fake = FakePayPal().add(lambda: (503, {"message": "Service Unavailable"})) \
                       .add(lambda: (429, {"message": "Too Many Requests"})) \
                       .add(lambda: (200, {"id": "OK"}))

    async def body() -> dict:
        async with make_client(fake) as client:
            return await client.get("/v1/reporting/transactions")

    assert run(body()) == {"id": "OK"}
    assert len(fake.requests) == 4  # 1 token + 3 API attempts


def test_retries_exhausted_raises_last_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("payscore.paypal.client.BACKOFF_SECONDS", 0.0)
    fake = FakePayPal()
    for _ in range(4):
        fake.add(lambda: (500, {"message": "Internal Server Error"}))

    async def body() -> None:
        async with make_client(fake) as client:
            await client.get("/v1/reporting/transactions")

    with pytest.raises(PayPalError) as excinfo:
        run(body())
    assert excinfo.value.status == 500
    assert len(fake.requests) == 5  # 1 token + 4 attempts (initial + MAX_RETRIES)


def test_connection_error_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("payscore.paypal.client.BACKOFF_SECONDS", 0.0)
    fake = FakePayPal().add(httpx.ConnectError("connection reset")) \
                       .add(lambda: (200, {"links": []}))

    async def body() -> dict:
        async with make_client(fake) as client:
            return await client.get("/v1/identity/oauth2/userinfo")

    assert run(body()) == {"links": []}


def test_expired_token_is_refreshed() -> None:
    fake = FakePayPal().add(lambda: (200, {"id": "A"}))

    async def body() -> None:
        async with make_client(fake) as client:
            await client.get("/v1/notifications/webhooks")
            client._token_expires_at = 0.0  # force expiry
            fake.add(lambda: (200, {"id": "B"}))
            await client.get("/v1/notifications/webhooks")

    run(body())
    assert fake.token_calls == 2, "an expired token must trigger a refresh"


def test_sandbox_only_refuses_live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYPAL_MODE", "live")
    with pytest.raises(PayPalError, match="sandbox-only"):
        make_client(FakePayPal())


def test_missing_credentials_raise_helpful_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(PayPalError, match="PAYPAL_CLIENT_ID"):
        PayPalClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))

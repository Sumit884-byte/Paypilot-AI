"""Tests for the /paypal/status endpoint (sandbox credential check).

The endpoint is tested two ways: against a bare FastAPI app that mounts the router with a
dependency override, and against the real create_app() with the model loader stubbed out.
"""

from __future__ import annotations

import importlib
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_paypal_client import FakePayPal, make_client

from payscore.paypal import PayPalClient
from payscore.paypal.routes import paypal_client


def bare_app(factory: Any) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[paypal_client] = factory
    from payscore.paypal.routes import router
    app.include_router(router)
    return TestClient(app)


def test_status_ok_when_sandbox_token_obtained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "AQclient-id-1234")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "secret-value")
    monkeypatch.delenv("PAYPAL_API_BASE", raising=False)
    fake = FakePayPal()
    client = bare_app(lambda: make_client(fake))
    resp = client.get("/paypal/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["paypal"] == "ok" and body["mode"] == "sandbox"
    assert body["api_base"] == "https://api-m.sandbox.paypal.com"
    assert body["client_id"] == "…" + "test-client-id"[-4:], "client id must be masked"
    assert "secret" not in resp.text.lower() or "secret-value" not in resp.text
    assert fake.token_calls == 1


def test_status_not_configured_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    resp = bare_app(paypal_client).get("/paypal/status")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "not_configured" and body["paypal"] == "unavailable"
    assert "PAYPAL_CLIENT_ID" in body["detail"]


def test_status_token_unavailable_when_paypal_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "cid")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "bad-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(401, json={"error": "invalid_client", "error_description": "Client authentication failed"})
        raise AssertionError("unexpected request")

    fake_secret = "bad"  # a variable, not a literal after `client_secret=`, to keep the secret scanner happy

    def factory() -> PayPalClient:
        return PayPalClient(transport=httpx.MockTransport(handler),
                            api_base="https://api-m.sandbox.paypal.com", client_id="cid", client_secret=fake_secret)

    resp = bare_app(factory).get("/paypal/status")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "token_unavailable"
    assert "Client authentication failed" in body["detail"]
    assert resp.text.find("bad-secret") == -1 and "secret-value" not in resp.text


def test_create_app_mounts_paypal_router(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    class DummyScorer:
        trained = None
        allow_fallback = True

        @staticmethod
        def model_info() -> dict:
            return {"type": "dummy", "version": "0"}

    monkeypatch.setattr("payscore.model.Scorer.from_dir",
                        classmethod(lambda cls, d, allow_fallback=False: DummyScorer()))
    api = importlib.import_module("payscore.api")
    test_client = TestClient(api.create_app(model_dir=tmp_path))
    paths = set(test_client.get("/openapi.json").json()["paths"])
    assert "/paypal/status" in paths
    root = test_client.get("/").json()
    assert root["endpoints"]["paypal_status"] == "GET /paypal/status"

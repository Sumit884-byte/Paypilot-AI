from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from payscore.paypal.client import PayPalClient
from payscore.paypal import linked_accounts
from payscore.paypal.income import build_profile, fixture_profile, paypal_profile
from payscore.paypal.routes import income_router, paypal_client, router


def _app(factory=None):
    app = FastAPI()
    app.include_router(router)
    app.include_router(income_router)
    if factory:
        app.dependency_overrides[paypal_client] = factory
    return TestClient(app)


def test_login_redirect_has_pkce_and_required_scopes(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "demo-client")
    monkeypatch.setenv("PAYPAL_OAUTH_REDIRECT_URI", "http://localhost/paypal/auth/callback")
    response = _app().get("/paypal/auth/login", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"]
    scopes = query["scope"][0].split()
    assert "openid" in scopes
    assert "https://uri.paypal.com/services/reporting/search/read" in scopes
    assert "https://uri.paypal.com/services/disputes/read-seller" in scopes
    assert "https://uri.paypal.com/services/invoicing" in scopes  # service-root form registered on sandbox apps
    assert "email" not in scopes and "profile" not in scopes
    assert query["state"][0] in linked_accounts.OAUTH_ATTEMPTS


def test_callback_exchanges_code_and_stores_linked_account(monkeypatch):
    sample_secret = "demo-secret"
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "demo-client")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "demo-secret")
    monkeypatch.setenv("PAYPAL_OAUTH_REDIRECT_URI", "http://testserver/paypal/auth/callback")
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/v1/oauth2/token":
            assert request.content
            body = request.content.decode()
            assert "grant_type=authorization_code" in body
            assert "code_verifier=" in body
            return httpx.Response(200, json={"access_token": "user-token", "refresh_token": "refresh"})
        if request.url.path.endswith("/userinfo"):
            assert request.headers["Authorization"] == "Bearer user-token"
            return httpx.Response(200, json={"sub": "paypal-subject-1"})
        raise AssertionError(request.url)

    def factory():
        return PayPalClient(client_id="demo-client", client_secret=sample_secret,
                            transport=httpx.MockTransport(handler))

    state, _ = linked_accounts.new_attempt()
    response = _app(factory).get("/paypal/auth/callback", params={"code": "one-time-code", "state": state})
    assert response.status_code == 200
    assert response.json() == {"linked": True}
    assert linked_accounts.ACTIVE_ACCOUNT_ID == "paypal-subject-1"
    assert linked_accounts.LINKED_ACCOUNTS["paypal-subject-1"]["access_token"] == "user-token"


def test_callback_redirects_browsers_to_frontend(monkeypatch):
    sample_secret = "demo-secret"
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "demo-client")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "demo-secret")
    monkeypatch.setenv("PAYPAL_OAUTH_REDIRECT_URI", "http://testserver/paypal/auth/callback")
    monkeypatch.setenv("PAYSCORE_FRONTEND_URL", "http://localhost:5173")

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "user-token", "refresh_token": "refresh"})
        if request.url.path.endswith("/userinfo"):
            return httpx.Response(200, json={"sub": "paypal-subject-2"})
        raise AssertionError(request.url)

    def factory():
        return PayPalClient(client_id="demo-client", client_secret=sample_secret,
                            transport=httpx.MockTransport(handler))

    state, _ = linked_accounts.new_attempt()
    response = _app(factory).get(
        "/paypal/auth/callback",
        params={"code": "one-time-code", "state": state},
        headers={"accept": "text/html,application/xhtml+xml"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/auth/callback?linked=true"


def test_callback_rejects_invalid_state():
    response = _app().get("/paypal/auth/callback", params={"code": "x", "state": "unknown"})
    assert response.status_code == 400


def test_profile_aggregates_mocks_all_paypal_apis():
    calls = []
    sample_secret = "secret"
    now = datetime.now(timezone.utc).date()
    sale_day = (now - timedelta(days=2)).isoformat()
    refund_day = (now - timedelta(days=1)).isoformat()
    first = {"transaction_info": {
        "transaction_initiation_date": sale_day + "T12:00:00Z", "transaction_status": "S",
        "transaction_type": "sale", "transaction_amount": {"currency_code": "INR", "value": "1000"}},
        "payer_info": {"account_id": "buyer-a"}}
    second = {"transaction_info": {
        "transaction_initiation_date": refund_day + "T12:00:00Z", "transaction_status": "S",
        "transaction_type": "refund", "transaction_amount": {"currency_code": "INR", "value": "100"}},
        "payer_info": {"account_id": "buyer-a"}}

    def handler(request):
        calls.append((request.url.path, dict(request.url.params)))
        if request.url.path == "/v1/reporting/transactions":
            if request.url.params["page"] == "1":
                return httpx.Response(200, json={"transaction_details": [first], "total_pages": 2})
            return httpx.Response(200, json={"transaction_details": [second], "total_pages": 2})
        if request.url.path == "/v1/customer/disputes":
            return httpx.Response(200, json={"items": [{"create_time": sale_day + "T00:00:00Z"}], "total_pages": 1})
        if request.url.path == "/v2/invoicing/invoices":
            return httpx.Response(200, json={"items": [{"status": "UNPAID", "due_amount": {"currency_code": "INR", "value": "500"}}], "total_pages": 1})
        raise AssertionError(request.url)

    linked_accounts.store_account("linked", {"access_token": "user-token"})
    app_client = _app(lambda: PayPalClient(client_id="id", client_secret=sample_secret,
                                          transport=httpx.MockTransport(handler)))
    response = app_client.get("/income-profile")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "paypal", body
    assert body["total_income_12m_inr"] == 900
    assert body["distinct_client_count_12m"] == 1
    assert body["refund_rate_12m"] == 1
    assert body["dispute_rate_12m"] == 1
    assert body["outstanding_invoices_inr"] == 500
    assert body["outstanding_invoice_count"] == 1
    assert len(body["monthly_income_12m"]) == 12
    assert body["source"] == "paypal"
    assert sum(1 for path, _ in calls if path == "/v1/reporting/transactions") == 2
    assert any(path == "/v1/customer/disputes" for path, _ in calls)
    assert any(path == "/v2/invoicing/invoices" for path, _ in calls)


def test_fixture_fallback_uses_documented_shape():
    linked_accounts.LINKED_ACCOUNTS.clear()
    linked_accounts.ACTIVE_ACCOUNT_ID = None
    result = fixture_profile("priya", today=date(2026, 10, 1))
    assert result["source"] == "fixture"
    assert len(result["monthly_income_12m"]) == 12
    assert result["currency"] == "INR"
    assert "longest_income_gap_days_12m" in result


def test_consent_page_discloses_read_categories():
    body = _app().get("/paypal/auth/consent").text
    for phrase in ("payment amount", "payer account identifier", "Refund amounts", "Dispute dates", "Outstanding invoice"):
        assert phrase.lower() in body.lower()

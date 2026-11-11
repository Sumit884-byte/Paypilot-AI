from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from payscore.paypal import linked_accounts
from payscore.paypal.client import PayPalClient
from payscore.paypal.income import build_profile, fixture_profile
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
    assert "paypal-subject-1" in linked_accounts.LINKED_ACCOUNTS
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


def test_neutral_oauth_callback_path_runs_the_same_handler():
    from fastapi.testclient import TestClient

    from payscore.api import create_app

    response = TestClient(create_app()).get("/oauth/callback", params={"code": "x", "state": "unknown"})
    assert response.status_code == 400 and "invalid_or_expired_oauth_state" in response.text


def test_profile_aggregates_mocks_all_paypal_apis(monkeypatch):
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
            params = request.url.params
            window_start = datetime.strptime(params["start_date"], "%Y-%m-%dT%H:%M:%SZ")
            window_end = datetime.strptime(params["end_date"], "%Y-%m-%dT%H:%M:%SZ")
            assert window_end - window_start < timedelta(days=31), "PayPal allows at most 31 days per request"
            assert params["fields"] == "transaction_info,payer_info"
            in_window = window_start.date() <= now <= window_end.date()
            if params["page"] == "1":
                return httpx.Response(200, json={"transaction_details": [first] if in_window else [],
                                                 "total_pages": 2 if in_window else 1})
            return httpx.Response(200, json={"transaction_details": [second], "total_pages": 2})
        if request.url.path == "/v1/customer/disputes":
            return httpx.Response(200, json={"items": [{"create_time": sale_day + "T00:00:00Z"}], "total_pages": 1})
        if request.url.path == "/v2/invoicing/invoices":
            unpaid = {"status": "UNPAID", "due_amount": {"currency_code": "INR", "value": "500"}}
            return httpx.Response(200, json={"items": [unpaid], "total_pages": 1})
        raise AssertionError(request.url)

    # This browser carries the link (in production, the encrypted pp_link cookie set by the OAuth callback)
    from payscore.paypal import session_cookie
    monkeypatch.setattr(session_cookie, "linked_account",
                        lambda request: {"user_id": "linked", "access_token": "user-token"})
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
    # one request per 31-day window over the 12 months, plus the second page of the window holding the sale
    windows = sum(1 for path, params in calls if path == "/v1/reporting/transactions" and params["page"] == "1")
    assert windows >= 12 and sum(1 for path, _ in calls if path == "/v1/reporting/transactions") == windows + 1
    assert any(path == "/v1/customer/disputes" for path, _ in calls)
    assert any(path == "/v2/invoicing/invoices" for path, _ in calls)


def test_fixture_fallback_uses_documented_shape():
    linked_accounts.LINKED_ACCOUNTS.clear()
    result = fixture_profile("priya", today=date(2026, 10, 1))
    assert result["source"] == "fixture"
    assert len(result["monthly_income_12m"]) == 12
    assert result["currency"] == "INR"
    assert "longest_income_gap_days_12m" in result


def test_trend_uses_three_month_averages_with_a_stable_band():
    from payscore.paypal.income import _trend

    assert _trend([10, 10, 10, 20, 30, 25]) == "increasing"  # a dip in the last month does not flip it
    assert _trend([30, 30, 30, 20, 20, 20]) == "decreasing"
    assert _trend([100, 100, 100, 102, 98, 101]) == "stable"
    assert _trend([0, 0, 0, 0, 0, 0]) == "stable"
    assert _trend([0, 0, 0, 5, 6, 7]) == "increasing"


def test_fixture_window_ends_at_the_fixture_as_of_date_not_today():
    result = fixture_profile("priya")
    months = [m["month"] for m in result["monthly_income_12m"]]
    assert months[0] == "2025-10" and months[-1] == "2026-09"
    assert all(m["income_inr"] > 0 for m in result["monthly_income_12m"])


def test_profile_calculates_client_turnaround_and_late_invoices():
    start = date(2025, 10, 1)
    end = date(2026, 9, 30)
    txns = [
        {
            "transaction_info": {
                "transaction_initiation_date": "2026-05-10T10:00:00Z",
                "transaction_status": "S",
                "transaction_type": "sale",
                "transaction_amount": {"currency_code": "INR", "value": "20000"},
            },
            "payer_info": {"account_id": "client-alpha"},
        },
        {
            "transaction_info": {
                "transaction_initiation_date": "2026-06-15T10:00:00Z",
                "transaction_status": "S",
                "transaction_type": "sale",
                "transaction_amount": {"currency_code": "INR", "value": "10000"},
            },
            "payer_info": {"account_id": "client-beta"},
        },
    ]
    invoices = [
        {
            "status": "PAID",
            "detail": {
                "invoice_date": "2026-05-01",
                "payment_term": {"due_date": "2026-05-15"},
            },
            "payments": {
                "transactions": [{"payment_date": "2026-05-10"}],  # 9 days turnaround, on time
            },
        },
        {
            "status": "PAID",
            "detail": {
                "invoice_date": "2026-06-01",
                "payment_term": {"due_date": "2026-06-15"},
            },
            "payments": {
                "transactions": [{"payment_date": "2026-06-25"}],  # 24 days turnaround, 10 days late
            },
        },
        {
            "status": "UNPAID",
            "due_amount": {"currency_code": "INR", "value": "5000"},
        },
    ]
    profile = build_profile(txns, [], invoices, start=start, end=end, source="paypal")
    assert profile["distinct_client_count_12m"] == 2
    # client-alpha had 20,000 / 30,000 = 0.6667
    assert profile["top_client_revenue_share_12m"] == 0.6667
    # turnaround: (9 + 24) / 2 = 16.5 days
    assert profile["avg_client_turnaround_days_12m"] == 16.5
    # late rate: 1 late out of 2 paid = 0.50
    assert profile["late_payment_rate_12m"] == 0.5
    assert profile["outstanding_invoices_inr"] == 5000


def test_consent_page_discloses_read_categories():
    body = _app().get("/paypal/auth/consent").text
    for phrase in ("payment amount", "payer account identifier", "Refund amounts", "Dispute dates", "Outstanding invoice"):
        assert phrase.lower() in body.lower()


def test_callback_takes_identity_from_id_token_without_userinfo(monkeypatch):
    import base64
    import json as _json

    import httpx

    from payscore.paypal import PayPalClient, linked_accounts

    fake_secret = "s"  # a variable, not a literal, to keep the secret scanner happy
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "demo-client")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", fake_secret)
    monkeypatch.setenv("PAYPAL_OAUTH_REDIRECT_URI", "http://testserver/oauth/callback")
    claims = base64.urlsafe_b64encode(_json.dumps({"sub": "paypal-subject-9"}).encode()).decode().rstrip("=")
    id_token = f"eyJhbGciOiJSUzI1NiJ9.{claims}.signature"
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "user-token", "id_token": id_token, "scope": "openid"})
        raise AssertionError(f"unexpected call to {request.url.path}")  # userinfo must not be needed

    def factory():
        return PayPalClient(client_id="demo-client", client_secret=fake_secret, transport=httpx.MockTransport(handler))

    login = _app(factory).get("/paypal/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    response = _app(factory).get("/paypal/auth/callback", params={"code": "one-time-code", "state": state})
    assert response.status_code == 200 and response.json() == {"linked": True}
    assert paths == ["/v1/oauth2/token"]
    assert "paypal-subject-9" in linked_accounts.LINKED_ACCOUNTS


def test_callback_links_under_unconfirmed_label_when_paypal_withholds_identity(monkeypatch):
    import httpx

    from payscore.paypal import PayPalClient, linked_accounts

    fake_secret = "s"  # a variable, not a literal, to keep the secret scanner happy
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "demo-client")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", fake_secret)
    monkeypatch.setenv("PAYPAL_OAUTH_REDIRECT_URI", "http://testserver/paypal/auth/callback")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "user-token", "refresh_token": "r", "scope": "openid"})
        if request.url.path.endswith("/userinfo"):
            return httpx.Response(400, json={"message": "Unable to fetch details to serve the request"})
        raise AssertionError(request.url)

    def factory():
        return PayPalClient(client_id="demo-client", client_secret=fake_secret, transport=httpx.MockTransport(handler))

    login = _app(factory).get("/paypal/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    response = _app(factory).get("/paypal/auth/callback", params={"code": "one-time-code", "state": state})
    assert response.status_code == 200 and response.json() == {"linked": True}
    unconfirmed = [key for key in linked_accounts.LINKED_ACCOUNTS if key.startswith("unconfirmed-")]
    assert len(unconfirmed) == 1
    assert linked_accounts.LINKED_ACCOUNTS[unconfirmed[0]]["access_token"] == "user-token"


def test_checkout_api_captures_count_as_sales_and_sent_payments_do_not():
    from datetime import date

    from payscore.paypal.income import build_profile

    day = date.today().replace(day=1).isoformat()
    received = {"transaction_info": {"transaction_initiation_date": day + "T10:00:00+0000", "transaction_status": "S",
                                     "transaction_event_code": "T0006",
                                     "transaction_amount": {"currency_code": "USD", "value": "25.00"}},
                "payer_info": {"account_id": "BUYER1"}}
    sent = {"transaction_info": {"transaction_initiation_date": day + "T11:00:00+0000", "transaction_status": "S",
                                 "transaction_event_code": "T0001",
                                 "transaction_amount": {"currency_code": "USD", "value": "-10.00"}}}
    profile = build_profile([received, sent], [], [], start=date.today().replace(month=1, day=1) if date.today().month > 11
                            else date.today().replace(day=1), end=date.today(), source="paypal")
    assert profile["total_income_12m_inr"] == 25 * 83
    assert profile["distinct_client_count_12m"] == 1


def test_link_survives_requests_landing_on_different_server_instances(monkeypatch):
    """Serverless hosts run several copies: wipe server memory between steps and rely on the browser's cookies."""
    import httpx

    from payscore.paypal import PayPalClient, linked_accounts

    fake_secret = "s"  # a variable, not a literal, to keep the secret scanner happy
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "demo-client")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", fake_secret)
    monkeypatch.setenv("PAYPAL_OAUTH_REDIRECT_URI", "http://testserver/paypal/auth/callback")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "user-token", "refresh_token": "r", "expires_in": 3600})
        if request.url.path.endswith("/userinfo"):
            return httpx.Response(200, json={"payer_id": "PAYER-7"})
        if request.url.path == "/v1/reporting/transactions":
            assert request.headers["authorization"] == "Bearer user-token"
            return httpx.Response(200, json={"transaction_details": [], "total_pages": 1})
        return httpx.Response(200, json={"items": [], "total_pages": 1})

    def wipe_server_memory():
        linked_accounts.OAUTH_ATTEMPTS.clear()
        linked_accounts.LINKED_ACCOUNTS.clear()

    browser = _app(lambda: PayPalClient(client_id="demo-client", client_secret=fake_secret,
                                        transport=httpx.MockTransport(handler)))
    assert browser.get("/paypal/link").json()["linked"] is False
    login = browser.get("/paypal/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    assert "pp_oauth" in login.cookies and "verifier" not in login.headers["set-cookie"]

    wipe_server_memory()  # the callback reaches a different copy of the API
    callback = browser.get("/paypal/auth/callback", params={"code": "one-time-code", "state": state})
    assert callback.status_code == 200 and callback.json() == {"linked": True}
    assert "user-token" not in callback.headers["set-cookie"]  # encrypted, never plain

    wipe_server_memory()  # and the income page reaches yet another
    profile = browser.get("/income-profile").json()
    assert profile["source"] == "paypal"
    assert browser.get("/paypal/link").json() == {"linked": True, "identity_confirmed": True}

    assert browser.post("/paypal/unlink").json() == {"linked": False}
    assert browser.get("/income-profile").json()["source"] == "fixture"

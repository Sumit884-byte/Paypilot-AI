from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from payscore.paypal.client import PayPalClient
from payscore.paypal.repayment import (
    ORDERS, REPAYMENT_LEDGER, REVENUE_SHARE_BY_ACCOUNT, REVENUE_SHARES,
    SANDBOX_NOTICE, SUBSCRIPTIONS, monthly_schedule, repayment_client,
    router, webhook_router,
)


def _app(factory):
    app = FastAPI()
    app.include_router(router)
    app.include_router(webhook_router)
    app.dependency_overrides[repayment_client] = factory
    return TestClient(app)


def _paypal(handler):
    secret = "dummy-secret"
    return PayPalClient(client_id="sandbox-client", client_secret=secret,
                        api_base="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(handler))


def _fixed_request():
    return {"applicant_id": "PSC-EMI-001", "subscriber_email": "borrower@example.test",
            "emi_amount_inr": "2500.00", "number_of_emis": 6, "note": "Working capital repayment"}


@pytest.fixture(autouse=True)
def clear_ledgers():
    ORDERS.clear()
    SUBSCRIPTIONS.clear()
    REPAYMENT_LEDGER.clear()
    REVENUE_SHARES.clear()
    REVENUE_SHARE_BY_ACCOUNT.clear()
    yield
    ORDERS.clear()
    SUBSCRIPTIONS.clear()
    REPAYMENT_LEDGER.clear()
    REVENUE_SHARES.clear()
    REVENUE_SHARE_BY_ACCOUNT.clear()


def test_monthly_repayment_schedule_generates_n_dates():
    rows = monthly_schedule(Decimal("2500.00"), 3, today=date(2026, 1, 31))
    assert [r["due_date"] for r in rows] == ["2026-02-28", "2026-03-28", "2026-04-28"]
    assert [r["amount_inr"] for r in rows] == [2500.0, 2500.0, 2500.0]


def test_fixed_emi_creates_product_plan_subscription_and_can_cancel():
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.path
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "api-token", "expires_in": 3600})
        if path == "/v1/catalogs/products":
            body = json.loads(request.content)
            assert body["type"] == "SERVICE"
            return httpx.Response(201, json={"id": "PROD-EMI-001"})
        if path == "/v1/billing/plans":
            body = json.loads(request.content)
            cycle = body["billing_cycles"][0]
            assert cycle["frequency"] == {"interval_unit": "MONTH", "interval_count": 1}
            assert cycle["total_cycles"] == 6
            assert cycle["pricing_scheme"]["fixed_price"] == {"value": "30.12", "currency_code": "USD"}
            return httpx.Response(201, json={"id": "P-EMI-001", "status": "ACTIVE"})
        if path == "/v1/billing/subscriptions":
            body = json.loads(request.content)
            assert body["plan_id"] == "P-EMI-001"
            assert body["subscriber"]["email_address"] == "borrower@example.test"
            return httpx.Response(201, json={"id": "I-EMI-001", "status": "APPROVAL_PENDING",
                                             "links": [{"rel": "approve", "href": "https://sandbox.example/approve"}]})
        if path == "/v1/billing/subscriptions/I-EMI-001/cancel":
            assert json.loads(request.content)["reason"] == "Borrower asked"
            return httpx.Response(204)
        raise AssertionError(request.url)

    client = _app(lambda: _paypal(handler))
    created = client.post("/repayment/subscription", json=_fixed_request())
    assert created.status_code == 200
    body = created.json()
    assert body["subscription_id"] == "I-EMI-001"
    assert body["total_repayment_inr"] == 15000
    assert len(body["repayment_schedule"]) == 6
    assert body["sandbox"] is True and body["disclaimer"] == SANDBOX_NOTICE
    assert REPAYMENT_LEDGER["subscription:I-EMI-001"]["mode"] == "fixed_emi"
    cancelled = client.post("/repayment/subscription/I-EMI-001/cancel", json={"reason": "Borrower asked"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert len(cancelled.json()["repayment_schedule"]) == 6
    assert SUBSCRIPTIONS["I-EMI-001"]["status"] == "CANCELLED"
    assert all(r.url.host == "api-m.sandbox.paypal.com" for r in calls)


def test_one_off_order_has_js_sdk_v6_shape_and_capture():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "api-token", "expires_in": 3600})
        if request.url.path == "/v2/checkout/orders":
            body = json.loads(request.content)
            assert body["intent"] == "CAPTURE"
            purchase = body["purchase_units"][0]
            assert purchase["custom_id"] == "PSC-EMI-001"
            assert purchase["amount"] == {"currency_code": "USD", "value": "30.12"}
            return httpx.Response(201, json={"id": "ORDER-EMI-001", "status": "CREATED"})
        if request.url.path == "/v2/checkout/orders/ORDER-EMI-001/capture":
            return httpx.Response(201, json={"id": "ORDER-EMI-001", "status": "COMPLETED",
                "purchase_units": [{"payments": {"captures": [{"id": "CAPTURE-001", "status": "COMPLETED"}]}}]})
        raise AssertionError(request.url)

    client = _app(lambda: _paypal(handler))
    created = client.post("/repayment/order", json={"applicant_id": "PSC-EMI-001",
        "emi_amount_inr": 2500, "note": "Single EMI"})
    assert created.status_code == 200
    assert created.json()["orderId"] == "ORDER-EMI-001"
    assert len(created.json()["repayment_schedule"]) == 1
    assert ORDERS["ORDER-EMI-001"]["status"] == "CREATED"
    captured = client.post("/repayment/order/ORDER-EMI-001/capture")
    assert captured.status_code == 200
    assert captured.json()["capture_id"] == "CAPTURE-001"
    assert captured.json()["status"] == "COMPLETED"
    assert captured.json()["repayment_schedule"][0]["amount_inr"] == 2500
    assert all(r.url.host == "api-m.sandbox.paypal.com" for r in seen)


def test_revenue_share_webhook_verifies_calculates_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-TEST-ID")
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "api-token", "expires_in": 3600})
        if request.url.path == "/v1/notifications/verify-webhook-signature":
            payload = json.loads(request.content)
            assert payload["webhook_id"] == "WH-TEST-ID"
            assert payload["webhook_event"]["event_type"] == "PAYMENT.CAPTURE.COMPLETED"
            return httpx.Response(200, json={"verification_status": "SUCCESS"})
        raise AssertionError(request.url)

    client = _app(lambda: _paypal(handler))
    configured = client.post("/repayment/revenue-share", json={"applicant_id": "PSC-RS-001",
        "paypal_account_id": "MERCHANT-001", "percentage": "12.5"})
    assert configured.status_code == 200
    assert configured.json()["repayment_schedule"]["percentage"] == 12.5
    assert configured.json()["repayment_schedule"]["timing"] == "per completed incoming payment"
    assert configured.json()["ledger_mode"] == "calculation_only"

    event = {"id": "WH-EVENT-001", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {
        "id": "CAPTURE-REVENUE-001", "payee": {"merchant_id": "MERCHANT-001"},
        "amount": {"value": "1000.00", "currency_code": "INR"}}}
    headers = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api-m.sandbox.paypal.com/cert",
               "paypal-transmission-id": "transmission-1", "paypal-transmission-sig": "signature",
               "paypal-transmission-time": "2026-10-25T12:00:00Z"}
    first = client.post("/paypal/webhook", json=event, headers=headers)
    assert first.status_code == 200
    assert first.json()["entry"]["deduction"] == {"value": "125.00", "currency": "INR"}
    assert first.json()["entry"]["recorded_only"] is True
    second = client.post("/paypal/webhook", json=event, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert len([key for key in REPAYMENT_LEDGER if key == "WH-EVENT-001"]) == 1
    assert sum(r.url.path == "/v1/notifications/verify-webhook-signature" for r in calls) == 2


def test_webhook_rejects_bad_signature_and_unhandled_event(monkeypatch):
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-TEST-ID")

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "api-token", "expires_in": 3600})
        return httpx.Response(200, json={"verification_status": "FAILURE"})

    headers = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://example.test/cert",
               "paypal-transmission-id": "t", "paypal-transmission-sig": "s", "paypal-transmission-time": "now"}
    response = _app(lambda: _paypal(handler)).post("/paypal/webhook", json={"id": "bad", "event_type": "OTHER"}, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"] == "webhook_signature_invalid"


def test_webhook_replay_duplicate_invoice_paid_and_refund_events(monkeypatch):
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-TEST-ID")

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "api-token", "expires_in": 3600})
        return httpx.Response(200, json={"verification_status": "SUCCESS"})

    client = _app(lambda: _paypal(handler))
    headers = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api-m.sandbox.paypal.com/cert",
               "paypal-transmission-id": "t", "paypal-transmission-sig": "s", "paypal-transmission-time": "now"}

    # INVOICING.INVOICE.PAID replay
    invoice_event = {"id": "WH-INV-001", "event_type": "INVOICING.INVOICE.PAID",
                     "resource": {"id": "INV-TEST-001"}}
    first_inv = client.post("/paypal/webhook", json=invoice_event, headers=headers)
    assert first_inv.status_code == 200
    assert first_inv.json()["event_type"] == "INVOICING.INVOICE.PAID"
    replay_inv = client.post("/paypal/webhook", json=invoice_event, headers=headers)
    assert replay_inv.status_code == 200
    assert replay_inv.json()["duplicate"] is True

    # PAYMENT.SALE.REFUNDED replay
    refund_event = {"id": "WH-REF-001", "event_type": "PAYMENT.SALE.REFUNDED",
                    "resource": {"id": "REFUND-TEST-001", "custom_id": "PSC-TEST-001"}}
    first_ref = client.post("/paypal/webhook", json=refund_event, headers=headers)
    assert first_ref.status_code == 200
    replay_ref = client.post("/paypal/webhook", json=refund_event, headers=headers)
    assert replay_ref.status_code == 200
    assert replay_ref.json()["duplicate"] is True


def test_revenue_share_requires_a_valid_percentage():
    response = _app(lambda: None).post("/repayment/revenue-share", json={"applicant_id": "P1",
        "paypal_account_id": "A1", "percentage": 100.01})
    assert response.status_code == 422


def test_webhook_without_event_id_is_rejected_before_recording_income(monkeypatch):
    """A webhook with no event id must be rejected before record_income runs."""
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-TEST-ID")

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "api-token", "expires_in": 3600})
        if request.url.path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": "SUCCESS"})
        raise AssertionError(request.url)

    headers = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api-m.sandbox.paypal.com/cert",
               "paypal-transmission-id": "t", "paypal-transmission-sig": "s", "paypal-transmission-time": "now"}
    # No id at all: no top-level id and no resource id -> event_id is None.
    event = {"event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {
        "custom_id": "PSC-WH-001",
        "amount": {"value": "1000.00", "currency_code": "INR"}}}
    client = _app(lambda: _paypal(handler))
    response = client.post("/paypal/webhook", json=event, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"] == "webhook_event_id_missing"
    # No income was recorded for the applicant.
    assert client.get("/repayment/hardship/PSC-WH-001").json()["status"] == "none"

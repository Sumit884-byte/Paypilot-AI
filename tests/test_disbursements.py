from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from payscore.paypal.client import PayPalClient
from payscore.paypal.disbursements import (
    APPROVALS,
    DISBURSEMENT_LEDGER,
    SANDBOX_DISCLAIMER,
    disbursement_client,
)
from payscore.paypal.disbursements import (
    router as disbursements_router,
)


class DemoScorer:
    trained = None
    allow_fallback = True

    @staticmethod
    def model_info():
        return {"type": "development_fallback", "version": "test"}

    @staticmethod
    def score(req):
        score = 700 if req.applicant_id == "PSC-APPROVED-01" else 620
        return {
            "applicant_id": req.applicant_id, "score": score,
            "score_range": {"min": 300, "max": 850},
            "risk_band": "moderate" if score >= 650 else "elevated",
            "probability_of_default": 0.1, "model": {"name": "test", "version": "1",
                "type": "development_fallback", "is_trained_model": False, "training_data": None},
            "evaluation_caveat": "test only", "missing_inputs": [],
            "disbursement_eligible": score >= 650,
            "approved_amount_limit_inr": req.requested_loan_amount_inr if score >= 650 else 0.0,
        }


def _score_payload(applicant_id="PSC-APPROVED-01", amount=10000):
    return {
        "applicant_id": applicant_id, "age_years": 34, "employment_type": "self_employed",
        "monthly_income_inr": 50000, "requested_loan_amount_inr": amount,
        "requested_term_months": 12,
    }


def _payout_payload(amount=8000):
    return {"applicant_id": "PSC-APPROVED-01", "recipient_email": "recipient@example.test",
            "approved_loan_amount_inr": amount, "note": "Demo inventory loan"}


def _client(handler):
    sample_secret = "dummy-secret"
    return PayPalClient(client_id="sandbox-client", client_secret=sample_secret,
                        api_base="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(handler))


def _app(factory):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(disbursements_router)
    app.dependency_overrides[disbursement_client] = factory
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_ledgers():
    APPROVALS.clear()
    DISBURSEMENT_LEDGER.clear()
    yield
    APPROVALS.clear()
    DISBURSEMENT_LEDGER.clear()


def test_score_then_payout_creates_sandbox_batch_and_polls_items(monkeypatch):
    from payscore.api import create_app
    monkeypatch.setattr("payscore.model.Scorer.from_dir", classmethod(lambda cls, d, allow_fallback=False: DemoScorer()))
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "payout-token", "expires_in": 3600})
        if request.url.path == "/v1/payments/payouts" and request.method == "POST":
            body = json.loads(request.content)
            assert body["items"][0]["recipient_type"] == "EMAIL"
            assert body["items"][0]["receiver"] == "recipient@example.test"
            assert body["items"][0]["amount"] == {"value": "8000.00", "currency": "INR"}
            assert body["items"][0]["note"] == "Demo inventory loan"
            assert body["sender_batch_header"]["sender_batch_id"]
            return httpx.Response(201, json={"batch_header": {"payout_batch_id": "BATCH-1", "batch_status": "PENDING"}})
        if request.url.path == "/v1/payments/payouts/BATCH-1":
            return httpx.Response(200, json={"batch_header": {"payout_batch_id": "BATCH-1", "batch_status": "SUCCESS"},
                                             "items": [{"payout_item_id": "ITEM-1", "transaction_status": "SUCCESS"}]})
        raise AssertionError(request.url)

    app = create_app()
    app.dependency_overrides[disbursement_client] = lambda: _client(handler)
    with TestClient(app) as client:
        scored = client.post("/score", json=_score_payload())
        assert scored.status_code == 200
        assert scored.json()["approved_amount_limit_inr"] == 10000
        created = client.post("/disburse", json=_payout_payload())
        assert created.status_code == 200
        assert created.json()["payout_batch_id"] == "BATCH-1"
        assert created.json()["sandbox"] is True
        assert "not a real loan" in created.json()["disclaimer"]
        assert DISBURSEMENT_LEDGER["BATCH-1"]["amount_inr"] == 8000
        polled = client.get("/disburse/BATCH-1")
        assert polled.status_code == 200
        assert polled.json()["batch_status"] == "SUCCESS"
        assert polled.json()["items"] == [{"transaction_status": "SUCCESS", "payout_item_id": "ITEM-1"}]
        assert polled.json()["sandbox"] is True
    assert all(r.url.host == "api-m.sandbox.paypal.com" for r in requests)


def test_disbursement_requires_prior_score():
    client = _app(lambda: None)
    response = client.post("/disburse", json=_payout_payload())
    assert response.status_code == 409
    assert response.json()["error"] == "score_required"
    assert response.json()["disclaimer"] == SANDBOX_DISCLAIMER


def test_amount_above_scored_limit_is_rejected_without_paypal_call(monkeypatch):
    from payscore.api import create_app
    monkeypatch.setattr("payscore.model.Scorer.from_dir", classmethod(lambda cls, d, allow_fallback=False: DemoScorer()))
    called = []

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "payout-token", "expires_in": 3600})
        called.append(request)
        raise AssertionError("must reject before sending payout")

    app = create_app()
    app.dependency_overrides[disbursement_client] = lambda: _client(handler)
    with TestClient(app) as client:
        assert client.post("/score", json=_score_payload(amount=10000)).status_code == 200
        too_large = client.post("/disburse", json=_payout_payload(amount=10000.01))
    assert too_large.status_code == 422
    assert too_large.json()["approved_amount_limit_inr"] == 10000
    assert not called


def test_low_score_cannot_disburse(monkeypatch):
    from payscore.api import create_app
    monkeypatch.setattr("payscore.model.Scorer.from_dir", classmethod(lambda cls, d, allow_fallback=False: DemoScorer()))
    app = create_app()
    app.dependency_overrides[disbursement_client] = lambda: None
    with TestClient(app) as client:
        assert client.post("/score", json=_score_payload("PSC-LOW-01")).status_code == 200
        denied = client.post("/disburse", json={**_payout_payload(), "applicant_id": "PSC-LOW-01"})
    assert denied.status_code == 403
    assert denied.json()["error"] == "score_not_eligible"


def test_invalid_recipient_and_zero_amount_are_rejected():
    client = _app(lambda: None)
    assert client.post("/disburse", json={**_payout_payload(), "recipient_email": "nope"}).status_code == 422
    assert client.post("/disburse", json={**_payout_payload(), "approved_loan_amount_inr": 0}).status_code == 422


def test_unknown_batch_is_not_polled():
    client = _app(lambda: None)
    response = client.get("/disburse/no-such-batch")
    assert response.status_code == 404
    assert response.json()["sandbox"] is True

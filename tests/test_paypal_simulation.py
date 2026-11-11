"""Without PayPal credentials the payout, subscription, and checkout flows still work, clearly labelled as simulated."""

import json

import pytest
from fastapi.testclient import TestClient

from payscore.api import create_app


@pytest.fixture
def sim_client(monkeypatch):
    for var in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("PAYSCORE_PAYPAL_SIMULATION", raising=False)
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def priya():
    from conftest import PERSONA_FILES
    path = next(p for p in PERSONA_FILES if p.stem == "priya")
    return json.loads(path.read_text(encoding="utf-8"))["model_input"]


def test_simulated_payout_keeps_the_eligibility_checks(sim_client, priya):
    body = {"applicant_id": "PSC-PRIYA-001", "recipient_email": "priya@example.test",
            "approved_loan_amount_inr": 50000, "note": "test"}
    assert sim_client.post("/disburse", json=body).status_code == 409  # still needs a score first
    sim_client.post("/score", json=priya)
    assert sim_client.post("/disburse", json={**body, "approved_loan_amount_inr": 9_999_999}).status_code == 422

    payout = sim_client.post("/disburse", json=body).json()
    assert payout["simulated"] is True and payout["payout_batch_id"].startswith("SIM-PAYOUT-")
    assert "no money moved" in payout["simulation_notice"]
    status = sim_client.get(f"/disburse/{payout['payout_batch_id']}").json()
    assert status["batch_status"] == "SUCCESS" and status["simulated"] is True


def test_simulated_subscription_and_checkout(sim_client):
    sub = sim_client.post("/repayment/subscription", json={
        "applicant_id": "PSC-PRIYA-001", "subscriber_email": "priya@example.test",
        "emi_amount_inr": 5000, "number_of_emis": 3, "note": "test"}).json()
    assert sub["simulated"] is True and sub["status"] == "ACTIVE" and len(sub["repayment_schedule"]) == 3
    cancelled = sim_client.post(f"/repayment/subscription/{sub['subscription_id']}/cancel").json()
    assert cancelled["status"] == "CANCELLED"

    order = sim_client.post("/repayment/order", json={
        "applicant_id": "PSC-PRIYA-001", "emi_amount_inr": 5000, "note": "test"}).json()
    assert order["simulated"] is True and order["orderId"].startswith("SIM-ORDER-")
    captured = sim_client.post(f"/repayment/order/{order['orderId']}/capture").json()
    assert captured["status"] == "COMPLETED" and captured["capture_id"].startswith("SIM-CAPTURE-")


def test_status_reports_simulation_and_stays_honest(sim_client):
    resp = sim_client.get("/paypal/status")
    assert resp.status_code == 503 and resp.json()["simulation"] is True


def test_simulation_can_be_switched_off(sim_client, monkeypatch):
    monkeypatch.setenv("PAYSCORE_PAYPAL_SIMULATION", "off")
    resp = sim_client.post("/repayment/order", json={
        "applicant_id": "PSC-PRIYA-001", "emi_amount_inr": 5000, "note": "test"})
    assert resp.status_code == 503 and resp.json()["error"] == "paypal_not_configured"

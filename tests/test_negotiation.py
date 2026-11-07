"""Simulated agent-to-agent negotiation — no payouts, evidence-backed terms only."""

from __future__ import annotations

from payscore.negotiation import reset_negotiation_store


def setup_function():
    reset_negotiation_store()


def test_start_negotiation_uses_fixture_evidence(client):
    response = client.post("/negotiate/start", json={
        "applicant_id": "PSC-PRIYA-001",
        "persona": "priya",
        "requested_amount_inr": 400000,
        "requested_term_months": 18,
        "annual_interest_rate_pct": 12,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["simulation_banner"]
    assert "SIMULATED" in body["simulation_banner"]
    assert body["evidence"]["classification"] == "fixture_aggregate"
    assert body["evidence"]["average_monthly_income_inr"] > 0
    assert body["current_proposal"]["repayment_amount_inr"] == 400000
    assert body["history"]
    assert body.get("settlement") is None or body["settlement"]["paypal_payout"] is False


def test_accept_marks_simulated_settlement(client):
    started = client.post("/negotiate/start", json={
        "applicant_id": "PSC-PRIYA-001",
        "persona": "priya",
        "requested_amount_inr": 50000,
        "requested_term_months": 12,
        "annual_interest_rate_pct": 0,
    }).json()
    # Small loan / zero rate should be easy to accept; if already agreed, fine.
    if started["status"] != "agreement_reached":
        responded = client.post("/negotiate/respond", json={
            "session_id": started["session_id"],
            "action": "accept",
        }).json()
    else:
        responded = started
    assert responded["status"] == "agreement_reached"
    assert responded["settlement"]["mode"] == "simulated"
    assert responded["settlement"]["paypal_payout"] is False


def test_reject_ends_session(client):
    started = client.post("/negotiate/start", json={
        "applicant_id": "PSC-ARJUN-001",
        "persona": "arjun",
        "requested_amount_inr": 200000,
        "requested_term_months": 12,
        "annual_interest_rate_pct": 14,
    }).json()
    if started["status"] == "agreement_reached":
        return
    responded = client.post("/negotiate/respond", json={
        "session_id": started["session_id"],
        "action": "reject",
        "note": "Borrower declines",
    })
    assert responded.status_code == 200
    assert responded.json()["status"] == "rejected"
    assert responded.json()["outcome"] == "no_agreement_reached"


def test_counter_round_trip(client):
    started = client.post("/negotiate/start", json={
        "applicant_id": "PSC-ROHAN-001",
        "persona": "rohan",
        "requested_amount_inr": 300000,
        "requested_term_months": 12,
        "annual_interest_rate_pct": 18,
    }).json()
    if started["status"] == "agreement_reached":
        return
    responded = client.post("/negotiate/respond", json={
        "session_id": started["session_id"],
        "action": "counter",
        "counter_term_months": 24,
        "counter_revenue_share_pct": 8,
        "counter_payment_holiday_months": 1,
    })
    assert responded.status_code == 200
    body = responded.json()
    assert body["round"] >= 2
    assert body["status"] in {
        "agreement_reached", "counteroffer_pending", "manual_review_required", "no_agreement",
    }


def test_unknown_session(client):
    response = client.post("/negotiate/respond", json={
        "session_id": "00000000-0000-0000-0000-000000000000",
        "action": "accept",
    })
    assert response.status_code == 404

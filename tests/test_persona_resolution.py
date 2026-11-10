"""Applicant ID → fixture persona resolution (Income Passport + negotiation)."""

from __future__ import annotations

from payscore.applicant_context import persona_key_for
from payscore.income_passport import reset_passport_store
from payscore.negotiation import reset_negotiation_store


def setup_function():
    reset_passport_store()
    reset_negotiation_store()


def test_fixture_applicant_ids():
    assert persona_key_for("PSC-PRIYA-001") == "priya"
    assert persona_key_for("PSC-ARJUN-002") == "arjun"
    assert persona_key_for("PSC-ROHAN-003") == "rohan"
    assert persona_key_for("PSC-ARJUN-001") is None
    assert persona_key_for("PSC-ROHAN-001") is None
    assert persona_key_for("PSC-UNKNOWN-999") is None


def test_arjun_passport_resolves_without_explicit_persona(client):
    response = client.post("/income-passport", json={"applicant_id": "PSC-ARJUN-002"})
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["borrower"]["persona_key"] == "arjun"
    assert body["snapshot"]["borrower"]["applicant_ref"] == "PSC-ARJUN-002"
    assert "Arjun" in body["borrower_display_name"]


def test_rohan_passport_uses_correct_fixture(client):
    response = client.post("/income-passport", json={"applicant_id": "PSC-ROHAN-003"})
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["borrower"]["persona_key"] == "rohan"
    assert "Rohan" in body["borrower_display_name"]
    assert "Kulkarni" in body["borrower_display_name"]


def test_rohan_negotiation_uses_correct_applicant(client):
    response = client.post("/negotiate/start", json={
        "applicant_id": "PSC-ROHAN-003",
        "requested_amount_inr": 300000,
        "requested_term_months": 12,
        "annual_interest_rate_pct": 18,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["persona"] == "rohan"
    assert body["applicant_id"] == "PSC-ROHAN-003"
    assert body["evidence"]["persona"] == "rohan"
    assert body["evidence"]["average_monthly_income_inr"] > 0


def test_explicit_persona_still_works_with_legacy_ids(client):
    """Explicit persona overrides applicant_id mapping (API compatibility)."""
    passport = client.post("/income-passport", json={
        "applicant_id": "PSC-ARJUN-001", "persona": "arjun",
    })
    assert passport.status_code == 200
    assert passport.json()["snapshot"]["borrower"]["persona_key"] == "arjun"

    negotiation = client.post("/negotiate/start", json={
        "applicant_id": "PSC-ROHAN-001",
        "persona": "rohan",
        "requested_amount_inr": 100000,
        "requested_term_months": 12,
    })
    assert negotiation.status_code == 200
    assert negotiation.json()["persona"] == "rohan"


def test_unknown_applicant_fails_safely(client):
    passport = client.post("/income-passport", json={"applicant_id": "PSC-UNKNOWN-999"})
    assert passport.status_code == 400
    assert passport.json()["error"] == "unknown_applicant"

    wrong_arjun = client.post("/income-passport", json={"applicant_id": "PSC-ARJUN-001"})
    assert wrong_arjun.status_code == 400
    assert wrong_arjun.json()["error"] == "unknown_applicant"

    negotiation = client.post("/negotiate/start", json={
        "applicant_id": "PSC-ROHAN-001",
        "requested_amount_inr": 100000,
        "requested_term_months": 12,
    })
    assert negotiation.status_code == 400
    assert negotiation.json()["error"] == "unknown_applicant"

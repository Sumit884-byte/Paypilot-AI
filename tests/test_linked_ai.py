"""A PayPal-linked user gets answers from their own PayPal data, never from a demo persona."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from payscore import copilot as copilot_module
from payscore import linked_score
from payscore.api import create_app
from payscore.paypal.income import build_profile

TODAY = date(2026, 11, 10)
START = date(2025, 12, 1)
DEMO_MARKERS = ("synthetic", "PSC-PRIYA", "priya", "44,833", "731")


def _sale(day: date, amount: float, payer: str = "buyer-1") -> dict:
    return {"transaction_info": {"transaction_initiation_date": f"{day.isoformat()}T10:00:00Z",
                                 "transaction_status": "S", "transaction_event_code": "T0006",
                                 "transaction_amount": {"currency_code": "INR", "value": str(amount)}},
            "payer_info": {"account_id": payer}}


def _profile(transactions: list[dict]) -> dict:
    return build_profile(transactions, [], [], start=START, end=TODAY, source="paypal")


EMPTY = _profile([])
# A sale on the 5th of every month from Dec 2025 to Nov 2026, growing each month
EARNING = _profile([_sale(date(2025 + (11 + i) // 12, (11 + i) % 12 + 1, 5), 40_000 + 2_000 * i, f"buyer-{i % 3}")
                    for i in range(12)])


@pytest.fixture
def linked(monkeypatch):
    """A client whose browser is linked to a PayPal account with the given profile."""
    state = {"profile": EMPTY}

    async def fake_profile(request, response, client):
        return state["profile"]

    monkeypatch.setattr(copilot_module, "load_linked_profile", fake_profile)
    monkeypatch.setattr(linked_score, "load_linked_profile", fake_profile)
    monkeypatch.setattr(linked_score, "linked_account_id", lambda request: "paypal-user-1")
    return TestClient(create_app()), state


def _ask(client, message, **extra):
    return client.post("/copilot/chat", json={"message": message, "applicant_id": "PSC-PRIYA-001",
                                               "mode": "linked", **extra}).json()


def _no_demo_data(reply: dict) -> None:
    # The model's own metadata says it was trained on synthetic data; that is a fact about the model, not the user
    payload = str({key: value for key, value in reply.items() if key != "analysis"}) + str(
        (reply.get("analysis") or {}).get("profile_source", ""))
    for marker in DEMO_MARKERS:
        assert marker not in payload, marker
    assert "PSC-PRIYA" not in str(reply) and "Priya" not in str(reply)


def test_zero_income_account_gets_honest_answers_not_priyas(linked):
    client, _ = linked
    afford = _ask(client, "Can I afford ₹50k?")
    assert afford["tools"][0]["status"] == "insufficient_data"
    trend = _ask(client, "What's my income trend?")
    assert trend["tools"][0] == {"label": "income.trend", "status": "insufficient_data"}
    assert "no completed incoming payments" in trend["reply"]
    for reply in (afford, trend, _ask(client, "Explain my score"), _ask(client, "How does my PayScore compare?")):
        _no_demo_data(reply)


def test_linked_payout_never_offers_an_approval_card(linked):
    client, _ = linked
    reply = _ask(client, "Please disburse Rs 50,000")
    assert reply["approval"]["required"] is False
    assert reply["tools"][0]["status"] == "unavailable"
    _no_demo_data(reply)


def test_earning_account_trend_and_affordability_come_from_paypal(linked):
    client, state = linked
    state["profile"] = EARNING
    trend = _ask(client, "What's my income trend?")
    assert trend["tools"][0]["status"] == "done"
    assert trend["analysis"]["result"]["status"] == "increasing"
    assert "linked PayPal account" in trend["reply"]
    assert "This month so far" in trend["reply"]  # the unfinished November is reported but not trended
    afford = _ask(client, "Can I afford ₹50k?")
    assert afford["tools"][0]["status"] == "done"
    assert "linked PayPal account" in afford["analysis"]["profile_source"]
    _no_demo_data(trend)
    _no_demo_data(afford)


def test_score_needs_details_and_declared_income_when_paypal_shows_none(linked):
    client, _ = linked
    details = {"age_years": 31, "employment_type": "self_employed", "requested_loan_amount_inr": 100000,
               "requested_term_months": 12}
    refused = client.post("/score/linked", json=details)
    assert refused.status_code == 422 and refused.json()["error"] == "no_income_evidence"
    scored = client.post("/score/linked", json={**details, "monthly_income_inr": 30000})
    assert scored.status_code == 200
    body = scored.json()
    assert body["applicant_id"].startswith("PAYPAL-") and "paypal-user-1" not in str(body)
    assert body["payout_available"] is False
    sources = {row["field"]: row["source"] for row in body["inputs"]}
    assert sources["monthly_income_inr"] == "you"
    assert sources["active_months_12m"] == "paypal"
    assert sources["dispute_rate_12m"] == "not_available"


def test_paypal_income_feeds_the_score_and_the_copilot_explains_it(linked):
    client, state = linked
    state["profile"] = EARNING
    scored = client.post("/score/linked", json={"age_years": 31, "employment_type": "self_employed",
                                                "requested_loan_amount_inr": 100000, "requested_term_months": 12})
    assert scored.status_code == 200
    body = scored.json()
    application = body["application"]
    assert {row["field"]: row["source"] for row in body["inputs"]}["monthly_income_inr"] == "paypal"
    assert application["active_months_12m"] == 12 and application["txn_count_90d"] == 3
    explained = _ask(client, "Explain my score", application=application)
    assert explained["tools"][0]["label"] == "shap.TreeExplainer"
    assert f"PayScore {body['score']}" in explained["reply"]
    _no_demo_data(explained)


def test_linked_mode_without_a_link_says_so(monkeypatch):
    async def nothing_linked(request, response, client):
        return None

    monkeypatch.setattr(copilot_module, "load_linked_profile", nothing_linked)
    reply = _ask(TestClient(create_app()), "What's my income trend?")
    assert reply["tools"][0]["status"] == "not_linked"


def test_demo_income_trend_is_a_trend_not_volatility(client):
    reply = client.post("/copilot/chat", json={"message": "What's my income trend?",
                                               "applicant_id": "PSC-PRIYA-001"}).json()
    assert reply["tools"][0]["label"] == "income.trend"
    assert reply["analysis"]["result"]["status"] in {"increasing", "stable", "decreasing"}


def test_profile_reports_90_day_sale_metrics():
    profile = _profile([_sale(TODAY - timedelta(days=10), 1000), _sale(TODAY - timedelta(days=40), 3000),
                        _sale(TODAY - timedelta(days=200), 9000)])
    assert profile["sale_count_90d"] == 2
    assert profile["avg_sale_value_90d_inr"] == 2000
    assert profile["refund_rate_90d"] == 0


def test_demo_browser_gets_priya_even_after_someone_else_links_paypal():
    """A PayPal login in one browser must not replace the demo persona in another (the server is shared)."""
    from payscore.paypal import linked_accounts

    linked_accounts.store_account("someone-else", {"access_token": "their-token"})
    try:
        body = TestClient(create_app()).get("/income-profile", params={"persona": "priya"}).json()
        assert body["source"] == "fixture" and body["total_income_12m_inr"] > 0
    finally:
        linked_accounts.LINKED_ACCOUNTS.pop("someone-else", None)

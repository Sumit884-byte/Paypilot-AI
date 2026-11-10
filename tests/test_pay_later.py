"""Pay Later comparison reuses Offer Guard pricing and does not invent terms for unsupported markets."""

import pytest

from payscore.finance import level_payment

OFFER = {"advertised_apr_pct": 18, "processing_fee_pct": 4, "term_months": 12, "lender_name": "Example NBFC"}


def _option(body, option_id):
    return next(o for o in body["options"] if o["id"] == option_id)


def test_india_reports_pay_later_unavailable_and_only_prices_the_loan(client):
    body = client.post("/offer-guard/pay-later", json={**OFFER, "purchase_amount": 50000, "market": "IN"}).json()
    assert body["pay_later_availability"] == "unavailable"
    assert body["currency"] == "INR"
    assert [o["id"] for o in body["options"]] == ["loan_offer"]
    assert body["cheapest"]["id"] == "loan_offer"
    assert "not offered in IN" in body["availability_note"]


def test_loan_side_matches_offer_guard(client):
    guard = client.post("/offer-guard", json={**OFFER, "principal_inr": 1200}).json()
    body = client.post("/offer-guard/pay-later", json={**OFFER, "purchase_amount": 1200, "market": "US"}).json()
    loan = _option(body, "loan_offer")
    assert loan["effective_annual_pct"] == guard["estimated_real_apr_pct"]
    assert loan["instalment"] == guard["calculation"]["installment_inr"]
    assert loan["cost_of_credit"] == pytest.approx(loan["instalment"] * 12 + 48 - 1200, abs=0.01)


def test_us_pay_in_4_is_cheapest_for_an_eligible_purchase(client):
    body = client.post("/offer-guard/pay-later", json={**OFFER, "purchase_amount": 1200, "market": "US"}).json()
    assert body["pay_later_availability"] == "modelled"
    assert body["cheapest"]["id"] == "paypal_pay_in_4"
    pay_in_4 = _option(body, "paypal_pay_in_4")
    assert pay_in_4["instalment"] == 300 and pay_in_4["cost_of_credit"] == 0
    assert body["cheapest"]["saving_vs_offer"] == _option(body, "loan_offer")["cost_of_credit"]


def test_pay_monthly_ranks_at_highest_apr_and_snaps_to_an_offered_term(client):
    body = client.post("/offer-guard/pay-later", json={**OFFER, "purchase_amount": 5000, "term_months": 10, "market": "us"}).json()
    monthly = _option(body, "paypal_pay_monthly")
    assert _option(body, "paypal_pay_in_4")["eligible"] is False
    assert monthly["term_months"] == 12 and monthly["term_note"]
    assert monthly["instalment"] == pytest.approx(level_payment(5000, 0.3599, 12, 12), abs=0.01)
    assert monthly["cost_of_credit_best"] < monthly["cost_of_credit"]
    assert monthly["effective_annual_pct"] > 35.99


def test_amount_outside_every_pay_later_range_keeps_the_loan(client):
    body = client.post("/offer-guard/pay-later", json={**OFFER, "purchase_amount": 50000, "market": "US"}).json()
    assert not _option(body, "paypal_pay_in_4")["eligible"]
    assert not _option(body, "paypal_pay_monthly")["eligible"]
    assert body["cheapest"]["id"] == "loan_offer"


def test_other_pay_later_market_is_not_modelled(client):
    body = client.post("/offer-guard/pay-later", json={**OFFER, "purchase_amount": 500, "market": "GB"}).json()
    assert body["pay_later_availability"] == "not_modelled"
    assert len(body["options"]) == 1


def test_rejects_bad_input(client):
    assert client.post("/offer-guard/pay-later", json={**OFFER, "purchase_amount": 0}).status_code == 422
    assert client.post("/offer-guard/pay-later", json={**OFFER, "purchase_amount": 10, "extra": 1}).status_code == 422

"""Affordability uses the instalment formula and explicit stress rules."""

from payscore.affordability import assess
from payscore.finance import level_payment, npv_at_periodic_rate, solve_periodic_irr


def _base(**overrides):
    payload = {
        "requested_amount_inr": 50000,
        "monthly_income_inr": 12000,
        "essential_expenses_inr": 4000,
        "existing_monthly_debt_payments_inr": 2000,
        "tenure_months": 12,
        "annual_interest_rate_pct": 18,
        "frequency": "monthly",
    }
    payload.update(overrides)
    return assess(payload)


def test_level_payment_matches_zero_rate_and_known_irr():
    assert level_payment(12000, 0, 12, 12) == 1000
    payment = level_payment(50000, 0.18, 12, 12)
    periodic = solve_periodic_irr(50000, payment, 12)
    assert abs(periodic - 0.015) < 1e-9
    assert abs(npv_at_periodic_rate(50000, payment, 12, periodic)) < 1e-4


def test_normal_case_warns_when_only_the_income_stress_breaks():
    result = _base(scenarios=[{
        "name": "income_down_20",
        "income_factor": 0.8,
        "expense_factor": 1,
        "unexpected_cost_inr": 0,
        "description": "Monthly income is 20% lower.",
    }])
    assert result["status"] == "warn"
    assert result["regulated_advice"] is False
    assert result["installment_inr"] == round(level_payment(50000, 0.18, 12, 12), 2)
    assert result["post_payment_cashflow_inr"] > 0
    failed = [row["name"] for row in result["scenarios"] if row["status"] == "below_buffer"]
    assert failed == ["income_down_20"]
    assert any("income_down_20" in reason for reason in result["reasons"])


def test_pass_when_base_and_default_stress_stay_non_negative():
    result = _base(monthly_income_inr=40000, essential_expenses_inr=8000, existing_monthly_debt_payments_inr=2000)
    assert result["status"] == "pass"
    assert result["debt_service_ratio"] is not None
    assert result["disposable_income_inr"] == round(40000 - 8000 - 2000, 2)


def test_fail_when_base_cash_flow_is_negative():
    result = _base(monthly_income_inr=8000)
    assert result["status"] == "fail"
    assert result["post_payment_cashflow_inr"] < 0


def test_zero_income_fails_and_does_not_divide():
    result = _base(monthly_income_inr=0, essential_expenses_inr=0, existing_monthly_debt_payments_inr=0, annual_interest_rate_pct=0)
    assert result["status"] == "fail"
    assert result["debt_service_ratio"] is None
    assert result["installment_inr"] == 4166.67


def test_missing_essentials_and_rate_are_incomplete_not_a_pass():
    result = assess({
        "requested_amount_inr": 50000,
        "monthly_income_inr": 55000,
        "existing_monthly_debt_payments_inr": 6000,
        "tenure_months": 12,
    })
    assert result["status"] == "incomplete"
    assert result["rate_mode"] == "zero_interest_lower_bound"
    assert result["installment_inr"] == 4166.67
    assert "essential_expenses_inr" in result["missing_inputs"]
    assert result["post_payment_cashflow_inr"] is None


def test_invalid_numbers_are_rejected():
    assert assess({"requested_amount_inr": -1, "tenure_months": 12, "monthly_income_inr": 1})["status"] == "invalid"
    assert assess({"requested_amount_inr": 1000, "tenure_months": 0, "monthly_income_inr": 1})["status"] == "invalid"
    assert assess({"requested_amount_inr": 1000, "tenure_months": 12, "monthly_income_inr": -5})["status"] == "invalid"
    assert assess({
        "requested_amount_inr": 1000, "tenure_months": 12, "monthly_income_inr": 1000,
        "annual_interest_rate_pct": 900,
    })["status"] == "invalid"
    quarterly = assess({
        "requested_amount_inr": 9000, "tenure_months": 10, "monthly_income_inr": 10000,
        "essential_expenses_inr": 1000, "existing_monthly_debt_payments_inr": 0,
        "annual_interest_rate_pct": 0, "frequency": "quarterly",
    })
    assert quarterly["status"] == "invalid"


def test_fee_above_principal_is_invalid_and_endpoint_matches(client):
    direct = assess({
        "requested_amount_inr": 10000, "tenure_months": 12, "monthly_income_inr": 20000,
        "essential_expenses_inr": 1000, "existing_monthly_debt_payments_inr": 0,
        "annual_interest_rate_pct": 0, "upfront_fee_inr": 10000,
    })
    assert direct["status"] == "invalid"
    response = client.post("/affordability", json={
        "requested_amount_inr": 50000,
        "monthly_income_inr": 40000,
        "essential_expenses_inr": 8000,
        "existing_monthly_debt_payments_inr": 0,
        "tenure_months": 12,
        "annual_interest_rate_pct": 0,
    })
    assert response.status_code == 200
    assert response.json()["installment_inr"] == 4166.67
    assert response.json()["status"] == "pass"


def test_api_rejects_negative_income(client):
    response = client.post("/affordability", json={"requested_amount_inr": 1000, "monthly_income_inr": -1, "tenure_months": 12})
    assert response.status_code == 422

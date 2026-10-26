"""Revenue-share recommendations use the supplied observations and no imputed history."""

from payscore.revenue_volatility import analyse


def test_stable_revenue_recommends_the_low_volatility_band():
    result = analyse([100_000] * 6)
    assert result["status"] == "ok"
    assert result["recommended_percentage"] == 20
    assert result["metrics"]["sample_std_inr"] == 0
    assert result["metrics"]["coefficient_of_variation"] == 0
    assert result["confidence"] == "moderate"
    assert result["statistically_validated"] is False
    assert result["metrics"]["stress_revenue_inr"] == 100_000
    assert analyse([100_000] * 6) == result


def test_volatile_revenue_drops_to_the_minimum_percentage():
    result = analyse([10, 100, 10, 100, 10, 100])
    assert result["metrics"]["coefficient_of_variation"] >= 0.60
    assert result["recommended_percentage"] == 5
    assert result["confidence"] == "low"
    assert result["statistically_validated"] is False


def test_zero_and_negative_mean_do_not_invent_a_percentage():
    zeros = analyse([0, 0, 0, 0])
    assert zeros["status"] == "insufficient_data"
    assert zeros["reason"] == "non_positive_mean_revenue"
    assert zeros["recommended_percentage"] is None
    negatives = analyse([-5, -5, -5, -5])
    assert negatives["reason"] == "non_positive_mean_revenue"
    assert negatives["recommended_percentage"] is None


def test_insufficient_history_and_invalid_inputs():
    short = analyse([100, 120])
    assert short["status"] == "insufficient_data"
    assert short["reason"] == "fewer_than_3_observations"
    assert short["recommended_percentage"] is None
    assert analyse(None)["reason"] == "no_observations"
    assert analyse([100, float("nan"), 100])["status"] == "invalid"
    assert analyse([100, 100, 100], min_percentage=40, max_percentage=10)["status"] == "invalid"
    mixed = analyse([100, -10, 100, 100, 100, 100])
    assert mixed["status"] == "ok"
    assert mixed["confidence"] == "low"
    assert mixed["metrics"]["negative_observations"] == 1


def test_obligation_and_expense_constraints():
    covered = analyse([100] * 6, obligation_inr=10, min_percentage=5, max_percentage=30)
    assert covered["recommended_percentage"] == 10
    assert covered["reason"] == "smallest_percentage_covering_obligation_under_stress"
    uncovered = analyse([100] * 6, obligation_inr=50)
    assert uncovered["status"] == "obligation_not_covered"
    assert uncovered["recommended_percentage"] is None
    constrained = analyse([100] * 6, essential_expenses_inr=95)
    assert constrained["recommended_percentage"] == 5
    assert constrained["tested_alternatives"]


def test_persona_endpoint_uses_fixture_history_only(client):
    response = client.post("/revenue-volatility", json={"applicant_id": "PSC-PRIYA-001"})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "synthetic_persona_monthly_summary"
    assert body["metrics"]["n"] >= 3
    assert body["statistically_validated"] is False
    missing = client.post("/revenue-volatility", json={"applicant_id": "PSC-MISSING-001"})
    assert missing.json()["reason"] == "applicant_history_not_found"
    assert missing.json()["recommended_percentage"] is None

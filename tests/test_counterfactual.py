"""Counterfactuals are accepted only when the trained model re-scores them."""

from payscore.counterfactual import analyse_counterfactual
from payscore.model import Scorer, pd_to_score
from payscore.schema import ScoreRequest


def _score(scorer, req: ScoreRequest) -> int:
    import pandas as pd

    probability = float(scorer.trained.predict_pd(pd.DataFrame([req.model_dump(mode="json")]))[0])
    return pd_to_score(probability)


def test_valid_smaller_loan_is_rescored_by_the_model(example_request):
    scorer = Scorer.from_dir("models")
    req = ScoreRequest.model_validate(example_request)
    proposed = round(req.requested_loan_amount_inr * 0.8, 2)
    result = analyse_counterfactual(scorer, req, {"requested_loan_amount_inr": proposed})
    updated = req.model_copy(update={"requested_loan_amount_inr": proposed})
    suggestion = result["suggestions"][0]
    assert result["model_evaluated"] is True
    assert suggestion["estimated_score"] == _score(scorer, updated)
    assert suggestion["estimated_score_difference"] == suggestion["estimated_score"] - result["current_score"]
    assert suggestion["changes"][0]["feature"] == "requested_loan_amount_inr"
    assert "historical" not in suggestion["changes"][0]["description"].lower() or "not any historical" in suggestion["changes"][0]["description"]


def test_invalid_identity_and_history_changes_are_rejected(example_request):
    scorer = Scorer.from_dir("models")
    req = ScoreRequest.model_validate(example_request)
    for changes in (
        {"age_years": 50},
        {"prior_defaults_count": 0},
        {"txn_count_90d": 999},
        {"monthly_income_inr": req.monthly_income_inr + 10000},
    ):
        result = analyse_counterfactual(scorer, req, changes)
        assert result["suggestions"] == []
        assert result["status"] == "rejected"
        assert result["rejected_changes"]
        assert result["model_evaluated"] is False


def test_unchanged_proposal_has_zero_score_difference(example_request):
    scorer = Scorer.from_dir("models")
    req = ScoreRequest.model_validate(example_request)
    result = analyse_counterfactual(scorer, req, {"requested_term_months": req.requested_term_months})
    assert result["status"] == "unchanged"
    suggestion = result["suggestions"][0]
    assert suggestion["estimated_score_difference"] == 0
    assert suggestion["estimated_score"] == result["current_score"]
    assert suggestion["model_evaluated"] is True


def test_impossible_search_when_no_eligible_move_remains(example_request):
    scorer = Scorer.from_dir("models")
    saturated = {
        **example_request,
        "requested_loan_amount_inr": 1000,
        "requested_term_months": 360,
        "existing_monthly_debt_payments_inr": 0,
        "refund_rate_90d": 0,
        "dispute_rate_12m": 0,
        "revenue_volatility_cv": 0.05,
        "active_months_12m": 12,
    }
    result = analyse_counterfactual(scorer, ScoreRequest.model_validate(saturated))
    assert result["status"] == "no_feasible_improvement"
    assert result["suggestions"] == []
    assert result["model_evaluated"] is True
    assert result["evaluated_count"] == 0


def test_search_suggestions_are_model_scored_and_eligible(example_request):
    scorer = Scorer.from_dir("models")
    req = ScoreRequest.model_validate(example_request)
    result = analyse_counterfactual(scorer, req)
    assert result["status"] == "ok"
    assert result["suggestions"]
    forbidden = {"age_years", "employment_type", "prior_defaults_count", "txn_count_90d", "monthly_income_inr"}
    for suggestion in result["suggestions"]:
        assert suggestion["estimated_score"] > result["current_score"]
        data = req.model_dump(mode="json")
        for change in suggestion["changes"]:
            assert change["feature"] not in forbidden
            data[change["feature"]] = change["proposed"]
        assert suggestion["estimated_score"] == _score(scorer, ScoreRequest.model_validate(data))


def test_fallback_counterfactual_is_unavailable(example_request):
    scorer = Scorer(None, allow_fallback=True)
    result = analyse_counterfactual(scorer, ScoreRequest.model_validate(example_request))
    assert result["status"] == "unavailable"
    assert result["model_evaluated"] is False
    assert result["suggestions"] == []

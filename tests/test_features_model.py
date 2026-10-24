import numpy as np
import pandas as pd
import pytest
from conftest import ROOT

from payscore.features import FEATURE_NAMES, build_features
from payscore.model import ModelArtifactError, Scorer, fallback_pd, load_model, pd_to_score, risk_band
from payscore.schema import ScoreRequest
from payscore.synthetic import generate


def _df(req):
    return pd.DataFrame([ScoreRequest.model_validate(req).model_dump(mode="json")])


def test_feature_columns_and_order(example_request):
    X = build_features(_df(example_request))
    assert list(X.columns) == FEATURE_NAMES


def test_derived_features_values(example_request):
    X = build_features(_df(example_request)).iloc[0]
    assert X["debt_to_income"] == pytest.approx(6000 / 55000)
    assert X["expense_ratio"] == pytest.approx(84000 / 140000)
    assert X["net_margin"] == pytest.approx(0.4)
    assert X["loan_to_annual_revenue"] == pytest.approx(400000 / (140000 * 12))
    assert X["installment_to_income"] == pytest.approx(400000 / 18 / 55000)


def test_missing_stays_nan_and_no_inf(example_request):
    req = {**example_request, "avg_monthly_revenue_inr": 0, "monthly_income_inr": 0}
    X = build_features(_df(req))
    assert not np.isinf(X.to_numpy(dtype=float)).any()
    assert np.isnan(X.loc[0, "expense_ratio"]) and np.isnan(X.loc[0, "installment_to_income"])
    req2 = {k: v for k, v in example_request.items() if k != "revenue_volatility_cv"}
    assert np.isnan(build_features(_df(req2)).loc[0, "revenue_volatility_cv"])


def test_score_mapping_monotonic_and_bounded():
    probs = [1e-9, 0.001, 0.01, 0.05, 0.2, 0.5, 0.9, 1 - 1e-9]
    scores = [pd_to_score(p) for p in probs]
    assert scores == sorted(scores, reverse=True)
    assert all(300 <= s <= 850 for s in scores)
    assert pd_to_score(1 / 13) == 600  # 12:1 odds -> base score


@pytest.mark.parametrize("score,band", [(850, "low"), (720, "low"), (719, "moderate"), (650, "moderate"),
                                        (649, "elevated"), (560, "elevated"), (559, "high"), (300, "high")])
def test_risk_band_boundaries(score, band):
    assert risk_band(score) == band


def test_trained_model_loads_and_scores(example_request):
    scorer = Scorer.from_dir(ROOT / "models", allow_fallback=False)
    out = scorer.score(ScoreRequest.model_validate(example_request))
    assert scorer.trained is not None
    assert 300 <= out["score"] <= 850 and 0 <= out["probability_of_default"] <= 1
    assert out["model"]["is_trained_model"] is True
    assert "SYNTHETIC" in out["evaluation_caveat"]


def test_scoring_is_deterministic(example_request):
    scorer = Scorer.from_dir(ROOT / "models")
    r = ScoreRequest.model_validate(example_request)
    assert scorer.score(r) == scorer.score(r)


def test_missing_inputs_reported(example_request):
    body = {k: v for k, v in example_request.items() if k not in ("refund_rate_90d", "dispute_rate_12m")}
    out = Scorer.from_dir(ROOT / "models").score(ScoreRequest.model_validate(body))
    assert set(out["missing_inputs"]) == {"refund_rate_90d", "dispute_rate_12m"}


def test_model_responds_sensibly_to_risk(example_request):
    scorer = Scorer.from_dir(ROOT / "models")
    base = scorer.score(ScoreRequest.model_validate(example_request))["score"]
    risky = {**example_request, "requested_loan_amount_inr": 3_000_000, "existing_monthly_debt_payments_inr": 40000,
             "prior_defaults_count": 3, "dispute_rate_12m": 0.1}
    assert scorer.score(ScoreRequest.model_validate(risky))["score"] < base - 50


def test_metadata_matches_features_and_no_leakage():
    import json
    md = json.loads((ROOT / "models" / "model_metadata.json").read_text())
    assert md["feature_names"] == FEATURE_NAMES
    assert "TARGET" not in md["feature_names"]
    assert md["training_data"]["kind"] == "synthetic_development_dataset"
    assert 0.5 < md["metrics"]["test"]["roc_auc"] < 1


def test_fallback_is_labelled(tmp_path, example_request):
    scorer = Scorer.from_dir(tmp_path, allow_fallback=True)  # empty dir -> no artifact
    out = scorer.score(ScoreRequest.model_validate(example_request))
    assert out["model"]["type"] == "development_fallback" and out["model"]["is_trained_model"] is False
    assert "DEVELOPMENT FALLBACK" in out["evaluation_caveat"]
    assert 0 < fallback_pd(_df(example_request))[0] < 1


def test_no_model_and_no_fallback_unavailable(tmp_path):
    assert not Scorer.from_dir(tmp_path, allow_fallback=False).available


def test_corrupt_and_incomplete_artifacts_raise(tmp_path):
    (tmp_path / "payscore_lgbm.txt").write_text("not a model")
    with pytest.raises(ModelArtifactError):  # incomplete: no metadata
        load_model(tmp_path)
    (tmp_path / "model_metadata.json").write_text("{}")
    with pytest.raises(ModelArtifactError):  # corrupt
        load_model(tmp_path)


def test_synthetic_generator_reproducible_and_labelled():
    a, b = generate(500, seed=1), generate(500, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert 0 < a["TARGET"].mean() < 0.3
    assert a["applicant_id"].str.startswith("SYN-").all()

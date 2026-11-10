import json

import pandas as pd
import pytest
from pydantic import ValidationError

from payscore.features import FEATURE_NAMES, build_features
from payscore.model import (
    ModelArtifactError,
    Scorer,
    load_model,
    pd_to_score,
    risk_band,
)
from payscore.schema import ScoreRequest
from payscore.synthetic import generate
from payscore.train import train


def test_load_returns_none_when_no_artifact(tmp_path):
    assert load_model(tmp_path) is None


def test_load_and_predict_with_artifact(trained_dir, valid_payload):
    m = load_model(trained_dir)
    assert m is not None and m.metadata["feature_names"] == FEATURE_NAMES
    scorer = Scorer(m)
    out = scorer.score(ScoreRequest.model_validate(valid_payload))
    assert out["model"]["type"] == "lightgbm" and 0 < out["probability_of_default"] < 1


def test_riskier_applicant_scores_lower(trained_dir, valid_payload):
    scorer = Scorer.from_dir(trained_dir)
    good = scorer.score(ScoreRequest.model_validate(valid_payload))
    bad_payload = {**valid_payload, "prior_defaults_count": 4, "existing_monthly_debt_payments_inr": 50000,
                   "dispute_rate_12m": 0.1, "revenue_volatility_cv": 1.8, "requested_loan_amount_inr": 3_000_000}
    bad = scorer.score(ScoreRequest.model_validate(bad_payload))
    assert bad["score"] < good["score"]


def test_corrupt_artifact_raises(tmp_path):
    (tmp_path / "payscore_lgbm.txt").write_text("garbage")
    (tmp_path / "model_metadata.json").write_text(json.dumps({"feature_names": FEATURE_NAMES}))
    with pytest.raises(ModelArtifactError):
        load_model(tmp_path)


def test_incomplete_artifact_raises(tmp_path):
    (tmp_path / "model_metadata.json").write_text("{}")
    with pytest.raises(ModelArtifactError):
        load_model(tmp_path)


def test_synthetic_generation_reproducible_and_labelled():
    a, b = generate(500, seed=3), generate(500, seed=3)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(generate(500, seed=4))
    assert 0.02 < a["TARGET"].mean() < 0.2
    assert a["applicant_id"].str.startswith("SYN-").all()


def test_training_is_reproducible(tmp_path):
    kw = dict(source="synthetic", n_rows=2000, seed=5, num_boost_round=30, early_stopping_rounds=5)
    m1 = train(out_dir=tmp_path / "a", **kw)
    m2 = train(out_dir=tmp_path / "b", **kw)
    assert m1["metrics"] == m2["metrics"] and m1["training_data"]["sha256"] == m2["training_data"]["sha256"]
    assert (tmp_path / "a" / "payscore_lgbm.txt").read_text() == (tmp_path / "b" / "payscore_lgbm.txt").read_text()


def test_metadata_documents_synthetic_and_no_target_feature(trained_dir):
    meta = json.loads((trained_dir / "model_metadata.json").read_text())
    assert meta["training_data"]["kind"] == "synthetic_development_dataset"
    assert "NOT Home Credit" in meta["training_data"]["note"]
    assert not any("target" in f.lower() for f in meta["feature_names"])
    assert meta["metrics"]["test"]["roc_auc"] > 0.5


def test_features_handle_missing_and_zero_denominators():
    df = pd.DataFrame([{"employment_type": "salaried", "monthly_income_inr": 0.0,
                        "existing_monthly_debt_payments_inr": 100.0, "requested_loan_amount_inr": 1000.0,
                        "requested_term_months": 10}])
    f = build_features(df)
    assert list(f.columns) == FEATURE_NAMES
    assert pd.isna(f.loc[0, "debt_to_income"]) and pd.isna(f.loc[0, "expense_ratio"])
    assert not f.isin([float("inf")]).any().any()


def test_score_mapping_monotonic_and_bounded():
    scores = [pd_to_score(p) for p in (0.001, 0.02, 0.08, 0.2, 0.5, 0.9)]
    assert scores == sorted(scores, reverse=True)
    assert all(300 <= s <= 850 for s in scores)
    assert risk_band(800) == "low" and risk_band(700) == "moderate" and risk_band(600) == "elevated" and risk_band(400) == "high"


def test_homecredit_loader_with_mock_csv(tmp_path):
    from payscore.homecredit import load_homecredit
    csv = tmp_path / "application_train.csv"
    csv.write_text(
        "SK_ID_CURR,TARGET,DAYS_BIRTH,AMT_INCOME_TOTAL,AMT_CREDIT,AMT_ANNUITY,NAME_INCOME_TYPE,DAYS_EMPLOYED\n"
        "100001,0,-12000,120000,300000,15000,Working,-1500\n"
        "100002,1,-20000,60000,100000,5000,Pensioner,365243\n"
    )
    df = load_homecredit(str(csv))
    assert list(df["TARGET"]) == [0, 1] and df.loc[0, "employment_type"] == "salaried"
    assert df.loc[1, "employment_type"] == "other" and pd.isna(df.loc[1, "business_age_months"])
    assert df.loc[0, "requested_term_months"] == 20 and df.loc[0, "monthly_income_inr"] == 10000
    assert df["avg_monthly_revenue_inr"].isna().all()
    # and it trains end-to-end through the same pipeline (tiny mock file; metrics meaningless)
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError):
        load_homecredit(str(bad))


def test_schema_rejects_extra_and_bad_types():
    with pytest.raises(ValidationError):
        ScoreRequest.model_validate({"applicant_id": "x", "age_years": 30, "employment_type": "salaried",
                                     "monthly_income_inr": 1, "requested_loan_amount_inr": 1,
                                     "requested_term_months": 1, "extra": 1})

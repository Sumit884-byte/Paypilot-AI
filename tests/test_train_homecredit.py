
import pandas as pd
import pytest

from payscore.homecredit import load_homecredit
from payscore.model import Scorer
from payscore.schema import ScoreRequest
from payscore.train import main as train_main
from payscore.train import train


def test_train_small_end_to_end(tmp_path, example_request):
    md = train(n_rows=3000, seed=7, out_dir=tmp_path, num_boost_round=60, early_stopping_rounds=20)
    assert (tmp_path / "payscore_lgbm.txt").exists() and (tmp_path / "model_metadata.json").exists()
    assert md["metrics"]["test"]["roc_auc"] > 0.6
    out = Scorer.from_dir(tmp_path, allow_fallback=False).score(ScoreRequest.model_validate(example_request))
    assert 300 <= out["score"] <= 850


def test_train_is_deterministic(tmp_path):
    a = train(n_rows=2000, seed=3, out_dir=tmp_path / "a", num_boost_round=30)
    b = train(n_rows=2000, seed=3, out_dir=tmp_path / "b", num_boost_round=30)
    assert a["metrics"]["test"] == b["metrics"]["test"]
    first = (tmp_path / "a" / "payscore_lgbm.txt").read_text(encoding="utf-8")
    assert first == (tmp_path / "b" / "payscore_lgbm.txt").read_text(encoding="utf-8")


def test_train_cli_errors(tmp_path):
    assert train_main(["--source", "homecredit", "--out-dir", str(tmp_path)]) == 2


def test_homecredit_loader_mapping(tmp_path):
    raw = pd.DataFrame({
        "SK_ID_CURR": [1, 2], "TARGET": [0, 1], "DAYS_BIRTH": [-12000, -20000],
        "AMT_INCOME_TOTAL": [120000.0, 240000.0], "AMT_CREDIT": [100000.0, 50000.0], "AMT_ANNUITY": [5000.0, 0.0],
        "NAME_INCOME_TYPE": ["Working", "Businessman"], "DAYS_EMPLOYED": [-1000, 365243],
    })
    f = tmp_path / "hc.csv"
    raw.to_csv(f, index=False)
    df = load_homecredit(str(f))
    assert df.loc[0, "employment_type"] == "salaried" and df.loc[1, "employment_type"] == "business_owner"
    assert df.loc[0, "monthly_income_inr"] == pytest.approx(10000)
    assert pd.isna(df.loc[1, "business_age_months"])  # sentinel -> NaN
    assert pd.isna(df.loc[1, "requested_term_months"])  # zero annuity -> NaN, no inf
    assert list(df["TARGET"]) == [0, 1]


def test_homecredit_loader_rejects_wrong_columns(tmp_path):
    f = tmp_path / "x.csv"
    pd.DataFrame({"a": [1]}).to_csv(f, index=False)
    with pytest.raises(ValueError):
        load_homecredit(str(f))

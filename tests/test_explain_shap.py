"""SHAP explanations must come from the trained model, not the old heuristic."""

import numpy as np
import pandas as pd
import shap

from payscore.features import build_features
from payscore.model import Scorer
from payscore.schema import ScoreRequest


def test_score_explanation_matches_independent_tree_shap(example_request):
    scorer = Scorer.from_dir("models")
    req = ScoreRequest.model_validate(example_request)
    result = scorer.score(req)
    explanation = result["explanation"]
    assert explanation["status"] == "available"
    assert explanation["method"] == "shap.TreeExplainer"
    assert explanation["causal_claim"] is False
    assert explanation["matches_model_output"] is True
    assert explanation["matches_lightgbm_pred_contrib"] is True
    assert round(explanation["predicted_probability"], 4) == result["probability_of_default"]
    assert len(explanation["factors_lowering_risk"]) <= 3
    assert len(explanation["factors_raising_risk"]) <= 3
    for factor in explanation["factors_lowering_risk"] + explanation["factors_raising_risk"]:
        assert {"feature", "name", "contribution", "direction", "description"} <= set(factor)
        assert factor["method"] == "shap.TreeExplainer"
        assert "not a cause" in factor["description"]

    names = scorer.trained.metadata["feature_names"]
    matrix = np.asarray(build_features(pd.DataFrame([req.model_dump(mode="json")]))[names], dtype=float)
    explainer = shap.TreeExplainer(scorer.trained.booster)
    raw = explainer.shap_values(matrix)
    vector = np.asarray(raw, dtype=float).reshape(-1, len(names))[-1]
    returned = {row["feature"]: row["contribution"] for row in explanation["all_contributions"]}
    for name, value in zip(names, vector, strict=True):
        assert abs(returned[name] - float(value)) < 1e-6
    assert abs(explanation["base_value"] + sum(returned.values()) - explanation["predicted_log_odds"]) < 1e-5
    assert explanation["feature_names"] == names
    assert "heuristic_not_shap" not in str(result)


def test_fallback_does_not_substitute_heuristic_reasons(fallback_client, example_request):
    body = fallback_client.post("/score", json=example_request).json()
    assert body["explanation"]["status"] == "unavailable"
    assert body["explanation"]["method"] is None
    assert body["drivers"] == []
    assert body["counterfactual_preview"] is None
    assert "heuristic_not_shap" not in str(body)


def test_explain_endpoint_does_not_replace_score(client, example_request):
    scored = client.post("/score", json=example_request).json()
    explained = client.post("/explain", json=example_request).json()
    assert explained["score"] == scored["score"]
    assert explained["explanation"]["status"] == "available"
    assert explained["explanation"]["method"] == "shap.TreeExplainer"

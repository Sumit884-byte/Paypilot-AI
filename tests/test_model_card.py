"""Model card endpoints — only committed or recomputed metrics, never placeholders."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_model_card_matches_committed_metadata(client):
    meta = json.loads((ROOT / "models" / "model_metadata.json").read_text(encoding="utf-8"))
    response = client.get("/model-card")
    assert response.status_code == 200
    body = response.json()
    assert body["is_trained_model"] is True
    assert body["model_name"] == meta["model_name"]
    assert body["model_version"] == meta["model_version"]
    assert body["metrics"]["auc_roc"] == meta["metrics"]["test"]["roc_auc"]
    assert body["metrics"]["pr_auc"] == meta["metrics"]["test"]["pr_auc"]
    # Precision/recall/F1/accuracy are not in the committed artifact.
    assert body["metric_availability"]["precision"] == "not_yet_evaluated"
    assert body["metrics"]["precision"] is None
    assert "gender" in body["fairness"]["sensitive_attributes_excluded"]
    assert "age_years" in body["fairness"]["sensitive_or_proxy_features_used"]
    assert "decision_support_statement" in body
    assert "not guaranteed credit approval" in body["decision_support_statement"].lower()


def test_model_card_fallback_has_no_fake_metrics(fallback_client):
    body = fallback_client.get("/model-card").json()
    assert body["is_trained_model"] is False
    assert body["metrics"]["auc_roc"] is None
    assert body["metric_availability"]["auc_roc"] == "not_yet_evaluated"
    assert body["calibration_status"] == "Not yet evaluated"


def test_model_card_evaluation_curves(client):
    response = client.get("/model-card/evaluation?threshold=0.5")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["roc_curve"]["points"]
    assert body["calibration_curve"]["points"]
    assert body["confusion_matrix"]["true_positive"] + body["confusion_matrix"]["false_negative"] > 0
    metrics = body["threshold_metrics"]
    assert 0 <= metrics["precision"] <= 1
    assert 0 <= metrics["recall"] <= 1
    assert 0 <= metrics["f1_score"] <= 1
    assert 0 <= metrics["accuracy"] <= 1
    assert "synthetic" in metrics["note"].lower()


def test_model_card_evaluation_invalid_threshold(client):
    assert client.get("/model-card/evaluation?threshold=0").status_code == 422
    assert client.get("/model-card/evaluation?threshold=1").status_code == 422

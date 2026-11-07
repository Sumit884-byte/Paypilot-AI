"""Model card API — serves committed evaluation metadata and optional curve diagnostics.

Scalar metrics come from ``models/model_metadata.json``. Curve payloads (ROC,
calibration, confusion matrix, threshold metrics) are computed on demand from the
loaded LightGBM booster and the same synthetic stratified test split used at
training time. Nothing is fabricated: if the trained model is unavailable, curve
fields are marked ``not_yet_evaluated``.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

import numpy as np
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split

from .features import FEATURE_NAMES, build_features
from .synthetic import generate

router = APIRouter(tags=["model card"])

# Attributes that are intentionally not part of the feature vector.
# Only list attributes the pipeline truly never ingests.
SENSITIVE_ATTRIBUTES_EXCLUDED = [
    "gender",
    "sex",
    "race",
    "ethnicity",
    "religion",
    "caste",
    "nationality",
    "marital_status",
    "disability_status",
    "political_affiliation",
    "sexual_orientation",
]

# Inputs that ARE used and require fairness review before any real deployment.
SENSITIVE_OR_PROXY_FEATURES_USED = [
    "age_years",
    "employment_type_code",
]

DECISION_SUPPORT_STATEMENT = (
    "PayScore provides decision-support insights, not guaranteed credit approval or "
    "financial outcomes. Model outputs should be reviewed alongside the underlying evidence."
)

_curve_lock = threading.Lock()
_curve_cache: dict[str, Any] = {}


def _round_floats(obj: Any, ndigits: int = 6) -> Any:
    if isinstance(obj, float):
        return round(obj, ndigits) if np.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, ndigits) for v in obj]
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        return round(val, ndigits) if np.isfinite(val) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def _metadata_payload(scorer) -> dict[str, Any]:
    trained = scorer.trained
    if trained is None:
        info = scorer.model_info()
        return {
            "status": "development_fallback",
            "model_name": info.get("name") or "development_fallback",
            "model_version": info.get("version"),
            "model_type": info.get("type"),
            "model_purpose": (
                "Development fallback heuristic for integration testing only. "
                "Not a trained credit-risk model."
            ),
            "is_trained_model": False,
            "evaluation_dataset": None,
            "last_evaluation_date": None,
            "metrics": {
                "auc_roc": None,
                "precision": None,
                "recall": None,
                "f1_score": None,
                "accuracy": None,
                "pr_auc": None,
                "log_loss": None,
                "brier": None,
                "ks": None,
            },
            "metric_availability": {
                "auc_roc": "not_yet_evaluated",
                "precision": "not_yet_evaluated",
                "recall": "not_yet_evaluated",
                "f1_score": "not_yet_evaluated",
                "accuracy": "not_yet_evaluated",
                "pr_auc": "not_yet_evaluated",
                "log_loss": "not_yet_evaluated",
                "brier": "not_yet_evaluated",
                "ks": "not_yet_evaluated",
            },
            "calibration_status": "Not yet evaluated",
            "feature_names": list(FEATURE_NAMES),
            "feature_importance_gain": {},
            "baseline_logistic_regression_test": None,
            "caveat": (
                "DEVELOPMENT FALLBACK is active. No trained-model evaluation metrics are available."
            ),
            "decision_support_statement": DECISION_SUPPORT_STATEMENT,
            "fairness": _fairness_section(list(FEATURE_NAMES), {}),
            "limitations": _limitations(trained=False),
            "human_review_requirements": _human_review(),
            "explainability": {
                "method": "unavailable",
                "detail": "SHAP TreeExplainer requires the trained LightGBM booster.",
            },
        }

    md = trained.metadata
    test = (md.get("metrics") or {}).get("test") or {}
    training = md.get("training_data") or {}
    # Scalar metrics present in the committed artifact.
    availability = {
        "auc_roc": "available" if "roc_auc" in test else "not_yet_evaluated",
        "pr_auc": "available" if "pr_auc" in test else "not_yet_evaluated",
        "log_loss": "available" if "log_loss" in test else "not_yet_evaluated",
        "brier": "available" if "brier" in test else "not_yet_evaluated",
        "ks": "available" if "ks" in test else "not_yet_evaluated",
        # Not stored in model_metadata.json — filled only when curves are computed.
        "precision": "not_yet_evaluated",
        "recall": "not_yet_evaluated",
        "f1_score": "not_yet_evaluated",
        "accuracy": "not_yet_evaluated",
    }
    return {
        "status": "trained",
        "model_name": md.get("model_name"),
        "model_version": md.get("model_version"),
        "model_type": "lightgbm",
        "model_purpose": (
            "Binary probability-of-default estimator for demo credit-scoring of "
            "small online sellers and freelancers. Decision-support only."
        ),
        "is_trained_model": True,
        "evaluation_dataset": {
            "kind": training.get("kind"),
            "note": training.get("note"),
            "n_rows": training.get("n_rows"),
            "seed": training.get("seed"),
            "split": training.get("split"),
            "sha256": training.get("sha256"),
            "test_n": test.get("n"),
            "positive_rate_test": test.get("positive_rate"),
        },
        "last_evaluation_date": md.get("trained_at_utc"),
        "best_iteration": md.get("best_iteration"),
        "metrics": {
            "auc_roc": test.get("roc_auc"),
            "precision": None,
            "recall": None,
            "f1_score": None,
            "accuracy": None,
            "pr_auc": test.get("pr_auc"),
            "log_loss": test.get("log_loss"),
            "brier": test.get("brier"),
            "ks": test.get("ks"),
        },
        "metrics_by_split": md.get("metrics"),
        "metric_availability": availability,
        "calibration_status": (
            "Not calibrated on real outcomes. Brier score on the synthetic test split "
            "is reported; no isotonic/Platt calibration was fitted."
        ),
        "feature_names": md.get("feature_names") or list(FEATURE_NAMES),
        "feature_importance_gain": md.get("feature_importance_gain") or {},
        "baseline_logistic_regression_test": md.get("baseline_logistic_regression_test"),
        "library_versions": md.get("library_versions"),
        "caveat": md.get("caveat"),
        "decision_support_statement": DECISION_SUPPORT_STATEMENT,
        "fairness": _fairness_section(
            md.get("feature_names") or list(FEATURE_NAMES),
            md.get("feature_importance_gain") or {},
        ),
        "limitations": _limitations(trained=True),
        "human_review_requirements": _human_review(),
        "explainability": {
            "method": "TreeSHAP (shap.TreeExplainer) on the LightGBM booster",
            "detail": (
                "Contributions are log-odds of default for the scored input. "
                "They are attributions, not causal claims. Available via POST /explain."
            ),
        },
    }


def _fairness_section(features: list[str], importance: dict[str, float]) -> dict[str, Any]:
    used = [f for f in features if f in FEATURE_NAMES]
    return {
        "sensitive_attributes_excluded": SENSITIVE_ATTRIBUTES_EXCLUDED,
        "sensitive_or_proxy_features_used": [
            f for f in SENSITIVE_OR_PROXY_FEATURES_USED if f in used
        ],
        "features_used": used,
        "top_features_by_gain": [
            {"feature": name, "gain": gain}
            for name, gain in list(importance.items())[:10]
        ],
        "bias_considerations": [
            "No fairness or subgroup analysis has been run on real borrowers.",
            "age_years and employment_type are model inputs and can act as proxies for protected classes; "
            "they require human review before any production use.",
            "The model was trained on synthetic labels from a hand-written risk rule, so "
            "metric parity across groups would not demonstrate real-world fairness.",
            "PayPal-to-schema field mappings remain provisional and unverified.",
        ],
        "data_quality_limitations": [
            "Training labels are synthetic, not observed defaults.",
            "Home Credit loader maps only a subset of inputs and is unused by the shipped artifact.",
            "Missing values are passed as NaN; ratios are NaN when denominators are missing or ≤ 0.",
        ],
    }


def _limitations(*, trained: bool) -> list[str]:
    items = [
        "Not for real lending decisions or guaranteed credit outcomes.",
        "No drift monitoring or production calibration pipeline.",
        DECISION_SUPPORT_STATEMENT,
    ]
    if trained:
        items.insert(
            0,
            "Reported ROC-AUC and related figures come from a synthetic development split only.",
        )
    else:
        items.insert(0, "No trained model artifact is loaded; scoring uses a labelled heuristic.")
    return items


def _human_review() -> list[str]:
    return [
        "A human reviewer must inspect the underlying income and repayment evidence before any credit action.",
        "SHAP attributions and counterfactuals are explanatory aids, not automated approval rules.",
        "Disbursement and payout actions remain behind explicit user confirmation in the sandbox APIs.",
    ]


def _downsample_roc(fpr: np.ndarray, tpr: np.ndarray, max_points: int = 80) -> list[dict[str, float]]:
    n = len(fpr)
    if n == 0:
        return []
    if n <= max_points:
        idx = range(n)
    else:
        idx = np.linspace(0, n - 1, max_points, dtype=int)
    return [{"fpr": float(fpr[i]), "tpr": float(tpr[i])} for i in idx]


def compute_evaluation_curves(scorer, *, threshold: float = 0.5) -> dict[str, Any]:
    """Recompute ROC / calibration / confusion on the synthetic test split.

    Uses the same seed and row count recorded in model metadata when available.
    Results are cached in-process for the lifetime of the worker.
    """
    trained = scorer.trained
    if trained is None:
        return {
            "status": "not_yet_evaluated",
            "detail": "No trained model is loaded; curve diagnostics are unavailable.",
            "threshold": threshold,
            "roc_curve": None,
            "calibration_curve": None,
            "confusion_matrix": None,
            "threshold_metrics": None,
            "metrics_comparison": None,
            "computed_at_utc": None,
        }

    cache_key = f"{trained.metadata.get('model_version')}:{threshold}"
    with _curve_lock:
        cached = _curve_cache.get(cache_key)
        if cached is not None:
            return cached

    md = trained.metadata
    training = md.get("training_data") or {}
    seed = int(training.get("seed") or 42)
    n_rows = int(training.get("n_rows") or 30_000)
    kind = training.get("kind") or "synthetic_development_dataset"
    if kind != "synthetic_development_dataset":
        result = {
            "status": "not_yet_evaluated",
            "detail": (
                f"Curve recomputation is only implemented for the synthetic development dataset "
                f"(current kind={kind!r})."
            ),
            "threshold": threshold,
            "roc_curve": None,
            "calibration_curve": None,
            "confusion_matrix": None,
            "threshold_metrics": None,
            "metrics_comparison": None,
            "computed_at_utc": None,
        }
        with _curve_lock:
            _curve_cache[cache_key] = result
        return result

    df = generate(n_rows=n_rows, seed=seed)
    y = df["TARGET"].to_numpy()
    idx = np.arange(len(df))
    train_idx, rest_idx = train_test_split(idx, test_size=0.30, stratify=y, random_state=seed)
    _, test_idx = train_test_split(rest_idx, test_size=0.50, stratify=y[rest_idx], random_state=seed)
    X = build_features(df)
    y_test = y[test_idx]
    p_test = trained.booster.predict(X.iloc[test_idx])

    fpr, tpr, _ = roc_curve(y_test, p_test)
    # Reliability diagram on the synthetic test split (not real-outcome calibration).
    frac_pos, mean_pred = calibration_curve(y_test, p_test, n_bins=10, strategy="quantile")
    y_hat = (p_test >= threshold).astype(int)
    cm = confusion_matrix(y_test, y_hat, labels=[0, 1])
    tn, fp, fn, tp = (int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1]))

    threshold_metrics = {
        "threshold": threshold,
        "precision": float(precision_score(y_test, y_hat, zero_division=0)),
        "recall": float(recall_score(y_test, y_hat, zero_division=0)),
        "f1_score": float(f1_score(y_test, y_hat, zero_division=0)),
        "accuracy": float(accuracy_score(y_test, y_hat)),
        "positive_rate_predicted": float(np.mean(y_hat)),
        "positive_rate_actual": float(np.mean(y_test)),
        "n": int(len(y_test)),
        "note": (
            f"Computed on the synthetic stratified test split (n={len(y_test)}) "
            f"at PD threshold {threshold}. Not real-world performance."
        ),
    }

    stored_test = (md.get("metrics") or {}).get("test") or {}
    baseline = md.get("baseline_logistic_regression_test") or {}
    comparison = [
        {
            "label": "LightGBM (stored test)",
            "roc_auc": stored_test.get("roc_auc"),
            "pr_auc": stored_test.get("pr_auc"),
            "brier": stored_test.get("brier"),
            "ks": stored_test.get("ks"),
            "source": "model_metadata.json",
        },
        {
            "label": "Logistic regression baseline (stored test)",
            "roc_auc": baseline.get("roc_auc"),
            "pr_auc": baseline.get("pr_auc"),
            "brier": baseline.get("brier"),
            "ks": baseline.get("ks"),
            "source": "model_metadata.json",
        },
        {
            "label": f"LightGBM @ threshold {threshold} (recomputed)",
            "precision": threshold_metrics["precision"],
            "recall": threshold_metrics["recall"],
            "f1_score": threshold_metrics["f1_score"],
            "accuracy": threshold_metrics["accuracy"],
            "source": "on_demand_synthetic_test_split",
        },
    ]

    result = _round_floats({
        "status": "available",
        "detail": (
            "Curves recomputed from the loaded booster on the synthetic stratified test split "
            f"(seed={seed}, n_rows={n_rows}, test_n={len(y_test)}). Pipeline-check numbers only."
        ),
        "threshold": threshold,
        "dataset": {
            "kind": kind,
            "seed": seed,
            "n_rows": n_rows,
            "test_n": int(len(y_test)),
            "split": "stratified 70/15/15 train/valid/test",
        },
        "roc_curve": {
            "points": _downsample_roc(fpr, tpr),
            "diagonal": [{"fpr": 0.0, "tpr": 0.0}, {"fpr": 1.0, "tpr": 1.0}],
        },
        "calibration_curve": {
            "points": [
                {"mean_predicted": float(mp), "fraction_positives": float(fp_)}
                for mp, fp_ in zip(mean_pred, frac_pos, strict=False)
            ],
            "perfect": [{"mean_predicted": 0.0, "fraction_positives": 0.0},
                        {"mean_predicted": 1.0, "fraction_positives": 1.0}],
            "note": "Synthetic-split reliability diagram. Model is not calibrated on real outcomes.",
        },
        "confusion_matrix": {
            "labels": ["non_default (0)", "default (1)"],
            "matrix": [[tn, fp], [fn, tp]],
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
            "true_positive": tp,
            "threshold": threshold,
        },
        "threshold_metrics": threshold_metrics,
        "metrics_comparison": comparison,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    with _curve_lock:
        _curve_cache[cache_key] = result
    return result


@router.get("/model-card", summary="Model card metadata and responsible-AI disclosures", response_model=None)
def get_model_card(request: Request) -> dict:
    return _metadata_payload(request.app.state.scorer)


@router.get(
    "/model-card/evaluation",
    summary="ROC, calibration, confusion matrix from the synthetic test split",
    response_model=None,
)
def get_model_card_evaluation(request: Request, threshold: float = 0.5) -> dict | JSONResponse:
    if not 0.0 < threshold < 1.0:
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": "threshold must be between 0 and 1 exclusive"},
        )
    return compute_evaluation_curves(request.app.state.scorer, threshold=threshold)

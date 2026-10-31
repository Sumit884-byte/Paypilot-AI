"""TreeSHAP explanations for the trained LightGBM score.

Values come from shap.TreeExplainer on the same feature row the scorer predicts.
They are in log-odds of default. A positive value raises estimated default risk
and a negative value lowers it. They are attributions, not causes. If SHAP cannot
be tied back to the model output, the status is unavailable and no heuristic
reasons are substituted.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Request

from .features import build_features
from .schema import ScoreRequest

router = APIRouter(tags=["explainability"])
METHOD = "shap.TreeExplainer"
_EXPLAINERS: dict[int, Any] = {}

FEATURE_LABELS = {
    "age_years": "Age",
    "business_age_months": "Time in business",
    "monthly_income_inr": "Declared monthly income",
    "avg_monthly_revenue_inr": "Average monthly revenue",
    "avg_monthly_expenses_inr": "Average monthly expenses",
    "revenue_volatility_cv": "Revenue volatility",
    "txn_count_90d": "Recent transaction count",
    "avg_txn_value_inr": "Average transaction value",
    "active_months_12m": "Active months",
    "refund_rate_90d": "Refund rate",
    "dispute_rate_12m": "Dispute rate",
    "avg_client_turnaround_days": "Client payment turnaround time",
    "late_payment_rate_90d": "Late client payment rate (90d)",
    "top_client_revenue_share": "Top client revenue concentration",
    "existing_monthly_debt_payments_inr": "Existing debt payments",
    "prior_defaults_count": "Prior defaults",
    "requested_loan_amount_inr": "Requested loan amount",
    "requested_term_months": "Requested term",
    "debt_to_income": "Debt to income",
    "expense_ratio": "Expense ratio",
    "net_margin": "Net margin",
    "loan_to_annual_revenue": "Loan to annual revenue",
    "installment_to_income": "Instalment to income",
    "employment_type_code": "Employment type",
}


def unavailable(reason: str, detail: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "method": None,
        "reason": reason,
        "detail": detail,
        "causal_claim": False,
        "output_space": None,
        "base_value": None,
        "predicted_log_odds": None,
        "predicted_probability": None,
        "reconstruction_abs_error": None,
        "matches_model_output": False,
        "factors_lowering_risk": [],
        "factors_raising_risk": [],
        "drivers": [],
        "interpretation": "SHAP was not returned. Heuristic reasons were not substituted.",
    }


def _explainer(booster: Any) -> Any:
    import shap

    cached = _EXPLAINERS.get(id(booster))
    if cached is not None:
        return cached
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="LightGBM binary classifier")
        cached = shap.TreeExplainer(booster)
    _EXPLAINERS[id(booster)] = cached
    return cached


def _vector(values: Any, n_features: int) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.shape[-1] != n_features:
        raise ValueError("SHAP width does not match the model features")
    return array.reshape(-1, n_features)[-1]


def _margin_candidates(shap_values: Any, expected: Any, n_features: int) -> list[tuple[np.ndarray, float]]:
    found: list[tuple[np.ndarray, float]] = []
    if isinstance(shap_values, list):
        bases = np.asarray(expected, dtype=float).reshape(-1)
        for index, values in enumerate(shap_values):
            base = float(bases[index] if bases.size == len(shap_values) else bases[0])
            found.append((_vector(values, n_features), base))
        return found
    array = np.asarray(shap_values, dtype=float)
    bases = np.asarray(expected, dtype=float).reshape(-1)
    if array.ndim == 3:
        class_axis = 1 if array.shape[1] != n_features and array.shape[2] == n_features else array.ndim - 1
        count = array.shape[class_axis]
        for index in range(count):
            chosen = np.take(array, index, axis=class_axis)
            base = float(bases[index] if bases.size == count else bases[0])
            found.append((_vector(chosen, n_features), base))
        return found
    found.append((_vector(array, n_features), float(bases[0])))
    return found


def _factor(name: str, contribution: float) -> dict[str, Any]:
    direction = "raises_risk" if contribution > 0 else "lowers_risk"
    label = FEATURE_LABELS.get(name, name)
    verb = "increased" if contribution > 0 else "reduced"
    description = (
        f"{label} {verb} the model's estimated default risk by {abs(contribution):.4f} log-odds. "
        "This is a model attribution for this input, not a cause and not a lending decision."
    )
    return {
        "feature": name,
        "name": label,
        "label": label,
        "contribution": round(float(contribution), 8),
        "contribution_units": "log_odds_of_default",
        "direction": direction,
        "description": description,
        "message": description,
        "impact": description,
        "method": METHOD,
    }


def explain_trained(booster: Any, feature_names: list[str], record: pd.DataFrame, predicted_probability: float) -> dict[str, Any]:
    """Explain one row. predicted_probability must be the scorer's unrounded PD."""
    try:
        import shap  # noqa: F401
    except ImportError:
        return unavailable("shap_not_installed", "The shap package is not installed, so no explanation was produced.")
    matrix = build_features(record)[feature_names]
    values = np.asarray(matrix, dtype=float)
    try:
        raw = float(booster.predict(values, raw_score=True)[0])
        contrib = np.asarray(booster.predict(values, pred_contrib=True)[0], dtype=float)
        explainer = _explainer(booster)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="LightGBM binary classifier")
            shap_values = explainer.shap_values(values)
        matched = None
        for vector, base in _margin_candidates(shap_values, explainer.expected_value, len(feature_names)):
            if abs((base + float(vector.sum())) - raw) <= 1e-4:
                matched = (vector, base)
                break
        if matched is None:
            return unavailable(
                "shap_reconstruction_failed",
                "TreeSHAP values did not add back to this model's raw score, so they were not returned.",
            )
        vector, base = matched
        if contrib.shape[0] != len(feature_names) + 1 or np.max(np.abs(vector - contrib[:-1])) > 1e-5:
            return unavailable(
                "shap_disagrees_with_lightgbm",
                "shap.TreeExplainer did not match LightGBM pred_contrib for this row, so neither vector was returned as an explanation.",
            )
    except Exception:
        return unavailable("shap_failed", "SHAP could not be computed for this input. Heuristic reasons were not substituted.")
    probability = 1.0 / (1.0 + np.exp(-raw))
    if abs(probability - float(predicted_probability)) > 1e-4:
        return unavailable(
            "prediction_mismatch",
            "The explained raw score does not match the probability returned for this same input.",
        )
    factors = [_factor(name, float(value)) for name, value in zip(feature_names, vector, strict=True)]
    lowering = [factor for factor in factors if factor["contribution"] < 0]
    raising = [factor for factor in factors if factor["contribution"] > 0]
    lowering.sort(key=lambda factor: (factor["contribution"], factor["feature"]))
    raising.sort(key=lambda factor: (-factor["contribution"], factor["feature"]))
    drivers = lowering[:3] + raising[:3]
    return {
        "status": "available",
        "method": METHOD,
        "reason": None,
        "detail": "TreeSHAP log-odds contributions for the same LightGBM prediction the score uses.",
        "causal_claim": False,
        "output_space": "log_odds_of_default",
        "base_value": round(base, 8),
        "predicted_log_odds": round(raw, 8),
        "predicted_probability": round(float(probability), 8),
        "reconstruction_abs_error": abs((base + float(vector.sum())) - raw),
        "matches_model_output": True,
        "matches_lightgbm_pred_contrib": True,
        "feature_names": list(feature_names),
        "factors_lowering_risk": lowering[:3],
        "factors_raising_risk": raising[:3],
        "all_contributions": [
            {"feature": name, "contribution": round(float(value), 8)}
            for name, value in zip(feature_names, vector, strict=True)
        ],
        "drivers": drivers,
        "interpretation": (
            "Positive log-odds contributions raise estimated default risk and negative contributions lower it. "
            "These are not causal effects, and changing a feature by the contribution amount is not a recommendation."
        ),
    }


def explain_request(scorer: Any, req: ScoreRequest, predicted_probability: float) -> dict[str, Any]:
    if scorer.trained is None:
        return unavailable(
            "shap_requires_trained_lightgbm",
            "No trained LightGBM model is loaded. The development fallback was not given heuristic reasons in place of SHAP.",
        )
    frame = pd.DataFrame([req.model_dump(mode="json")])
    return explain_trained(
        scorer.trained.booster,
        list(scorer.trained.metadata["feature_names"]),
        frame,
        predicted_probability,
    )


@router.post("/explain", summary="SHAP explanation for one application, without recording a disbursement")
def explain_endpoint(req: ScoreRequest, request: Request) -> dict[str, Any]:
    result = request.app.state.scorer.score(req)
    return {
        "applicant_id": result["applicant_id"],
        "score": result["score"],
        "probability_of_default": result["probability_of_default"],
        "risk_band": result["risk_band"],
        "explanation": result["explanation"],
        "drivers": result["drivers"],
        "to_move_up": result["to_move_up"],
        "counterfactual_preview": result.get("counterfactual_preview"),
        "model": result["model"],
        "evaluation_caveat": result["evaluation_caveat"],
        "disclaimer": "SHAP values attribute this model score. They are not causes and not a lending decision.",
    }

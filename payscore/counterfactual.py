"""Counterfactual score changes evaluated on the trained model.

Search only proposes changes a person could make without inventing history:
a smaller requested amount, a modestly longer term, a real reduction in other
debt payments, or a later improvement in refunds, disputes, or revenue stability.
Age, employment, prior defaults, income, and transaction fields are rejected.
Every kept suggestion is re-scored with the trained model. The development
fallback is not used.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Request
from pydantic import ValidationError

from .schema import ScoreRequest

router = APIRouter(tags=["counterfactuals"])
DISCLAIMER = (
    "Estimated change in this model's score only. It is not a guaranteed credit decision, "
    "cash-flow outcome, or causal effect. Do not change submitted records so they match a hypothetical."
)

IMMUTABLE_REASONS = {
    "age_years": "Age cannot be changed for this application.",
    "employment_type": "Employment type is treated as an identity attribute and is not a recommended edit.",
    "applicant_id": "The applicant id is not a credit feature to edit.",
    "prior_defaults_count": "Prior defaults are historical facts. PayScore will not suggest hiding or altering them.",
    "monthly_income_inr": "Income is not adjusted. Report only income that is actually received.",
    "business_age_months": "Time in business cannot be changed for an application decided now.",
    "avg_monthly_revenue_inr": "Revenue history is not edited or fabricated.",
    "avg_monthly_expenses_inr": "Expense history is not edited or fabricated.",
    "txn_count_90d": "Transaction counts must not be edited or fabricated.",
    "avg_txn_value_inr": "Transaction amounts must not be edited or fabricated.",
    "avg_client_turnaround_days": "Client payment turnaround time is an observed record and cannot be edited.",
    "late_payment_rate_90d": "Late client payment history is an observed record and cannot be edited.",
    "top_client_revenue_share": "Client concentration is an observed business structure and cannot be edited.",
    "debt_to_income": "Derived ratios change only when their underlying inputs change.",
    "expense_ratio": "Derived ratios change only when their underlying inputs change.",
    "net_margin": "Derived ratios change only when their underlying inputs change.",
    "loan_to_annual_revenue": "Derived ratios change only when their underlying inputs change.",
    "installment_to_income": "The instalment ratio changes only when amount, term, or income changes.",
    "employment_type_code": "Employment type is not a dial to turn.",
}


def _predict(scorer: Any, req: ScoreRequest) -> tuple[int, float]:
    from .model import pd_to_score

    frame = pd.DataFrame([req.model_dump(mode="json")])
    probability = float(scorer.trained.predict_pd(frame)[0])
    return pd_to_score(probability), probability


def _apply(req: ScoreRequest, updates: dict[str, Any]) -> ScoreRequest:
    data = req.model_dump(mode="json")
    data.update(updates)
    return ScoreRequest.model_validate(data)


def _suggestion(changes: list[dict[str, Any]], current_score: int, current_pd: float, new_score: int, new_pd: float) -> dict[str, Any]:
    return {
        "changes": changes,
        "current_score": current_score,
        "estimated_score": new_score,
        "estimated_score_difference": new_score - current_score,
        "current_probability_of_default": round(current_pd, 6),
        "estimated_probability_of_default": round(new_pd, 6),
        "model_evaluated": True,
        "recommended": new_score > current_score,
        "note": DISCLAIMER,
    }


def _reject(feature: str, proposed: Any, req: ScoreRequest) -> Optional[str]:
    current = req.model_dump(mode="json")
    if feature in IMMUTABLE_REASONS:
        return IMMUTABLE_REASONS[feature]
    if feature not in {
        "requested_loan_amount_inr", "requested_term_months", "existing_monthly_debt_payments_inr",
        "refund_rate_90d", "dispute_rate_12m", "revenue_volatility_cv", "active_months_12m",
    }:
        return "This field is outside the eligible counterfactual set."
    if isinstance(proposed, bool) or not isinstance(proposed, (int, float)):
        return "The proposed value must be a number."
    if feature == "requested_loan_amount_inr":
        if not 0 < float(proposed) <= 1_000_000_000:
            return "Loan amount must stay inside the application limits."
        return None
    if feature == "requested_term_months":
        if int(proposed) != proposed or not 1 <= int(proposed) <= 360:
            return "Term must be a whole number of months from 1 to 360."
        return None
    if feature == "existing_monthly_debt_payments_inr":
        if current.get("existing_monthly_debt_payments_inr") is None:
            return "Existing debt payments are missing, so a reduction is not invented."
        current_debt = float(current["existing_monthly_debt_payments_inr"])
        if float(proposed) < 0 or float(proposed) > current_debt:
            return "Only an actual reduction in other debt payments is eligible. Raising or inventing the payment is not."
        return None
    if feature in {"refund_rate_90d", "dispute_rate_12m"}:
        current_rate = current.get(feature)
        if current_rate is None:
            return "This rate is missing, so there is no observed value to improve."
        if not 0 <= float(proposed) <= float(current_rate):
            return "Only a lower future rate is eligible. Do not raise it or edit the historical record."
        return None
    if feature == "revenue_volatility_cv":
        current_cv = current.get(feature)
        if current_cv is None:
            return "Revenue volatility is missing, so there is no observed value to improve."
        if float(proposed) < 0.02 or float(proposed) > float(current_cv):
            return "Volatility can only move down to a still-realistic 0.02, not to an invented zero or a higher value."
        return None
    current_months = current.get("active_months_12m")
    if current_months is None:
        return "Active months are missing, so a future activity change is not proposed from nothing."
    if int(proposed) != proposed or not int(current_months) < int(proposed) <= min(12, int(current_months) + 3):
        return "Active months can rise by at most 3, and only up to 12. This is a what-if about future activity, not an edit of old transactions."
    return None


def _change(feature: str, current: Any, proposed: Any, description: str) -> dict[str, Any]:
    return {"feature": feature, "current": current, "proposed": proposed, "description": description}


def _search_candidates(req: ScoreRequest) -> list[list[dict[str, Any]]]:
    data = req.model_dump(mode="json")
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in (
        "requested_loan_amount_inr", "requested_term_months", "existing_monthly_debt_payments_inr",
        "refund_rate_90d", "dispute_rate_12m", "revenue_volatility_cv", "active_months_12m",
    )}
    amount = float(data["requested_loan_amount_inr"])
    floor = max(1000.0, round(amount * 0.2, 2))
    for fraction in (0.9, 0.8, 0.7, 0.5):
        proposed = round(amount * fraction, 2)
        if floor <= proposed < amount - 0.5:
            groups["requested_loan_amount_inr"].append(_change(
                "requested_loan_amount_inr", amount, proposed,
                "Request a smaller loan amount. This changes the ask, not any historical record.",
            ))
    term = int(data["requested_term_months"])
    for extra in (3, 6, 12):
        proposed_term = term + extra
        if proposed_term <= min(360, term + 24):
            groups["requested_term_months"].append(_change(
                "requested_term_months", term, proposed_term,
                "Request a longer term, at most 24 months beyond the current term.",
            ))
    debt = data.get("existing_monthly_debt_payments_inr")
    if debt:
        for fraction in (0.75, 0.5):
            proposed_debt = round(float(debt) * fraction, 2)
            groups["existing_monthly_debt_payments_inr"].append(_change(
                "existing_monthly_debt_payments_inr", debt, proposed_debt,
                "If other monthly debt payments were actually reduced, for example by paying balances down. Do not report a lower figure unless the payment has changed.",
            ))
    for feature, text in (
        ("refund_rate_90d", "If a later refund rate were lower because fewer orders were refunded. Do not alter refund records."),
        ("dispute_rate_12m", "If a later dispute rate were lower because disputes were resolved and not repeated. Do not alter dispute records."),
    ):
        current = data.get(feature)
        if current:
            groups[feature].append(_change(feature, current, round(float(current) * 0.5, 6), text))
            groups[feature].append(_change(feature, current, 0, text))
    volatility = data.get("revenue_volatility_cv")
    if volatility is not None and float(volatility) > 0.05:
        for fraction in (0.75, 0.5):
            proposed_cv = round(max(0.05, float(volatility) * fraction), 6)
            if proposed_cv < float(volatility):
                groups["revenue_volatility_cv"].append(_change(
                    "revenue_volatility_cv", volatility, proposed_cv,
                    "If later monthly revenue were steadier. Zero volatility is not suggested.",
                ))
    active = data.get("active_months_12m")
    if active is not None and int(active) < 12:
        for extra in (1, 2, 3):
            proposed_months = int(active) + extra
            if proposed_months <= 12:
                groups["active_months_12m"].append(_change(
                    "active_months_12m", active, proposed_months,
                    "If sales landed in more recent months going forward. This is not an instruction to edit old transactions.",
                ))
    return [group for group in groups.values() if group]


def _score_change_list(scorer: Any, req: ScoreRequest, changes: list[dict[str, Any]], current_score: int, current_pd: float) -> Optional[dict[str, Any]]:
    updates = {change["feature"]: change["proposed"] for change in changes}
    try:
        updated = _apply(req, updates)
    except ValidationError:
        return None
    new_score, new_pd = _predict(scorer, updated)
    return _suggestion(changes, current_score, current_pd, new_score, new_pd)


def _unavailable() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "model_evaluated": False,
        "reason": "counterfactuals_require_trained_model",
        "current_score": None,
        "current_probability_of_default": None,
        "suggestions": [],
        "rejected_changes": [],
        "evaluated_count": 0,
        "assumptions": ["The development fallback is not used to invent counterfactuals."],
        "summary": "Counterfactuals are unavailable because no trained LightGBM model is loaded.",
        "disclaimer": DISCLAIMER,
    }


def analyse_counterfactual(scorer: Any, req: ScoreRequest, proposed_changes: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if scorer.trained is None:
        return _unavailable()
    current_score, current_pd = _predict(scorer, req)
    assumptions = [
        "Each suggestion is re-scored with the trained LightGBM model and the same feature pipeline as /score.",
        "Eligible search moves are a smaller loan (not below the greater of Rs 1,000 and 20% of the current ask), a term up to 24 months longer, a real cut in other debt payments, a lower refund or dispute rate, revenue volatility down to 0.05, or up to three more active months.",
        "Age, employment, income, business age, prior defaults, and transaction amounts or counts are not recommended changes.",
        DISCLAIMER,
    ]
    if proposed_changes:
        rejected = []
        accepted = []
        for feature, proposed in proposed_changes.items():
            reason = _reject(str(feature), proposed, req)
            if reason:
                rejected.append({"feature": feature, "proposed": proposed, "reason": reason})
            else:
                current_value = req.model_dump(mode="json").get(feature)
                accepted.append(_change(str(feature), current_value, proposed, "Caller-supplied what-if. Evaluated with the trained model."))
        suggestion = None
        if accepted:
            suggestion = _score_change_list(scorer, req, accepted, current_score, current_pd)
            if suggestion is None:
                rejected.append({"feature": ",".join(change["feature"] for change in accepted), "proposed": None, "reason": "The combined change is outside the application schema."})
        difference = 0 if suggestion is None else suggestion["estimated_score_difference"]
        unchanged = suggestion is not None and difference == 0 and abs(suggestion["estimated_probability_of_default"] - round(current_pd, 6)) < 1e-9
        if suggestion is None:
            status = "rejected"
        elif unchanged:
            status = "unchanged"
        else:
            status = "evaluated"
        summary = DISCLAIMER if suggestion is None else (
            f"Estimated model score moves from {current_score} to {suggestion['estimated_score']} "
            f"({difference:+d}). This is not a guaranteed financial outcome."
        )
        return {
            "status": status,
            "model_evaluated": suggestion is not None,
            "reason": None if suggestion is not None else "no_eligible_change",
            "current_score": current_score,
            "current_probability_of_default": round(current_pd, 6),
            "suggestions": [suggestion] if suggestion is not None else [],
            "rejected_changes": rejected,
            "evaluated_count": 1 if suggestion is not None else 0,
            "assumptions": assumptions,
            "summary": summary,
            "disclaimer": DISCLAIMER,
        }

    evaluated: list[dict[str, Any]] = []
    best_by_feature: dict[str, dict[str, Any]] = {}
    for group in _search_candidates(req):
        for change in group:
            suggestion = _score_change_list(scorer, req, [change], current_score, current_pd)
            if suggestion is None:
                continue
            evaluated.append(suggestion)
            if suggestion["estimated_score"] > current_score:
                feature = change["feature"]
                current_best = best_by_feature.get(feature)
                if current_best is None or suggestion["estimated_score"] > current_best["estimated_score"]:
                    best_by_feature[feature] = suggestion
    pair_features = (
        ("requested_loan_amount_inr", "requested_term_months"),
        ("requested_loan_amount_inr", "existing_monthly_debt_payments_inr"),
    )
    for left, right in pair_features:
        if left in best_by_feature and right in best_by_feature:
            combined = best_by_feature[left]["changes"] + best_by_feature[right]["changes"]
            suggestion = _score_change_list(scorer, req, combined, current_score, current_pd)
            if suggestion is not None:
                evaluated.append(suggestion)
    improving = [item for item in evaluated if item["estimated_score"] > current_score]
    improving.sort(key=lambda item: (-item["estimated_score"], len(item["changes"]), item["changes"][0]["feature"]))
    top = improving[:3]
    if top:
        best = top[0]
        # Each description is a full sentence already, so join them as sentences rather than with "; "
        described = " ".join(change["description"] for change in best["changes"])
        summary = (
            f"Estimated model score could move from {current_score} to {best['estimated_score']} "
            f"({best['estimated_score_difference']:+d}) if: {described}"
        )
        status = "ok"
    else:
        summary = "No eligible input change in the searched set raised the model score."
        status = "no_feasible_improvement"
    return {
        "status": status,
        "model_evaluated": True,
        "reason": None if top else "no_improving_eligible_change",
        "current_score": current_score,
        "current_probability_of_default": round(current_pd, 6),
        "suggestions": top,
        "rejected_changes": [],
        "evaluated_count": len(evaluated),
        "assumptions": assumptions,
        "summary": summary,
        "disclaimer": DISCLAIMER,
    }


def preview_for_score(scorer: Any, req: ScoreRequest) -> dict[str, Any]:
    result = analyse_counterfactual(scorer, req)
    best = result["suggestions"][0] if result["suggestions"] else None
    return {
        "status": result["status"],
        "summary": result["summary"],
        "best": best,
        "disclaimer": DISCLAIMER,
    }


class CounterfactualRequest(ScoreRequest):
    proposed_changes: Optional[dict[str, Any]] = None


@router.post("/counterfactuals", summary="Model-evaluated what-if changes for one application")
def counterfactuals(req: CounterfactualRequest, request: Request) -> dict[str, Any]:
    application = ScoreRequest.model_validate(req.model_dump(exclude={"proposed_changes"}))
    return analyse_counterfactual(request.app.state.scorer, application, req.proposed_changes)

"""Heuristic score drivers for the demo UI. These are NOT SHAP values."""

from __future__ import annotations

from typing import Any

from .schema import ScoreRequest

DRIVER_NOTE = "heuristic_not_shap"


def _installment_ratio(req: ScoreRequest) -> float:
    return float(req.requested_loan_amount_inr) / max(req.requested_term_months, 1) / max(req.monthly_income_inr, 1)


def heuristic_drivers(req: ScoreRequest) -> tuple[list[dict[str, Any]], str]:
    """Return up to three qualitative drivers plus a 'to move up' line."""
    candidates: list[tuple[float, dict[str, Any]]] = []
    installment = _installment_ratio(req)

    if installment >= 0.35:
        candidates.append((installment, {
            "feature": "installment_to_income", "direction": "raises_risk",
            "message": "The requested instalment is large relative to declared income.",
            "method": DRIVER_NOTE,
        }))
    if (req.existing_monthly_debt_payments_inr or 0) / max(req.monthly_income_inr, 1) >= 0.2:
        candidates.append((0.8, {
            "feature": "debt_to_income", "direction": "raises_risk",
            "message": "Existing monthly debt is a material share of income.",
            "method": DRIVER_NOTE,
        }))
    if (req.revenue_volatility_cv or 0) >= 0.25:
        candidates.append((req.revenue_volatility_cv or 0, {
            "feature": "revenue_volatility_cv", "direction": "raises_risk",
            "message": "Monthly PayPal revenue is lumpy compared with a stable seller.",
            "method": DRIVER_NOTE,
        }))
    if (req.refund_rate_90d or 0) > 0:
        candidates.append((req.refund_rate_90d or 0, {
            "feature": "refund_rate_90d", "direction": "raises_risk",
            "message": "Recent refunds reduce the quality of cashflow history.",
            "method": DRIVER_NOTE,
        }))
    if (req.dispute_rate_12m or 0) > 0:
        candidates.append((1.5, {
            "feature": "dispute_rate_12m", "direction": "raises_risk",
            "message": "Open or recent disputes weigh against a clean seller record.",
            "method": DRIVER_NOTE,
        }))
    if (req.prior_defaults_count or 0) > 0:
        candidates.append((2.0, {
            "feature": "prior_defaults_count", "direction": "raises_risk",
            "message": "Prior defaults are the strongest negative signal in this demo.",
            "method": DRIVER_NOTE,
        }))
    if (req.active_months_12m or 0) >= 10:
        candidates.append((0.3, {
            "feature": "active_months_12m", "direction": "lowers_risk",
            "message": "Sales landed in most of the last 12 months.",
            "method": DRIVER_NOTE,
        }))
    if (req.revenue_volatility_cv is not None and req.revenue_volatility_cv < 0.12):
        candidates.append((0.25, {
            "feature": "revenue_volatility_cv", "direction": "lowers_risk",
            "message": "Revenue is relatively smooth month to month.",
            "method": DRIVER_NOTE,
        }))
    if not candidates:
        candidates.append((0.1, {
            "feature": "monthly_income_inr", "direction": "lowers_risk",
            "message": "Declared income and a complete application are the main available signals.",
            "method": DRIVER_NOTE,
        }))

    candidates.sort(key=lambda item: item[0], reverse=True)
    drivers = [item[1] for item in candidates[:3]]
    if any(d["feature"] == "installment_to_income" for d in drivers):
        action = "Ask for a smaller amount or a longer term to bring the instalment share down."
    elif any(d["feature"] == "dispute_rate_12m" for d in drivers):
        action = "Resolve open disputes and keep refunds low for a few months."
    elif any(d["feature"] == "revenue_volatility_cv" and d["direction"] == "raises_risk" for d in drivers):
        action = "Show a longer stretch of consistent monthly sales."
    else:
        action = "Keep filing complete optional cashflow fields; missing inputs weaken the demo score."
    return drivers, action

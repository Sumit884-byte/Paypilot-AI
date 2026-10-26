"""Revenue-share percentage from observed revenue volatility.

The recommendation is a deterministic policy so it can be tested. It is not a
statistically validated credit model, and it never fills in missing history.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["revenue share"])

DISCLAIMER = (
    "Deterministic illustration from the supplied observations. Not a statistically validated "
    "model, a lending decision, or an instruction to change a PayPal deduction."
)
MIN_HISTORY = 3
ADEQUATE_HISTORY = 6


class RevenueShareAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revenues_inr: Optional[list[float]] = None
    applicant_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    obligation_inr: Optional[float] = Field(default=None, gt=0, le=1_000_000_000)
    essential_expenses_inr: Optional[float] = Field(default=None, ge=0, le=1_000_000_000)
    min_percentage: float = Field(default=5, gt=0, le=100)
    max_percentage: float = Field(default=30, gt=0, le=100)


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _grid(min_percentage: float, max_percentage: float, step: float = 1.0) -> list[float]:
    start = int(round(min_percentage * 100))
    stop = int(round(max_percentage * 100))
    stride = int(round(step * 100))
    values = []
    cursor = start
    while cursor < stop:
        values.append(cursor / 100.0)
        cursor += stride
    values.append(stop / 100.0)
    return values


def _metrics(revenues: list[float]) -> dict[str, Any]:
    n = len(revenues)
    mean = statistics.fmean(revenues) if n else None
    sample_std = statistics.stdev(revenues) if n >= 2 else None
    cv = None
    if mean is not None and sample_std is not None and mean > 0:
        cv = sample_std / mean
    downside = None if mean is None or sample_std is None else mean - sample_std
    observed_min = min(revenues) if n else None
    if downside is None or observed_min is None:
        stress = None
    else:
        stress = max(0.0, min(observed_min, downside))
    return {
        "n": n,
        "mean_inr": None if mean is None else _round_money(mean),
        "sample_std_inr": None if sample_std is None else _round_money(sample_std),
        "coefficient_of_variation": None if cv is None else round(cv, 6),
        "downside_mean_minus_one_std_inr": None if downside is None else _round_money(downside),
        "observed_min_inr": None if observed_min is None else _round_money(observed_min),
        "stress_revenue_inr": None if stress is None else _round_money(stress),
        "negative_observations": sum(1 for value in revenues if value < 0),
        "zero_observations": sum(1 for value in revenues if value == 0),
    }


def _cv_target(cv: float) -> float:
    """Policy targets, not fitted parameters. Clamped by the caller to min/max."""
    if cv < 0.15:
        return 20.0
    if cv < 0.35:
        return 12.0
    if cv < 0.60:
        return 8.0
    return 0.0  # caller substitutes the configured minimum


def analyse(
    revenues: Optional[list[float]],
    *,
    obligation_inr: Optional[float] = None,
    essential_expenses_inr: Optional[float] = None,
    min_percentage: float = 5.0,
    max_percentage: float = 30.0,
    source: str = "supplied_observations",
) -> dict[str, Any]:
    assumptions = [
        "Mean is the arithmetic mean of the supplied observations. No missing month was imputed.",
        "Standard deviation is the sample standard deviation (divisor n-1) when n is at least 2.",
        "Coefficient of variation is sample standard deviation / mean, and is undefined when the mean is not positive.",
        "Stress revenue is the lower of the minimum observation and mean-minus-one-standard-deviation, floored at zero.",
        "At least 3 observations are required before a percentage is recommended. Fewer than 6 observations, any negative observation, or a coefficient of variation of 0.60 or more keeps confidence low.",
        "Default bounds are 5% to 30%. They are product settings, not a regulatory cap. The repayment API separately accepts up to 100% when a person configures it.",
        "If an obligation is supplied, the smallest grid percentage whose stress deduction covers it is preferred, subject to the expense constraint.",
        "If no obligation or essential-expense figure is supplied, the percentage follows fixed coefficient-of-variation bands: 20% below 0.15, 12% below 0.35, 8% below 0.60, otherwise the configured minimum.",
        "statistically_validated is false. This policy has not been fit or back-tested on repayment outcomes.",
        DISCLAIMER,
    ]
    base = {
        "estimate": True,
        "regulated_advice": False,
        "statistically_validated": False,
        "source": source,
        "assumptions": assumptions,
        "disclaimer": DISCLAIMER,
        "recommended_percentage": None,
        "tested_alternatives": [],
        "confidence": "low",
    }
    if revenues is None:
        return {**base, "status": "insufficient_data", "reason": "no_observations", "metrics": _metrics([])}
    if not isinstance(revenues, list) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in revenues):
        return {**base, "status": "invalid", "reason": "non_finite_observation", "metrics": None}
    values = [float(v) for v in revenues]
    if min_percentage <= 0 or max_percentage <= 0 or min_percentage > 100 or max_percentage > 100 or min_percentage > max_percentage:
        return {**base, "status": "invalid", "reason": "invalid_percentage_bounds", "metrics": _metrics(values)}
    if obligation_inr is not None and (not math.isfinite(obligation_inr) or obligation_inr <= 0):
        return {**base, "status": "invalid", "reason": "invalid_obligation", "metrics": _metrics(values)}
    if essential_expenses_inr is not None and (not math.isfinite(essential_expenses_inr) or essential_expenses_inr < 0):
        return {**base, "status": "invalid", "reason": "invalid_expenses", "metrics": _metrics(values)}

    metrics = _metrics(values)
    if len(values) < MIN_HISTORY:
        return {
            **base,
            "status": "insufficient_data",
            "reason": "fewer_than_3_observations",
            "confidence": "low",
            "metrics": metrics,
        }
    if metrics["mean_inr"] is None or metrics["mean_inr"] <= 0:
        return {
            **base,
            "status": "insufficient_data",
            "reason": "non_positive_mean_revenue",
            "confidence": "low",
            "metrics": metrics,
        }

    mean = float(statistics.fmean(values))
    stress = float(metrics["stress_revenue_inr"])
    cv = metrics["coefficient_of_variation"]
    history_quality = "adequate" if len(values) >= ADEQUATE_HISTORY and metrics["negative_observations"] == 0 else "limited"
    confidence = "moderate"
    if len(values) < ADEQUATE_HISTORY or metrics["negative_observations"] or cv is None or cv >= 0.60:
        confidence = "low"

    alternatives = []
    for pct in _grid(min_percentage, max_percentage):
        expected_deduction = mean * pct / 100.0
        stress_deduction = stress * pct / 100.0
        stress_retained = stress * (1.0 - pct / 100.0)
        affordable = None if essential_expenses_inr is None else stress_retained + 1e-9 >= essential_expenses_inr
        alternatives.append({
            "percentage": round(pct, 2),
            "expected_deduction_inr": _round_money(expected_deduction),
            "stress_deduction_inr": _round_money(stress_deduction),
            "expected_retained_inr": _round_money(mean - expected_deduction),
            "stress_retained_inr": _round_money(stress_retained),
            "expected_obligation_coverage": None if obligation_inr is None else round(expected_deduction / obligation_inr, 4),
            "stress_obligation_coverage": None if obligation_inr is None else round(stress_deduction / obligation_inr, 4),
            "stress_covers_essential_expenses": affordable,
        })

    eligible = [
        row for row in alternatives
        if essential_expenses_inr is None or row["stress_covers_essential_expenses"]
    ]
    status = "ok"
    reason = "cv_band"
    recommended = None
    if essential_expenses_inr is not None and not eligible:
        status = "no_affordable_percentage"
        reason = "stress_revenue_does_not_cover_essential_expenses"
    elif obligation_inr is not None:
        reason = "smallest_percentage_covering_obligation_under_stress"
        covering = [row for row in eligible if (row["stress_obligation_coverage"] or 0) >= 1]
        if covering:
            recommended = covering[0]["percentage"]
        else:
            status = "obligation_not_covered"
            reason = "no_percentage_in_range_covers_the_obligation_under_stress"
            recommended = None
    else:
        if cv is None:
            target = min_percentage
        else:
            target = _cv_target(cv)
            if target <= 0:
                target = min_percentage
        target = min(max(target, min_percentage), max_percentage)
        # Snap to the tested grid point nearest the target, preferring the lower point on a tie.
        recommended = min(eligible or alternatives, key=lambda row: (abs(row["percentage"] - target), row["percentage"]))["percentage"]
        if eligible and recommended not in {row["percentage"] for row in eligible}:
            recommended = eligible[-1]["percentage"]

    return {
        **base,
        "status": status,
        "reason": reason,
        "recommended_percentage": recommended,
        "confidence": confidence,
        "history_quality": history_quality,
        "metrics": metrics,
        "obligation_inr": obligation_inr,
        "essential_expenses_inr": essential_expenses_inr,
        "min_percentage": min_percentage,
        "max_percentage": max_percentage,
        "tested_alternatives": alternatives,
        "bounds": {"min_percentage": min_percentage, "max_percentage": max_percentage, "step": 1},
    }


@router.post("/revenue-volatility", summary="Recommend a revenue-share percentage from observed revenue")
def revenue_volatility(req: RevenueShareAnalysisRequest) -> dict[str, Any]:
    from .applicant_context import revenues_for_applicant

    kwargs = {
        "obligation_inr": req.obligation_inr,
        "essential_expenses_inr": req.essential_expenses_inr,
        "min_percentage": req.min_percentage,
        "max_percentage": req.max_percentage,
    }
    if req.revenues_inr is not None:
        return analyse(req.revenues_inr, source="supplied_observations", **kwargs)
    if req.applicant_id:
        loaded = revenues_for_applicant(req.applicant_id)
        if loaded is None:
            result = analyse(None, source="applicant_not_found", **kwargs)
            result["reason"] = "applicant_history_not_found"
            return result
        values, source = loaded
        return analyse(values, source=source, **kwargs)
    return analyse(None, source="no_input", **kwargs)

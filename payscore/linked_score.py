"""PayScore for a PayPal-linked account.

The model needs two kinds of input. Transaction behaviour (revenue, volatility, sale counts, refunds, disputes, client
concentration) comes from the linked account's PayPal history. Personal facts PayPal does not share with the app (age,
employment, existing debt, the loan being asked for) come from the applicant. Each input is labelled with its source,
and nothing is borrowed from a demo persona.
"""

from __future__ import annotations

import hashlib
import statistics
from typing import Any, Optional

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .live_state import record_score
from .model import ModelUnavailableError
from .paypal.client import PayPalError
from .paypal.routes import ClientDep, LinkedProfileError, linked_account_id, load_linked_profile
from .schema import EmploymentType, Money, ScoreRequest

router = APIRouter(tags=["scoring"])
PAYPAL_SOURCE = "paypal_transaction_search"


class LinkedDetails(BaseModel):
    """What the applicant tells us; PayPal sign-in does not share these."""

    model_config = ConfigDict(extra="forbid")
    age_years: int = Field(..., ge=18, le=100)
    employment_type: EmploymentType
    requested_loan_amount_inr: float = Field(..., gt=0, le=1_000_000_000, allow_inf_nan=False)
    requested_term_months: int = Field(..., ge=1, le=360)
    monthly_income_inr: Optional[Money] = Field(
        None, description="Declared monthly income. When empty, the 12-month PayPal average is used.")
    business_age_months: Optional[int] = Field(None, ge=0, le=1200)
    avg_monthly_expenses_inr: Optional[Money] = None
    existing_monthly_debt_payments_inr: Optional[Money] = None
    prior_defaults_count: Optional[int] = Field(None, ge=0, le=50)


class NoIncomeEvidence(ValueError):
    """Neither PayPal history nor a declared figure gives a monthly income."""


def linked_applicant_id(user_id: str) -> str:
    """A stable, non-reversible applicant id for a PayPal account, so no PayPal identifier leaves the server."""
    return "PAYPAL-" + hashlib.sha256(f"paypilot-applicant:{user_id}".encode()).hexdigest()[:10].upper()


def monthly_values(profile: dict) -> list[float]:
    return [float(row.get("income_inr") or 0) for row in profile.get("monthly_income_12m") or []]


def since_first_income(values: list[float]) -> list[float]:
    """Months from the first one with income: a young business is not penalised for months before it traded."""
    first = next((i for i, value in enumerate(values) if value > 0), None)
    return [] if first is None else values[first:]


def paypal_features(profile: dict) -> dict[str, Any]:
    """Model inputs that PayPal history answers, computed the way payscore/derive.py computed them for training."""
    months = monthly_values(profile)
    recent = since_first_income(months[-6:])
    mean_recent = statistics.fmean(recent) if recent else 0.0
    active = sum(1 for value in months if value > 0)
    return {
        "avg_monthly_revenue_inr": round(max(mean_recent, 0.0), 2),
        "revenue_volatility_cv": (round(statistics.pstdev(recent) / mean_recent, 4)
                                  if len(recent) >= 3 and mean_recent > 0 else None),
        "txn_count_90d": int(profile.get("sale_count_90d") or 0),
        "avg_txn_value_inr": profile.get("avg_sale_value_90d_inr"),
        "active_months_12m": active,
        "refund_rate_90d": profile.get("refund_rate_90d"),
        # With no sales a rate of 0 would read as "never disputed"; unknown is the honest value
        "dispute_rate_12m": profile.get("dispute_rate_12m") if active else None,
        "avg_client_turnaround_days": profile.get("avg_client_turnaround_days_12m"),
        "top_client_revenue_share": profile.get("top_client_revenue_share_12m"),
    }


def build_application(user_id: str, profile: dict, details: LinkedDetails) -> tuple[dict[str, Any], list[dict]]:
    """The scoring request plus a per-field record of where each value came from."""
    paypal = paypal_features(profile)
    supplied = details.model_dump(exclude_none=True)
    average_income = round(sum(monthly_values(profile)) / 12, 2)
    if "monthly_income_inr" not in supplied:
        if average_income <= 0:
            raise NoIncomeEvidence(
                "Your linked PayPal account shows no completed incoming payments in the last 12 months, so there is "
                "no income to score. Enter your monthly income to score with a declared (unverified) figure.")
        supplied["monthly_income_inr"] = average_income
        income_source = "paypal"
    else:
        income_source = "you"

    application = {"applicant_id": linked_applicant_id(user_id), **paypal, **supplied}
    application = ScoreRequest.model_validate(application).model_dump(mode="json")
    inputs = []
    for field, value in application.items():
        if field == "applicant_id":
            continue
        source = ("paypal" if field in paypal else "you") if field != "monthly_income_inr" else income_source
        inputs.append({"field": field, "value": value, "source": source if value is not None else "not_available"})
    return application, inputs


@router.post("/score/linked", summary="PayScore for the linked PayPal account (PayPal history + applicant details)",
             response_model=None)
async def score_linked(details: LinkedDetails, request: Request, response: Response,
                       client: ClientDep = None) -> dict | JSONResponse:
    try:
        profile = await load_linked_profile(request, response, client)
    except LinkedProfileError as exc:
        return JSONResponse(status_code=exc.status, content={"error": exc.code})
    except PayPalError as exc:
        return JSONResponse(status_code=502, content={"error": "paypal_unavailable", "detail": str(exc)})
    if profile is None:
        return JSONResponse(status_code=401, content={"error": "paypal_not_linked",
                                                      "detail": "Log in with PayPal to score your own account."})
    try:
        application, inputs = build_application(linked_account_id(request) or "", profile, details)
    except NoIncomeEvidence as exc:
        return JSONResponse(status_code=422, content={"error": "no_income_evidence", "detail": str(exc)})
    try:
        result = request.app.state.scorer.score(ScoreRequest.model_validate(application))
    except ModelUnavailableError as exc:
        return JSONResponse(status_code=503, content={"error": "model_unavailable", "detail": str(exc)})
    record_score(application["applicant_id"], application, result)
    return {**result, "application": application, "inputs": inputs, "linked": True,
            "paypal_window": {"start": profile.get("window_start"), "end": profile.get("window_end")},
            # Payouts need a verified recipient; PayPal sign-in shares no email with this app
            "payout_available": False}

"""Affordability stress test.

This is an estimate of monthly cash flow under stated assumptions. It is not
regulated financial advice and it does not use a universal debt-service cap.
A result fails only when the estimated instalment, existing debt, and known
essential expenses already exceed income, or when the caller sets a cash buffer
the residual does not meet. Stress scenarios are explicit inputs.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from .finance import CalculationError, level_payment

router = APIRouter(tags=["affordability"])

DISCLAIMER = (
    "Estimate only. Not regulated financial advice, a lending decision, or a promise that a "
    "lender will offer these terms."
)

FREQUENCIES = {
    "monthly": 12,
    "quarterly": 4,
    "weekly": 52,
}

# Documented demo stresses. Callers can replace them. They are not regulatory tests.
DEFAULT_SCENARIOS = (
    {
        "name": "income_down_20",
        "income_factor": 0.8,
        "expense_factor": 1.0,
        "unexpected_cost_inr": 0.0,
        "description": "Monthly income is 20% lower than the figure used in the base case.",
    },
    {
        "name": "expenses_up_15",
        "income_factor": 1.0,
        "expense_factor": 1.15,
        "unexpected_cost_inr": 0.0,
        "description": "Essential expenses are 15% higher than the figure used in the base case.",
    },
    {
        "name": "unexpected_5000",
        "income_factor": 1.0,
        "expense_factor": 1.0,
        "unexpected_cost_inr": 5000.0,
        "description": "An unexpected cost of Rs 5,000 is added in the month.",
    },
)


class StressScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    income_factor: float = Field(default=1.0, ge=0, le=5)
    expense_factor: float = Field(default=1.0, ge=0, le=5)
    unexpected_cost_inr: float = Field(default=0, ge=0, le=1_000_000_000)
    description: str = Field(default="", max_length=300)


class AffordabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_amount_inr: float = Field(gt=0, le=1_000_000_000)
    monthly_income_inr: Optional[float] = Field(default=None, ge=0, le=1_000_000_000)
    essential_expenses_inr: Optional[float] = Field(default=None, ge=0, le=1_000_000_000)
    existing_monthly_debt_payments_inr: Optional[float] = Field(default=None, ge=0, le=1_000_000_000)
    tenure_months: Optional[int] = Field(default=None, ge=1, le=360)
    annual_interest_rate_pct: Optional[float] = Field(default=None, ge=0, le=500)
    upfront_fee_inr: float = Field(default=0, ge=0, le=1_000_000_000)
    upfront_fee_pct: Optional[float] = Field(default=None, ge=0, le=100)
    frequency: str = Field(default="monthly", pattern="^(monthly|quarterly|weekly)$")
    cash_buffer_inr: float = Field(default=0, ge=0, le=1_000_000_000)
    scenarios: Optional[list[StressScenario]] = None
    include_illustrative_rate: bool = False
    illustrative_annual_interest_rate_pct: float = Field(default=18, ge=0, le=500)


def _issue(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _periods(frequency: str, tenure_months: int) -> tuple[int, int, Optional[str]]:
    per_year = FREQUENCIES[frequency]
    if frequency == "monthly":
        return tenure_months, per_year, None
    if frequency == "quarterly":
        if tenure_months % 3 != 0:
            raise CalculationError("quarterly repayment needs a tenure that is a multiple of 3 months")
        return tenure_months // 3, per_year, None
    periods = int(round(tenure_months * 52 / 12))
    note = (
        f"Weekly periods are round({tenure_months} x 52/12) = {periods}. "
        "Income and expenses stay monthly, and the weekly instalment is converted with x 52/12."
    )
    if periods < 1:
        raise CalculationError("tenure is too short to produce a weekly instalment")
    return periods, per_year, note


def _monthly_equivalent(payment: float, frequency: str) -> float:
    if frequency == "monthly":
        return payment
    if frequency == "quarterly":
        return payment / 3.0
    return payment * 52.0 / 12.0


def _cashflow(
    income: float,
    essential: Optional[float],
    existing: float,
    monthly_payment: float,
    extra: float,
    income_factor: float,
    expense_factor: float,
) -> dict[str, Optional[float]]:
    stressed_income = income * income_factor
    debt_service = None if stressed_income <= 0 else (existing + monthly_payment) / stressed_income
    residual_before = stressed_income - existing - monthly_payment - extra
    if essential is None:
        return {
            "income_inr": round(stressed_income, 2),
            "essential_expenses_inr": None,
            "debt_service_ratio": None if debt_service is None else round(debt_service, 6),
            "residual_before_essential_expenses_inr": round(residual_before, 2),
            "post_payment_cashflow_inr": None,
            "disposable_income_before_new_instalment_inr": None,
        }
    stressed_essential = essential * expense_factor
    disposable = stressed_income - stressed_essential - existing
    post = disposable - monthly_payment - extra
    return {
        "income_inr": round(stressed_income, 2),
        "essential_expenses_inr": round(stressed_essential, 2),
        "debt_service_ratio": None if debt_service is None else round(debt_service, 6),
        "residual_before_essential_expenses_inr": round(residual_before - stressed_essential, 2),
        "post_payment_cashflow_inr": round(post, 2),
        "disposable_income_before_new_instalment_inr": round(disposable, 2),
    }


def assess(payload: dict[str, Any]) -> dict[str, Any]:
    """Pure assessment. Invalid numbers return a structured result instead of raising."""
    issues: list[dict[str, str]] = []
    amount = payload.get("requested_amount_inr")
    income = payload.get("monthly_income_inr")
    essential = payload.get("essential_expenses_inr")
    existing = payload.get("existing_monthly_debt_payments_inr")
    tenure = payload.get("tenure_months")
    rate_pct = payload.get("annual_interest_rate_pct")
    fee = payload.get("upfront_fee_inr") or 0
    fee_pct = payload.get("upfront_fee_pct")
    frequency = payload.get("frequency") or "monthly"
    buffer = payload.get("cash_buffer_inr") or 0
    include_illustrative = bool(payload.get("include_illustrative_rate"))
    illustrative_pct = payload.get("illustrative_annual_interest_rate_pct", 18)

    def bad_number(name: str, value: Any, minimum: float, maximum: float, integer: bool = False) -> bool:
        if value is None:
            return False
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            issues.append(_issue(name, "must be a finite number"))
            return True
        if integer and int(value) != value:
            issues.append(_issue(name, "must be a whole number"))
            return True
        if float(value) < minimum or float(value) > maximum:
            issues.append(_issue(name, f"must be between {minimum} and {maximum}"))
            return True
        return False

    bad_number("requested_amount_inr", amount, 0.01, 1_000_000_000)
    bad_number("monthly_income_inr", income, 0, 1_000_000_000)
    bad_number("essential_expenses_inr", essential, 0, 1_000_000_000)
    bad_number("existing_monthly_debt_payments_inr", existing, 0, 1_000_000_000)
    bad_number("tenure_months", tenure, 1, 360, integer=True)
    bad_number("annual_interest_rate_pct", rate_pct, 0, 500)
    bad_number("upfront_fee_inr", fee, 0, 1_000_000_000)
    bad_number("upfront_fee_pct", fee_pct, 0, 100)
    bad_number("cash_buffer_inr", buffer, 0, 1_000_000_000)
    if frequency not in FREQUENCIES:
        issues.append(_issue("frequency", "must be monthly, quarterly, or weekly"))
    if issues or amount is None:
        return {
            "status": "invalid",
            "estimate": True,
            "regulated_advice": False,
            "issues": issues,
            "reasons": ["One or more inputs are missing a usable number or are outside the supported range."],
            "assumptions": [],
            "scenarios": [],
            "disclaimer": DISCLAIMER,
        }

    missing = [
        name for name, value in (
            ("monthly_income_inr", income),
            ("existing_monthly_debt_payments_inr", existing),
            ("tenure_months", tenure),
            ("essential_expenses_inr", essential),
            ("annual_interest_rate_pct", rate_pct),
        ) if value is None
    ]
    assumptions = [
        "The instalment is a level reducing-balance payment on the gross requested amount.",
        "An upfront fee reduces what the borrower receives and is not added on top of the instalment.",
        "No universal debt-to-income cutoff is applied. The configured cash buffer defaults to Rs 0.",
        "Debt-service ratio is (existing monthly debt + monthly-equivalent new instalment) / income, and is omitted when income is zero.",
        DISCLAIMER,
    ]
    fee_warnings: list[str] = []
    upfront = float(fee)
    if fee_pct is not None:
        pct_amount = float(amount) * float(fee_pct) / 100.0
        if upfront and abs(upfront - pct_amount) > max(1.0, 0.01 * float(amount)):
            fee_warnings.append(
                "Upfront fee amount and percent disagree. The rupee amount was used."
            )
        elif not upfront:
            upfront = pct_amount
    if upfront >= float(amount):
        return {
            "status": "invalid",
            "estimate": True,
            "regulated_advice": False,
            "issues": [_issue("upfront_fee_inr", "fee must be smaller than the requested amount")],
            "reasons": ["Net proceeds would not be positive."],
            "assumptions": assumptions,
            "scenarios": [],
            "disclaimer": DISCLAIMER,
        }

    if tenure is None or frequency not in FREQUENCIES:
        return _incomplete(amount, missing, assumptions, fee_warnings, "Tenure or frequency is not usable.")

    try:
        n_periods, per_year, frequency_note = _periods(frequency, int(tenure))
    except CalculationError as exc:
        return {
            "status": "invalid",
            "estimate": True,
            "regulated_advice": False,
            "issues": [_issue("tenure_months", str(exc))],
            "reasons": [str(exc)],
            "assumptions": assumptions,
            "scenarios": [],
            "disclaimer": DISCLAIMER,
        }
    if frequency_note:
        assumptions.append(frequency_note)

    rate_mode = "stated_nominal"
    nominal_decimal = None
    if rate_pct is None:
        rate_mode = "zero_interest_lower_bound"
        nominal_decimal = 0.0
        assumptions.append(
            "No interest rate was supplied. The instalment is the zero-interest lower bound "
            "(amount divided by the number of periods). A priced loan would cost more."
        )
    else:
        nominal_decimal = float(rate_pct) / 100.0
        assumptions.append(
            "The supplied annual interest rate is treated as a nominal rate divided by the "
            "number of periods per year, not as an effective APR."
        )

    try:
        payment = level_payment(float(amount), nominal_decimal, n_periods, per_year)
    except CalculationError as exc:
        return {
            "status": "invalid",
            "estimate": True,
            "regulated_advice": False,
            "issues": [_issue("annual_interest_rate_pct", str(exc))],
            "reasons": [str(exc)],
            "assumptions": assumptions,
            "scenarios": [],
            "disclaimer": DISCLAIMER,
        }
    monthly_payment = _monthly_equivalent(payment, frequency)
    illustrative = None
    if include_illustrative and rate_pct is None:
        try:
            illus_payment = level_payment(float(amount), float(illustrative_pct) / 100.0, n_periods, per_year)
            illustrative = {
                "name": "illustrative_nominal_rate",
                "annual_interest_rate_pct": float(illustrative_pct),
                "installment_inr": round(illus_payment, 2),
                "monthly_equivalent_installment_inr": round(_monthly_equivalent(illus_payment, frequency), 2),
                "note": (
                    "Illustration only, using a nominal annual rate because none was supplied. "
                    "It is not a market quote and it is not the primary result."
                ),
            }
        except CalculationError:
            illustrative = None

    reasons: list[str] = []
    scenario_defs = payload.get("scenarios")
    if scenario_defs is None:
        scenario_defs = [dict(item) for item in DEFAULT_SCENARIOS]
        assumptions.append(
            "Default stress scenarios are income down 20%, essential expenses up 15%, and an unexpected Rs 5,000 cost."
        )
    else:
        assumptions.append("Caller-supplied stress scenarios replaced the defaults.")

    base = None
    scenarios_out: list[dict[str, Any]] = []
    if income is not None and existing is not None:
        base = _cashflow(float(income), None if essential is None else float(essential), float(existing), monthly_payment, 0.0, 1.0, 1.0)
        for raw in scenario_defs:
            name = str(raw.get("name") or "scenario")
            description = str(raw.get("description") or "")
            income_factor = float(raw.get("income_factor", 1))
            expense_factor = float(raw.get("expense_factor", 1))
            extra = float(raw.get("unexpected_cost_inr", 0))
            if essential is None and expense_factor != 1:
                scenarios_out.append({
                    "name": name,
                    "description": description,
                    "status": "skipped",
                    "reason": "Essential expenses were not provided, so an expense shock cannot be applied.",
                })
                continue
            row = _cashflow(float(income), None if essential is None else float(essential), float(existing), monthly_payment, extra, income_factor, expense_factor)
            focus = row["post_payment_cashflow_inr"]
            if focus is None:
                focus = row["residual_before_essential_expenses_inr"]
            row.update({
                "name": name,
                "description": description,
                "status": "below_buffer" if focus is not None and focus < float(buffer) else "within_buffer",
            })
            scenarios_out.append(row)
    else:
        reasons.append("Income or existing debt payments are missing, so cash flow was not judged.")

    status = "incomplete"
    if income is not None and existing is not None:
        focus_base = None if base is None else base["post_payment_cashflow_inr"]
        if essential is None:
            focus_base = None if base is None else base["residual_before_essential_expenses_inr"]
        if focus_base is not None and focus_base < float(buffer):
            status = "fail"
            reasons.append(
                "Base-case cash left is below the configured buffer even before any missing living costs are added."
                if essential is None else
                "Base-case cash left after income, essential expenses, existing debt, and the new instalment is below the configured buffer."
            )
        elif essential is None or rate_pct is None:
            status = "incomplete"
            if essential is None:
                reasons.append("Essential expenses were not provided, so this cannot be a pass or a warn.")
            if rate_pct is None and status != "fail":
                reasons.append("The instalment is only a zero-interest lower bound, so a priced loan was not passed.")
        else:
            stressed_fail = [
                row["name"] for row in scenarios_out
                if row.get("status") == "below_buffer"
            ]
            if stressed_fail:
                status = "warn"
                reasons.append(
                    "The base case stays at or above the buffer, but these stress scenarios do not: "
                    + ", ".join(stressed_fail) + "."
                )
            else:
                status = "pass"
                reasons.append(
                    "With the supplied income, essential expenses, existing debt, rate, tenure, and fee, "
                    "base and configured stress cash flows stay at or above the buffer of Rs "
                    f"{float(buffer):.2f}."
                )
    if income == 0 and monthly_payment > 0 and status == "fail":
        reasons.append("Income is zero, so the debt-service ratio is undefined and the instalment is uncovered.")

    return {
        "status": status,
        "estimate": True,
        "regulated_advice": False,
        "requested_amount_inr": float(amount),
        "frequency": frequency,
        "tenure_months": int(tenure),
        "n_periods": n_periods,
        "periods_per_year": per_year,
        "annual_interest_rate_pct": None if rate_pct is None else float(rate_pct),
        "rate_mode": rate_mode,
        "installment_inr": round(payment, 2),
        "monthly_equivalent_installment_inr": round(monthly_payment, 2),
        "upfront_fee_inr": round(upfront, 2),
        "net_proceeds_inr": round(float(amount) - upfront, 2),
        "cash_buffer_inr": float(buffer),
        "base": base,
        "debt_service_ratio": None if base is None else base["debt_service_ratio"],
        "disposable_income_inr": None if base is None else base["disposable_income_before_new_instalment_inr"],
        "post_payment_cashflow_inr": None if base is None else base["post_payment_cashflow_inr"],
        "residual_before_essential_expenses_inr": None if base is None else base["residual_before_essential_expenses_inr"],
        "scenarios": scenarios_out,
        "illustrative_scenario": illustrative,
        "missing_inputs": missing,
        "reasons": reasons,
        "fee_warnings": fee_warnings,
        "assumptions": assumptions,
        "issues": [],
        "formula": "level payment = P * i * (1+i)^n / ((1+i)^n - 1), i = nominal annual rate / periods per year; i = 0 uses P / n",
        "disclaimer": DISCLAIMER,
    }


def _incomplete(amount: float, missing: list[str], assumptions: list[str], fee_warnings: list[str], reason: str) -> dict[str, Any]:
    return {
        "status": "incomplete",
        "estimate": True,
        "regulated_advice": False,
        "requested_amount_inr": float(amount),
        "missing_inputs": missing,
        "reasons": [reason],
        "fee_warnings": fee_warnings,
        "assumptions": assumptions,
        "scenarios": [],
        "issues": [],
        "disclaimer": DISCLAIMER,
    }


@router.post("/affordability", summary="Estimate instalment burden and stressed cash flow")
def affordability(req: AffordabilityRequest) -> dict[str, Any]:
    return assess(req.model_dump())

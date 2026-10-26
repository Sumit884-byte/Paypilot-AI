"""Normalised input schema (the contract between PayPal/mock data and the model).

Everything the model needs is expressed here, in INR. The model never sees raw
PayPal payloads: Person 2 maps PayPal data into this schema (see
docs/FEATURE_MAPPING.md).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmploymentType(str, Enum):
    salaried = "salaried"
    self_employed = "self_employed"
    freelancer = "freelancer"
    business_owner = "business_owner"
    other = "other"


Money = Annotated[float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)]
Ratio = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]

EXAMPLE_REQUEST = {
    "applicant_id": "PSC-EXAMPLE-001",
    "age_years": 34,
    "employment_type": "self_employed",
    "business_age_months": 38,
    "monthly_income_inr": 55000,
    "avg_monthly_revenue_inr": 140000,
    "avg_monthly_expenses_inr": 84000,
    "revenue_volatility_cv": 0.08,
    "txn_count_90d": 95,
    "avg_txn_value_inr": 4500,
    "active_months_12m": 12,
    "refund_rate_90d": 0.02,
    "dispute_rate_12m": 0.0,
    "existing_monthly_debt_payments_inr": 6000,
    "prior_defaults_count": 0,
    "requested_loan_amount_inr": 400000,
    "requested_term_months": 18,
}


class ScoreRequest(BaseModel):
    """Normalised model input. Optional fields may be omitted or null."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [EXAMPLE_REQUEST]})

    # --- required core fields ---
    applicant_id: str = Field(
        ..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$",
        description="Pseudonymous ID (letters, digits, '_' or '-'). Never use a real name/email.",
    )
    age_years: int = Field(..., ge=18, le=100, description="Age in whole years.")
    employment_type: EmploymentType
    monthly_income_inr: Money = Field(
        ..., description="Self-declared total monthly personal income, all sources (INR)."
    )
    requested_loan_amount_inr: float = Field(..., gt=0, le=1_000_000_000, allow_inf_nan=False)
    requested_term_months: int = Field(..., ge=1, le=360)

    # --- optional fields (null/omitted -> treated as missing by the model) ---
    business_age_months: Optional[int] = Field(None, ge=0, le=1200)
    avg_monthly_revenue_inr: Optional[Money] = Field(None, description="Mean net revenue/month, last 6 months.")
    avg_monthly_expenses_inr: Optional[Money] = Field(None, description="Mean expenses/month, last 6 months.")
    revenue_volatility_cv: Optional[Annotated[float, Field(ge=0, le=10, allow_inf_nan=False)]] = Field(
        None, description="Std-dev / mean of monthly net revenue over the last 6 months."
    )
    txn_count_90d: Optional[int] = Field(None, ge=0, le=1_000_000, description="Completed sales, last 90 days.")
    avg_txn_value_inr: Optional[Money] = Field(None, description="Mean sale value, last 90 days.")
    active_months_12m: Optional[int] = Field(None, ge=0, le=12, description="Months with >=1 sale, last 12.")
    refund_rate_90d: Optional[Ratio] = Field(None, description="Refunds / sales (count), last 90 days.")
    dispute_rate_12m: Optional[Ratio] = Field(None, description="Disputes / sales (count), last 12 months.")
    existing_monthly_debt_payments_inr: Optional[Money] = None
    prior_defaults_count: Optional[int] = Field(None, ge=0, le=50)


class ModelInfo(BaseModel):
    name: str
    version: str
    type: str = Field(description="'lightgbm' or 'development_fallback'")
    is_trained_model: bool
    training_data: Optional[str] = None


class ScoreRange(BaseModel):
    min: int = 300
    max: int = 850


class ScoreResponse(BaseModel):
    applicant_id: str
    score: int = Field(description="PayScore, 300-850 (higher = lower risk).")
    score_range: ScoreRange
    risk_band: str = Field(description="low | moderate | elevated | high")
    probability_of_default: float = Field(
        description="Estimated default probability. For the development fallback this is a heuristic, not a calibrated model output."
    )
    model: ModelInfo
    evaluation_caveat: str
    missing_inputs: list[str] = Field(description="Optional inputs that were absent (treated as missing).")
    disbursement_eligible: bool = Field(description="Demo policy: true when score is at least 650.")
    approved_amount_limit_inr: float = Field(description="Demo disbursement ceiling recorded for this applicant (INR).")
    drivers: list[dict] = Field(default_factory=list, description="Heuristic (not SHAP) reasons for the demo UI.")
    to_move_up: str = Field(default="", description="Suggested action to improve the demo score.")


class ErrorDetail(BaseModel):
    field: str
    message: str
    type: str


class ErrorResponse(BaseModel):
    error: str
    detail: list[ErrorDetail] | str

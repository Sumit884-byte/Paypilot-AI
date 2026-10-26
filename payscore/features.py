"""Feature engineering shared by training and inference (single code path)."""

from __future__ import annotations

import numpy as np
import pandas as pd

EMPLOYMENT_CATEGORIES = ["salaried", "self_employed", "freelancer", "business_owner", "other"]
EMPLOYMENT_CODE = {name: i for i, name in enumerate(EMPLOYMENT_CATEGORIES)}

NUMERIC_INPUTS = [
    "age_years", "business_age_months", "monthly_income_inr", "avg_monthly_revenue_inr",
    "avg_monthly_expenses_inr", "revenue_volatility_cv", "txn_count_90d", "avg_txn_value_inr",
    "active_months_12m", "refund_rate_90d", "dispute_rate_12m",
    "existing_monthly_debt_payments_inr", "prior_defaults_count",
    "requested_loan_amount_inr", "requested_term_months",
]
DERIVED = ["debt_to_income", "expense_ratio", "net_margin", "loan_to_annual_revenue", "installment_to_income"]
CATEGORICAL = ["employment_type_code"]
FEATURE_NAMES = NUMERIC_INPUTS + DERIVED + CATEGORICAL
INPUT_COLUMNS = NUMERIC_INPUTS + ["employment_type"]


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """num/den; NaN when den is missing or <= 0 (no inf values)."""
    return num / den.where(den > 0)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Normalised records -> model feature matrix. Missing values stay NaN
    (LightGBM handles NaN natively; no statistics are fitted here, so no leakage)."""
    out = pd.DataFrame(index=df.index)
    for col in NUMERIC_INPUTS:
        out[col] = pd.to_numeric(df[col], errors="coerce").astype("float64") if col in df else np.nan

    emp = df["employment_type"] if "employment_type" in df else pd.Series(np.nan, index=df.index)
    out["debt_to_income"] = _ratio(out["existing_monthly_debt_payments_inr"], out["monthly_income_inr"])
    out["expense_ratio"] = _ratio(out["avg_monthly_expenses_inr"], out["avg_monthly_revenue_inr"])
    out["net_margin"] = _ratio(
        out["avg_monthly_revenue_inr"] - out["avg_monthly_expenses_inr"], out["avg_monthly_revenue_inr"]
    )
    out["loan_to_annual_revenue"] = _ratio(out["requested_loan_amount_inr"], out["avg_monthly_revenue_inr"] * 12)
    # Rough instalment (no interest): amount / term, relative to monthly income.
    out["installment_to_income"] = _ratio(
        _ratio(out["requested_loan_amount_inr"], out["requested_term_months"]), out["monthly_income_inr"]
    )
    out["employment_type_code"] = emp.map(EMPLOYMENT_CODE).astype("float64")
    return out[FEATURE_NAMES].replace([np.inf, -np.inf], np.nan)

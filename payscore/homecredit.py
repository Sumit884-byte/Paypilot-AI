"""Optional loader mapping the Kaggle *Home Credit Default Risk* ``application_train.csv``
onto the normalised schema. This repo does NOT download or redistribute that data.

Access: needs a Kaggle account and acceptance of the competition rules (check them
for permitted use). Place the file locally and pass its path to ``payscore.train``.

Only a handful of normalised fields have a Home Credit counterpart; the rest stay NaN
(revenue, volatility, transaction metrics, refunds/disputes, debt payments, defaults).
Amounts are in the dataset's own currency units and are NOT converted to INR.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import INPUT_COLUMNS

REQUIRED_COLUMNS = ["TARGET", "DAYS_BIRTH", "AMT_INCOME_TOTAL", "AMT_CREDIT", "AMT_ANNUITY",
                    "NAME_INCOME_TYPE", "DAYS_EMPLOYED"]
_EMPLOYMENT_MAP = {"Working": "salaried", "State servant": "salaried", "Commercial associate": "salaried",
                   "Businessman": "business_owner"}
_DAYS_EMPLOYED_SENTINEL = 365243  # Home Credit's placeholder for "not employed"


def load_homecredit(path: str, nrows: int | None = None) -> pd.DataFrame:
    raw = pd.read_csv(path, nrows=nrows)
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"{path} is missing expected Home Credit columns: {missing}")
    days_emp = raw["DAYS_EMPLOYED"].where(raw["DAYS_EMPLOYED"] != _DAYS_EMPLOYED_SENTINEL)
    term = (raw["AMT_CREDIT"] / raw["AMT_ANNUITY"].where(raw["AMT_ANNUITY"] > 0)).round().clip(6, 360)
    ids = ("HC-" + raw["SK_ID_CURR"].astype(str)) if "SK_ID_CURR" in raw else raw.index.astype(str)
    df = pd.DataFrame(np.nan, index=raw.index, columns=["applicant_id", *INPUT_COLUMNS, "TARGET"])
    df["applicant_id"] = ids
    df["age_years"] = (-raw["DAYS_BIRTH"] / 365.25).round()
    df["employment_type"] = raw["NAME_INCOME_TYPE"].map(_EMPLOYMENT_MAP).fillna("other")
    df["business_age_months"] = (-days_emp / 30.4375).round().clip(lower=0)  # employment length used as proxy
    df["monthly_income_inr"] = raw["AMT_INCOME_TOTAL"] / 12.0
    df["requested_loan_amount_inr"] = raw["AMT_CREDIT"]
    df["requested_term_months"] = term
    df["TARGET"] = raw["TARGET"].astype(int)
    return df.replace([np.inf, -np.inf], np.nan)

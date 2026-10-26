"""SYNTHETIC development dataset generator.

NOT real data. Rows are drawn from invented distributions and labelled with a
hand-written risk process plus noise, so the pipeline can be exercised end to
end. Metrics measured on this data say nothing about real-world performance
and must never be presented as Home Credit (or PayPal) benchmark results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import EMPLOYMENT_CATEGORIES, INPUT_COLUMNS

TARGET_RATE = 0.08  # mimics the ~8% default rate of Home Credit; purely illustrative
LABEL_NOISE = 1.0   # std-dev of unobserved-risk noise; arbitrary, NOT tuned to hit any AUC


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def generate(n_rows: int = 30_000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = n_rows
    emp = rng.choice(EMPLOYMENT_CATEGORIES, size=n, p=[0.30, 0.30, 0.20, 0.15, 0.05])
    is_biz = np.isin(emp, ["self_employed", "freelancer", "business_owner"])

    age = np.clip(rng.normal(36, 9, n), 21, 65).round()
    biz_age = np.clip(rng.exponential(48, n), 1, 300).round()
    revenue = rng.lognormal(np.log(80_000), 0.7, n)
    expense_ratio = np.clip(rng.beta(5, 3, n), 0.3, 1.2)
    profit = np.maximum(revenue * (1 - expense_ratio), 0)
    income = np.where(
        is_biz,
        np.maximum(profit * rng.uniform(0.5, 0.9, n) + rng.normal(5_000, 3_000, n), 3_000),
        rng.lognormal(np.log(45_000), 0.5, n),
    )
    cv = np.clip(rng.lognormal(np.log(0.35), 0.5, n), 0.02, 3.0)
    avg_ticket = rng.lognormal(np.log(2_500), 0.8, n)
    txn90 = rng.poisson(np.clip(3 * revenue / avg_ticket, 1, 3_000))
    active = np.clip(np.minimum(12, biz_age) - rng.binomial(12, np.clip(cv * 0.15, 0, 0.9)), 0, 12)
    refund = np.clip(rng.beta(1.5, 30, n), 0, 1)
    dispute = np.clip(rng.beta(1, 150, n), 0, 1)
    debt = np.where(rng.random(n) < 0.65, income * rng.beta(2, 6, n), 0.0)
    defaults = rng.poisson(0.15, n)
    amount = rng.lognormal(np.log(300_000), 0.8, n)
    term = rng.choice([6, 12, 18, 24, 36, 48, 60], size=n)

    dti = debt / income
    inst = (amount / term) / income
    z = (
        2.0 * np.clip(dti, 0, 1.5) + 1.8 * np.clip(inst, 0, 2) + 1.2 * np.clip(cv, 0, 2)
        + 0.8 * (expense_ratio - 0.67) + 6.0 * refund + 25.0 * dispute + 0.7 * defaults
        - 0.01 * np.minimum(biz_age, 120) - 0.5 * (np.log(income) - 10.5) - 0.02 * (age - 36)
        + 1.0 * ((cv > 0.8) & (inst > 0.5))
        + rng.normal(0, LABEL_NOISE, n)
    )
    # Calibrate the intercept (bisection) so the mean default probability is TARGET_RATE.
    lo, hi = -15.0, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _sigmoid(z + mid).mean() < TARGET_RATE else (lo, mid)
    p = _sigmoid(z + (lo + hi) / 2)
    target = (rng.random(n) < p).astype(int)

    df = pd.DataFrame({
        "applicant_id": [f"SYN-{i:06d}" for i in range(n)],
        "age_years": age.astype(int),
        "employment_type": emp,
        "business_age_months": np.where(is_biz, biz_age, np.nan),
        "monthly_income_inr": income.round(0),
        "avg_monthly_revenue_inr": revenue.round(0),
        "avg_monthly_expenses_inr": (revenue * expense_ratio).round(0),
        "revenue_volatility_cv": cv.round(4),
        "txn_count_90d": txn90.astype(float),
        "avg_txn_value_inr": avg_ticket.round(0),
        "active_months_12m": active.astype(float),
        "refund_rate_90d": refund.round(4),
        "dispute_rate_12m": dispute.round(4),
        "existing_monthly_debt_payments_inr": debt.round(0),
        "prior_defaults_count": defaults.astype(float),
        "requested_loan_amount_inr": amount.round(0),
        "requested_term_months": term,
    })
    # Missingness: salaried/other mostly lack business metrics; plus random gaps.
    biz_cols = ["avg_monthly_revenue_inr", "avg_monthly_expenses_inr", "revenue_volatility_cv",
                "txn_count_90d", "avg_txn_value_inr", "active_months_12m", "refund_rate_90d", "dispute_rate_12m"]
    structural = (~is_biz) & (rng.random(n) < 0.7)
    df.loc[structural, biz_cols] = np.nan
    for col in ["revenue_volatility_cv", "dispute_rate_12m", "prior_defaults_count",
                "existing_monthly_debt_payments_inr", "refund_rate_90d"]:
        df.loc[rng.random(n) < 0.10, col] = np.nan
    df["TARGET"] = target
    return df[["applicant_id", *INPUT_COLUMNS, "TARGET"]]

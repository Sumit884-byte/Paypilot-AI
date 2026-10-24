"""Reference derivation: synthetic transaction history -> normalised model-input metrics.

This is the reference implementation of the 'derived' rows in docs/FEATURE_MAPPING.md.
Person 2 can port the same rules to whatever real transaction source is verified.
Windows are anchored to ``as_of`` (exclusive): the last 6 / 12 complete calendar
months and the last 90 days.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Any, Optional

Txn = dict[str, Any]


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def months_before(as_of: date, n: int) -> list[str]:
    """The n complete calendar months before ``as_of`` (oldest first)."""
    y, m = as_of.year, as_of.month
    keys = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        keys.append(f"{y:04d}-{m:02d}")
    return keys[::-1]


def _d(t: Txn) -> date:
    return date.fromisoformat(t["date"])


def monthly_summary(txns: list[Txn], months: list[str]) -> list[dict[str, Any]]:
    rows = []
    for mk in months:
        in_m = [t for t in txns if month_key(_d(t)) == mk]
        sales = [t for t in in_m if t["type"] == "sale"]
        refunds = [t for t in in_m if t["type"] == "refund"]
        exp = [t for t in in_m if t["type"] == "expense"]
        rev, ref = sum(t["amount_inr"] for t in sales), sum(t["amount_inr"] for t in refunds)
        rows.append({"month": mk, "sales_inr": round(rev, 2), "refunds_inr": round(ref, 2),
                     "net_revenue_inr": round(rev - ref, 2),
                     "expenses_inr": round(sum(t["amount_inr"] for t in exp), 2), "sale_count": len(sales)})
    return rows


def derive_metrics(txns: list[Txn], as_of: date) -> dict[str, Optional[float]]:
    first = min(_d(t) for t in txns)
    window = [m for m in months_before(as_of, 6) if m >= month_key(first)]
    summ = monthly_summary(txns, window)
    net = [r["net_revenue_inr"] for r in summ]
    mean_net = statistics.fmean(net)
    cv = round(statistics.pstdev(net) / mean_net, 4) if len(net) >= 3 and mean_net > 0 else None

    since90 = as_of - timedelta(days=90)
    s90 = [t for t in txns if t["type"] == "sale" and since90 <= _d(t) < as_of]
    r90 = [t for t in txns if t["type"] == "refund" and since90 <= _d(t) < as_of]
    months12 = set(months_before(as_of, 12))
    s12 = [t for t in txns if t["type"] == "sale" and month_key(_d(t)) in months12]
    d12 = [t for t in txns if t["type"] == "dispute" and month_key(_d(t)) in months12]
    return {
        "avg_monthly_revenue_inr": round(mean_net, 2),
        "avg_monthly_expenses_inr": round(statistics.fmean(r["expenses_inr"] for r in summ), 2),
        "revenue_volatility_cv": cv,
        "txn_count_90d": len(s90),
        "avg_txn_value_inr": round(statistics.fmean(t["amount_inr"] for t in s90), 2) if s90 else None,
        "active_months_12m": len({month_key(_d(t)) for t in s12}),
        "refund_rate_90d": round(min(len(r90) / len(s90), 1.0), 4) if s90 else None,
        "dispute_rate_12m": round(min(len(d12) / len(s12), 1.0), 4) if s12 else None,
    }


def months_between(start: date, as_of: date) -> int:
    return (as_of.year - start.year) * 12 + (as_of.month - start.month)

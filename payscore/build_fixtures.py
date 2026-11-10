"""Deterministically (re)generate the three fictional persona fixtures.

    python -m payscore.build_fixtures
All names, IDs and transactions are invented. Metrics in ``model_input`` are
computed from the generated transactions by payscore.derive (so they stay consistent).
"""

from __future__ import annotations

import calendar
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from .derive import derive_metrics, monthly_summary, months_before, months_between
from .export_schema import persona_schema
from .schema import ScoreRequest

AS_OF = date(2026, 10, 1)
OUT_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "personas"

PERSONAS: list[dict[str, Any]] = [
    {
        "file": "priya.json", "tag": "PRIYA", "seed": 101, "persona_id": "PSC-PRIYA-001", "display_name": "Priya Nair (fictional)",
        "profile": {
            "city": "Kochi", "business_type": "Handmade jewellery and home decor",
            "description": "Priya runs a three-year-old online shop selling handmade silk-thread jewellery and decor to buyers in India and abroad, paid through PayPal. Demand is steady and growing.",
            "business_start_date": "2023-08-01", "age_years": 34, "employment_type": "self_employed",
            "income_note": "Monthly drawings from the business (~its monthly profit); no other income.",
        },
        "scenario": {
            "headline": "Festive-season inventory financing",
            "loan_purpose": "Buy silk thread, packaging and gold-plated findings ahead of Diwali and Christmas orders",
            "requested_amount_inr": 400000, "requested_term_months": 18,
            "narrative": "Priya expects festive orders to rise sharply but must pay suppliers up front. She wants a short working-capital loan repaid from the following months' sales. Her revenue is stable with few refunds, making her a strong, steady-income case.",
        },
        "months": 12, "gross": [128, 131, 152, 139, 126, 130, 133, 137, 141, 146, 150, 158], "ticket": 4500,
        "refund_prob": 0.02, "disputes": [], "expense_ratio": 0.58,
        "expense_cats": ["supplier_materials", "shipping", "packaging", "marketplace_fees", "software_subscriptions"],
        "sale_cats": ["international_buyer", "domestic_buyer"],
        "inputs": {
            "monthly_income_inr": 55000, "existing_monthly_debt_payments_inr": 6000, "prior_defaults_count": 0,
            "avg_client_turnaround_days": 12.0, "late_payment_rate_90d": 0.01, "top_client_revenue_share": 0.18,
        },
    },
    {
        "file": "arjun.json", "tag": "ARJUN", "seed": 202, "persona_id": "PSC-ARJUN-002", "display_name": "Arjun Mehta (fictional)",
        "profile": {
            "city": "Bengaluru", "business_type": "Freelance UX design",
            "description": "Arjun is a freelance UX designer invoicing overseas clients through PayPal. Project-based work makes his monthly income lumpy, but he has been active for over two years.",
            "business_start_date": "2024-08-01", "age_years": 29, "employment_type": "freelancer",
            "income_note": "Average personal withdrawals; the remainder of profit is kept for taxes and gaps between projects.",
        },
        "scenario": {
            "headline": "Equipment upgrade with income-gap cushion",
            "loan_purpose": "Replace workstation and monitors, and keep a few months of runway between projects",
            "requested_amount_inr": 250000, "requested_term_months": 12,
            "narrative": "Arjun's earnings swing from slow months to big project payments. A fixed monthly instalment needs checking against that volatility, so he is a case that shows why revenue stability matters.",
        },
        "months": 12, "gross": [95, 40, 180, 60, 210, 85, 140, 55, 190, 70, 160, 100], "ticket": 18000,
        "refund_prob": 0.01, "disputes": [], "expense_ratio": 0.35,
        "expense_cats": ["software_subscriptions", "coworking", "internet_phone", "hardware", "professional_fees"],
        "sale_cats": ["international_client", "international_client", "domestic_client"],
        "inputs": {
            "monthly_income_inr": 65000, "existing_monthly_debt_payments_inr": 8000, "prior_defaults_count": 0,
            "avg_client_turnaround_days": 26.0, "late_payment_rate_90d": 0.12, "top_client_revenue_share": 0.42,
        },
    },
    {
        "file": "rohan.json", "tag": "ROHAN", "seed": 303, "persona_id": "PSC-ROHAN-003", "display_name": "Rohan Kulkarni (fictional)",
        "profile": {
            "city": "Nagpur", "business_type": "Online tea and spice reseller",
            "description": "Rohan started reselling regional teas and spices online seven months ago. Sales are growing quickly from a small base, with thin margins, a few refunds and one payment dispute.",
            "business_start_date": "2026-03-01", "age_years": 24, "employment_type": "business_owner",
            "income_note": "About Rs 14,000 from part-time work at a family shop plus business profit; self-declared.",
        },
        "scenario": {
            "headline": "Large expansion loan on a thin track record",
            "loan_purpose": "Rent a small warehouse and buy bulk stock to double sales volume",
            "requested_amount_inr": 600000, "requested_term_months": 36,
            "narrative": "Rohan wants a loan far larger than his current monthly profit comfortably supports, with a short history, informal buy-now-pay-later debt and one earlier missed instalment. This is a thin-file case where any offer should be cautious.",
        },
        "months": 7, "gross": [30, 41, 48, 57, 62, 70, 72], "ticket": 1100,
        "refund_prob": 0.07, "disputes": [(5, 1100)], "expense_ratio": 0.90,
        "expense_cats": ["inventory", "shipping", "packaging", "marketplace_fees", "ads"],
        "sale_cats": ["domestic_buyer"],
        "inputs": {
            "monthly_income_inr": 17500, "existing_monthly_debt_payments_inr": 9500, "prior_defaults_count": 1,
            "avg_client_turnaround_days": 38.0, "late_payment_rate_90d": 0.32, "top_client_revenue_share": 0.65,
        },
    },
]


def _day(rng: np.random.Generator, month_key: str) -> date:
    y, m = map(int, month_key.split("-"))
    return date(y, m, int(rng.integers(1, calendar.monthrange(y, m)[1] + 1)))


def build_transactions(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rng = np.random.default_rng(spec["seed"])
    months = months_before(AS_OF, spec["months"])
    txns: list[dict[str, Any]] = []

    def add(d: date, typ: str, amount: int, cat: str, direction: str, status: str = "completed") -> None:
        txns.append({"date": d.isoformat(), "type": typ, "direction": direction, "amount_inr": int(amount),
                     "category": cat, "status": status})

    for i, mk in enumerate(months):
        target = int(spec["gross"][i] * 1000)
        n = max(3, round(target / spec["ticket"]))
        w = rng.lognormal(0, 0.5, n)
        amounts = np.maximum((w / w.sum() * target / 10).round() * 10, 100).astype(int)
        amounts[0] += target - int(amounts.sum())  # make the month total exact
        y, m = map(int, mk.split("-"))
        for a in amounts:
            d = _day(rng, mk)
            add(d, "sale", int(a), str(rng.choice(spec["sale_cats"])), "inflow")
            if rng.random() < spec["refund_prob"]:
                last = calendar.monthrange(y, m)[1]
                rd = date(y, m, min(d.day + int(rng.integers(1, 6)), last))
                add(rd, "refund", int(a), "customer_refund", "outflow")
        for idx, amt in spec["disputes"]:
            if idx == i:
                add(_day(rng, mk), "dispute", amt, "buyer_dispute", "outflow", status="open")
        exp_total = int(target * spec["expense_ratio"] * rng.uniform(0.95, 1.05))
        k = len(spec["expense_cats"])
        shares = rng.dirichlet(np.ones(k) * 4)
        parts = (shares * exp_total).round().astype(int)
        parts[0] += exp_total - int(parts.sum())
        for cat, amt in zip(spec["expense_cats"], parts, strict=False):
            add(_day(rng, mk), "expense", max(int(amt), 1), cat, "outflow")

    txns.sort(key=lambda t: (t["date"], t["type"], t["amount_inr"]))
    for n, t in enumerate(txns, 1):
        t["txn_id"] = f"SYN-{spec['tag']}-{n:05d}"
    return [{k: t[k] for k in ("txn_id", "date", "type", "direction", "amount_inr", "category", "status")} for t in txns]


def build_persona(spec: dict[str, Any]) -> dict[str, Any]:
    txns = build_transactions(spec)
    prof, scen = spec["profile"], spec["scenario"]
    derived = derive_metrics(txns, AS_OF)
    model_input = {
        "applicant_id": spec["persona_id"], "age_years": prof["age_years"],
        "employment_type": prof["employment_type"],
        "business_age_months": months_between(date.fromisoformat(prof["business_start_date"]), AS_OF),
        **spec["inputs"], **derived,
        "requested_loan_amount_inr": scen["requested_amount_inr"], "requested_term_months": scen["requested_term_months"],
    }
    ScoreRequest.model_validate(model_input)  # fail early if not a valid /score body
    return {
        "schema_version": "1.0", "persona_id": spec["persona_id"], "display_name": spec["display_name"],
        "synthetic": True, "currency": "INR", "as_of_date": AS_OF.isoformat(),
        "profile": prof, "scenario": scen,
        "monthly_summary": monthly_summary(txns, months_before(AS_OF, spec["months"])),
        "transactions": txns, "model_input": model_input,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    validator = Draft202012Validator(persona_schema())
    for spec in PERSONAS:
        persona = build_persona(spec)
        errors = list(validator.iter_errors(persona))
        if errors:
            raise SystemExit(f"{spec['file']} fails schema: {errors[0].message}")
        (OUT_DIR / spec["file"]).write_text(json.dumps(persona, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {spec['file']}: {len(persona['transactions'])} txns; input={persona['model_input']}")


if __name__ == "__main__":
    main()

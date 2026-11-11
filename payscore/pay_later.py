"""Compare a purchase loan offer with PayPal Pay Later on the same purchase.

Pay Later terms are PayPal's published consumer terms, not a quote. PayPal does not publish a pricing API:
the actual offer, APR, and approval are decided at checkout. Only the US terms are modelled. PayPal does not
offer Pay Later in India, so an INR comparison reports it as unavailable instead of inventing terms.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from .finance import level_payment
from .offer_analysis import analyse, manual_fields

router = APIRouter(tags=["offer-guard"])

TERMS_SOURCE = "https://developer.paypal.com/docs/checkout/pay-later/us/"
TERMS_RETRIEVED = "2026-11-09"
PAY_LATER_MARKETS = {"US", "AU", "CA", "FR", "DE", "IT", "ES", "GB"}
MARKET_CURRENCY = {"US": "USD", "IN": "INR"}

US_PAY_IN_4 = {"min": 10.0, "max": 2000.0, "payments": 4}
US_PAY_MONTHLY = {"min": 49.0, "max": 10_000.0, "terms_months": (3, 6, 12, 24), "apr_pct": (9.99, 35.99)}

DISCLAIMER = (
    "Sandbox comparison. PayPal Pay Later terms are PayPal's published terms, not an offer. Eligibility, APR, and "
    "term are decided by PayPal (Pay Monthly lender: WebBank) at checkout and are subject to credit approval."
)


class PayLaterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purchase_amount: float = Field(gt=0, le=1_000_000_000)
    market: str = Field(default="IN", min_length=2, max_length=2, description="ISO country of the buyer")
    advertised_apr_pct: float = Field(ge=0, le=100)
    processing_fee_pct: float = Field(ge=0, le=50, default=0)
    term_months: int = Field(ge=1, le=360)
    lender_name: str = Field(default="Unknown lender", max_length=120)


def _money(value: float) -> float:
    return round(value, 2)


def _loan_option(req: PayLaterRequest) -> dict[str, Any]:
    result = analyse(manual_fields({
        "advertised_apr_pct": req.advertised_apr_pct,
        "processing_fee_pct": req.processing_fee_pct,
        "principal_inr": req.purchase_amount,
        "term_months": req.term_months,
        "lender_name": req.lender_name,
    }), input_mode="manual")
    calc = result["calculation"]
    instalment = calc.get("installment_inr")
    fees = calc.get("upfront_fees_inr") or 0.0
    option: dict[str, Any] = {
        "id": "loan_offer",
        "provider": req.lender_name,
        "name": f"{req.lender_name} loan",
        "eligible": instalment is not None,
        "ineligible_reason": None if instalment is not None else "The offer terms could not be priced.",
        "payments": req.term_months,
        "interval": "monthly",
        "term_months": req.term_months,
        "instalment": instalment,
        "upfront_fees": fees,
        "effective_annual_pct": calc.get("effective_annual_pct_display"),
        "apr_basis": "Offer Guard monthly IRR on net proceeds, as effective annual cost",
    }
    if instalment is not None:
        # A fee deducted from the loan has to be paid from the buyer's own cash to complete the purchase
        total = instalment * req.term_months + fees
        option["total_paid"] = _money(total)
        option["cost_of_credit"] = _money(total - req.purchase_amount)
        option["cost_of_credit_best"] = option["cost_of_credit"]
    return option


def _pay_in_4(amount: float) -> dict[str, Any]:
    eligible = US_PAY_IN_4["min"] <= amount <= US_PAY_IN_4["max"]
    return {
        "id": "paypal_pay_in_4",
        "provider": "PayPal",
        "name": "PayPal Pay in 4",
        "eligible": eligible,
        "ineligible_reason": None if eligible else (
            f"Pay in 4 covers purchases of {US_PAY_IN_4['min']:.0f}–{US_PAY_IN_4['max']:.0f} USD."),
        "payments": 4,
        "interval": "every 2 weeks, first at purchase",
        "term_months": None,
        "instalment": _money(amount / 4),
        "upfront_fees": 0.0,
        "effective_annual_pct": 0.0,
        "apr_basis": "Interest-free",
        "total_paid": _money(amount),
        "cost_of_credit": 0.0,
        "cost_of_credit_best": 0.0,
    }


def _nearest_term(months: int) -> int:
    return min(US_PAY_MONTHLY["terms_months"], key=lambda t: (abs(t - months), t))


def _pay_monthly(amount: float, months: int) -> dict[str, Any]:
    term = _nearest_term(months)
    low, high = US_PAY_MONTHLY["apr_pct"]
    eligible = US_PAY_MONTHLY["min"] <= amount <= US_PAY_MONTHLY["max"]
    worst = level_payment(amount, high / 100.0, term, 12)
    best = level_payment(amount, low / 100.0, term, 12)
    return {
        "id": "paypal_pay_monthly",
        "provider": "PayPal (lender: WebBank)",
        "name": "PayPal Pay Monthly",
        "eligible": eligible,
        "ineligible_reason": None if eligible else (
            f"Pay Monthly covers purchases of {US_PAY_MONTHLY['min']:.0f}–{US_PAY_MONTHLY['max']:,.0f} USD."),
        "payments": term,
        "interval": "monthly",
        "term_months": term,
        "term_note": None if term == months else f"Pay Monthly offers 3, 6, 12, or 24 months; {term} is closest to {months}.",
        "instalment": _money(worst),
        "instalment_best": _money(best),
        "upfront_fees": 0.0,
        # PayPal quotes a nominal APR; effective annual cost compounds it monthly
        "effective_annual_pct": round(((1 + high / 1200) ** 12 - 1) * 100, 2),
        "effective_annual_pct_best": round(((1 + low / 1200) ** 12 - 1) * 100, 2),
        "apr_pct_range": [low, high],
        "apr_basis": f"Fixed APR {low}–{high}% set by credit approval. Ranked at {high}%, the highest.",
        "total_paid": _money(worst * term),
        "cost_of_credit": _money(worst * term - amount),
        "cost_of_credit_best": _money(best * term - amount),
    }


def compare(req: PayLaterRequest) -> dict[str, Any]:
    market = req.market.upper()
    loan = _loan_option(req)
    options = [loan]
    if market == "US":
        options += [_pay_in_4(req.purchase_amount), _pay_monthly(req.purchase_amount, req.term_months)]
        availability = "modelled"
        note = "US Pay Later terms from PayPal's published developer documentation."
    elif market in PAY_LATER_MARKETS:
        availability = "not_modelled"
        note = f"PayPal offers Pay Later in {market}, but only US terms are modelled here."
    else:
        availability = "unavailable"
        note = (f"PayPal Pay Later is not offered in {market}. PayPal lists the US, Australia, Canada, France, "
                "Germany, Italy, Spain, and the UK.")

    eligible = [o for o in options if o["eligible"] and o.get("cost_of_credit") is not None]
    cheapest: Optional[dict[str, Any]] = min(eligible, key=lambda o: o["cost_of_credit"]) if eligible else None
    summary = None
    if cheapest is not None:
        saving = (loan.get("cost_of_credit") or 0.0) - cheapest["cost_of_credit"] if loan["eligible"] else None
        cheapest_out = {"id": cheapest["id"], "name": cheapest["name"], "cost_of_credit": cheapest["cost_of_credit"],
                        "saving_vs_offer": _money(saving) if saving is not None else None}
        if cheapest["id"] == "loan_offer":
            summary = "No cheaper PayPal Pay Later option is available for this purchase."
        else:
            currency = MARKET_CURRENCY.get(market, "")
            summary = (f"{cheapest['name']} costs {currency} {cheapest_out['saving_vs_offer']:,.2f} less in credit costs than "
                       f"the {req.lender_name} offer, before any late fees.")
            if cheapest["id"] == "paypal_pay_in_4":
                summary += " It is repaid within 6 weeks, so each payment is larger."
    else:
        cheapest_out = None

    return {
        "market": market,
        "currency": MARKET_CURRENCY.get(market),
        "purchase_amount": req.purchase_amount,
        "pay_later_availability": availability,
        "availability_note": note,
        "options": options,
        "cheapest": cheapest_out,
        "summary": summary,
        "ranking_basis": "Cost of credit: total paid minus purchase price. Late fees and penalties are excluded.",
        "terms_source": {"url": TERMS_SOURCE, "retrieved": TERMS_RETRIEVED},
        "sandbox": True,
        "disclaimer": DISCLAIMER,
    }


@router.post("/offer-guard/pay-later", summary="Compare a loan offer with PayPal Pay Later on the same purchase")
def pay_later(req: PayLaterRequest) -> dict:
    return compare(req)

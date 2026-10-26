"""Copilot turns call the scoring, affordability, offer, and revenue-share functions.

Keyword routing only chooses a tool. Financial figures in the reply come from that
tool. Payouts are never created here; a disbursement request returns an approval card.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import ValidationError

from .affordability import assess
from .applicant_context import application_for, revenues_for_applicant
from .offer_analysis import analyse, manual_fields
from .revenue_volatility import analyse as analyse_revenue
from .schema import ScoreRequest

DISCLAIMER = "Sandbox copilot. It cannot move money without an explicit Approve tap."

_DISBURSE = re.compile(r"\b(disburse|payout|pay\s+out|send\s+(?:me\s+)?(?:the\s+)?money|transfer\s+funds)\b", re.I)
_AFFORD = re.compile(r"\b(afford|affordability|stress[\s-]?test|can\s+i\s+pay)\b", re.I)
_COUNTER = re.compile(r"\b(counterfactual|what\s+if|improve|move\s+up|raise\s+my\s+score)\b", re.I)
_EXPLAIN = re.compile(r"\b(explain|shap|why|what\s+shaped|drivers|contribut)\b", re.I)
_REVENUE = re.compile(r"\brevenue[\s-]?share\b|\bvolatility\b", re.I)
_OFFER = re.compile(r"\b(offer|apr|kfs|processing\s+fee)\b", re.I)
_EMI = re.compile(r"\b(emi|instal+ments?)\b", re.I)
_INCOME = re.compile(r"\b(income|revenue\s+trend|sales\s+trend)\b", re.I)
_SCORE = re.compile(r"\b(payscore|risk\s+band|\bscore\b)\b", re.I)
_LOAN = re.compile(r"\bloan\b", re.I)


def _envelope(reply: str, tools: list[dict[str, str]], analysis: Optional[dict[str, Any]] = None, approval: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "reply": reply,
        "tools": tools,
        "analysis": analysis,
        "approval": approval or {"required": False},
        "sandbox": True,
        "disclaimer": DISCLAIMER,
    }


def _multiplier(token: Optional[str]) -> float:
    label = (token or "").casefold()
    if label == "k":
        return 1000.0
    if label in {"lakh", "lac"}:
        return 100_000.0
    if label == "crore":
        return 10_000_000.0
    return 1.0


def parse_amount_inr(text: str) -> Optional[float]:
    patterns = (
        re.compile(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|lakh|lac|crore)?", re.I),
        re.compile(r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|lakh|lac|crore)\b", re.I),
        re.compile(r"(?<![\d.])([0-9]{4,9})(?![\d.])"),
    )
    for pattern in patterns:
        found = pattern.search(text)
        if not found:
            continue
        amount = float(found.group(1).replace(",", "")) * _multiplier(found.group(2) if found.lastindex and found.lastindex >= 2 else None)
        if amount > 0:
            return amount
    return None


def parse_rate_pct(text: str) -> Optional[float]:
    found = re.search(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*%", text)
    if not found:
        return None
    rate = float(found.group(1))
    if 0 <= rate <= 500:
        return rate
    return None


def parse_tenure_months(text: str) -> Optional[int]:
    found = re.search(r"\b(\d{1,3})\s*months?\b", text, re.I)
    if not found:
        return None
    months = int(found.group(1))
    if 1 <= months <= 360:
        return months
    return None


def _money(value: Optional[float]) -> str:
    if value is None:
        return "not available"
    return f"Rs {value:,.2f}"


def _application(applicant_id: str) -> tuple[Optional[ScoreRequest], str, Optional[str]]:
    raw, source = application_for(applicant_id)
    if raw is None:
        return None, source, "I could not find a synthetic application for that applicant, so I did not invent one."
    try:
        return ScoreRequest.model_validate(raw), source, None
    except ValidationError:
        return None, source, "The stored application could not be validated, so I did not score it."


def _afford(message: str, applicant_id: str, *, emi_only: bool) -> dict[str, Any]:
    application, source, error = _application(applicant_id)
    amount = parse_amount_inr(message)
    amount_note = None
    if amount is None and emi_only and application is not None:
        amount = float(application.requested_loan_amount_inr)
        amount_note = "The question did not name an amount, so this uses the requested amount on the synthetic application."
    if amount is None:
        return _envelope(
            "I need an amount, such as Rs 50,000, before I can calculate an instalment. I did not assume one.",
            [{"label": "affordability.assess", "status": "needs_input"}],
        )
    rate = parse_rate_pct(message)
    tenure = parse_tenure_months(message)
    tenure_assumed = tenure is None
    if tenure is None:
        tenure = 12
    payload = {
        "requested_amount_inr": amount,
        "monthly_income_inr": None if application is None else application.monthly_income_inr,
        "existing_monthly_debt_payments_inr": None if application is None else application.existing_monthly_debt_payments_inr,
        "essential_expenses_inr": None,
        "tenure_months": tenure,
        "annual_interest_rate_pct": rate,
        "frequency": "monthly",
        "include_illustrative_rate": rate is None,
    }
    result = assess(payload)
    bits = [
        f"Estimated instalment: {_money(result.get('installment_inr'))} per period.",
        f"Monthly-equivalent instalment: {_money(result.get('monthly_equivalent_installment_inr'))}.",
        f"Status: {result.get('status')}.",
    ]
    if result.get("residual_before_essential_expenses_inr") is not None:
        bits.append(
            "Cash left before essential living costs: "
            f"{_money(result.get('residual_before_essential_expenses_inr'))}."
        )
    if result.get("post_payment_cashflow_inr") is not None:
        bits.append(f"Cash left after essential expenses: {_money(result.get('post_payment_cashflow_inr'))}.")
    if amount_note:
        bits.append(amount_note)
    if tenure_assumed:
        bits.append("Tenure was not in the question, so 12 months was used and is labeled as an assumption.")
    bits.extend(result.get("reasons") or [])
    illustrative = result.get("illustrative_scenario")
    if illustrative:
        bits.append(
            f"Illustration at {illustrative['annual_interest_rate_pct']}% nominal: "
            f"{_money(illustrative['installment_inr'])} per period. {illustrative['note']}"
        )
    bits.append(f"Profile source: {source}. Essential living expenses were not invented.")
    return _envelope(
        " ".join(bits),
        [{"label": "affordability.assess", "status": "done"}],
        {"kind": "affordability", "result": result, "profile_source": source},
    )


def _explain(applicant_id: str, scorer: Any) -> dict[str, Any]:
    application, source, error = _application(applicant_id)
    if application is None:
        return _envelope(error or "No application is available.", [{"label": "score.explain", "status": "error"}])
    result = scorer.score(application)
    explanation = result.get("explanation") or {}
    if explanation.get("status") != "available":
        reply = explanation.get("detail") or "SHAP is unavailable for this score, and no heuristic reasons were substituted."
        return _envelope(reply, [{"label": "shap.TreeExplainer", "status": "unavailable"}], {"kind": "explanation", "result": explanation, "score": result["score"]})
    lines = [f"PayScore {result['score']} ({result['risk_band']}). These are TreeSHAP attributions, not causes."]
    for factor in explanation.get("factors_raising_risk") or []:
        lines.append(f"Raises risk: {factor['label']} ({factor['contribution']:+.4f} log-odds).")
    for factor in explanation.get("factors_lowering_risk") or []:
        lines.append(f"Lowers risk: {factor['label']} ({factor['contribution']:+.4f} log-odds).")
    lines.append(explanation.get("interpretation") or "")
    lines.append(f"Profile source: {source}. This call does not record a disbursement.")
    return _envelope(" ".join(lines), [{"label": "shap.TreeExplainer", "status": "done"}], {"kind": "explanation", "result": explanation, "score": result})


def _counterfactual(applicant_id: str, scorer: Any) -> dict[str, Any]:
    from .counterfactual import analyse_counterfactual

    application, source, error = _application(applicant_id)
    if application is None:
        return _envelope(error or "No application is available.", [{"label": "counterfactual.search", "status": "error"}])
    result = analyse_counterfactual(scorer, application)
    return _envelope(
        f"{result['summary']} Profile source: {source}.",
        [{"label": "counterfactual.search", "status": "done" if result.get("model_evaluated") else "unavailable"}],
        {"kind": "counterfactual", "result": result, "profile_source": source},
    )


def _revenue(applicant_id: str) -> dict[str, Any]:
    loaded = revenues_for_applicant(applicant_id)
    if loaded is None:
        result = analyse_revenue(None, source="applicant_not_found")
        result["reason"] = "applicant_history_not_found"
        return _envelope(
            "I do not have monthly net-revenue observations for that applicant, so I did not invent a history or a percentage.",
            [{"label": "revenue_volatility.analyse", "status": "insufficient_data"}],
            {"kind": "revenue_share", "result": result},
        )
    values, source = loaded
    result = analyse_revenue(values, source=source)
    metrics = result.get("metrics") or {}
    recommended = result.get("recommended_percentage")
    share = "no percentage" if recommended is None else f"{recommended:.0f}%"
    reply = (
        f"From {metrics.get('n')} observed net-revenue months, mean {_money(metrics.get('mean_inr'))}, "
        f"sample standard deviation {_money(metrics.get('sample_std_inr'))}, "
        f"coefficient of variation {metrics.get('coefficient_of_variation')}. "
        f"Status {result.get('status')}, confidence {result.get('confidence')}. "
        f"The deterministic policy illustrates {share}. It is not statistically validated. Source: {source}."
    )
    return _envelope(reply, [{"label": "revenue_volatility.analyse", "status": "done"}], {"kind": "revenue_share", "result": result})


def _income(applicant_id: str) -> dict[str, Any]:
    return _revenue(applicant_id)


def _offer(message: str) -> dict[str, Any]:
    principal = re.search(r"\b(?:principal|loan amount|amount)\s*[:=]\s*(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*)", message, re.I)
    term = re.search(r"\b(?:term|tenure)\s*[:=]\s*(\d{1,3})\s*months?\b", message, re.I)
    apr = re.search(r"\bapr\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?", message, re.I)
    fee = re.search(r"\bfee\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", message, re.I)
    if not (principal and term and apr):
        return _envelope(
            "I will not guess offer terms. Upload the PDF on Offer guard, or send principal, tenure, and APR as labeled numbers, for example principal=50000, tenure=12 months, APR 18%, fee 4%.",
            [{"label": "offer_guard.analyse", "status": "needs_input"}],
        )
    payload = {
        "principal_inr": float(principal.group(1).replace(",", "")),
        "term_months": int(term.group(1)),
        "advertised_apr_pct": float(apr.group(1)),
        "processing_fee_pct": float(fee.group(1)) if fee else 0.0,
        "lender_name": "Unknown lender",
    }
    result = analyse(manual_fields(payload), input_mode="copilot")
    return _envelope(
        (
            f"Calculated effective annualised cost: {result.get('estimated_real_apr_pct')}%. "
            f"Advertised APR: {result.get('advertised_apr_pct')}%. "
            f"Comparison: {result.get('comparison_status')}. "
            "This is an IRR of the cash flows, not a legal finding. "
            f"Directory check: {result.get('rbi_directory_match')}."
        ),
        [{"label": "offer_guard.analyse", "status": "done"}],
        {"kind": "offer_guard", "result": result},
    )


def _score(applicant_id: str, scorer: Any) -> dict[str, Any]:
    application, source, error = _application(applicant_id)
    if application is None:
        return _envelope(error or "No application is available.", [{"label": "score.score", "status": "error"}])
    result = scorer.score(application)
    return _envelope(
        (
            f"PayScore {result['score']} ({result['risk_band']}), estimated default probability {result['probability_of_default']}. "
            "There is no peer distribution loaded, so I did not invent a comparison. "
            f"{result['evaluation_caveat']} Profile source: {source}."
        ),
        [{"label": "score.score", "status": "done"}],
        {"kind": "score", "result": {"score": result["score"], "risk_band": result["risk_band"], "probability_of_default": result["probability_of_default"]}},
    )


def _disburse(message: str, applicant_id: str) -> dict[str, Any]:
    amount = parse_amount_inr(message)
    approval = {
        "required": True,
        "action": "Approve a sandbox disbursement demo? No real money moves until you confirm.",
        "applicant_id": applicant_id,
        "prompt": "Approve a sandbox disbursement demo? No real money moves.",
        "endpoint": "POST /disburse",
    }
    if amount is not None:
        approval["amount"] = amount
    return _envelope(
        "I will not create a payout, subscription, or transfer unless you approve it. The calculation tools do not move money.",
        [{"label": "disbursement.approval", "status": "blocked"}],
        approval=approval,
    )


def handle_chat(message: str, applicant_id: str, scorer: Any) -> dict[str, Any]:
    try:
        if _DISBURSE.search(message):
            return _disburse(message, applicant_id)
        if _AFFORD.search(message) or (_LOAN.search(message) and parse_amount_inr(message) is not None):
            return _afford(message, applicant_id, emi_only=False)
        if _COUNTER.search(message):
            return _counterfactual(applicant_id, scorer)
        if _EXPLAIN.search(message):
            return _explain(applicant_id, scorer)
        if _REVENUE.search(message):
            return _revenue(applicant_id)
        if _OFFER.search(message):
            return _offer(message)
        if _EMI.search(message):
            return _afford(message, applicant_id, emi_only=True)
        if _INCOME.search(message):
            return _income(applicant_id)
        if _SCORE.search(message):
            return _score(applicant_id, scorer)
        return _envelope(
            "I can explain a PayScore with SHAP, test eligible what-ifs, price an offer, stress-test an amount, or estimate a revenue share from observed months. Ask one of those, or request a sandbox payout if you want an approval card. I will not move money on my own.",
            [{"label": "copilot.help", "status": "done"}],
        )
    except Exception:
        return _envelope(
            "The tool failed before it finished. No money was moved and no figure was invented in its place.",
            [{"label": "copilot", "status": "error"}],
        )

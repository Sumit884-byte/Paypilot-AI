"""Copilot turns call the scoring, affordability, offer, and revenue-share functions.

Keyword routing only chooses a tool. Financial figures in the reply come from that
tool. Payouts are never created here; a disbursement request returns an approval card.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import ValidationError

from .affordability import assess
from .applicant_context import application_for, revenues_for_applicant
from .offer_analysis import analyse, manual_fields
from .revenue_volatility import analyse as analyse_revenue
from .schema import ScoreRequest

LINKED_SOURCE = "your linked PayPal account (Transaction Search)"
NEED_LINKED_SCORE = (
    "I need your PayScore first. Open PayScore and run it: it combines your PayPal history with a few details PayPal "
    "does not share (age, employment, existing repayments, the loan you want). I will not borrow a demo persona's figures."
)


@dataclass
class LinkedContext:
    """A real PayPal-linked user: answers come from their PayPal profile and their own PayScore request."""

    profile: dict[str, Any]
    application: Optional[dict[str, Any]] = None

    def score_request(self) -> Optional[ScoreRequest]:
        if not self.application:
            return None
        try:
            return ScoreRequest.model_validate(self.application)
        except ValidationError:
            return None

    def months(self) -> list[float]:
        return [float(row.get("income_inr") or 0) for row in self.profile.get("monthly_income_12m") or []]

    def window(self) -> str:
        return f"{self.profile.get('window_start')} to {self.profile.get('window_end')}"

DISCLAIMER = "Sandbox copilot. It cannot move money without an explicit Approve tap."

_DISBURSE = re.compile(r"\b(disburse|payout|pay\s+out|send\s+(?:me\s+)?(?:the\s+)?money|transfer\s+funds)\b", re.I)
_HARDSHIP = re.compile(r"\b(hardship|payment\s+holiday|lower\s+revenue.?share|reduce\s+revenue|no\s+income|haven.t\s+been\s+paid)\b", re.I)
_DISPUTE = re.compile(r"\b(chargeback|dispute|charge back)\b", re.I)
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


def _resolve(applicant_id: str, linked: Optional[LinkedContext]) -> tuple[Optional[ScoreRequest], str, Optional[str]]:
    """The application a score-based answer uses: a demo persona's fixture, or the linked user's own PayScore request."""
    if linked is None:
        return _application(applicant_id)
    request = linked.score_request()
    if request is None:
        return None, LINKED_SOURCE, NEED_LINKED_SCORE
    return request, "your PayScore inputs (PayPal history plus the details you entered)", None


def _afford(message: str, applicant_id: str, *, emi_only: bool) -> dict[str, Any]:
    application, source, error = _application(applicant_id)
    return _afford_with(
        message, emi_only=emi_only, source=source,
        income=None if application is None else application.monthly_income_inr,
        debt=None if application is None else application.existing_monthly_debt_payments_inr,
        default_amount=None if application is None else float(application.requested_loan_amount_inr),
        default_note="The question did not name an amount, so this uses the requested amount on the synthetic application.",
    )


def _afford_with(message: str, *, emi_only: bool, source: str, income: Optional[float], debt: Optional[float],
                 default_amount: Optional[float], default_note: str, extra_notes: tuple[str, ...] = ()) -> dict[str, Any]:
    amount = parse_amount_inr(message)
    amount_note = None
    if amount is None and emi_only and default_amount is not None:
        amount = default_amount
        amount_note = default_note
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
        "monthly_income_inr": income,
        "existing_monthly_debt_payments_inr": debt,
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
    bits.extend(extra_notes)
    bits.append(f"Profile source: {source}. Essential living expenses were not invented.")
    return _envelope(
        " ".join(bits),
        [{"label": "affordability.assess", "status": "done"}],
        {"kind": "affordability", "result": result, "profile_source": source},
    )


def _explain(applicant_id: str, scorer: Any, linked: Optional[LinkedContext] = None) -> dict[str, Any]:
    application, source, error = _resolve(applicant_id, linked)
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


def _counterfactual(applicant_id: str, scorer: Any, linked: Optional[LinkedContext] = None) -> dict[str, Any]:
    from .counterfactual import analyse_counterfactual

    application, source, error = _resolve(applicant_id, linked)
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


def _trend_reply(values: list[float], source: str, window: str = "", partial_month: Optional[float] = None) -> dict[str, Any]:
    """Describe the observed monthly income: total, recent vs earlier average, direction. No forecast.

    `partial_month` is the current, unfinished month's income: it counts toward the total but not the trend, since a
    month that is a third over would otherwise always read as a decline.
    """
    from .paypal.income import TREND_BAND, _trend

    total = sum(values) + (partial_month or 0.0)
    span = f" ({window})" if window else ""
    if total <= 0:
        return _envelope(
            f"There are no completed incoming payments in the last {len(values)} months{span}, so there is no income "
            f"trend to read. I did not fill the gap with example data. Source: {source}.",
            [{"label": "income.trend", "status": "insufficient_data"}],
            {"kind": "income_trend", "result": {"status": "no_income", "months": values}},
        )
    recent, earlier = values[-3:], values[-6:-3]
    recent_avg = sum(recent) / len(recent)
    earlier_avg = sum(earlier) / len(earlier) if earlier else None
    trend = _trend(values)
    active = sum(1 for value in values if value > 0)
    compare = (f"averaging {_money(recent_avg)} a month over the last 3 months against {_money(earlier_avg)} in the 3 "
               f"before, so the trend is {trend} (a change within {TREND_BAND:.0%} counts as stable)."
               if earlier_avg is not None else f"averaging {_money(recent_avg)} a month recently.")
    so_far = (f" This month so far: {_money(partial_month)}, left out of the trend because the month is not over."
              if partial_month is not None else "")
    return _envelope(
        f"Income over the last {len(values)} full months{span}: {_money(total - (partial_month or 0.0))}, with income in "
        f"{active} of them, {compare}{so_far} This describes what happened; it is not a forecast. Source: {source}.",
        [{"label": "income.trend", "status": "done"}],
        {"kind": "income_trend", "result": {"status": trend, "total_inr": round(total, 2), "active_months": active,
                                            "recent_avg_inr": round(recent_avg, 2),
                                            "earlier_avg_inr": None if earlier_avg is None else round(earlier_avg, 2)}},
    )


def _income(applicant_id: str) -> dict[str, Any]:
    loaded = revenues_for_applicant(applicant_id)
    if loaded is None:
        return _revenue(applicant_id)
    values, source = loaded
    return _trend_reply(values, source)


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


def _score(applicant_id: str, scorer: Any, linked: Optional[LinkedContext] = None) -> dict[str, Any]:
    application, source, error = _resolve(applicant_id, linked)
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


def _hardship(applicant_id: str) -> dict[str, Any]:
    from .hardship import get_hardship

    case = get_hardship(applicant_id)
    if case.get("status") == "none":
        return _envelope(
            "I do not see a hardship flag for that applicant. Income events come from PayPal capture webhooks; "
            "when about two weeks pass with no income, a relief offer (payment holiday or lower revenue-share) "
            "is drafted here and nothing is applied without your approval.",
            [{"label": "hardship.review", "status": "none"}],
            {"kind": "hardship", "result": case},
        )
    offer = case.get("offer") or {}
    return _envelope(
        f"Hardship flagged: {case.get('reason')}. {offer.get('summary', '')} "
        "No subscription or revenue-share change is applied unless you approve it.",
        [{"label": "hardship.review", "status": "flagged"}],
        approval={"required": True, "action": "Approve hardship relief?",
                  "applicant_id": applicant_id, "kind": offer.get("kind")},
        analysis={"kind": "hardship", "result": case},
    )


def _dispute(applicant_id: str) -> dict[str, Any]:
    """Draft a borrower-protective response to an open chargeback. Never sends it."""
    from .disputes import draft_response, list_open_chargebacks

    payload = list_open_chargebacks(applicant_id)
    disputes = payload.get("disputes") or []
    if not disputes:
        return _envelope(
            "I don't see any open chargebacks for that applicant, so there's nothing to draft a response to.",
            [{"label": "disputes.draft", "status": "none"}],
            {"kind": "dispute", "result": {"disputes": [], "source": payload.get("source")}},
        )
    dispute = disputes[0]
    drafted = draft_response(dispute, applicant_id)
    amount = dispute.get("amount_inr")
    currency = dispute.get("currency") or "INR"
    reply = (
        f"Open chargeback {drafted['dispute_id']} for {amount} {currency} "
        f"({dispute.get('reason')}), opened {dispute.get('opened_at')}. "
        "Here is a borrower-protective draft you can review and send — PayScore does not file it for you: "
        f"{drafted['draft']}"
    )
    return _envelope(
        reply,
        [{"label": "disputes.draft", "status": "done"}],
        {"kind": "dispute", "result": drafted},
    )


def _linked_afford(message: str, linked: LinkedContext, *, emi_only: bool) -> dict[str, Any]:
    request = linked.score_request()
    months = linked.months()
    paypal_average = round(sum(months) / len(months), 2) if months else 0.0
    if request is not None:
        income, source = request.monthly_income_inr, "your PayScore inputs (PayPal history plus the details you entered)"
        notes: tuple[str, ...] = ()
    else:
        income, source = paypal_average, f"{LINKED_SOURCE}, {linked.window()}"
        notes = ("Income is the 12-month PayPal average. Existing repayments are unknown until you run PayScore, "
                 "so they are not counted.",)
    if not income or income <= 0:
        return _envelope(
            "Your linked PayPal account shows no completed incoming payments in the last 12 months, so I cannot judge "
            "whether a repayment is affordable. I did not substitute example income. Run PayScore with a declared "
            "monthly income if PayPal is not where you get paid.",
            [{"label": "affordability.assess", "status": "insufficient_data"}],
            {"kind": "affordability", "result": {"status": "no_income"}, "profile_source": source},
        )
    return _afford_with(
        message, emi_only=emi_only, source=source, income=float(income),
        debt=None if request is None else request.existing_monthly_debt_payments_inr,
        default_amount=None if request is None else float(request.requested_loan_amount_inr),
        default_note="The question did not name an amount, so this uses the loan amount on your PayScore request.",
        extra_notes=notes,
    )


def _linked_revenue(linked: LinkedContext) -> dict[str, Any]:
    first = next((i for i, value in enumerate(linked.months()) if value > 0), None)
    values = [] if first is None else linked.months()[first:]
    result = analyse_revenue(values or None, source="paypal_transaction_search")
    if not values:
        return _envelope(
            "Your linked PayPal account has no months with income yet, so there is no history to size a revenue share "
            "from. I did not invent one.",
            [{"label": "revenue_volatility.analyse", "status": "insufficient_data"}],
            {"kind": "revenue_share", "result": result},
        )
    metrics = result.get("metrics") or {}
    recommended = result.get("recommended_percentage")
    share = "no percentage" if recommended is None else f"{recommended:.0f}%"
    return _envelope(
        f"From {metrics.get('n')} months of your PayPal income since your first sale, mean {_money(metrics.get('mean_inr'))}, "
        f"coefficient of variation {metrics.get('coefficient_of_variation')}. Status {result.get('status')}, "
        f"confidence {result.get('confidence')}. The deterministic policy illustrates {share}; it is not statistically "
        f"validated. Source: {LINKED_SOURCE}, {linked.window()}.",
        [{"label": "revenue_volatility.analyse", "status": "done"}],
        {"kind": "revenue_share", "result": result},
    )


def _linked_trend(linked: LinkedContext) -> dict[str, Any]:
    from calendar import monthrange
    from datetime import date

    months = linked.months()
    try:
        end = date.fromisoformat(str(linked.profile.get("window_end")))
        partial = end.day < monthrange(end.year, end.month)[1]
    except ValueError:
        partial = False
    if partial and months:
        return _trend_reply(months[:-1], LINKED_SOURCE, linked.window(), partial_month=months[-1])
    return _trend_reply(months, LINKED_SOURCE, linked.window())


def _linked_disburse() -> dict[str, Any]:
    return _envelope(
        "I can't set up a payout for your linked account. PayPal sign-in doesn't share your PayPal email with "
        "Paypilot, so there is no verified recipient, and I won't send money to a guessed address. The demo personas "
        "show the full approve-then-pay flow in the sandbox.",
        [{"label": "disbursement.approval", "status": "unavailable"}],
    )


def _linked_dispute(linked: LinkedContext) -> dict[str, Any]:
    rate = linked.profile.get("dispute_rate_12m")
    return _envelope(
        f"Your linked PayPal account's dispute rate over the last 12 months is {rate if rate is not None else 'not available'} "
        "(disputes per completed sale). Drafting a response needs the dispute's details, which Paypilot only has for "
        "the demo personas; open the case in PayPal's Resolution Center to respond.",
        [{"label": "disputes.summary", "status": "done"}],
        {"kind": "dispute", "result": {"dispute_rate_12m": rate, "source": "paypal"}},
    )


def _linked_hardship(linked: LinkedContext) -> dict[str, Any]:
    months = linked.months()
    recent = months[-1] if months else 0.0
    gap = linked.profile.get("longest_income_gap_days_12m")
    return _envelope(
        "Hardship relief applies to a PayScore loan, and your linked account has none, so there is nothing to pause. "
        f"For context, PayPal shows {_money(recent)} of income this month and a longest gap of {gap} days between "
        "payments in the last 12 months.",
        [{"label": "hardship.review", "status": "none"}],
        {"kind": "hardship", "result": {"status": "none", "source": "paypal"}},
    )


def _handle_linked(message: str, linked: LinkedContext, scorer: Any) -> dict[str, Any]:
    """The same intents as the demo, answered from the linked account. A demo persona is never consulted."""
    if _DISBURSE.search(message):
        return _linked_disburse()
    if _HARDSHIP.search(message):
        return _linked_hardship(linked)
    if _DISPUTE.search(message):
        return _linked_dispute(linked)
    if _AFFORD.search(message) or (_LOAN.search(message) and parse_amount_inr(message) is not None):
        return _linked_afford(message, linked, emi_only=False)
    if _COUNTER.search(message):
        return _counterfactual("", scorer, linked)
    if _EXPLAIN.search(message):
        return _explain("", scorer, linked)
    if _REVENUE.search(message):
        return _linked_revenue(linked)
    if _OFFER.search(message):
        return _offer(message)
    if _EMI.search(message):
        return _linked_afford(message, linked, emi_only=True)
    if _INCOME.search(message):
        return _linked_trend(linked)
    if _SCORE.search(message):
        return _score("", scorer, linked)
    return _envelope(
        "I answer from your linked PayPal account: your income trend, whether a repayment fits, a revenue share from "
        "your history, or an offer's real cost. Run PayScore to unlock score explanations and what-ifs.",
        [{"label": "copilot.help", "status": "done"}],
    )


def handle_chat(message: str, applicant_id: str, scorer: Any, linked: Optional[LinkedContext] = None) -> dict[str, Any]:
    if linked is not None:
        try:
            return _handle_linked(message, linked, scorer)
        except Exception:
            return _envelope(
                "The tool failed before it finished. No money was moved and no figure was invented in its place.",
                [{"label": "copilot", "status": "error"}],
            )
    try:
        if _DISBURSE.search(message):
            return _disburse(message, applicant_id)
        if _HARDSHIP.search(message):
            return _hardship(applicant_id)
        if _DISPUTE.search(message):
            return _dispute(applicant_id)
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

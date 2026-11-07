"""Agent-to-agent repayment negotiation (demo / decision-support only).

Both agents read the same verified fixture / income aggregates and affordability
helpers. Neither fabricates income, transactions, or repayment history.
No PayPal payout is executed — any settlement remains explicitly simulated.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .affordability import assess
from .paypal.income import fixture_profile

router = APIRouter(tags=["negotiation"])

MAX_ROUNDS = 3
SIMULATION_BANNER = (
    "SIMULATED negotiation only. Terms are not lender-approved and do not move money. "
    "No PayPal payout is created by this flow."
)

PERSONA_BY_APPLICANT = {
    "PSC-PRIYA-001": "priya",
    "PSC-ARJUN-001": "arjun",
    "PSC-ROHAN-001": "rohan",
}

_SESSIONS: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


class StartNegotiationRequest(BaseModel):
    applicant_id: str = Field(min_length=3, max_length=64)
    persona: Optional[Literal["priya", "arjun", "rohan"]] = None
    requested_amount_inr: float = Field(gt=0, le=10_000_000)
    requested_term_months: int = Field(ge=1, le=60)
    annual_interest_rate_pct: float = Field(default=12.0, ge=0, le=60)


class CounterRequest(BaseModel):
    session_id: str
    action: Literal["accept", "reject", "counter"]
    counter_term_months: Optional[int] = Field(default=None, ge=1, le=60)
    counter_revenue_share_pct: Optional[float] = Field(default=None, ge=1, le=30)
    counter_payment_holiday_months: Optional[int] = Field(default=None, ge=0, le=3)
    note: Optional[str] = Field(default=None, max_length=500)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _persona(applicant_id: str, persona: Optional[str]) -> str:
    if persona in {"priya", "arjun", "rohan"}:
        return persona
    return PERSONA_BY_APPLICANT.get(applicant_id, "priya")


def _load_evidence(applicant_id: str, persona: str) -> dict[str, Any]:
    profile = fixture_profile(persona)
    monthly = profile.get("monthly_income_12m") or []
    incomes = [float(m.get("income_inr") or 0) for m in monthly]
    avg_income = round(sum(incomes) / len(incomes), 2) if incomes else 0.0
    return {
        "applicant_id": applicant_id,
        "persona": persona,
        "source": profile.get("source"),
        "total_income_12m_inr": profile.get("total_income_12m_inr"),
        "average_monthly_income_inr": avg_income,
        "income_trend_12m": profile.get("income_trend_12m"),
        "refund_rate_12m": profile.get("refund_rate_12m"),
        "dispute_rate_12m": profile.get("dispute_rate_12m"),
        "longest_income_gap_days_12m": profile.get("longest_income_gap_days_12m"),
        "outstanding_invoices_inr": profile.get("outstanding_invoices_inr"),
        "window_start": profile.get("window_start"),
        "window_end": profile.get("window_end"),
        "classification": "fixture_aggregate" if profile.get("source") == "fixture" else "paypal_aggregate",
        "note": (
            "Agents share this aggregate evidence only. Raw transaction descriptions are not used."
        ),
    }


def _monthly_installment(amount: float, months: int, annual_rate_pct: float) -> float:
    if months <= 0:
        return amount
    if annual_rate_pct <= 0:
        return round(amount / months, 2)
    r = annual_rate_pct / 100.0 / 12.0
    return round(amount * (r * (1 + r) ** months) / ((1 + r) ** months - 1), 2)


def _lender_initial(evidence: dict[str, Any], req: StartNegotiationRequest) -> dict[str, Any]:
    avg = float(evidence["average_monthly_income_inr"] or 0)
    refund = float(evidence.get("refund_rate_12m") or 0)
    dispute = float(evidence.get("dispute_rate_12m") or 0)
    gap = int(evidence.get("longest_income_gap_days_12m") or 0)

    term = int(req.requested_term_months)
    share = 12.0
    holiday = 0
    reasons = [
        f"Verified aggregate average monthly income is INR {avg:,.0f} ({evidence['classification']}).",
        f"Requested amount INR {req.requested_amount_inr:,.0f} over {term} months.",
    ]
    if refund > 0.05:
        share = min(18.0, share + 3.0)
        reasons.append(f"Refund rate {refund:.1%} suggests a higher revenue-share buffer.")
    if dispute > 0.02:
        share = min(20.0, share + 2.0)
        reasons.append(f"Dispute rate {dispute:.1%} increases lender caution.")
    if gap > 45:
        holiday = 0
        term = max(6, term - 3)
        reasons.append(f"Longest income gap of {gap} days — shorter term proposed, no payment holiday.")
    elif evidence.get("income_trend_12m") == "increasing":
        holiday = 1
        reasons.append("Increasing income trend — one-month payment holiday offered at start.")

    installment = _monthly_installment(req.requested_amount_inr, term, req.annual_interest_rate_pct)
    afford = assess({
        "requested_amount_inr": req.requested_amount_inr,
        "monthly_income_inr": avg,
        "essential_expenses_inr": None,
        "existing_monthly_debt_payments_inr": 0,
        "tenure_months": term,
        "annual_interest_rate_pct": req.annual_interest_rate_pct,
    })

    return {
        "agent": "lender",
        "label": "Lender Agent",
        "repayment_amount_inr": req.requested_amount_inr,
        "term_months": term,
        "monthly_installment_inr": installment,
        "revenue_share_pct": share,
        "payment_holiday_months": holiday,
        "annual_interest_rate_pct": req.annual_interest_rate_pct,
        "reasons": reasons,
        "affordability_status": afford.get("status"),
        "simulated": True,
    }


def _borrower_evaluate(evidence: dict[str, Any], proposal: dict[str, Any], rate: float) -> dict[str, Any]:
    avg = float(evidence["average_monthly_income_inr"] or 0)
    installment = float(proposal["monthly_installment_inr"])
    share = float(proposal["revenue_share_pct"])
    term = int(proposal["term_months"])
    amount = float(proposal["repayment_amount_inr"])

    # Without essential expenses the affordability helper returns incomplete — still use cash-flow ratio.
    burden = installment / avg if avg > 0 else 1.0
    concerns = []
    accept = True
    counter = None

    if burden > 0.35:
        accept = False
        concerns.append(
            f"Proposed instalment INR {installment:,.0f} is {burden:.0%} of average monthly income "
            f"INR {avg:,.0f} — above the borrower's 35% comfort heuristic."
        )
    if share > 15:
        accept = False
        concerns.append(f"Revenue-share {share:.1f}% is high relative to income volatility observed in aggregates.")
    if int(proposal.get("payment_holiday_months") or 0) == 0 and int(evidence.get("longest_income_gap_days_12m") or 0) > 30:
        concerns.append("Borrower prefers a short payment holiday given historical income gaps.")

    if accept and not concerns:
        return {
            "agent": "borrower",
            "label": "Borrower Agent (Priya)",
            "decision": "accept",
            "concerns": ["Proposal fits within the borrower's income-based comfort checks."],
            "counteroffer": None,
            "simulated": True,
        }

    # Counter: stretch term, lower share, request holiday.
    counter_term = min(60, term + 6) if burden > 0.35 else term
    counter_share = max(8.0, share - 4.0)
    counter_holiday = max(1, int(proposal.get("payment_holiday_months") or 0))
    counter_installment = _monthly_installment(amount, counter_term, rate)
    counter = {
        "repayment_amount_inr": amount,
        "term_months": counter_term,
        "monthly_installment_inr": counter_installment,
        "revenue_share_pct": counter_share,
        "payment_holiday_months": counter_holiday,
        "annual_interest_rate_pct": rate,
        "reasons": concerns
        + [
            f"Counter: extend term to {counter_term} months (instalment INR {counter_installment:,.0f}).",
            f"Counter: revenue-share {counter_share:.1f}%.",
            f"Counter: payment holiday {counter_holiday} month(s).",
        ],
    }
    return {
        "agent": "borrower",
        "label": "Borrower Agent (Priya)",
        "decision": "counter",
        "concerns": concerns,
        "counteroffer": counter,
        "simulated": True,
    }


def _lender_review_counter(evidence: dict[str, Any], counter: dict[str, Any], round_no: int) -> dict[str, Any]:
    avg = float(evidence["average_monthly_income_inr"] or 0)
    installment = float(counter["monthly_installment_inr"])
    share = float(counter["revenue_share_pct"])
    burden = installment / avg if avg > 0 else 1.0
    reasons = []

    # Accept if still covered under stress: share covers roughly installment / avg.
    if burden <= 0.4 and share >= 8:
        reasons.append("Counteroffer still leaves instalment within 40% of average aggregate income.")
        reasons.append("Revenue-share remains at or above the lender floor of 8%.")
        return {
            "agent": "lender",
            "label": "Lender Agent",
            "decision": "accept",
            "proposal": {**counter, "agent": "lender", "label": "Lender Agent", "reasons": reasons, "simulated": True},
            "reasons": reasons,
            "simulated": True,
        }

    if round_no >= MAX_ROUNDS:
        reasons.append("Maximum negotiation rounds reached without an acceptable midpoint.")
        return {
            "agent": "lender",
            "label": "Lender Agent",
            "decision": "manual_review",
            "proposal": None,
            "reasons": reasons,
            "simulated": True,
        }

    # Midpoint counter from lender.
    mid = {
        "repayment_amount_inr": counter["repayment_amount_inr"],
        "term_months": max(6, int(counter["term_months"]) - 3),
        "revenue_share_pct": round((share + 12) / 2, 1),
        "payment_holiday_months": min(1, int(counter.get("payment_holiday_months") or 0)),
        "annual_interest_rate_pct": counter["annual_interest_rate_pct"],
    }
    mid["monthly_installment_inr"] = _monthly_installment(
        float(mid["repayment_amount_inr"]), int(mid["term_months"]), float(mid["annual_interest_rate_pct"])
    )
    reasons.append("Lender proposes a midpoint between the prior offer and the borrower counter.")
    return {
        "agent": "lender",
        "label": "Lender Agent",
        "decision": "counter",
        "proposal": {**mid, "agent": "lender", "label": "Lender Agent", "reasons": reasons, "simulated": True},
        "reasons": reasons,
        "simulated": True,
    }


def _session_view(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session["session_id"],
        "applicant_id": session["applicant_id"],
        "status": session["status"],
        "round": session["round"],
        "max_rounds": MAX_ROUNDS,
        "evidence": session["evidence"],
        "current_proposal": session.get("current_proposal"),
        "latest_borrower": session.get("latest_borrower"),
        "history": session["history"],
        "outcome": session.get("outcome"),
        "settlement": session.get("settlement"),
        "simulation_banner": SIMULATION_BANNER,
        "updated_at_utc": session["updated_at_utc"],
    }


def reset_negotiation_store() -> None:
    with _lock:
        _SESSIONS.clear()


@router.post("/negotiate/start", summary="Start lender/borrower negotiation (simulated)", response_model=None)
def start_negotiation(body: StartNegotiationRequest) -> dict:
    persona = _persona(body.applicant_id, body.persona)
    evidence = _load_evidence(body.applicant_id, persona)
    proposal = _lender_initial(evidence, body)
    borrower = _borrower_evaluate(evidence, proposal, body.annual_interest_rate_pct)

    session_id = str(uuid4())
    history = [
        {"at": _utcnow(), "round": 1, "event": "lender_proposal", "payload": proposal},
        {"at": _utcnow(), "round": 1, "event": "borrower_review", "payload": borrower},
    ]
    status = "agreement_reached" if borrower["decision"] == "accept" else "counteroffer_pending"
    outcome = "agreement_reached" if borrower["decision"] == "accept" else None
    settlement = None
    if outcome == "agreement_reached":
        settlement = {
            "mode": "simulated",
            "paypal_payout": False,
            "terms": proposal,
            "message": "Agreement recorded in the demo session only. No PayPal payout was sent.",
        }

    session = {
        "session_id": session_id,
        "applicant_id": body.applicant_id,
        "persona": persona,
        "rate": body.annual_interest_rate_pct,
        "evidence": evidence,
        "round": 1,
        "status": status,
        "current_proposal": proposal if borrower["decision"] == "accept" else (borrower.get("counteroffer") or proposal),
        "latest_borrower": borrower,
        "history": history,
        "outcome": outcome,
        "settlement": settlement,
        "updated_at_utc": _utcnow(),
    }
    with _lock:
        _SESSIONS[session_id] = session
    return _session_view(session)


@router.post("/negotiate/respond", summary="Accept, reject, or continue a negotiation round", response_model=None)
def respond_negotiation(body: CounterRequest) -> dict | JSONResponse:
    with _lock:
        session = _SESSIONS.get(body.session_id)
        if not session:
            return JSONResponse(status_code=404, content={"error": "session_not_found"})
        if session["status"] in {"agreement_reached", "no_agreement", "manual_review_required", "rejected"}:
            return JSONResponse(status_code=409, content={"error": "session_closed", "status": session["status"]})

        if body.action == "reject":
            session["status"] = "rejected"
            session["outcome"] = "no_agreement_reached"
            session["history"].append({"at": _utcnow(), "round": session["round"], "event": "borrower_reject",
                                       "payload": {"note": body.note, "simulated": True}})
            session["updated_at_utc"] = _utcnow()
            return _session_view(session)

        if body.action == "accept":
            terms = session.get("current_proposal")
            session["status"] = "agreement_reached"
            session["outcome"] = "agreement_reached"
            session["settlement"] = {
                "mode": "simulated",
                "paypal_payout": False,
                "terms": terms,
                "message": "Borrower accepted. Simulated settlement only — no PayPal payout.",
                "confirmation_required_for_any_real_payout": True,
            }
            session["history"].append({"at": _utcnow(), "round": session["round"], "event": "borrower_accept",
                                       "payload": {"terms": terms, "simulated": True}})
            session["updated_at_utc"] = _utcnow()
            return _session_view(session)

        # action == counter — optional user-adjusted counter, else use agent counter
        session["round"] += 1
        if session["round"] > MAX_ROUNDS:
            session["status"] = "manual_review_required"
            session["outcome"] = "manual_review_required"
            session["history"].append({"at": _utcnow(), "round": session["round"], "event": "max_rounds",
                                       "payload": {"detail": "Exceeded maximum rounds."}})
            session["updated_at_utc"] = _utcnow()
            return _session_view(session)

        base = session.get("latest_borrower", {}).get("counteroffer") or session["current_proposal"]
        counter = {
            "repayment_amount_inr": base["repayment_amount_inr"],
            "term_months": body.counter_term_months or base["term_months"],
            "revenue_share_pct": body.counter_revenue_share_pct or base["revenue_share_pct"],
            "payment_holiday_months": (
                body.counter_payment_holiday_months
                if body.counter_payment_holiday_months is not None
                else base.get("payment_holiday_months", 0)
            ),
            "annual_interest_rate_pct": session["rate"],
            "reasons": [body.note] if body.note else base.get("reasons", []),
        }
        counter["monthly_installment_inr"] = _monthly_installment(
            float(counter["repayment_amount_inr"]),
            int(counter["term_months"]),
            float(counter["annual_interest_rate_pct"]),
        )
        session["history"].append({"at": _utcnow(), "round": session["round"], "event": "borrower_counter",
                                   "payload": {"agent": "borrower", **counter, "simulated": True}})

        lender = _lender_review_counter(session["evidence"], counter, session["round"])
        session["history"].append({"at": _utcnow(), "round": session["round"], "event": "lender_review",
                                   "payload": lender})

        if lender["decision"] == "accept":
            session["status"] = "agreement_reached"
            session["outcome"] = "agreement_reached"
            session["current_proposal"] = lender["proposal"]
            session["settlement"] = {
                "mode": "simulated",
                "paypal_payout": False,
                "terms": lender["proposal"],
                "message": "Lender accepted counter. Simulated only — no PayPal payout.",
            }
        elif lender["decision"] == "manual_review":
            session["status"] = "manual_review_required"
            session["outcome"] = "manual_review_required"
        else:
            session["status"] = "counteroffer_pending"
            session["current_proposal"] = lender["proposal"]
            # Auto borrower re-eval for timeline transparency
            borrower = _borrower_evaluate(session["evidence"], lender["proposal"], session["rate"])
            session["latest_borrower"] = borrower
            session["history"].append({"at": _utcnow(), "round": session["round"], "event": "borrower_review",
                                       "payload": borrower})
            if borrower["decision"] == "accept":
                session["status"] = "agreement_reached"
                session["outcome"] = "agreement_reached"
                session["settlement"] = {
                    "mode": "simulated",
                    "paypal_payout": False,
                    "terms": lender["proposal"],
                    "message": "Borrower accepted lender midpoint. Simulated only.",
                }
            elif session["round"] >= MAX_ROUNDS:
                session["status"] = "no_agreement"
                session["outcome"] = "no_agreement_reached"

        session["updated_at_utc"] = _utcnow()
        return _session_view(session)


@router.get("/negotiate/{session_id}", summary="Fetch a negotiation session", response_model=None)
def get_negotiation(session_id: str) -> dict | JSONResponse:
    with _lock:
        session = _SESSIONS.get(session_id)
        if not session:
            return JSONResponse(status_code=404, content={"error": "session_not_found"})
        return _session_view(session)


@router.get("/negotiate", summary="List negotiation sessions for an applicant", response_model=None)
def list_negotiations(applicant_id: str = Query(..., min_length=3)) -> dict:
    with _lock:
        rows = [_session_view(s) for s in _SESSIONS.values() if s["applicant_id"] == applicant_id]
    return {"sessions": rows, "count": len(rows), "simulation_banner": SIMULATION_BANNER}

"""Hardship agent: flags ~2 weeks of no income and drafts relief.

Detected from PayPal capture webhooks (record_income is called by the
POST /paypal/webhook handler). When a borrower has had no income for the
configured gap (default 14 days) and carries an active repayment, a case is
flagged and a local agent drafts either a payment holiday or a reduced
revenue-share offer.

Nothing is applied automatically: any subscription cancellation or
revenue-share change stays behind the borrower's explicit approval through
the existing POST /repayment/subscription/{id}/cancel and
POST /repayment/revenue-share endpoints.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

HARDSHIP_GAP_DAYS = int(os.getenv("PAYSCORE_HARDSHIP_GAP_DAYS", "14"))

HARDSHIP_CASES: dict[str, dict[str, Any]] = {}
INCOME_EVENTS: dict[str, list[dict[str, Any]]] = {}
SEEN_EVENT_IDS: dict[str, set[str]] = {}

DISCLAIMER = (
    "Sandbox hardship draft. No subscription or revenue-share change is applied "
    "without the borrower's explicit approval."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def record_income(
    applicant_id: str, amount_inr: float, captured_at: Optional[str], event_id: Optional[str] = None
) -> dict[str, Any]:
    """Record an incoming payment capture and flag hardship if the gap is too wide.

    Returns the resulting hardship case (or {"status": "none"} when no flag is
    raised). Idempotent per event: a repeated event_id is ignored, so webhook
    retries do not double-count a capture.
    """
    if event_id is not None:
        seen = SEEN_EVENT_IDS.setdefault(applicant_id, set())
        if str(event_id) in seen:
            existing = HARDSHIP_CASES.get(applicant_id)
            return dict(existing) if existing else {"applicant_id": applicant_id, "status": "none", "gap_days": None}
        seen.add(str(event_id))
    when = _parse_ts(captured_at) or datetime.now(timezone.utc)
    event = {
        "amount_inr": float(amount_inr),
        "captured_at": when.isoformat(),
        "event_id": event_id,
    }
    INCOME_EVENTS.setdefault(applicant_id, []).append(event)
    events = INCOME_EVENTS[applicant_id]

    gap_days = None
    previous = None
    if len(events) >= 2:
        previous = events[-2]["captured_at"]
        previous_ts = _parse_ts(previous)
        if previous_ts is not None:
            gap_days = (when - previous_ts).days

    case = HARDSHIP_CASES.get(applicant_id)
    if gap_days is not None and gap_days >= HARDSHIP_GAP_DAYS:
        drafted = _draft_offer(applicant_id, gap_days)
        if case is None or case.get("status") != "flagged":
            case = {
                "applicant_id": applicant_id,
                "status": "flagged",
                "reason": f"no_income_for_{gap_days}_days",
                "gap_days": gap_days,
                "last_income_at": previous,
                "created_at": _now(),
                "updated_at": _now(),
                "offer": drafted,
                "requires_approval": True,
                "applied": False,
            }
            HARDSHIP_CASES[applicant_id] = case
        else:
            case["gap_days"] = gap_days
            case["last_income_at"] = previous
            case["updated_at"] = _now()
            case["offer"] = drafted
    return case or {"applicant_id": applicant_id, "status": "none", "gap_days": gap_days}


def _draft_offer(applicant_id: str, gap_days: int) -> dict[str, Any]:
    """Local agent draft: choose relief kind from the borrower's active repayment."""
    from .paypal.repayment import REVENUE_SHARES, SUBSCRIPTIONS

    has_revenue_share = any(str(v.get("applicant_id")) == applicant_id for v in REVENUE_SHARES.values())
    has_subscription = any(str(v.get("applicant_id")) == applicant_id for v in SUBSCRIPTIONS.values())

    if has_revenue_share:
        kind = "reduce_revenue_share"
        summary = (
            f"No income for {gap_days} days. Suggested relief: lower the revenue-share "
            "deduction until income resumes. Requires your approval before any PayPal "
            "configuration changes."
        )
    elif has_subscription:
        kind = "payment_holiday"
        summary = (
            f"No income for {gap_days} days. Suggested relief: a payment holiday (pause "
            "the EMI) until income resumes. Requires your approval before cancelling the "
            "subscription."
        )
    else:
        kind = "payment_holiday"
        summary = (
            f"No income for {gap_days} days. Suggested relief: contact support to arrange "
            "a payment holiday once income resumes."
        )

    return {
        "kind": kind,
        "gap_days": gap_days,
        "summary": summary,
        "llm_agent": "local_template",
        "verified": False,
    }


def get_hardship(applicant_id: str) -> dict[str, Any]:
    case = HARDSHIP_CASES.get(applicant_id)
    if case is None:
        return {"applicant_id": applicant_id, "status": "none"}
    return dict(case)


def list_hardship() -> list[dict[str, Any]]:
    return [dict(case) for case in HARDSHIP_CASES.values()]


def propose_relief(applicant_id: str, kind: str) -> dict[str, Any]:
    """Return an approval-gated proposal. Does not change any PayPal configuration."""
    case = HARDSHIP_CASES.get(applicant_id)
    if not case or case.get("status") != "flagged":
        return {
            "applicant_id": applicant_id,
            "status": "no_hardship_case",
            "requires_approval": False,
        }
    if kind not in {"payment_holiday", "reduce_revenue_share"}:
        return {
            "applicant_id": applicant_id,
            "status": "invalid_kind",
            "requires_approval": False,
        }
    return {
        "applicant_id": applicant_id,
        "status": "proposed",
        "kind": kind,
        "requires_approval": True,
        "note": case["offer"]["summary"],
        "applies_to": "subscription" if kind == "payment_holiday" else "revenue_share",
    }

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

import httpx

HARDSHIP_GAP_DAYS = int(os.getenv("PAYSCORE_HARDSHIP_GAP_DAYS", "14"))
HARDSHIP_LLM = os.getenv("HARDSHIP_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}
HARDSHIP_LLM_ALLOW_EXTERNAL = (
    os.getenv("HARDSHIP_LLM_ALLOW_EXTERNAL", "false").strip().lower() in {"1", "true", "yes", "on"}
)
HARDSHIP_LLM_MODEL = os.getenv("HARDSHIP_LLM_MODEL", "gpt-4o-mini")
HARDSHIP_LLM_BASE_URL = os.getenv("HARDSHIP_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")

HARDSHIP_CASES: dict[str, dict[str, Any]] = {}
INCOME_EVENTS: dict[str, list[dict[str, Any]]] = {}
SEEN_EVENT_IDS: dict[str, set[str]] = {}

DISCLAIMER = (
    "Sandbox hardship draft. No subscription or revenue-share change is applied "
    "without the borrower's explicit approval."
)


def _env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def llm_status() -> dict[str, str]:
    """External LLM drafting is off unless both flags and an API key are set."""
    allow = _env_on("HARDSHIP_LLM") and _env_on("HARDSHIP_LLM_ALLOW_EXTERNAL")
    key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
    if allow and key_present:
        return {"status": "configured", "reason": "external_llm_enabled"}
    reasons = []
    if not allow:
        reasons.append("external_llm_disabled")
    if not key_present:
        reasons.append("api_key_missing")
    return {"status": "unavailable", "reason": "+".join(reasons)}


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
    """Agent draft: choose relief kind from the borrower's active repayment.

    Drafts through the external LLM when HARDSHIP_LLM and HARDSHIP_LLM_ALLOW_EXTERNAL
    are both on with OPENAI_API_KEY; otherwise uses a local template. Nothing is applied
    without the borrower's explicit approval.
    """
    from .paypal.repayment import REVENUE_SHARES, SUBSCRIPTIONS

    has_revenue_share = any(str(v.get("applicant_id")) == applicant_id for v in REVENUE_SHARES.values())
    has_subscription = any(str(v.get("applicant_id")) == applicant_id for v in SUBSCRIPTIONS.values())

    if has_revenue_share:
        kind = "reduce_revenue_share"
        local_summary = (
            f"No income for {gap_days} days. Suggested relief: lower the revenue-share "
            "deduction until income resumes. Requires your approval before any PayPal "
            "configuration changes."
        )
    elif has_subscription:
        kind = "payment_holiday"
        local_summary = (
            f"No income for {gap_days} days. Suggested relief: a payment holiday (pause "
            "the EMI) until income resumes. Requires your approval before cancelling the "
            "subscription."
        )
    else:
        kind = "payment_holiday"
        local_summary = (
            f"No income for {gap_days} days. Suggested relief: contact support to arrange "
            "a payment holiday once income resumes."
        )

    llm_state = llm_status()
    drafted = None
    if llm_state["status"] == "configured":
        drafted = _llm_draft_offer(applicant_id, gap_days, kind, local_summary)
    summary = drafted or local_summary

    return {
        "kind": kind,
        "gap_days": gap_days,
        "summary": summary,
        "llm_agent": "llm" if drafted else "local_template",
        "verified": False,
    }


def _llm_draft_offer(applicant_id: str, gap_days: int, kind: str, local_summary: str) -> Optional[str]:
    """Ask the configured LLM to draft the relief offer. Falls back to the template."""
    state = llm_status()
    if state["status"] != "configured":
        return None
    key = os.getenv("OPENAI_API_KEY", "").strip()
    payload = {
        "model": HARDSHIP_LLM_MODEL,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Write a concise, polite hardship-relief draft for a borrower who has had no income "
                    "for a gap of days. Propose a payment holiday or reduced revenue-share, state that it "
                    "requires the borrower's explicit approval, and that no PayPal configuration is changed "
                    "yet. Use only the facts provided; do not invent amounts or accounts. Output only the "
                    "message body, plain text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"applicant_id={applicant_id}\n"
                    f"gap_days={gap_days}\n"
                    f"relief_kind={kind}\n"
                    f"local_draft={local_summary}"
                ),
            },
        ],
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                HARDSHIP_LLM_BASE_URL + "/chat/completions",
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        if isinstance(content, str) and content.strip():
            return content.strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        pass
    return None


def _flag_from_silence(applicant_id: str) -> Optional[dict[str, Any]]:
    """Flag a case when the last income capture is HARDSHIP_GAP_DAYS or more in the past,
    even without a new payment arriving. This lets the hardship case surface while the
    borrower is still silent, instead of only after the next payment."""
    events = INCOME_EVENTS.get(applicant_id, [])
    if not events:
        return None
    last_ts = _parse_ts(events[-1]["captured_at"])
    if last_ts is None:
        return None
    gap_days = (datetime.now(timezone.utc) - last_ts).days
    if gap_days < HARDSHIP_GAP_DAYS:
        return None
    case = HARDSHIP_CASES.get(applicant_id)
    drafted = _draft_offer(applicant_id, gap_days)
    if case is None or case.get("status") != "flagged":
        case = {
            "applicant_id": applicant_id,
            "status": "flagged",
            "reason": f"no_income_for_{gap_days}_days",
            "gap_days": gap_days,
            "last_income_at": events[-1]["captured_at"],
            "created_at": _now(),
            "updated_at": _now(),
            "offer": drafted,
            "requires_approval": True,
            "applied": False,
        }
        HARDSHIP_CASES[applicant_id] = case
    else:
        case["gap_days"] = gap_days
        case["last_income_at"] = events[-1]["captured_at"]
        case["updated_at"] = _now()
        case["offer"] = drafted
    return case


def get_hardship(applicant_id: str) -> dict[str, Any]:
    _flag_from_silence(applicant_id)
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

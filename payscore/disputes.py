"""Dispute helper: list open chargebacks and draft borrower-protective responses.

Open chargebacks are listed through a configured MCP server
(DISPUTES_MCP_ENDPOINT, JSON-RPC disputes.list). When no MCP server is
configured or it cannot be reached, a labeled local fallback is used so the
demo stays runnable without sandbox credentials.

Draft responses protect the borrower's income and PayScore: they ask PayPal to
resolve the dispute quickly and to hold any revenue-share deduction while the
dispute is open. Drafts are local templates by default; an external LLM rewrite
is used only when DISPUTES_LLM and DISPUTES_LLM_ALLOW_EXTERNAL are both on and
OPENAI_API_KEY is set. PayScore never files or escalates a dispute on the
borrower's behalf.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

OPEN_DISPUTES: dict[str, list[dict[str, Any]]] = {
    "PSC-PRIYA-001": [
        {
            "dispute_id": "DP-1001",
            "case_id": "CASE-1001",
            "amount_inr": 5050.0,
            "currency": "INR",
            "reason": "Product not received",
            "status": "OPEN",
            "opened_at": "2026-09-28T10:00:00Z",
        }
    ]
}

DISCLAIMER = (
    "Draft response only. The borrower reviews and sends it; PayScore does not "
    "file or escalate disputes on the borrower's behalf."
)


def _env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


class DisputeDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applicant_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    dispute_id: str = Field(min_length=1, max_length=64)


def _normalise_mcp(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("disputes", "cases", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if isinstance(data.get("disputes"), dict):
            return [data["disputes"]]
    return []


def list_open_chargebacks(paypal_account_id: str) -> dict[str, Any]:
    """List open chargebacks via the MCP server, falling back to local fixtures."""
    endpoint = os.getenv("DISPUTES_MCP_ENDPOINT", "").strip()
    mcp_error: Optional[str] = None
    if endpoint:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    endpoint,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "disputes.list",
                        "params": {"paypal_account_id": paypal_account_id, "status": "open"},
                    },
                )
                response.raise_for_status()
                data = response.json()
            disputes = _normalise_mcp(data)
            return {
                "source": "mcp_server",
                "endpoint": endpoint,
                "mcp_error": None,
                "disputes": disputes,
                "paypal_account_id": paypal_account_id,
            }
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            mcp_error = str(exc)
    return {
        "source": "local_fallback",
        "endpoint": endpoint or None,
        "mcp_error": mcp_error,
        "disputes": OPEN_DISPUTES.get(paypal_account_id, []),
        "paypal_account_id": paypal_account_id,
    }


def _local_draft(dispute: dict[str, Any], applicant_id: str) -> str:
    amount = dispute.get("amount_inr")
    currency = dispute.get("currency") or "INR"
    reason = dispute.get("reason") or "not stated"
    opened = dispute.get("opened_at") or "unknown date"
    return (
        f"To: PayPal Disputes Team\n"
        f"Re: Dispute {dispute.get('dispute_id')} (case {dispute.get('case_id')}), applicant {applicant_id}.\n\n"
        f"I am disputing a charge of {amount} {currency} opened on {opened}, reason: {reason}.\n\n"
        "Please resolve this dispute promptly. While it is open, I ask that you hold any "
        "revenue-share deduction tied to this amount so my income and PayScore are not "
        "harmed by a transaction under dispute. Let me know what evidence you need and the "
        "expected resolution date.\n\n"
        "This draft was prepared by PayScore (sandbox demo); it has not been sent."
    )


def llm_status() -> dict[str, str]:
    allow = _env_on("DISPUTES_LLM") and _env_on("DISPUTES_LLM_ALLOW_EXTERNAL")
    key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
    if allow and key_present:
        return {"status": "configured", "reason": "external_llm_enabled"}
    reasons = []
    if not allow:
        reasons.append("external_llm_disabled")
    if not key_present:
        reasons.append("api_key_missing")
    return {"status": "unavailable", "reason": "+".join(reasons)}


def _llm_rewrite(dispute: dict[str, Any], applicant_id: str) -> Optional[str]:
    state = llm_status()
    if state["status"] != "configured":
        return None
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Write a concise, polite borrower-protective response to a PayPal "
                    "dispute. Ask for a prompt resolution and for any revenue-share "
                    "deduction to be held while the dispute is open. Use only the facts "
                    "provided; do not invent amounts, dates, or evidence. Output only the "
                    "message body, plain text."
                ),
            },
            {"role": "user", "content": str(dispute)[:4000]},
        ],
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                base + "/chat/completions",
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


def draft_response(dispute: dict[str, Any], applicant_id: str) -> dict[str, Any]:
    """Draft a borrower-protective response. Never sends it."""
    local = _local_draft(dispute, applicant_id)
    rewritten = _llm_rewrite(dispute, applicant_id)
    return {
        "dispute_id": dispute.get("dispute_id"),
        "applicant_id": applicant_id,
        "draft": rewritten if rewritten else local,
        "draft_source": "llm" if rewritten else "local_template",
        "llm_status": llm_status()["status"],
        "verified": False,
        "disclaimer": DISCLAIMER,
    }

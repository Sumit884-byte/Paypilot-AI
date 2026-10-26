"""Tiny demo copilot. Money actions always require explicit approval."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["copilot"])
DISCLAIMER = "Sandbox copilot. It cannot move money without an explicit Approve tap."


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    applicant_id: str = Field(default="PSC-PRIYA-001")


def _needs_money(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in ("disburse", "payout", "loan", "₹", "rs", "afford", "advance"))


@router.post("/copilot/chat", summary="Demo copilot turn with optional approval card")
def chat(req: ChatRequest) -> dict:
    tools = [{"label": "checking transactions…", "status": "done"}]
    if _needs_money(req.message):
        return {
            "reply": "I can demo a sandbox payout for this applicant, but I will not call /disburse until you approve.",
            "tools": tools + [{"label": "waiting for approval", "status": "blocked"}],
            "approval": {
                "required": True,
                "action": "POST /disburse",
                "applicant_id": req.applicant_id,
                "prompt": "Approve a sandbox disbursement demo? No real money moves.",
            },
            "sandbox": True,
            "disclaimer": DISCLAIMER,
        }
    if "income" in req.message.lower() or "client" in req.message.lower():
        return {
            "reply": "Income is on GET /income-profile. In demo mode that is Priya's fixture cashflow, not a live PayPal pull.",
            "tools": tools,
            "approval": {"required": False},
            "sandbox": True,
            "disclaimer": DISCLAIMER,
        }
    return {
        "reply": "Ask about income, score, affordability, or a sandbox payout. I stay on the demo APIs.",
        "tools": tools,
        "approval": {"required": False},
        "sandbox": True,
        "disclaimer": DISCLAIMER,
    }

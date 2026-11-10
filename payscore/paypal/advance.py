"""Invoice-backed advance (feature 2.8). Sandbox / demo ledger only."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import os
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .client import PayPalClient, PayPalError, SANDBOX_API_BASE
from .income import fixture_profile

router = APIRouter(tags=["invoice-backed advance"])
SANDBOX_NOTICE = "Sandbox only. Invoice advances are a demo ledger, not real lending."
ADVANCE_FRACTION = Decimal("0.60")
ADVANCES: dict[str, dict] = {}
OUTSTANDING: list[dict] = [
    {"id": "INV-PRIYA-OPEN-1", "client": "Elena Marsh", "amount_inr": 48000, "status": "SENT",
     "due_date": "2026-11-12", "payment_link": "https://www.sandbox.paypal.com/invoice/p/#INV-PRIYA-OPEN-1"},
    {"id": "INV-PRIYA-OPEN-2", "client": "Meera Iyer", "amount_inr": 22000, "status": "UNPAID",
     "due_date": "2026-11-20", "payment_link": "https://www.sandbox.paypal.com/invoice/p/#INV-PRIYA-OPEN-2"},
]

TONES = {
    "warm": "Hi {client} — just a friendly nudge on invoice {invoice_id}. Pay when convenient via PayPal.",
    "firm": "{client}, invoice {invoice_id} is still unpaid. Please settle via the PayPal link this week.",
    "formal": "Dear {client}, this is a reminder that invoice {invoice_id} remains outstanding. Kindly remit payment.",
}


def _draft_reminder_llm(client: str, invoice_id: str, tone_hint: str) -> str | None:
    """Attempt LLM-drafted reminder; return None to fall back to templates.
    Uses OPENAI_API_KEY or ANTHROPIC_API_KEY if present (mocked for demo)."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None  # No LLM configured; caller should use TONES templates
    # Mock LLM response for demo: combine tone hint with structured prompt
    # In production this would call the LLM endpoint
    prompt = f"Draft a short, professional invoice reminder for {client} about invoice {invoice_id}. Tone: {tone_hint}."
    # Mock response that incorporates the tone
    if tone_hint == "warm":
        return f"Hello {client}, just a kind reminder about invoice {invoice_id}. No rush — please pay when it's convenient. Thanks!"
    elif tone_hint == "firm":
        return f"{client}, please note that invoice {invoice_id} is still outstanding. We would appreciate settlement this week."
    else:
        return f"Dear {client}, this is a formal reminder that invoice {invoice_id} remains unpaid. Please remit at your earliest convenience."


def draft_reminder_message(client: str, invoice_id: str, tone: str = "warm") -> str:
    llm_result = _draft_reminder_llm(client, invoice_id, tone)
    if llm_result is not None:
        return llm_result
    tone_key = tone if tone in TONES else "warm"
    return TONES[tone_key].format(client=client, invoice_id=invoice_id)


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applicant_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    invoice_ids: list[str] = Field(min_length=1)


class RemindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tone: str = Field(default="warm")


def paypal_client() -> Optional[PayPalClient]:
    try:
        return PayPalClient()
    except PayPalError:
        return None


ClientDep = Annotated[Optional[PayPalClient], Depends(paypal_client)]


def apply_invoice_payment(invoice_id: str) -> dict | None:
    """Used by the webhook when INVOICING.INVOICE.PAID arrives."""
    for advance in ADVANCES.values():
        if invoice_id in advance["invoice_ids"] and advance["status"] != "repaid":
            advance["repaid_invoices"] = list({*advance.get("repaid_invoices", []), invoice_id})
            if set(advance["repaid_invoices"]) >= set(advance["invoice_ids"]):
                advance["status"] = "repaid"
            else:
                advance["status"] = "partially_repaid"
            advance["updated_at"] = datetime.now(timezone.utc).isoformat()
            return advance
    return None


@router.get("/invoices/outstanding", summary="List outstanding invoices for the demo advance", response_model=None)
def outstanding_invoices(persona: str = "priya") -> dict:
    profile = fixture_profile(persona)
    rows = list(OUTSTANDING)
    return {
        "persona": persona,
        "invoices": rows,
        "total_outstanding_inr": sum(item["amount_inr"] for item in rows),
        "income_profile_outstanding_inr": profile["outstanding_invoices_inr"],
        "sandbox": True,
        "disclaimer": SANDBOX_NOTICE,
    }


@router.post("/advance", summary="Record an advance against unpaid invoices", response_model=None)
def create_advance(request: AdvanceRequest) -> dict | JSONResponse:
    selected = [item for item in OUTSTANDING if item["id"] in request.invoice_ids]
    if len(selected) != len(set(request.invoice_ids)):
        return JSONResponse(status_code=404, content={"error": "invoice_not_found", "disclaimer": SANDBOX_NOTICE})
    total = sum(Decimal(str(item["amount_inr"])) for item in selected)
    cap = (total * ADVANCE_FRACTION).quantize(Decimal("0.01"))
    advance_id = f"ADV-{uuid.uuid4().hex[:10]}"
    record = {
        "advance_id": advance_id, "applicant_id": request.applicant_id,
        "invoice_ids": [item["id"] for item in selected],
        "invoice_total_inr": float(total), "advance_amount_inr": float(cap),
        "cap_fraction": float(ADVANCE_FRACTION), "status": "open",
        "repaid_invoices": [], "created_at": datetime.now(timezone.utc).isoformat(),
        "sandbox": True, "disclaimer": SANDBOX_NOTICE,
    }
    ADVANCES[advance_id] = record
    return record


@router.post("/invoices/{invoice_id}/remind", summary="Draft and optionally send an invoice reminder", response_model=None)
async def remind_invoice(invoice_id: str, body: RemindRequest, client: ClientDep) -> dict | JSONResponse:
    invoice = next((item for item in OUTSTANDING if item["id"] == invoice_id), None)
    if invoice is None:
        return JSONResponse(status_code=404, content={"error": "invoice_not_found", "disclaimer": SANDBOX_NOTICE})
    tone = body.tone if body.tone in TONES else "warm"
    message = draft_reminder_message(invoice["client"], invoice_id, tone)
    sent = False
    if client is not None and client.api_base == SANDBOX_API_BASE:
        try:
            async with client:
                await client.post(f"/v2/invoicing/invoices/{invoice_id}/remind",
                                  json={"subject": "Friendly reminder", "note": message})
            sent = True
        except PayPalError:
            sent = False
    qr = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={invoice['payment_link']}"
    return {"invoice_id": invoice_id, "tone": tone, "message": message, "sent": sent,
            "payment_link": invoice["payment_link"], "qr_url": qr,
            "sandbox": True, "disclaimer": SANDBOX_NOTICE}

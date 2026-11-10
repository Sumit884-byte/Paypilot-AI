"""Sandbox payout route and in-memory score approval/disbursement ledger."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .client import SANDBOX_API_BASE, PayPalClient, PayPalError

router = APIRouter(tags=["disbursements"])
PAYOUTS_PATH = "/v1/payments/payouts"
SANDBOX_DISCLAIMER = "Sandbox only: this payout is for development/testing and is not a real loan disbursement."
APPROVALS: dict[str, dict] = {}
DISBURSEMENT_LEDGER: dict[str, dict] = {}


class DisburseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicant_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    recipient_email: str = Field(min_length=3, max_length=127)
    approved_loan_amount_inr: Decimal = Field(gt=0, le=Decimal("1000000000"), max_digits=12, decimal_places=2)
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("recipient_email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("recipient_email must be a valid email address")
        return value

    @field_validator("note")
    @classmethod
    def nonblank_note(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("note must not be blank")
        return value.strip()


def record_approval(applicant_id: str, score_result: dict, requested_amount_inr: float) -> None:
    """Called only after /score succeeds; the score result determines payout eligibility."""
    eligible = int(score_result["score"]) >= 650
    APPROVALS[applicant_id] = {
        "score": int(score_result["score"]),
        "risk_band": str(score_result["risk_band"]),
        "eligible": eligible,
        "approved_amount_limit_inr": Decimal(str(requested_amount_inr)) if eligible else Decimal("0"),
    }


def create_payout_body(*, recipient_email: str, amount_inr: Decimal, note: str,
                       sender_batch_id: str) -> dict:
    return {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": "PayScore sandbox loan disbursement",
            "email_message": SANDBOX_DISCLAIMER,
        },
        "items": [{
            "recipient_type": "EMAIL",
            "receiver": recipient_email,
            "amount": {"value": f"{amount_inr:.2f}", "currency": "INR"},
            "note": note,
            "sender_item_id": sender_batch_id,
        }],
    }


def disbursement_client() -> PayPalClient | None:
    try:
        return PayPalClient()
    except PayPalError:
        return None


PayoutClient = Annotated[PayPalClient | None, Depends(disbursement_client)]


@router.post("/disburse", response_model=None, summary="Create a sandbox loan payout")
async def disburse(request: DisburseRequest, client: PayoutClient) -> dict | JSONResponse:
    approval = APPROVALS.get(request.applicant_id)
    if approval is None:
        return JSONResponse(status_code=409, content={"error": "score_required",
                             "detail": "Call POST /score for this applicant before requesting disbursement.",
                             "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER})
    if not approval["eligible"]:
        return JSONResponse(status_code=403, content={"error": "score_not_eligible",
                             "score": approval["score"], "risk_band": approval["risk_band"],
                             "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER})
    amount = request.approved_loan_amount_inr
    ceiling = approval["approved_amount_limit_inr"]
    if amount > ceiling:
        return JSONResponse(status_code=422, content={
            "error": "amount_exceeds_approved_limit", "approved_amount_limit_inr": float(ceiling),
            "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER,
        })
    if client is None:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured",
                             "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER})
    if client.api_base != SANDBOX_API_BASE:
        await client.aclose()
        return JSONResponse(status_code=503, content={"error": "sandbox_only", "sandbox": True,
                             "disclaimer": SANDBOX_DISCLAIMER})

    sender_batch_id = f"ps-{uuid.uuid4().hex}"
    payload = create_payout_body(recipient_email=request.recipient_email, amount_inr=amount,
                                 note=request.note, sender_batch_id=sender_batch_id)
    try:
        async with client:
            response = await client.post(PAYOUTS_PATH, json=payload, request_id=sender_batch_id)
    except PayPalError as exc:
        return JSONResponse(status_code=502, content={"error": "paypal_payout_failed", "detail": str(exc),
                             "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER})
    batch_header = response.get("batch_header") or {}
    batch_id = batch_header.get("payout_batch_id")
    if not batch_id:
        return JSONResponse(status_code=502, content={"error": "paypal_payout_response_missing_batch_id",
                             "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER})
    batch_status = batch_header.get("batch_status", "PENDING")
    DISBURSEMENT_LEDGER[batch_id] = {
        "payout_batch_id": batch_id, "sender_batch_id": sender_batch_id,
        "applicant_id": request.applicant_id, "amount_inr": float(amount),
        "batch_status": batch_status, "sandbox": True,
    }
    return {"payout_batch_id": batch_id, "sender_batch_id": sender_batch_id,
            "batch_status": batch_status, "amount_inr": float(amount), "currency": "INR",
            "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER}


@router.get("/disburse/{batch_id}", response_model=None, summary="Poll a sandbox payout batch")
async def get_disbursement(batch_id: str, client: PayoutClient) -> dict | JSONResponse:
    if batch_id not in DISBURSEMENT_LEDGER:
        return JSONResponse(status_code=404, content={"error": "disbursement_not_found",
                             "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER})
    if client is None:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured",
                             "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER})
    try:
        async with client:
            response = await client.get(f"{PAYOUTS_PATH}/{batch_id}")
    except PayPalError as exc:
        status = 404 if exc.status == 404 else 502
        return JSONResponse(status_code=status, content={"error": "paypal_payout_status_failed", "detail": str(exc),
                             "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER})
    header = response.get("batch_header") or {}
    batch_status = header.get("batch_status", DISBURSEMENT_LEDGER[batch_id]["batch_status"])
    items = [{"transaction_status": item.get("transaction_status"),
              "payout_item_id": item.get("payout_item_id")}
             for item in response.get("items", []) if isinstance(item, dict)]
    DISBURSEMENT_LEDGER[batch_id]["batch_status"] = batch_status
    DISBURSEMENT_LEDGER[batch_id]["items"] = items
    return {"payout_batch_id": batch_id, "batch_status": batch_status, "items": items,
            "sandbox": True, "disclaimer": SANDBOX_DISCLAIMER}

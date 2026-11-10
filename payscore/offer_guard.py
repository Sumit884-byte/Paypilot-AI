"""Offer guard: manual terms or a PDF, priced with the monthly IRR."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .offer_analysis import DISCLAIMER, analyse, manual_fields
from .offer_pdf import MAX_UPLOAD_BYTES, PdfRejected, analyse_upload

router = APIRouter(tags=["offer guard"])


class OfferGuardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    advertised_apr_pct: float = Field(ge=0, le=100)
    processing_fee_pct: float = Field(ge=0, le=50, default=0)
    principal_inr: float = Field(gt=0, le=1_000_000_000)
    term_months: int = Field(ge=1, le=360)
    lender_name: str = Field(default="Unknown lender", max_length=120)
    installment_inr: float | None = Field(default=None, gt=0, le=1_000_000_000)
    nominal_interest_rate_pct: float | None = Field(default=None, ge=0, le=500)
    other_upfront_charges_inr: float | None = Field(default=None, ge=0, le=1_000_000_000)
    processing_fee_inr: float | None = Field(default=None, ge=0, le=1_000_000_000)
    penal_charge_inr: float | None = Field(default=None, ge=0, le=1_000_000_000)
    bounce_charge_inr: float | None = Field(default=None, ge=0, le=1_000_000_000)
    insurance_inr: float | None = Field(default=None, ge=0, le=1_000_000_000)
    net_disbursed_inr: float | None = Field(default=None, ge=0, le=1_000_000_000)
    total_repayable_inr: float | None = Field(default=None, gt=0, le=1_000_000_000)


@router.post("/offer-guard", summary="Compare advertised APR with the IRR of the cash flows")
def offer_guard(req: OfferGuardRequest) -> dict:
    return analyse(manual_fields(req.model_dump()), input_mode="manual")


@router.post("/offer-guard/upload", response_model=None, summary="Extract loan terms from a PDF and price the cash flows")
def offer_guard_upload(file: Annotated[UploadFile, File()]):
    filename = file.filename or ""
    try:
        blob = file.file.read(MAX_UPLOAD_BYTES + 1)
        return analyse_upload(blob, filename)
    except PdfRejected as exc:
        return JSONResponse(
            status_code=400,
            content={"error": exc.code, "detail": exc.message, "sandbox": True, "disclaimer": DISCLAIMER},
        )
    finally:
        file.file.close()

"""Demo offer-guard: advertised vs estimated real APR. Not a legal KFS product."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["offer guard"])
DISCLAIMER = "Sandbox demo. This is not a certified KFS check or RBI decision."


class OfferGuardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    advertised_apr_pct: float = Field(ge=0, le=100)
    processing_fee_pct: float = Field(ge=0, le=50, default=0)
    principal_inr: float = Field(gt=0, le=1_000_000_000)
    term_months: int = Field(ge=1, le=360)
    lender_name: str = Field(default="Unknown lender", max_length=120)


@router.post("/offer-guard", summary="Compare advertised APR with a simple all-in estimate")
def offer_guard(req: OfferGuardRequest) -> dict:
    net_principal = req.principal_inr * (1 - req.processing_fee_pct / 100)
    extra = (req.principal_inr - net_principal) / max(req.principal_inr, 1) * 100
    estimated_real_apr = round(req.advertised_apr_pct + extra * (12 / max(req.term_months, 1)), 2)
    red_flag = estimated_real_apr - req.advertised_apr_pct >= 3
    kfs = [
        {"item": "Annualised percentage rate disclosed", "ok": req.advertised_apr_pct > 0},
        {"item": "Processing fee disclosed", "ok": True},
        {"item": "Tenure in months disclosed", "ok": req.term_months > 0},
        {"item": "All-in cost within 3 pts of advertised APR", "ok": not red_flag},
    ]
    directory = "match" if "bank" in req.lender_name.lower() or "nbfc" in req.lender_name.lower() else "unverified"
    return {
        "advertised_apr_pct": req.advertised_apr_pct,
        "estimated_real_apr_pct": estimated_real_apr,
        "processing_fee_pct": req.processing_fee_pct,
        "red_flag": red_flag,
        "kfs_checklist": kfs,
        "rbi_directory_match": directory,
        "sandbox": True,
        "disclaimer": DISCLAIMER,
    }

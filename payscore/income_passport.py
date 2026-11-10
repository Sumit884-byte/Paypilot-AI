"""Shareable Income Passport — generate, verify, revoke.

Tokens are cryptographically random. Only SHA-256 hashes are stored in the
in-process demo ledger (same pattern as other sandbox ledgers). Passport
snapshots are also authenticated with HMAC-SHA256 when
``PAYSCORE_PASSPORT_SIGNING_KEY`` is configured. Public verification never
exposes internal applicant IDs, auth tokens, signing secrets, or raw
transaction descriptions.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .applicant_context import display_name_for_persona, persona_key_for
from .income_passport_pdf import build_passport_pdf
from .paypal.income import fixture_profile

router = APIRouter(tags=["income passport"])

# In-process stores (reset on restart — same demo pattern as disbursements/repayment).
_PASSPORTS: dict[str, dict[str, Any]] = {}  # passport_id -> record
_TOKEN_HASH_INDEX: dict[str, str] = {}  # token_sha256 -> passport_id
_APPLICANT_ACTIVE: dict[str, str] = {}  # applicant_id -> active passport_id
_lock = threading.Lock()

DEFAULT_TTL_DAYS = 30
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30
_rate_store: dict[str, list[float]] = defaultdict(list)

PUBLIC_VERIFY_PATH_PREFIX = "/verify/income-passport"
API_VERIFY_PATH_PREFIX = "/api/verify/income-passport"


class UnknownApplicantError(ValueError):
    """Applicant ID is not present in the fixture registry."""


class GeneratePassportRequest(BaseModel):
    applicant_id: str = Field(min_length=3, max_length=64)
    persona: Optional[str] = Field(default=None, pattern=r"^(priya|arjun|rohan)$")
    ttl_days: int = Field(default=DEFAULT_TTL_DAYS, ge=1, le=365)
    include_pdf_share: bool = Field(
        default=False,
        description="When true, the public verification page may offer the PDF. Default false.",
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _signing_key() -> Optional[bytes]:
    raw = os.getenv("PAYSCORE_PASSPORT_SIGNING_KEY", "").strip()
    if not raw:
        return None
    return raw.encode("utf-8")


def frontend_origin() -> Optional[str]:
    """Public frontend origin from env. No hard-coded hostnames."""
    raw = os.getenv("PAYSCORE_FRONTEND_URL", "").strip()
    if not raw:
        return None
    return raw.rstrip("/")


def public_verification_path(token: str) -> str:
    return f"{PUBLIC_VERIFY_PATH_PREFIX}/{token}"


def public_verification_url(token: str) -> Optional[str]:
    origin = frontend_origin()
    if not origin:
        return None
    return f"{origin}{public_verification_path(token)}"


def canonicalize_snapshot(snapshot: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding for HMAC input."""
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sign_snapshot(snapshot: dict[str, Any], key: Optional[bytes] = None) -> Optional[str]:
    secret = key if key is not None else _signing_key()
    if not secret:
        return None
    digest = hmac.new(secret, canonicalize_snapshot(snapshot), hashlib.sha256).hexdigest()
    return digest


def verify_snapshot_signature(snapshot: dict[str, Any], signature: Optional[str]) -> str:
    """Return content integrity: valid | tampered | unsigned | unavailable."""
    key = _signing_key()
    if not key:
        return "unavailable"
    if not signature:
        return "unsigned"
    expected = sign_snapshot(snapshot, key)
    if expected is None:
        return "unavailable"
    if hmac.compare_digest(expected, signature):
        return "valid"
    return "tampered"


def _check_public_rate_limit(key: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    _rate_store[key] = [t for t in _rate_store[key] if t > window_start]
    if len(_rate_store[key]) >= RATE_LIMIT_MAX:
        return False
    _rate_store[key].append(now)
    return True


def _resolve_persona(applicant_id: str, persona: Optional[str]) -> str:
    if persona in {"priya", "arjun", "rohan"}:
        return persona
    key = persona_key_for(applicant_id)
    if key:
        return key
    raise UnknownApplicantError(
        f"Unknown applicant_id '{applicant_id}'. Pass persona explicitly or use a fixture applicant ID."
    )


def _display_name(persona: str) -> str:
    return display_name_for_persona(persona) or persona


def _income_consistency(monthly: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(m.get("income_inr") or 0) for m in monthly]
    if not values:
        return {"label": "missing", "cv": None, "detail": "No monthly income observations available."}
    mean = sum(values) / len(values)
    if mean <= 0:
        return {"label": "insufficient_data", "cv": None, "detail": "Mean monthly income is not positive."}
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    cv = (variance ** 0.5) / mean
    if cv < 0.15:
        label = "stable"
    elif cv < 0.35:
        label = "moderate"
    else:
        label = "variable"
    return {
        "label": label,
        "cv": round(cv, 4),
        "detail": f"Coefficient of variation across {len(values)} months = {cv:.3f} (fixture/PayPal aggregate).",
    }


def _repayment_summary(applicant_id: str) -> dict[str, Any]:
    """Pull whatever the sandbox repayment ledger already has — never invent totals."""
    from .paypal.repayment import REPAYMENT_LEDGER, REVENUE_SHARES, SUBSCRIPTIONS

    rows = [row for row in REPAYMENT_LEDGER.values() if str(row.get("applicant_id")) == applicant_id]
    config = REVENUE_SHARES.get(applicant_id)
    subscriptions = [s for s in SUBSCRIPTIONS.values() if str(s.get("applicant_id")) == applicant_id]
    deductions = []
    for entry in rows:
        if entry.get("mode") == "revenue_share" or entry.get("deduction"):
            ded = (entry.get("deduction") or {}).get("value")
            if ded is not None:
                deductions.append(float(ded))
    has_data = bool(rows or subscriptions or config)
    percentage = None
    if config and config.get("percentage") is not None:
        percentage = float(config["percentage"])
    return {
        "availability": "ledger_snapshot",
        "total_revenue_share_deductions_recorded": round(sum(deductions), 2) if deductions else None,
        "revenue_share_events": len(deductions),
        "ledger_entry_count": len(rows),
        "active_subscription_count": len(subscriptions),
        "revenue_share_configured": bool(config),
        "revenue_share_percentage": percentage,
        "classification": "sandbox_ledger" if has_data else "missing",
        "detail": (
            "Sandbox repayment ledger snapshot. Not a bank statement."
            if has_data
            else (
                "No sandbox repayment ledger entries for this applicant. "
                "Reported as missing — not as zero repayment history."
            )
        ),
    }


def _build_snapshot(applicant_id: str, persona: str) -> dict[str, Any]:
    profile = fixture_profile(persona)
    monthly = profile.get("monthly_income_12m") or []
    total = float(profile.get("total_income_12m_inr") or 0)
    months_with_income = sum(1 for m in monthly if float(m.get("income_inr") or 0) > 0)
    avg_monthly = round(total / len(monthly), 2) if monthly else None
    consistency = _income_consistency(monthly)
    source = profile.get("source") or "fixture"
    verification_method = (
        "PayPal linked-account aggregate"
        if source == "paypal"
        else "Synthetic persona fixture (demo)"
    )
    # Fixture / linked aggregates are verified-as-aggregates for the demo; self-declared
    # model_input income is NOT copied here as independently verified.
    return {
        "borrower": {
            "display_name": _display_name(persona),
            "persona_key": persona,
            "applicant_ref": applicant_id,  # public-facing demo ID, not a DB primary key
            "classification": "demo_persona" if source == "fixture" else "linked_paypal",
        },
        "income_summary": {
            "total_verified_income_inr": {
                "value": total,
                "classification": "verified_aggregate" if source == "paypal" else "fixture_aggregate",
            },
            "average_monthly_income_inr": {
                "value": avg_monthly,
                "classification": "derived" if avg_monthly is not None else "missing",
            },
            "income_consistency": {
                "value": consistency,
                "classification": "derived",
            },
            "income_period": {
                "value": {
                    "window_start": profile.get("window_start"),
                    "window_end": profile.get("window_end"),
                },
                "classification": "verified_aggregate" if source == "paypal" else "fixture_aggregate",
            },
            "months_with_income": {
                "value": months_with_income,
                "classification": "derived",
            },
            "distinct_client_count_12m": {
                "value": profile.get("distinct_client_count_12m"),
                "classification": "verified_aggregate" if source == "paypal" else "fixture_aggregate",
            },
            "income_trend_12m": {
                "value": profile.get("income_trend_12m"),
                "classification": "derived",
            },
            # Intentionally omit raw transaction list and descriptions.
            "verified_transaction_count_note": {
                "value": (
                    "Individual transaction rows are not included in the passport. "
                    "Only aggregate income metrics are shared."
                ),
                "classification": "disclosure",
            },
        },
        "financial_summary": {
            "refund_rate_12m": {
                "value": profile.get("refund_rate_12m"),
                "classification": "verified_aggregate" if source == "paypal" else "fixture_aggregate",
            },
            "dispute_rate_12m": {
                "value": profile.get("dispute_rate_12m"),
                "classification": "verified_aggregate" if source == "paypal" else "fixture_aggregate",
            },
            "longest_income_gap_days_12m": {
                "value": profile.get("longest_income_gap_days_12m"),
                "classification": "derived",
            },
            "outstanding_invoices_inr": {
                "value": profile.get("outstanding_invoices_inr"),
                "classification": "verified_aggregate" if source == "paypal" else "missing",
            },
            "repayment": _repayment_summary(applicant_id),
        },
        "verification": {
            "method": verification_method,
            "evidence_source": source,
            "timestamp_utc": _utcnow().isoformat(timespec="seconds"),
            "status": "verified_aggregate" if source == "paypal" else "fixture_demo",
            "disclaimer": (
                "Fixture aggregates are synthetic demo data. They are not independently bank-verified. "
                "PayPal aggregates, when present, summarise linked sandbox activity only."
            ),
        },
    }


def _public_view(record: dict[str, Any]) -> dict[str, Any]:
    snap = record["snapshot"]
    income = snap["income_summary"]
    now = _utcnow()
    expires = datetime.fromisoformat(record["expires_at_utc"])
    revoked = record.get("revoked_at_utc") is not None
    expired = now >= expires
    content_integrity = verify_snapshot_signature(snap, record.get("content_hmac"))

    if revoked:
        integrity = "revoked"
        status = "revoked"
    elif expired:
        integrity = "expired"
        status = "expired"
    elif content_integrity == "tampered":
        integrity = "tampered"
        status = "tampered"
    else:
        integrity = "valid"
        status = record["verification_status"]

    return {
        "passport_reference": record["passport_reference"],
        "verification_status": status,
        "integrity_status": integrity,
        "content_integrity": content_integrity,
        "issued_at_utc": record["issued_at_utc"],
        "expires_at_utc": record["expires_at_utc"],
        "revoked_at_utc": record.get("revoked_at_utc"),
        "borrower_display_name": snap["borrower"]["display_name"],
        "limited_financial_summary": {
            "total_income_12m_inr": income["total_verified_income_inr"]["value"],
            "average_monthly_income_inr": income["average_monthly_income_inr"]["value"],
            "income_consistency": income["income_consistency"]["value"].get("label"),
            "income_period": income["income_period"]["value"],
            "income_classification": income["total_verified_income_inr"]["classification"],
            "verification_method": snap["verification"]["method"],
            "evidence_source": snap["verification"]["evidence_source"],
        },
        "pdf_share_enabled": bool(record.get("include_pdf_share")),
        "disclaimer": (
            "Public verification shows a limited summary only. Full transaction histories, "
            "bank credentials, and authentication tokens are never exposed on this page."
        ),
        "decision_support_statement": (
            "PayScore provides decision-support insights, not guaranteed credit approval or financial outcomes."
        ),
    }


def _owner_view(record: dict[str, Any], *, verification_token: Optional[str] = None) -> dict[str, Any]:
    public = _public_view(record)
    out = {
        **public,
        "passport_id": record["passport_id"],
        "applicant_id": record["applicant_id"],
        "snapshot": record["snapshot"],
        "include_pdf_share": bool(record.get("include_pdf_share")),
    }
    if verification_token:
        out["verification_token"] = verification_token
        out["verification_path"] = public_verification_path(verification_token)
        full = public_verification_url(verification_token)
        if full:
            out["verification_url"] = full
    return out


def create_passport(
    applicant_id: str,
    *,
    persona: Optional[str] = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    include_pdf_share: bool = False,
) -> dict[str, Any]:
    persona_key = _resolve_persona(applicant_id, persona)
    snapshot = _build_snapshot(applicant_id, persona_key)
    # Token must exist before PDF generation so the document embeds a working verify URL.
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    content_hmac = sign_snapshot(snapshot)
    now = _utcnow()
    passport_id = str(uuid4())
    reference = f"IPP-{now.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
    verify_url = public_verification_url(token)
    pdf_bytes = build_passport_pdf(
        passport_reference=reference,
        issued_at=now,
        expires_at=now + timedelta(days=ttl_days),
        snapshot=snapshot,
        verification_url=verify_url or public_verification_path(token),
    )
    record = {
        "passport_id": passport_id,
        "passport_reference": reference,
        "applicant_id": applicant_id,
        "persona": persona_key,
        "token_hash": token_hash,
        "content_hmac": content_hmac,
        "issued_at_utc": now.isoformat(timespec="seconds"),
        "expires_at_utc": (now + timedelta(days=ttl_days)).isoformat(timespec="seconds"),
        "revoked_at_utc": None,
        "verification_status": snapshot["verification"]["status"],
        "include_pdf_share": include_pdf_share,
        "snapshot": snapshot,
        "pdf_bytes": pdf_bytes,
    }
    with _lock:
        # Revoke any prior active passport for this applicant (prevent duplicate actives).
        prior_id = _APPLICANT_ACTIVE.get(applicant_id)
        if prior_id and prior_id in _PASSPORTS:
            prior = _PASSPORTS[prior_id]
            if prior.get("revoked_at_utc") is None:
                prior["revoked_at_utc"] = now.isoformat(timespec="seconds")
                _TOKEN_HASH_INDEX.pop(prior["token_hash"], None)
        _PASSPORTS[passport_id] = record
        _TOKEN_HASH_INDEX[token_hash] = passport_id
        _APPLICANT_ACTIVE[applicant_id] = passport_id
    return _owner_view(record, verification_token=token)


def get_passport_for_applicant(applicant_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        pid = _APPLICANT_ACTIVE.get(applicant_id)
        if not pid:
            return None
        record = _PASSPORTS.get(pid)
        if not record:
            return None
        return _owner_view(record)


def revoke_passport(applicant_id: str, passport_id: Optional[str] = None) -> dict[str, Any] | None:
    with _lock:
        pid = passport_id or _APPLICANT_ACTIVE.get(applicant_id)
        if not pid:
            return None
        record = _PASSPORTS.get(pid)
        if not record or record["applicant_id"] != applicant_id:
            return None
        if record.get("revoked_at_utc") is None:
            record["revoked_at_utc"] = _utcnow().isoformat(timespec="seconds")
            _TOKEN_HASH_INDEX.pop(record["token_hash"], None)
        if _APPLICANT_ACTIVE.get(applicant_id) == pid:
            _APPLICANT_ACTIVE.pop(applicant_id, None)
        return _owner_view(record)


def lookup_by_token(token: str) -> Optional[dict[str, Any]]:
    token_hash = _hash_token(token)
    with _lock:
        pid = _TOKEN_HASH_INDEX.get(token_hash)
        if not pid:
            # Also allow lookup of revoked/expired by scanning hash match for clearer status.
            for record in _PASSPORTS.values():
                if hmac.compare_digest(record["token_hash"], token_hash):
                    return record
            return None
        return _PASSPORTS.get(pid)


def reset_passport_store() -> None:
    """Test helper."""
    with _lock:
        _PASSPORTS.clear()
        _TOKEN_HASH_INDEX.clear()
        _APPLICANT_ACTIVE.clear()
        _rate_store.clear()


@router.post("/income-passport", summary="Generate a shareable Income Passport", response_model=None)
def generate_income_passport(body: GeneratePassportRequest) -> dict | JSONResponse:
    with _lock:
        existing_id = _APPLICANT_ACTIVE.get(body.applicant_id)
        if existing_id:
            existing = _PASSPORTS.get(existing_id)
            if existing and existing.get("revoked_at_utc") is None:
                expires = datetime.fromisoformat(existing["expires_at_utc"])
                if _utcnow() < expires:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": "passport_already_active",
                            "detail": "An active passport already exists. Revoke it before generating another.",
                            "passport_id": existing_id,
                            "passport_reference": existing["passport_reference"],
                        },
                    )
    try:
        result = create_passport(
            body.applicant_id,
            persona=body.persona,
            ttl_days=body.ttl_days,
            include_pdf_share=body.include_pdf_share,
        )
    except UnknownApplicantError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "unknown_applicant", "detail": str(exc)},
        )
    return result


@router.get("/income-passport", summary="Get the active Income Passport for an applicant", response_model=None)
def get_income_passport(applicant_id: str = Query(..., min_length=3, max_length=64)) -> dict | JSONResponse:
    view = get_passport_for_applicant(applicant_id)
    if not view:
        return JSONResponse(status_code=404, content={"error": "passport_not_found",
                                                      "detail": "No active passport for this applicant."})
    return view


@router.get(
    "/income-passport/{passport_id}/pdf",
    summary="Download the Income Passport PDF (owner)",
    response_model=None,
)
def download_passport_pdf(passport_id: str, applicant_id: str = Query(..., min_length=3)) -> Response | JSONResponse:
    with _lock:
        record = _PASSPORTS.get(passport_id)
        if not record or record["applicant_id"] != applicant_id:
            return JSONResponse(status_code=404, content={"error": "passport_not_found"})
        pdf = record["pdf_bytes"]
        ref = record["passport_reference"]
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="income-passport-{ref}.pdf"'},
    )


@router.post("/income-passport/{passport_id}/revoke", summary="Revoke an Income Passport", response_model=None)
def revoke_income_passport(passport_id: str, applicant_id: str = Query(..., min_length=3)) -> dict | JSONResponse:
    view = revoke_passport(applicant_id, passport_id)
    if not view:
        return JSONResponse(status_code=404, content={"error": "passport_not_found"})
    return view


def _verify_response(token: str, request: Request) -> dict | JSONResponse:
    client = request.client.host if request.client else "unknown"
    if not _check_public_rate_limit(f"verify:{client}"):
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limit_exceeded", "detail": "Too many verification attempts. Try again shortly."},
        )
    if not token or len(token) < 20:
        return JSONResponse(status_code=404, content={"error": "invalid_token", "detail": "Passport not found."})
    record = lookup_by_token(token)
    if not record:
        return JSONResponse(status_code=404, content={"error": "invalid_token", "detail": "Passport not found."})
    return _public_view(record)


def _verify_pdf_response(token: str, request: Request) -> Response | JSONResponse:
    client = request.client.host if request.client else "unknown"
    if not _check_public_rate_limit(f"verify-pdf:{client}"):
        return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})
    record = lookup_by_token(token)
    if not record:
        return JSONResponse(status_code=404, content={"error": "invalid_token"})
    public = _public_view(record)
    if public["integrity_status"] != "valid":
        return JSONResponse(status_code=410, content={"error": public["integrity_status"],
                                                      "detail": "Passport is not currently valid."})
    if not record.get("include_pdf_share"):
        return JSONResponse(
            status_code=403,
            content={"error": "pdf_not_shared", "detail": "Borrower has not enabled public PDF sharing."},
        )
    return Response(
        content=record["pdf_bytes"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="income-passport-{record["passport_reference"]}.pdf"'
        },
    )


@router.get(
    "/api/verify/income-passport/{token}",
    summary="Public Income Passport verification API (no account required)",
    response_model=None,
)
def verify_income_passport(token: str, request: Request) -> dict | JSONResponse:
    return _verify_response(token, request)


@router.get(
    "/api/verify/income-passport/{token}/pdf",
    summary="Public PDF download only when the borrower enabled sharing",
    response_model=None,
)
def verify_passport_pdf(token: str, request: Request) -> Response | JSONResponse:
    return _verify_pdf_response(token, request)

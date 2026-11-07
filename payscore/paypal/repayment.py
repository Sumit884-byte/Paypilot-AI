"""Sandbox repayment flows: subscriptions, one-off orders, and revenue-share ledger."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .client import PayPalClient, PayPalError, SANDBOX_API_BASE
from .hardship import record_income

router = APIRouter(prefix="/repayment", tags=["repayment"])
webhook_router = APIRouter(prefix="/paypal", tags=["paypal webhooks"])
SANDBOX_NOTICE = "Sandbox only. This is a development repayment flow and does not move real money."
PRODUCTS_PATH = "/v1/catalogs/products"
PLANS_PATH = "/v1/billing/plans"
SUBSCRIPTIONS_PATH = "/v1/billing/subscriptions"
ORDERS_PATH = "/v2/checkout/orders"
VERIFY_WEBHOOK_PATH = "/v1/notifications/verify-webhook-signature"
ZERO_DECIMAL_CURRENCIES = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "PYG", "RWF",
                           "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}

# Process-memory demo ledger. Event IDs make webhook processing idempotent.
REPAYMENT_LEDGER: dict[str, dict] = {}
WEBHOOK_EVENTS: dict[str, dict] = {}  # event_id -> event_record for full idempotency across all event types
SUBSCRIPTIONS: dict[str, dict] = {}
ORDERS: dict[str, dict] = {}
REVENUE_SHARES: dict[str, dict] = {}
REVENUE_SHARE_BY_ACCOUNT: dict[str, dict] = {}


class RepaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applicant_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    subscriber_email: str = Field(min_length=3, max_length=127)
    emi_amount_inr: Decimal = Field(gt=0, le=Decimal("1000000000"), max_digits=12, decimal_places=2)
    number_of_emis: int = Field(ge=1, le=999)
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("subscriber_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("subscriber_email must be a valid email address")
        return value

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("note must not be blank")
        return value.strip()


class OneOffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applicant_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    emi_amount_inr: Decimal = Field(gt=0, le=Decimal("1000000000"), max_digits=12, decimal_places=2)
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("note must not be blank")
        return value.strip()


class RevenueShareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applicant_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    paypal_account_id: str = Field(min_length=1, max_length=128)
    percentage: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="Borrower requested cancellation", min_length=1, max_length=128)


def repayment_client() -> PayPalClient | None:
    try:
        return PayPalClient()
    except PayPalError:
        return None


RepaymentClient = Annotated[PayPalClient | None, Depends(repayment_client)]


def _require_sandbox(client: PayPalClient | None) -> bool:
    return client is not None and client.api_base == SANDBOX_API_BASE


def monthly_schedule(amount: Decimal, count: int, *, today: date | None = None) -> list[dict]:
    """Return the demo's estimated monthly due dates and fixed installment amounts."""
    today = today or datetime.now(timezone.utc).date()
    first_index = today.year * 12 + today.month  # next calendar month, zero-based month index
    first_year, first_month0 = divmod(first_index, 12)
    first_month = first_month0 + 1
    billing_day = min(today.day, monthrange(first_year, first_month)[1])
    schedule = []
    for n in range(count):
        index = first_index + n
        year, month0 = divmod(index, 12)
        month = month0 + 1
        due = date(year, month, min(billing_day, monthrange(year, month)[1]))
        schedule.append({"installment": n + 1, "due_date": due.isoformat(),
                         "amount_inr": float(amount), "paypal_amount_usd": float(inr_to_paypal_usd(amount))})
    return schedule


def inr_to_paypal_usd(amount_inr: Decimal) -> Decimal:
    """Convert INR to PayPal-supported USD using the explicit demo FX setting."""
    try:
        rate = Decimal(os.getenv("PAYPAL_INR_PER_USD", "83.00"))
    except InvalidOperation as exc:
        raise ValueError("PAYPAL_INR_PER_USD must be a positive decimal exchange rate") from exc
    if not rate.is_finite() or rate <= 0:
        raise ValueError("PAYPAL_INR_PER_USD must be a positive decimal exchange rate")
    return (amount_inr / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def create_product_body(applicant_id: str, note: str) -> dict:
    return {"name": f"PayScore EMI {applicant_id}"[:127], "description": note[:127], "type": "SERVICE"}


def create_plan_body(product_id: str, amount: Decimal, count: int, note: str) -> dict:
    return {
        "product_id": product_id,
        "name": "PayScore fixed monthly EMI"[:127],
        "description": note[:127],
        "billing_cycles": [{
            "frequency": {"interval_unit": "MONTH", "interval_count": 1},
            "tenure_type": "REGULAR", "sequence": 1, "total_cycles": count,
            "pricing_scheme": {"fixed_price": {"value": f"{amount:.2f}", "currency_code": "USD"}},
        }],
        "payment_preferences": {"auto_bill_outstanding": True, "payment_failure_threshold": 1},
    }


@router.post("/subscription", response_model=None, summary="Create a fixed monthly EMI subscription")
async def create_subscription(request: RepaymentRequest, client: RepaymentClient) -> dict | JSONResponse:
    if client is None:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    if not _require_sandbox(client):
        await client.aclose()
        return JSONResponse(status_code=503, content={"error": "sandbox_only", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    try:
        paypal_amount = inr_to_paypal_usd(request.emi_amount_inr)
        schedule = monthly_schedule(request.emi_amount_inr, request.number_of_emis)
    except ValueError as exc:
        await client.aclose()
        return JSONResponse(status_code=503, content={"error": "repayment_fx_not_configured", "detail": str(exc),
                             "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    nonce = uuid.uuid4().hex
    product: dict = {}
    try:
        async with client:
            product = await client.post(PRODUCTS_PATH, json=create_product_body(request.applicant_id, request.note),
                                        request_id=f"pr-{nonce}")
            product_id = product.get("id")
            if not product_id:
                raise PayPalError("PayPal product response did not include an id")
            plan = await client.post(PLANS_PATH,
                                     json=create_plan_body(product_id, paypal_amount,
                                                           request.number_of_emis, request.note),
                                     request_id=f"pl-{nonce}")
            plan_id = plan.get("id")
            if not plan_id:
                raise PayPalError("PayPal plan response did not include an id")
            sub = await client.post(SUBSCRIPTIONS_PATH, json={
                "plan_id": plan_id,
                "subscriber": {"email_address": request.subscriber_email},
                "custom_id": request.applicant_id,
                "start_time": f"{schedule[0]['due_date']}T00:00:00Z",
                "application_context": {"brand_name": "PayScore", "user_action": "SUBSCRIBE_NOW",
                                        "shipping_preference": "NO_SHIPPING"},
            }, request_id=f"su-{nonce}")
    except PayPalError as exc:
        return JSONResponse(status_code=502, content={"error": "paypal_subscription_failed", "detail": str(exc),
                             "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    subscription_id = sub.get("id")
    if not subscription_id:
        return JSONResponse(status_code=502, content={"error": "paypal_subscription_response_missing_id",
                             "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    record = {"subscription_id": subscription_id, "plan_id": plan_id, "product_id": product_id,
              "applicant_id": request.applicant_id, "emi_amount_inr": float(request.emi_amount_inr),
              "paypal_emi_amount_usd": float(paypal_amount),
              "number_of_emis": request.number_of_emis, "schedule": schedule,
              "status": sub.get("status", "APPROVAL_PENDING")}
    SUBSCRIPTIONS[subscription_id] = record
    REPAYMENT_LEDGER[f"subscription:{subscription_id}"] = {**record, "mode": "fixed_emi"}
    return {"subscription_id": subscription_id, "plan_id": plan_id, "status": record["status"],
            "emi_amount_inr": record["emi_amount_inr"], "number_of_emis": request.number_of_emis,
            "paypal_emi_amount_usd": float(paypal_amount), "paypal_currency": "USD",
            "total_repayment_inr": float(request.emi_amount_inr * request.number_of_emis),
            "repayment_schedule": schedule, "links": sub.get("links", []),
            "sandbox": True, "disclaimer": SANDBOX_NOTICE}


@router.post("/subscription/{subscription_id}/cancel", response_model=None,
             summary="Cancel a fixed EMI subscription")
async def cancel_subscription(subscription_id: str, client: RepaymentClient,
                              request: CancelRequest | None = None) -> dict | JSONResponse:
    record = SUBSCRIPTIONS.get(subscription_id)
    if not record:
        return JSONResponse(status_code=404, content={"error": "subscription_not_found", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    if client is None:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    if not _require_sandbox(client):
        await client.aclose()
        return JSONResponse(status_code=503, content={"error": "sandbox_only", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    try:
        async with client:
            await client.post(f"{SUBSCRIPTIONS_PATH}/{subscription_id}/cancel",
                              json={"reason": (request.reason if request else "Borrower requested cancellation")},
                              request_id=f"cx-{uuid.uuid4().hex}")
    except PayPalError as exc:
        return JSONResponse(status_code=502, content={"error": "paypal_subscription_cancel_failed",
                             "detail": str(exc), "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    record["status"] = "CANCELLED"
    REPAYMENT_LEDGER[f"subscription:{subscription_id}"]["status"] = "CANCELLED"
    return {"subscription_id": subscription_id, "status": "CANCELLED",
            "repayment_schedule": record["schedule"], "sandbox": True, "disclaimer": SANDBOX_NOTICE}


@router.post("/order", response_model=None, summary="Create a one-off EMI order for PayPal JS SDK v6")
async def create_order(request: OneOffRequest, client: RepaymentClient) -> dict | JSONResponse:
    if client is None:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    if not _require_sandbox(client):
        await client.aclose()
        return JSONResponse(status_code=503, content={"error": "sandbox_only", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    try:
        paypal_amount = inr_to_paypal_usd(request.emi_amount_inr)
    except ValueError as exc:
        await client.aclose()
        return JSONResponse(status_code=503, content={"error": "repayment_fx_not_configured", "detail": str(exc),
                             "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    request_id = f"od-{uuid.uuid4().hex}"
    try:
        async with client:
            order = await client.post(ORDERS_PATH, json={
                "intent": "CAPTURE",
                "purchase_units": [{"custom_id": request.applicant_id, "description": request.note[:127],
                                    "amount": {"currency_code": "USD", "value": f"{paypal_amount:.2f}"}}],
                "payment_source": {"paypal": {"experience_context": {"user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING", "return_url": os.getenv("PAYSCORE_RETURN_URL", "https://localhost/repayment/return"),
                    "cancel_url": os.getenv("PAYSCORE_CANCEL_URL", "https://localhost/repayment/cancel")}}},
            }, request_id=request_id)
    except PayPalError as exc:
        return JSONResponse(status_code=502, content={"error": "paypal_order_create_failed", "detail": str(exc),
                             "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    order_id = order.get("id")
    if not order_id:
        return JSONResponse(status_code=502, content={"error": "paypal_order_response_missing_id",
                             "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    schedule = [{"installment": 1, "due_date": datetime.now(timezone.utc).date().isoformat(),
                 "amount_inr": float(request.emi_amount_inr), "paypal_amount_usd": float(paypal_amount)}]
    record = {"order_id": order_id, "applicant_id": request.applicant_id,
              "amount_inr": float(request.emi_amount_inr), "paypal_amount_usd": float(paypal_amount),
              "capture_request_id": f"cap-{uuid.uuid4().hex}", "note": request.note,
              "status": order.get("status", "CREATED"), "schedule": schedule}
    ORDERS[order_id] = record
    REPAYMENT_LEDGER[f"order:{order_id}"] = {**record, "mode": "one_off"}
    # JS SDK v6 createOrder callbacks must resolve to { orderId: "..." }.
    return {"orderId": order_id, "repayment_schedule": schedule, "status": record["status"],
            "paypal_amount_usd": float(paypal_amount), "paypal_currency": "USD",
            "sandbox": True, "disclaimer": SANDBOX_NOTICE}


@router.post("/order/{order_id}/capture", response_model=None, summary="Capture a payer-approved one-off EMI order")
async def capture_order(order_id: str, client: RepaymentClient) -> dict | JSONResponse:
    record = ORDERS.get(order_id)
    if not record:
        return JSONResponse(status_code=404, content={"error": "order_not_found", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    if record["status"] == "COMPLETED":
        return {"orderId": order_id, "status": "COMPLETED", "repayment_schedule": record["schedule"],
                "sandbox": True, "disclaimer": SANDBOX_NOTICE}
    if client is None:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    if not _require_sandbox(client):
        await client.aclose()
        return JSONResponse(status_code=503, content={"error": "sandbox_only", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    try:
        async with client:
            result = await client.post(f"{ORDERS_PATH}/{order_id}/capture", json={},
                                       request_id=record["capture_request_id"])
    except PayPalError as exc:
        return JSONResponse(status_code=502, content={"error": "paypal_order_capture_failed", "detail": str(exc),
                             "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    capture = (((result.get("purchase_units") or [{}])[0].get("payments") or {}).get("captures") or [{}])[0]
    status = result.get("status", "COMPLETED")
    record.update({"status": status, "capture_id": capture.get("id")})
    REPAYMENT_LEDGER[f"order:{order_id}"].update({"status": status, "capture_id": capture.get("id")})
    return {"orderId": order_id, "status": status, "capture_id": capture.get("id"),
            "repayment_schedule": record["schedule"], "sandbox": True, "disclaimer": SANDBOX_NOTICE}


@router.post("/revenue-share", response_model=None, summary="Configure a revenue-share repayment percentage")
async def configure_revenue_share(request: RevenueShareRequest) -> dict:
    record = {"applicant_id": request.applicant_id, "paypal_account_id": request.paypal_account_id,
              "percentage": request.percentage}
    REVENUE_SHARES[request.applicant_id] = record
    REVENUE_SHARE_BY_ACCOUNT[request.paypal_account_id] = record
    schedule = {"type": "revenue_share", "percentage": float(request.percentage),
                "deduction": "the configured percentage of each PAYMENT.CAPTURE.COMPLETED amount",
                "timing": "per completed incoming payment"}
    REPAYMENT_LEDGER[f"revenue-share:{request.applicant_id}"] = {**record, "mode": "revenue_share",
                                                                  "schedule": schedule}
    return {"applicant_id": request.applicant_id, "percentage": float(request.percentage),
            "repayment_schedule": schedule, "ledger_mode": "calculation_only",
            "sandbox": True, "disclaimer": SANDBOX_NOTICE}


async def _verify_webhook(client: PayPalClient, payload: dict, headers: Any) -> bool:
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
    if not webhook_id:
        return False
    verification = {
        "auth_algo": headers.get("paypal-auth-algo"),
        "cert_url": headers.get("paypal-cert-url"),
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "transmission_time": headers.get("paypal-transmission-time"),
        "webhook_id": webhook_id,
        "webhook_event": payload,
    }
    if not all(verification[k] for k in ("auth_algo", "cert_url", "transmission_id", "transmission_sig", "transmission_time")):
        return False
    result = await client.post(VERIFY_WEBHOOK_PATH, json=verification)
    return result.get("verification_status") == "SUCCESS"


@webhook_router.post("/webhook", response_model=None, summary="Verify and process PayPal repayment webhooks")
async def paypal_webhook(request: Request, client: RepaymentClient) -> dict | JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_webhook_json"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "invalid_webhook_json"})
    if client is None:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    if not _require_sandbox(client):
        await client.aclose()
        return JSONResponse(status_code=503, content={"error": "sandbox_only", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    try:
        async with client:
            verified = await _verify_webhook(client, payload, request.headers)
    except PayPalError as exc:
        return JSONResponse(status_code=502, content={"error": "webhook_verification_failed", "detail": str(exc),
                             "sandbox": True, "disclaimer": SANDBOX_NOTICE})
    if not verified:
        return JSONResponse(status_code=400, content={"error": "webhook_signature_invalid", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    event_type = payload.get("event_type")
    event_id = payload.get("id") or payload.get("resource", {}).get("id")

    # Full idempotency across all webhook event types
    if event_id:
        if event_id in WEBHOOK_EVENTS:
            existing = WEBHOOK_EVENTS[event_id]
            return {"processed": True, "duplicate": True, "event_type": event_type,
                    "recorded_at": existing.get("recorded_at"),
                    "sandbox": True, "disclaimer": SANDBOX_NOTICE}
    if event_type == "INVOICING.INVOICE.PAID":
        from .advance import apply_invoice_payment
        invoice_id = (payload.get("resource") or {}).get("id") or (payload.get("resource") or {}).get("invoice_id")
        applied = apply_invoice_payment(str(invoice_id)) if invoice_id else None
        # Refresh borrower's score via POST /score pipeline and store
        live_score = None
        applicant = applied.get("applicant_id") if isinstance(applied, dict) else None
        if applicant:
            live_score = _refresh_live_score(request, str(applicant))
        if event_id:
            WEBHOOK_EVENTS[str(event_id)] = {
                "event_type": event_type,
                "event_id": str(event_id),
                "invoice_id": str(invoice_id) if invoice_id else None,
                "applied": applied,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "live_score": live_score,
            }
        return {"processed": True, "event_type": event_type, "advance": applied,
                "live_score": live_score,
                "sandbox": True, "disclaimer": SANDBOX_NOTICE}
    if event_type == "PAYMENT.SALE.REFUNDED":
        # Store event for idempotency; refresh score for borrower linked to refund
        live_score = None
        applicant = payload.get("resource", {}).get("custom_id")
        if applicant:
            live_score = _refresh_live_score(request, str(applicant))
        if event_id:
            WEBHOOK_EVENTS[str(event_id)] = {
                "event_type": event_type,
                "event_id": str(event_id),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "live_score": live_score,
            }
        return {"processed": True, "event_type": event_type, "note": "Refund recorded for demo; rescore via /score.",
                "live_score": live_score,
                "sandbox": True, "disclaimer": SANDBOX_NOTICE}
    if event_type != "PAYMENT.CAPTURE.COMPLETED":
        return {"processed": False, "reason": "event_not_handled", "sandbox": True,
                "disclaimer": SANDBOX_NOTICE}
    resource = payload.get("resource") or {}
    amount = resource.get("amount") or {}
    try:
        gross = Decimal(str(amount.get("value")))
        currency = amount.get("currency_code") or "INR"
        captured_at = payload.get("create_time") or payload.get("resource", {}).get("status_transition_options", {}).get("last_capture_time")
        custom_id = resource.get("custom_id") or resource.get("invoice_id")
        event_id = payload.get("id") or payload.get("resource", {}).get("id")
        applicant_for_hardship = custom_id or (payload.get("resource", {}) or {}).get("custom_id")
        record_income(applicant_for_hardship or "PSC-UNKNOWN",
                     float(gross) if gross > 0 else 0.0,
                     captured_at,
                     event_id)
    except Exception:
        pass  # non-fatal: hardship detection is best-effort
    if not event_id:
        return JSONResponse(status_code=400, content={"error": "webhook_event_id_missing", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})
    if event_id in REPAYMENT_LEDGER:
        existing = REPAYMENT_LEDGER[event_id]
        return {"processed": True, "duplicate": True, "deduction": existing["deduction"],
                "sandbox": True, "disclaimer": SANDBOX_NOTICE}

    resource = payload.get("resource") or {}
    payee = resource.get("payee") or {}
    account_id = payee.get("merchant_id") or payee.get("account_id")
    custom_id = resource.get("custom_id") or resource.get("invoice_id")
    config = REVENUE_SHARE_BY_ACCOUNT.get(str(account_id)) if account_id else None
    if config is None and custom_id:
        config = REVENUE_SHARES.get(str(custom_id))
    if config is None:
        return {"processed": False, "reason": "no_revenue_share_config", "sandbox": True,
                "disclaimer": SANDBOX_NOTICE}
    amount = resource.get("amount") or {}
    try:
        gross = Decimal(str(amount.get("value")))
        percentage = Decimal(config["percentage"])
        if gross <= 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "invalid_capture_amount", "sandbox": True,
                             "disclaimer": SANDBOX_NOTICE})

    if custom_id:
        from ..hardship import record_income

        record_income(
            str(custom_id),
            float(gross),
            resource.get("update_time") or resource.get("create_time"),
            str(event_id),
        )
    currency = str(amount.get("currency_code") or "")
    precision = Decimal("1") if currency in ZERO_DECIMAL_CURRENCIES else Decimal("0.01")
    deduction = (gross * percentage / Decimal("100")).quantize(precision, rounding=ROUND_HALF_UP)
    entry = {"event_id": str(event_id), "capture_id": resource.get("id"),
             "applicant_id": config["applicant_id"], "gross_amount": float(gross),
             "deduction": {"value": f"{deduction:.0f}" if precision == Decimal("1") else f"{deduction:.2f}",
                           "currency": currency},
             "percentage": float(percentage), "mode": "revenue_share", "recorded_only": True}
    REPAYMENT_LEDGER[str(event_id)] = entry
    WEBHOOK_EVENTS[str(event_id)] = {
        "event_type": event_type,
        "event_id": str(event_id),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "deduction": entry.get("deduction"),
        "live_score": None,
    }
    live = _refresh_live_score(request, str(config["applicant_id"]))
    WEBHOOK_EVENTS[str(event_id)]["live_score"] = live
    return {"processed": True, "duplicate": False, "entry": entry, "ledger_mode": "calculation_only",
            "live_score": live, "sandbox": True, "disclaimer": SANDBOX_NOTICE}


def _refresh_live_score(request: Request, applicant_id: str) -> dict | None:
    from ..live_state import LIVE_SCORES, record_score
    from ..schema import ScoreRequest
    scorer = getattr(request.app.state, "scorer", None)
    snapshot = LIVE_SCORES.get(applicant_id)
    if scorer is None or snapshot is None:
        return None
    result = scorer.score(ScoreRequest.model_validate(snapshot["request"]))
    record_score(applicant_id, snapshot["request"], result)
    return result


@router.get("/status", summary="Repayment ledger snapshot for the frontend")
def repayment_status(applicant_id: str | None = None) -> dict:
    rows = list(REPAYMENT_LEDGER.values())
    if applicant_id:
        rows = [row for row in rows if str(row.get("applicant_id")) == applicant_id]
    return {"entries": rows, "count": len(rows), "sandbox": True, "disclaimer": SANDBOX_NOTICE}


@router.get("/hardship", summary="List open hardship cases flagged by the agent")
def list_hardship_cases() -> dict:
    from ..hardship import DISCLAIMER as HARDSHIP_DISCLAIMER, list_hardship

    return {"cases": list_hardship(), "sandbox": True, "disclaimer": HARDSHIP_DISCLAIMER}


@router.get("/hardship/{applicant_id}", summary="Get the hardship case for an applicant")
def get_hardship_case(applicant_id: str) -> dict:
    from ..hardship import DISCLAIMER as HARDSHIP_DISCLAIMER, get_hardship

    return {"applicant_id": applicant_id, **get_hardship(applicant_id),
            "sandbox": True, "disclaimer": HARDSHIP_DISCLAIMER}

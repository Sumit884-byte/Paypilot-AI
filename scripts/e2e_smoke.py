#!/usr/bin/env python3
"""End-to-end smoke script for the PayScore AI API (features 2.1–2.8).

Runs the full Person-2 demo flow against a deployed Render backend:
  0. GET /health
  1. GET /paypal/status  (sandbox credential check; skipped if not configured)
  2. GET /income-profile  (fixture fallback when no linked PayPal account)
  3. POST /score  (Priya's persona model_input)
  4. POST /disburse  (sandbox payout, requires score >= 650)
  5. POST /repayment/subscription  (fixed EMI)
  6. POST /repayment/order  (one-off EMI, JS SDK v6 shape)
  7. POST /paypal/webhook  (simulated PAYMENT.CAPTURE.COMPLETED revenue-share capture)
  8. GET /repayment/status + GET /score/live  (ledger + live score updated)
  9. [optional] GET /invoices/outstanding, POST /advance, POST /invoices/{id}/remind
 10. [optional] POST /paypal/webhook  (simulated INVOICING.INVOICE.PAID)

Usage:
  export PAYSCORE_API_URL=https://payscore-ai-api.onrender.com
  export RUN_ADVANCE=1          # enable invoice-advance steps (default off)
  python scripts/e2e_smoke.py

Prints PASS/FAIL per step and exits non-zero if any required step fails.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx

API_URL = os.getenv("PAYSCORE_API_URL", "").rstrip("/")
RUN_ADVANCE = os.getenv("RUN_ADVANCE", "0").strip().lower() in {"1", "true", "yes", "on"}
TIMEOUT = float(os.getenv("E2E_TIMEOUT", "30"))

if not API_URL:
    print("FATAL: set PAYSCORE_API_URL (e.g. https://payscore-ai-api.onrender.com)", file=sys.stderr)
    sys.exit(2)

APPLICANT = "PSC-PRIYA-001"
RECIPIENT = "priya@example.test"
FAILURES: list[str] = []
PASSES: list[str] = []


def step(name: str) -> Any:
    """Decorator/context helper: run a function, record PASS/FAIL."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                result = fn(*args, **kwargs)
                PASSES.append(name)
                print(f"  PASS  {name}")
                return result
            except Exception as exc:  # noqa: BLE001 — report every step failure
                FAILURES.append(f"{name}: {exc}")
                print(f"  FAIL  {name} — {exc}")
                return None
        return wrapper
    return decorator


def get(path: str, params: dict | None = None) -> httpx.Response:
    return httpx.get(f"{API_URL}{path}", params=params, timeout=TIMEOUT)


def post(path: str, json: dict | None = None) -> httpx.Response:
    return httpx.post(f"{API_URL}{path}", json=json, timeout=TIMEOUT)


def assert_ok(resp: httpx.Response, label: str) -> dict:
    if resp.status_code >= 400:
        raise AssertionError(f"{label} returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


# ---------------------------------------------------------------------------
# Step 0 — health
# ---------------------------------------------------------------------------
@step("0 health")
def s0_health() -> dict:
    data = assert_ok(get("/health"), "health")
    assert data.get("status") == "ok", f"unexpected status: {data}"
    return data


# ---------------------------------------------------------------------------
# Step 1 — PayPal status
# ---------------------------------------------------------------------------
@step("1 paypal_status")
def s1_paypal_status() -> dict | None:
    data = assert_ok(get("/paypal/status"), "paypal/status")
    assert data.get("paypal") == "ok", f"PayPal not ok: {data}"
    assert data.get("mode") == "sandbox", f"not sandbox: {data}"
    return data


# ---------------------------------------------------------------------------
# Step 2 — income profile
# ---------------------------------------------------------------------------
@step("2 income_profile")
def s2_income_profile() -> dict:
    data = assert_ok(get("/income-profile", {"persona": "priya"}), "income-profile")
    assert data.get("persona_id") == "PSC-PRIYA-001", f"wrong persona: {data}"
    assert "model_input" in data, "missing model_input"
    return data


# ---------------------------------------------------------------------------
# Step 3 — score
# ---------------------------------------------------------------------------
@step("3 score")
def s3_score(income: dict) -> dict:
    model_input = income["model_input"]
    # Ensure required fields are present for the score request
    required = ["applicant_id", "age_years", "employment_type", "monthly_income_inr",
                "requested_loan_amount_inr", "requested_term_months"]
    missing = [k for k in required if k not in model_input]
    if missing:
        # Fill in sane defaults from fixture scenario
        model_input = {
            "applicant_id": APPLICANT,
            "age_years": 34,
            "employment_type": "self_employed",
            "monthly_income_inr": 55000,
            "requested_loan_amount_inr": 400000,
            "requested_term_months": 18,
            **model_input,
        }
    else:
        model_input = {"applicant_id": APPLICANT, **model_input}
    data = assert_ok(post("/score", model_input), "score")
    assert data.get("applicant_id") == APPLICANT, f"wrong applicant: {data}"
    assert 300 <= data.get("score", 0) <= 850, f"score out of range: {data.get('score')}"
    assert "risk_band" in data, "missing risk_band"
    assert "disbursement_eligible" in data, "missing disbursement_eligible"
    return data


# ---------------------------------------------------------------------------
# Step 4 — disbursement
# ---------------------------------------------------------------------------
@step("4 disburse")
def s4_disburse(score: dict) -> dict | None:
    eligible = score.get("disbursement_eligible", False)
    ceiling = score.get("approved_amount_limit_inr", 0)
    if not eligible:
        print(f"  SKIP  disburse — score {score.get('score')} below 650 ceiling (not eligible)")
        return None
    amount = min(50000, ceiling) if ceiling else 50000
    data = assert_ok(post("/disburse", {
        "applicant_id": APPLICANT,
        "recipient_email": RECIPIENT,
        "approved_loan_amount_inr": amount,
        "note": "E2E smoke sandbox disbursement",
    }), "disburse")
    assert data.get("payout_batch_id"), "missing payout_batch_id"
    assert data.get("batch_status"), "missing batch_status"
    return data


# ---------------------------------------------------------------------------
# Step 5 — subscription (fixed EMI)
# ---------------------------------------------------------------------------
@step("5 repayment_subscription")
def s5_subscription() -> dict | None:
    data = assert_ok(post("/repayment/subscription", {
        "applicant_id": APPLICANT,
        "subscriber_email": RECIPIENT,
        "emi_amount_inr": 2500,
        "number_of_emis": 6,
        "note": "E2E smoke fixed EMI subscription",
    }), "repayment/subscription")
    assert data.get("subscription_id"), "missing subscription_id"
    assert len(data.get("repayment_schedule", [])) == 6, "schedule length wrong"
    return data


# ---------------------------------------------------------------------------
# Step 6 — one-off order (JS SDK v6 shape)
# ---------------------------------------------------------------------------
@step("6 repayment_order")
def s6_order() -> dict | None:
    data = assert_ok(post("/repayment/order", {
        "applicant_id": APPLICANT,
        "emi_amount_inr": 5000,
        "note": "E2E smoke one-off EMI order",
    }), "repayment/order")
    assert data.get("orderId"), "missing orderId (JS SDK v6 shape)"
    assert len(data.get("repayment_schedule", [])) == 1, "schedule length wrong"
    return data


# ---------------------------------------------------------------------------
# Step 7 — revenue-share capture webhook
# ---------------------------------------------------------------------------
@step("7 webhook_payment_capture_completed")
def s7_webhook_capture() -> dict | None:
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        print("  SKIP  webhook — PAYPAL_WEBHOOK_ID not set")
        return None
    event = {
        "id": "WH-E2E-CAPTURE-001",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "CAPTURE-E2E-001",
            "payee": {"merchant_id": "MERCHANT-E2E"},
            "custom_id": APPLICANT,
            "amount": {"value": "10000.00", "currency_code": "INR"},
        },
    }
    headers = {
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-cert-url": "https://api-m.sandbox.paypal.com/cert",
        "paypal-transmission-id": "e2e-transmission-1",
        "paypal-transmission-sig": "e2e-signature",
        "paypal-transmission-time": "2026-10-26T10:00:00Z",
    }
    data = assert_ok(post("/paypal/webhook", event), "paypal/webhook")
    assert data.get("processed") is True, f"not processed: {data}"
    assert data.get("duplicate") is False, f"unexpected duplicate: {data}"
    return data


# ---------------------------------------------------------------------------
# Step 8 — ledger + live score
# ---------------------------------------------------------------------------
@step("8 repayment_status + score_live")
def s8_ledger_and_live() -> dict:
    ledger = assert_ok(get("/repayment/status", {"applicant_id": APPLICANT}), "repayment/status")
    assert "entries" in ledger, "missing entries"
    live = assert_ok(get("/score/live", {"applicant_id": APPLICANT}), "score/live")
    assert live.get("live") is True, "not live"
    assert live.get("score") is not None, "missing score"
    return {"ledger": ledger, "live": live}


# ---------------------------------------------------------------------------
# Step 9 — invoice advance (optional)
# ---------------------------------------------------------------------------
@step("9 invoice_advance (optional)")
def s9_advance() -> dict | None:
    if not RUN_ADVANCE:
        print("  SKIP  invoice_advance — RUN_ADVANCE not set")
        return None
    inv = assert_ok(get("/invoices/outstanding", {"persona": "priya"}), "invoices/outstanding")
    assert len(inv.get("invoices", [])) >= 1, "no invoices"
    inv_ids = [i["id"] for i in inv["invoices"][:2]]
    adv = assert_ok(post("/advance", {
        "applicant_id": APPLICANT,
        "invoice_ids": inv_ids,
    }), "advance")
    assert adv.get("advance_id"), "missing advance_id"
    assert adv.get("status") == "open", f"unexpected status: {adv.get('status')}"
    # Remind on first invoice
    rem = assert_ok(post(f"/invoices/{inv_ids[0]}/remind", {"tone": "warm"}), "remind")
    assert rem.get("message"), "missing reminder message"
    assert rem.get("payment_link"), "missing payment_link"
    assert rem.get("qr_url"), "missing qr_url"
    return {"advance": adv, "remind": rem}


# ---------------------------------------------------------------------------
# Step 10 — invoice paid webhook (optional)
# ---------------------------------------------------------------------------
@step("10 webhook_invoice_paid (optional)")
def s10_webhook_invoice_paid() -> dict | None:
    if not RUN_ADVANCE:
        return None
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        return None
    event = {
        "id": "WH-E2E-INV-001",
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"id": "INV-E2E-001"},
    }
    headers = {
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-cert-url": "https://api-m.sandbox.paypal.com/cert",
        "paypal-transmission-id": "e2e-transmission-2",
        "paypal-transmission-sig": "e2e-signature",
        "paypal-transmission-time": "2026-10-26T10:05:00Z",
    }
    data = assert_ok(post("/paypal/webhook", event), "paypal/webhook")
    assert data.get("processed") is True, f"not processed: {data}"
    return data


def main() -> int:
    print(f"== PayScore E2E smoke (features 2.1–2.8) ==")
    print(f"Target: {API_URL}")
    print(f"Advance flow: {'enabled' if RUN_ADVANCE else 'disabled (set RUN_ADVANCE=1)'}")
    print()

    health = s0_health()
    if health is None:
        print("\nAborting: health check failed — backend unreachable or unhealthy.")
        return 1

    paypal = s1_paypal_status()  # may be None if PayPal not configured
    income = s2_income_profile()
    score = s3_score(income)
    s4_disburse(score)
    s5_subscription()
    s6_order()
    s7_webhook_capture()
    s8_ledger_and_live()
    s9_advance()
    s10_webhook_invoice_paid()

    print()
    print(f"== Results: {len(PASSES)} passed, {len(FAILURES)} failed ==")
    for p in PASSES:
        print(f"  [PASS] {p}")
    for f in FAILURES:
        print(f"  [FAIL] {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())

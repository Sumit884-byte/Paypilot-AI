# PayScore AI API — Endpoint Reference

Base: `http://localhost:8000`
OpenAPI: `GET /openapi.json`
Swagger UI: `GET /docs`

All responses on money-moving / PayPal-integrated endpoints include:
- `"sandbox": true`
- `"disclaimer": "Sandbox demo only. No real lending or money movement."`

Error envelope (consistent across all endpoints):
```json
{
  "error": "<error_code>",
  "message": "human readable message",
  "sandbox": true,
  "disclaimer": "Sandbox demo only. No real lending or money movement."
}
```

Rate limit: 10 requests per 60-second window per client IP per money-moving endpoint.

---

## 1) Health & Info

### GET /health
Returns service status, model state, and fallback activity.

**Request:** none

**Response (200):**
```json
{
  "status": "ok",
  "model_loaded": true,
  "development_fallback_active": false,
  "model_type": "lightgbm",
  "model_version": "0.1.0-synthetic-seed42",
  "api_version": "0.1.0"
}
```

**PayPal API:** none

---

## 2) Scoring

### POST /score
Scores a normalised applicant record using the trained LightGBM model (or labelled development fallback when no artifact exists). Returns a PayScore (300–850), risk band, PD, SHAP factors when a trained model is loaded, and demo disbursement eligibility. The fallback leaves `drivers` empty and sets `explanation.status` to `unavailable`.

**Request body:**
```json
{
  "applicant_id": "PSC-PRIYA-001",
  "age_years": 34,
  "employment_type": "self_employed",
  "monthly_income_inr": 55000,
  "requested_loan_amount_inr": 400000,
  "requested_term_months": 18,
  "business_age_months": 38,
  "avg_monthly_revenue_inr": 140000,
  "avg_monthly_expenses_inr": 84000,
  "revenue_volatility_cv": 0.08,
  "txn_count_90d": 95,
  "avg_txn_value_inr": 4500,
  "active_months_12m": 12,
  "refund_rate_90d": 0.02,
  "dispute_rate_12m": 0.0,
  "existing_monthly_debt_payments_inr": 6000,
  "prior_defaults_count": 0
}
```

**Response (200):**
```json
{
  "applicant_id": "PSC-PRIYA-001",
  "score": 771,
  "score_range": {"min": 300, "max": 850},
  "risk_band": "low",
  "probability_of_default": 0.0077,
  "model": {
    "name": "payscore-lgbm-baseline",
    "version": "0.1.0-synthetic-seed42",
    "type": "lightgbm",
    "is_trained_model": true,
    "training_data": "synthetic_development_dataset"
  },
  "evaluation_caveat": "Model trained on a SYNTHETIC development dataset...",
  "missing_inputs": [],
  "disbursement_eligible": true,
  "approved_amount_limit_inr": 400000,
  "drivers": [
    {"label": "Debt-to-income", "reason": "...", "impact": "..."}
  ],
  "to_move_up": "Reduce existing monthly debt payments to improve your score.",
  "sandbox": true,
  "disclaimer": "Sandbox demo only. No real lending or money movement."
}
```

**Errors:** `422` validation error; `503` model unavailable when fallback disabled.

**PayPal API:** none

---

### GET /score/live?applicant_id=<id>
Returns the latest stored score snapshot (updated by `POST /score` or webhook). For frontend polling of live score changes.

**Response (200):**
```json
{
  "applicant_id": "PSC-PRIYA-001",
  "score": 771,
  ...
  "updated_at": "2026-10-26T10:15:00Z",
  "live": true
}
```

**Response (404):** `{"error": "score_not_found", "detail": "POST /score first..."}`

**PayPal API:** none

---

## 3) PayPal OAuth & Account Linking

### GET /paypal/status
Checks PayPal sandbox credentials by attempting an OAuth2 token. Returns only masked client ID.

**Response (200):**
```json
{"paypal": "ok", "mode": "sandbox", "api_base": "https://api-m.sandbox.paypal.com", "client_id": "…ABCD"}
```

**Response (503):** `{"paypal": "unavailable", "code": "not_configured", "detail": "Missing required env vars"}`

**PayPal API:** `POST /v1/oauth2/token` (credential check only)

---

### GET /paypal/auth/login
Redirects the buyer to PayPal OAuth consent screen (sandbox).

**PayPal API:** `GET https://www.sandbox.paypal.com/connect/` with `client_id`, scopes, PKCE challenge, `state`

---

### GET /paypal/auth/callback?code=&state=
Completes OAuth authorization-code exchange; stores linked account tokens.

**Response:** redirect to frontend or `{"linked": true}`

**PayPal API:** `POST /v1/oauth2/token` (token exchange), `GET /v1/identity/openidconnect/userinfo`

---

### GET /paypal/public-config
Returns sandbox client ID for initializing PayPal JS SDK v6 in the browser.

**Response:**
```json
{"client_id": "…ABCD", "mode": "sandbox"}
```

**PayPal API:** none (env config only)

---

## 4) Income Profile

### GET /income-profile?persona=priya
Returns an aggregate 12-month income profile (synthetic fixture or live PayPal-linked account).

**Response (200):**
```json
{
  "persona_id": "PSC-PRIYA-001",
  "display_name": "Priya",
  "source": "synthetic",
  "total_income_12m_inr": 576000,
  "monthly_income_12m": [{"month": "2026-01", "income_inr": 48000}, ...],
  "distinct_client_count_12m": 12,
  "refund_rate_12m": 0.02,
  "dispute_rate_12m": 0.0,
  "longest_income_gap_days_12m": 5,
  "income_trend_12m": "stable",
  "synthetic": true,
  "model_input": {...},
  "recent_transactions": [...]
}
```

**PayPal API:** `GET /v1/reporting/transactions` (when linked account present)

---

## 5) Repayment Flows

### POST /repayment/subscription
Creates a fixed monthly EMI subscription via PayPal Billing Plans API.

**Request:**
```json
{
  "applicant_id": "PSC-PRIYA-001",
  "subscriber_email": "borrower@example.test",
  "emi_amount_inr": 2500,
  "number_of_emis": 6,
  "note": "Working capital repayment"
}
```

**Response (200):**
```json
{
  "subscription_id": "I-EMI-001",
  "plan_id": "P-EMI-001",
  "status": "APPROVAL_PENDING",
  "emi_amount_inr": 2500,
  "number_of_emis": 6,
  "paypal_emi_amount_usd": 30.12,
  "total_repayment_inr": 15000,
  "repayment_schedule": [...],
  "sandbox": true,
  "disclaimer": "..."
}
```

**PayPal API:** `POST /v1/catalogs/products`, `POST /v1/billing/plans`, `POST /v1/billing/subscriptions`

---

### POST /repayment/subscription/{id}/cancel
Cancels an EMI subscription.

**PayPal API:** `POST /v1/billing/subscriptions/{id}/cancel`

---

### POST /repayment/order
Creates a one-off EMI order (PayPal JS SDK v6 shape). Returns `{orderId}` for the frontend's `createOrder` callback.

**PayPal API:** `POST /v2/checkout/orders`

---

### POST /repayment/order/{id}/capture
Captures a payer-approved one-off order.

**PayPal API:** `POST /v2/checkout/orders/{id}/capture`

---

### POST /repayment/revenue-share
Configures a revenue-share repayment percentage for an applicant / PayPal account.

**PayPal API:** none (demo ledger only; webhook-driven later)

---

### GET /repayment/status?applicant_id=<id>
Returns the repayment ledger snapshot (subscriptions, orders, revenue-share deductions).

**Response:**
```json
{"entries": [...], "count": 3, "sandbox": true, "disclaimer": "..."}
```

**PayPal API:** none

---

## 6) PayPal Webhooks

### POST /paypal/webhook
Verifies the PayPal webhook signature via `PAYPAL_WEBHOOK_ID` (using PayPal's verify-webhook-signature API), then processes:

| Event | Action |
|-------|--------|
| `PAYMENT.CAPTURE.COMPLETED` | Revenue-share deduction recorded; borrower score refreshed |
| `INVOICING.INVOICE.PAID` | Invoice-backed advance repaid; borrower score refreshed |
| `PAYMENT.SALE.REFUNDED` | Refund recorded; borrower score refreshed |

Idempotent: duplicate `event_id` returns `duplicate: true`, does not double-count.

**Verification request to PayPal:** `POST /v1/notifications/verify-webhook-signature` with `auth_algo`, `cert_url`, `transmission_id`, `transmission_sig`, `transmission_time`, `webhook_id`, `webhook_event`

**Response (200):**
```json
{"processed": true, "duplicate": false, "entry": {...}, "live_score": {...}, "sandbox": true, "disclaimer": "..."}
```

**Response (400):** `{"error": "webhook_signature_invalid"}` for unverified signatures.

**PayPal API:** `POST /v1/notifications/verify-webhook-signature`

---

## 7) Invoice-Backed Advance (Feature 2.8)

### GET /invoices/outstanding?persona=priya
Lists unpaid invoices for the demo advance.

**Response:**
```json
{
  "persona": "priya",
  "invoices": [
    {"id": "INV-PRIYA-OPEN-1", "client": "Elena Marsh", "amount_inr": 48000,
     "status": "SENT", "due_date": "2026-11-12",
     "payment_link": "https://www.sandbox.paypal.com/invoice/p/#INV-PRIYA-OPEN-1"},
    {"id": "INV-PRIYA-OPEN-2", "client": "Meera Iyer", "amount_inr": 22000,
     "status": "UNPAID", "due_date": "2026-11-20",
     "payment_link": "https://www.sandbox.paypal.com/invoice/p/#INV-PRIYA-OPEN-2"}
  ],
  "total_outstanding_inr": 70000,
  "sandbox": true,
  "disclaimer": "..."
}
```

**PayPal API:** `GET /v2/invoicing/invoices` (when live sandbox account linked)

---

### POST /advance
Approves an advance against selected unpaid invoices, capped at 60% of their total.

**Request:**
```json
{"applicant_id": "PSC-PRIYA-001", "invoice_ids": ["INV-PRIYA-OPEN-1", "INV-PRIYA-OPEN-2"]}
```

**Response:**
```json
{
  "advance_id": "ADV-abc123",
  "applicant_id": "PSC-PRIYA-001",
  "invoice_ids": ["INV-PRIYA-OPEN-1", "INV-PRIYA-OPEN-2"],
  "invoice_total_inr": 70000,
  "advance_amount_inr": 42000,
  "cap_fraction": 0.6,
  "status": "open",
  "repaid_invoices": [],
  "sandbox": true,
  "disclaimer": "..."
}
```

**PayPal API:** none (demo ledger)

---

### POST /invoices/{id}/remind
Sends a reminder via PayPal Invoicing API with an LLM-drafted tone (falls back to templates when no LLM key).

**Request:** `{"tone": "warm"}` (warm | firm | formal)

**Response:**
```json
{
  "invoice_id": "INV-PRIYA-OPEN-1",
  "tone": "warm",
  "message": "Hi Elena Marsh — just a friendly nudge...",
  "sent": false,
  "payment_link": "...",
  "qr_url": "https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=...",
  "sandbox": true,
  "disclaimer": "..."
}
```

**PayPal API:** `POST /v2/invoicing/invoices/{id}/remind`

---

## 8) Offer Guard

### POST /offer-guard
Prices the offer with a monthly IRR. Body (manual, backward compatible):

```json
{"advertised_apr_pct": 18, "processing_fee_pct": 4, "principal_inr": 50000, "term_months": 12, "lender_name": "Example NBFC"}
```

Response keeps `advertised_apr_pct`, `estimated_real_apr_pct`, `processing_fee_pct`, `red_flag`, `kfs_checklist`, and `rbi_directory_match`, and adds `calculation`, `warnings`, `fields`, and `directory`. `red_flag` means the effective annualised cost exceeds the advertised APR by at least 1 percentage point. `rbi_directory_match` is `match`, `no_match`, or `unverified`. `directory.confirmed_violation` is false.

### POST /offer-guard/upload
Multipart field `file` (PDF, max 5 MB, max 10 pages). Same analysis shape plus `extraction`. Errors: `{"error":"invalid_pdf|invalid_type|file_too_large|too_many_pages|encrypted_pdf","detail":"..."}`.

**PayPal API:** none

---

## 9) AI Copilot

### POST /copilot/chat
Chooses one local tool (SHAP, counterfactuals, affordability, offer guard, revenue volatility, or score) and returns that tool's figures. A disbursement request sets `approval.required` to true and does not create a payout.

```json
{"message": "Can I afford ₹50k?", "applicant_id": "PSC-PRIYA-001"}
```

**PayPal API:** none

### POST /explain
Same explanation as `/score` for one `ScoreRequest`. Does not record disbursement approval.

### POST /counterfactuals
`ScoreRequest` plus optional `proposed_changes`. Re-scores eligible changes on the trained model.

### POST /affordability
See README. Example: amount 50000, income 40000, essential expenses 8000, existing debt 0, tenure 12, rate 0 returns a zero-interest instalment of 4166.67 and `status: "pass"`.

### POST /revenue-volatility
`{"revenues_inr": [100000, 100000, 100000, 100000, 100000, 100000]}` or `{"applicant_id": "PSC-PRIYA-001"}`. Recommendations are deterministic and `statistically_validated` is false. Fewer than 3 observations return `insufficient_data`.

---

## 10) Demo Personas

### GET /demo/persona/{name}
Returns fixture narrative + `model_input` for the demo walkthrough (Priya, Arjun, Rohan).

**PayPal API:** none

---

## Notes for Person 4 (Postman collection)

- All money-moving endpoints are rate-limited: 10 req / 60 s per IP per path.
- PayPal sandbox endpoints require `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` env vars; live mode is refused.
- Webhook endpoint requires `PAYPAL_WEBHOOK_ID` for signature verification.
- Mock sandbox responses: tests use `httpx.MockTransport` against `api-m.sandbox.paypal.com` paths.
- Synthetic data only — no real PayPal data, no real money movement.

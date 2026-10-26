# PayPal Sandbox Setup Checklist (PayScore / Paypilot-AI)

Everything in this project runs against the **PayPal sandbox only**. Never configure the
live API here, and never commit real credentials — only sandbox test-account values go
in your local `.env` (which is git-ignored; see `tests/test_no_secrets.py`).

## 1. Create a developer account and REST app

- [ ] Sign in at <https://developer.paypal.com/dashboard/applications/sandbox> (create a developer account if needed).
- [ ] Click **Create App**, name it e.g. `payscore-hackathon-sandbox`.
- [ ] Select the **Merchant** sandbox business account created below as the app owner.
- [ ] Enable these API capabilities for the app (tick under the app's feature list):
  - [ ] **Transaction Search**
  - [ ] **Payouts**
  - [ ] **Subscriptions**
  - [ ] **Invoicing**
  - [ ] **Orders**
  - [ ] **Disputes** (for the optional sandbox buyer-dispute seeding flow)
- [ ] Copy the **Client ID** and **Secret** (secret is shown once — store it safely).

## 2. Create sandbox test accounts

Developer dashboard → **Testing Tools → Sandbox accounts** (two are auto-created; keep or rename):

- [ ] **Business account** (e.g. `payscore-business@<yourdomain>.com`) — the merchant whose
      data we query (transactions, invoices, payouts, subscriptions).
- [ ] **Personal account** (e.g. `payscore-buyer@<yourdomain>.com`) — a payer for
      subscription/order/invoice end-to-end tests.
- [ ] Note each account's password (viewable in the dashboard) for checkout flows.
- [ ] Optionally fund the personal account with a non-trivial balance for payout testing.
- [ ] Keep its email handy. The seeder requires `--buyer-email` so orders can be approved by
      this sandbox account.

## 2a. Buyer approval and dispute simulation

- [ ] The first seeder apply run creates Checkout orders and prints their approval links.
      Sign in as the personal sandbox buyer, approve the orders, then rerun the same command
      to capture them.
- [ ] PayPal's sandbox buyer dispute API requires buyer consent via Log in with PayPal and
      the `DISPUTE_CREATE` scope. Configure those capabilities for the REST app before
      expecting fixture disputes to appear through the API. Otherwise create them through
      the sandbox Resolution Center.

## 3. Create a webhook (optional but recommended)

- [ ] Note that the app must be publicly reachable to receive webhooks; for local dev use
      a tunnel (e.g. `ngrok http 8000`) or defer webhook testing.
- [ ] Dashboard → your app → **Add Webhook**, point it at `https://<your-host>/webhooks/paypal`.
- [ ] Subscribe to events needed by PayScore (e.g. `PAYMENT.SALE.COMPLETED`, `INVOICING.INVOICE.PAID`, `PAYMENT.PAYOUTS-ITEM.SUCCEEDED`).
- [ ] Copy the **Webhook ID** (shown under the webhook) for signature verification.

## 4. Configure local environment

- [ ] `cp .env.example .env` (or use your process manager's env config).
- [ ] Fill in:
  - `PAYPAL_CLIENT_ID` — sandbox app client id
  - `PAYPAL_CLIENT_SECRET` — sandbox app secret
  - `PAYPAL_MODE=sandbox` — **must stay sandbox**
  - `PAYPAL_WEBHOOK_ID` — from step 3 (optional)
  - `PAYPAL_API_BASE` — leave unset to default to `https://api-m.sandbox.paypal.com`
- [ ] Confirm `.env` is not tracked: `git status` must not list it.

## 5. Verify

- [ ] `pytest tests/ -q` passes (all PayPal tests use a mocked transport — no network).
- [ ] Manual smoke check (optional), using sandbox credentials from step 1:

  ```bash
  curl -s https://api-m.sandbox.paypal.com/v1/oauth2/token \
    -u "$PAYPAL_CLIENT_ID:$PAYPAL_CLIENT_SECRET" \
    -d grant_type=client_credentials | head -c 200
  ```

  A JSON body with `access_token` means the app credentials work.

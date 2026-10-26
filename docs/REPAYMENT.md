# Repayment APIs (feature 2.6)

All repayment routes are sandbox-only and use a process-memory ledger that resets on restart. PayPal documents Subscriptions as available to select partners only; your sandbox app must have the required Subscriptions product access.

## Fixed EMI subscription

`POST /repayment/subscription` accepts `applicant_id`, `subscriber_email`, `emi_amount_inr`, `number_of_emis` (1–999), and a note. The server creates a PayPal catalog product, finite monthly billing plan, and subscription. The response includes the subscription approval link and an estimated schedule from the next monthly due date. The borrower must approve the subscription with PayPal. `POST /repayment/subscription/{id}/cancel` cancels a subscription created by this process and returns its schedule.

## One-off EMI order

`POST /repayment/order` accepts `applicant_id`, `emi_amount_inr`, and a note. The response contains `orderId`, which is the object property expected by the PayPal JS SDK v6 `createOrder` flow, plus a one-installment schedule. After buyer approval, the frontend calls `POST /repayment/order/{id}/capture`. The server captures only orders created and held in its local ledger.

## Revenue share

`POST /repayment/revenue-share` accepts `applicant_id`, the receiving `paypal_account_id` (merchant account ID from the capture event's `resource.payee.merchant_id`), and a percentage from 0.01 to 100. `POST /paypal/webhook` verifies PayPal's transmission using `PAYPAL_WEBHOOK_ID` and processes `PAYMENT.CAPTURE.COMPLETED` events. It records a percentage calculation against the incoming capture, keyed idempotently by event ID. The record is accounting data only; this webhook does not withhold or move the calculated amount. Duplicate event IDs are not counted again.

## Currency and sandbox configuration

Inputs and schedules use INR for the product's loan presentation. PayPal Subscriptions does not support INR, so outbound subscription and one-off order amounts are converted to USD using `PAYPAL_INR_PER_USD` (default `83.00`, a demo constant). Responses expose both INR amounts and the PayPal USD amount. Configure the return/cancel URLs for the frontend and set the webhook ID in the PayPal developer dashboard. This FX value is a test setting, not a live rate. See PayPal's [subscription requirements](https://developer.paypal.com/platforms/subscriptions/integrate/) and [JS SDK v6 order ID format](https://developer.paypal.com/sdk/js/set-up/).

# Sandbox loan disbursements (feature 2.5)

`POST /score` records the score and requested amount in the process memory. This demo permits disbursement when the score is at least **650**; the entire amount submitted to `/score` is the recorded ceiling. A later `POST /disburse` must use the same `applicant_id`, and `approved_loan_amount_inr` must be positive and no larger than `approved_amount_limit_inr` from that score. Lower scores are ineligible. A newer score for the same applicant replaces the previous approval record.

Request body:

```json
{
  "applicant_id": "PSC-PRIYA-001",
  "recipient_email": "sandbox-recipient@example.test",
  "approved_loan_amount_inr": 25000,
  "note": "Demo inventory loan"
}
```

`recipient_email` is the sandbox borrower's PayPal email. The API does not put it in the local disbursement ledger or return it. Successful creation returns PayPal's `payout_batch_id`; use `GET /disburse/{batch_id}` to refresh batch/item statuses. The in-memory approval and payout ledger is lost when the process restarts.

Every response includes a sandbox indicator or disclosure. The integration refuses a non-sandbox API base and uses PayPal's Payouts API with INR. Configure `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MODE=sandbox`, and ensure Payouts is enabled for the REST app. This is a hackathon demo gate, not a calibrated credit or lending policy. Do not use it for real lending or real-money disbursements.

# Feature mapping: source data -> normalised `ScoreRequest`

> **STATUS: PROVISIONAL.** Every PayPal-side mapping in this document is a placeholder that has **not** been verified against
> PayPal documentation, a sandbox, or a real account. Nothing in this repository calls PayPal.

The model only ever sees the normalised schema (`schema/score_request.schema.json`). Person 2 maps real or mock
PayPal data into it. **Status of every PayPal-side source is UNVERIFIED**: confirm what the PayPal account/API
actually exposes (and its terms of use / consent requirements) before relying on any row marked *derived*.

Reference implementation of the *derived* rows: `payscore/derive.py`. Windows are anchored to `as_of`
(exclusive): last 6 / 12 **complete calendar months** and last 90 days. Transaction types: `sale`, `refund`, `dispute`, `expense`.

| Field | Req? | Source | Rule |
|---|---|---|---|
| `applicant_id` | yes | system | Pseudonymous ID `[A-Za-z0-9_-]{1,64}`; never a name/email |
| `age_years` | yes | applicant-declared | Whole years, 18-100 |
| `employment_type` | yes | applicant-declared | salaried / self_employed / freelancer / business_owner / other |
| `monthly_income_inr` | yes | applicant-declared | Total personal monthly income, all sources |
| `requested_loan_amount_inr` | yes | loan request | > 0 |
| `requested_term_months` | yes | loan request | 1-360 |
| `business_age_months` | no | declared start date | Whole months from start date to `as_of` |
| `avg_monthly_revenue_inr` | no | derived | Mean over last 6 complete months of (sales - refunds); months before first txn excluded |
| `avg_monthly_expenses_inr` | no | derived / declared | Mean monthly expenses, same window |
| `revenue_volatility_cv` | no | derived | population std / mean of monthly net revenue; null if < 3 months or mean <= 0 |
| `txn_count_90d` | no | derived | Count of `sale` in last 90 days |
| `avg_txn_value_inr` | no | derived | Mean `sale` amount, last 90 days; null if none |
| `active_months_12m` | no | derived | Distinct months with >= 1 sale, last 12 complete months |
| `refund_rate_90d` | no | derived | refunds / sales (count), 90 days, capped at 1 |
| `dispute_rate_12m` | no | derived | disputes / sales (count), 12 months, capped at 1 |
| `existing_monthly_debt_payments_inr` | no | declared (or bureau, if ever available) | Sum of monthly obligations |
| `prior_defaults_count` | no | declared / bureau | Count of past defaults |

Rules for integrators: convert to INR before sending; send `null`/omit unknown optionals (never `0` as a stand-in for
"unknown"); the API rejects unknown fields (422). Missing values are handled natively by the model and echoed in `missing_inputs`.

Engineered features (computed in `payscore/features.py`, NaN when a denominator is missing or <= 0):
`debt_to_income`, `expense_ratio`, `net_margin`, `loan_to_annual_revenue`, `installment_to_income` (principal / term / income, no interest), `employment_type_code`.

---

## Extended specification (types, units, examples, availability, privacy)

**Availability classes**

* `USER` — supplied by the applicant (form field / consent step). Not obtainable from PayPal.
* `TXN-DERIVED` — computed from transaction history using the rules above. **Whether PayPal can supply that history to this
  project is UNVERIFIED** (see the placeholder table below). For the demo it comes from synthetic fixtures.
* `SYNTHETIC-DEMO` — exists only in `fixtures/personas/*.json` / the synthetic training set.

No field below is a *verified* PayPal API field. Nothing in this repository calls PayPal.

| Field | Type / unit | Example | Class | Missing-value handling | Privacy / minimisation |
|---|---|---|---|---|---|
| `applicant_id` | string, pseudonymous | `PSC-PRIYA-001` | USER/system | required | Random ID only; never name, e-mail, phone or PayPal payer ID |
| `age_years` | int, years | `34` | USER | required | Prefer age (not date of birth); consider banding before any real use |
| `employment_type` | enum | `self_employed` | USER | required | Coarse category only |
| `monthly_income_inr` | float, INR/month | `55000` | USER | required | Self-declared total; no bank statements needed |
| `requested_loan_amount_inr` | float, INR | `400000` | USER | required | Loan request only |
| `requested_term_months` | int, months | `18` | USER | required | — |
| `business_age_months` | int, months | `38` | USER (start date) | null -> NaN | Send months, not the start date |
| `avg_monthly_revenue_inr` | float, INR/month | `144166.67` | TXN-DERIVED | null -> NaN | Aggregate only; no individual transactions leave the mapper |
| `avg_monthly_expenses_inr` | float, INR/month | `83784.50` | TXN-DERIVED or USER | null -> NaN | Aggregate only |
| `revenue_volatility_cv` | float, ratio >= 0 | `0.0577` | TXN-DERIVED | null if < 3 months or mean <= 0 | Aggregate only |
| `txn_count_90d` | int, count | `97` | TXN-DERIVED | null -> NaN | Count only |
| `avg_txn_value_inr` | float, INR | `4481.24` | TXN-DERIVED | null if no sales | Aggregate only |
| `active_months_12m` | int, 0-12 | `12` | TXN-DERIVED | null -> NaN | — |
| `refund_rate_90d` | float, 0-1 | `0.0` | TXN-DERIVED | null if no sales | — |
| `dispute_rate_12m` | float, 0-1 | `0.0` | TXN-DERIVED | null if no sales | — |
| `existing_monthly_debt_payments_inr` | float, INR/month | `6000` | USER | null -> NaN (never `0` for unknown) | Self-declared total |
| `prior_defaults_count` | int, count | `0` | USER | null -> NaN | Self-declared; sensitive |

Data minimisation: a request has 17 fields (6 required + 11 optional, including `applicant_id`), of which 16 are model inputs. Do not send, store or log raw transactions, counterparty names, payer
e-mails or account identifiers to `/score`. The API does not log request bodies and does not echo submitted values in errors.
All demo currency is INR; convert upstream (the model does not do FX).

### Placeholder mapping for Person 2 to verify against the real PayPal sandbox

PayPal's developer documentation was **not** consulted or reachable while writing this, so **nothing here is confirmed**. The
"candidate" column is an unverified guess at what a transaction-search style response may contain; treat every cell as a TODO.

| Concept needed by `derive.py` | Our field | Candidate PayPal source (UNVERIFIED) | Verification TODO |
|---|---|---|---|
| Transaction identity | `txn_id` | a transaction id in the transaction record | Confirm field path; do not forward to `/score` |
| Date of transaction | `date` | transaction initiation/update date | Confirm field, timezone, and date-range limits |
| Amount and currency | `amount_inr` | amount value + currency code | Confirm sign convention; convert non-INR to INR upstream |
| Sale vs refund vs dispute vs fee | `type` | event/type code and status | Confirm the event-code list that means sale / refund / chargeback-dispute / fee; define what counts as `expense` (PayPal may not expose seller expenses at all -> then `avg_monthly_expenses_inr` must be `USER`) |
| Completed only | `status` | transaction status | Confirm which statuses count as completed |
| History length available | — | API date-range / retention limits | Confirm how many months can be fetched; if < 6, `revenue_volatility_cv` is null |
| Sandbox availability for an India-based developer | — | — | Confirm sandbox access, required scopes/permissions and any consent requirements before depending on any of this |

Until verified, integrate against the mock fixtures; the schema above is the stable contract.

# Seeding the PayPal Sandbox with Persona Data

`payscore/paypal/seed.py` converts the synthetic fixture history for Priya, Arjun, and
Rohan into deterministic sandbox operations. Dry-run is the default and makes no API
calls.

```powershell
python -m payscore.paypal.seed --persona priya
python -m payscore.paypal.seed --persona priya,arjun,rohan
```

## Applying the plan

Set sandbox app credentials as described in [SANDBOX_SETUP.md](SANDBOX_SETUP.md). To
create PayPal orders, also provide the email address for a real personal sandbox account:

```powershell
python -m payscore.paypal.seed --persona priya --apply --buyer-email your-sandbox-buyer@example.test
```

PayPal Checkout orders need buyer approval before capture. The first apply run creates
orders and prints their approval URLs. Sign in to the sandbox buyer account to approve
each order, then rerun the same command to capture approved orders. The seeder uses stable
`PayPal-Request-Id` values so retries do not create duplicate orders during PayPal's
idempotency retention window. This is an interactive sandbox workflow; it cannot silently
turn hundreds of invented payments into completed transactions.

## What it creates

| Fixture data | Sandbox operation | Result |
|---|---|---|
| `sale` | Create and capture an Orders v2 payment after buyer approval | A real sandbox payment appears in Transaction Search |
| `refund` | Refund its matching prior sale capture | A refund appears in Transaction Search |
| `dispute` / open sale | Create a sandbox buyer dispute using the Disputes API | A dispute appears when buyer consent and `DISPUTE_CREATE` access are configured |
| `monthly_summary` row | Create and send one invoice, then record an external bank-transfer payment | A paid invoice appears in Invoicing |
| `expense` | Omitted; these are illustrative business costs, not PayPal activity | No sandbox record |

Invoice payment records use PayPal's external-payment endpoint (`POST
/v2/invoicing/invoices/{id}/payments`). They are accounting records on the invoice, not PayPal
sales, and do not create Transaction Search payment rows.

## Disputes

PayPal provides a sandbox-only buyer dispute creation endpoint. It requires a buyer
transaction and buyer consent configured through Log in with PayPal, plus the `DISPUTE_CREATE`
scope and a `PayPal-Auth-Assertion` header. The seeder attempts this after capturing a
fixture dispute transaction. If the app or buyer is not eligible, it reports the case under
`manual_disputes`; use the sandbox Resolution Center to create it manually. See PayPal's
[sandbox dispute testing guide](https://developer.paypal.com/disputes/test-go-live).

## Limits to the fixture-to-sandbox mapping

- PayPal processing dates are current; the APIs do not let this script backdate captures.
  The fixture date and transaction ID are retained in the order description and custom ID.
- Fixture values are INR. Orders convert them to USD at a fixed demo rate of INR 83 per
  USD; original INR values remain in descriptions. This rate is only for demo data.
- Each transaction gets a deterministic fictional client name. The configured sandbox
  buyer account must approve orders; its email is used for checkout and buyer-side dispute
  calls.
- The generated fixture disputes and order captures are demonstrations, not real customer
  activity or a valid credit history.

The command exits nonzero if API calls fail. Reports include created, skipped, failed,
pending approval, and manual-dispute items. Re-running is safe: transaction custom IDs,
invoice references, and PayPal request IDs are deterministic.

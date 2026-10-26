"""Seed the PayPal sandbox with synthetic data for the PayScore personas.

Run (dry-run is the default — nothing is written):
  python -m payscore.paypal.seed --persona priya
  python -m payscore.paypal.seed --persona priya --apply --buyer-email buyer@example.test

For each persona in fixtures/personas/{priya,arjun,rohan}.json the fixture's transaction
list is converted into sandbox API operations. Orders require buyer approval before capture;
disputes use PayPal's sandbox-only buyer API when buyer consent is configured. Invoice rows
are recorded as external payments through Invoicing.

Idempotency: orders are tagged with custom ID "payscore-seed:<txn_id>", invoices with
reference "<persona_id>-INV-<month>", and write calls use stable PayPal request IDs. Before
applying, Transaction Search and the invoice list are scanned for those tags (paginated).

Sandbox notes: PayPal Orders cannot be backdated, so items appear with today's processing
date while keeping each transaction's original amount, client and description. Fixture amounts are
INR; PayPal checkout does not accept INR, so amounts are converted to USD at a fixed
documented rate (see FX_INR_PER_USD) with the INR value kept in the order description.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from .client import PayPalClient, PayPalError

log = logging.getLogger("payscore.paypal.seed")

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "personas"
SEED_TAG = "payscore-seed"
FX_INR_PER_USD = 83.0  # fixed fictional rate: keep fixture INR amounts reproducible in USD
PERSONAS = ("priya", "arjun", "rohan")
SEARCH_WINDOW_DAYS = 30  # Transaction Search allows max 31 days per request
PAGE_SIZE = 100

CLIENT_NAMES = {
    "international": ["Elena Marsh", "Tomas Richter", "Ava Sinclair", "Noah Bennett", "Ines Duarte",
                      "Lucas Meyer", "Clara Fontaine", "Daniel Kovacs"],
    "domestic": ["Meera Iyer", "Kabir Shah", "Ananya Rao", "Vikram Nair", "Divya Menon",
                 "Rahul Bose", "Sneha Patil", "Aditya Gupta"],
}
_CLIENT_DOMAIN = "seed-buyers.example.com"

ClientFactory = Callable[[], PayPalClient]


def load_persona(name: str) -> dict:
    path = FIXTURE_DIR / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"unknown persona {name!r}: no such fixture {path}")
    persona = json.loads(path.read_text())
    if not persona.get("synthetic"):
        raise SystemExit(f"{path} is not marked synthetic; refusing to seed")
    return persona


def usd(amount_inr: float) -> str:
    return f"{round(amount_inr / FX_INR_PER_USD, 2):.2f}"


def _split_name(full: str) -> tuple[str, str]:
    parts = full.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else "Buyer")


def _request_id(kind: str, ref: str) -> str:
    """Stable PayPal idempotency key (38-character maximum)."""
    digest = hashlib.sha256(f"{kind}:{ref}".encode()).hexdigest()[:24]
    return f"ps-{kind[:5]}-{digest}"


def _buyer_assertion(client_id: str, buyer_email: str) -> str:
    """Build PayPal's sandbox buyer assertion after the buyer has granted consent."""
    def b64(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'iss': client_id, 'email': buyer_email})}."


def _payer(persona_id: str, txn: dict) -> dict:
    """Deterministic fictional payer per transaction (same input -> same client)."""
    rng = random.Random(f"{persona_id}:{txn['txn_id']}")
    international = "international" in txn.get("category", "")
    name = rng.choice(CLIENT_NAMES["international" if international else "domestic"])
    given, surname = _split_name(name)
    return {
        "name": name,
        "given_name": given,
        "surname": surname,
        "email_address": f"{txn['txn_id'].lower()}@{_CLIENT_DOMAIN}",
        "payer_id": f"SEED{rng.randrange(10**10):010d}",
    }


def _order_op(persona: dict, txn: dict, *, dispute: bool) -> dict:
    ref = txn["txn_id"]
    tag = f"{SEED_TAG}:{ref}"
    payer = _payer(persona["persona_id"], txn)
    return {
        "kind": "order", "ref": ref, "date": txn["date"], "dispute": dispute, "payer": payer,
        "payload": {
            "intent": "CAPTURE",
            "payment_source": {
                "paypal": {
                    "email_address": payer["email_address"],
                    "experience_context": {
                        "brand_name": "PayScore Sandbox Demo",
                        "user_action": "PAY_NOW",
                        "return_url": "https://example.com/payscore-seed/return",
                        "cancel_url": "https://example.com/payscore-seed/cancel",
                    },
                },
            },
            "purchase_units": [{
                "reference_id": ref,
                "custom_id": tag,
                "description": f"{persona['display_name']} payment from {payer['name']}: {txn['category']} "
                               f"({txn['amount_inr']:.0f} INR, fixture {ref}, {txn['date']})",
                "amount": {"currency_code": "USD", "value": usd(txn["amount_inr"])},
            }],
        },
    }


def _invoice_recipient(persona_id: str, month: str) -> dict:
    rng = random.Random(f"{persona_id}:invoice:{month}")
    name = rng.choice(CLIENT_NAMES["domestic"])
    given, surname = _split_name(name)
    return {
        "billing_info": {
            "name": {"given_name": given, "surname": surname},
            "email_address": f"{persona_id.lower()}-{month}@{_CLIENT_DOMAIN}",
        }
    }


def build_seed_plan(persona: dict) -> list[dict]:
    """Turn a persona fixture into a list of seed operations (pure function, no I/O)."""
    persona_id = persona["persona_id"]
    plan: list[dict] = []
    for txn in persona["transactions"]:
        kind = txn["type"]
        if kind == "sale":
            disputed = txn.get("status") == "open" or txn.get("category") == "buyer_dispute"
            plan.append(_order_op(persona, txn, dispute=disputed))
        elif kind == "dispute":
            plan.append(_order_op(persona, txn, dispute=True))
        elif kind == "refund":
            plan.append({"kind": "refund", "ref": txn["txn_id"], "date": txn["date"],
                         "amount": {"currency_code": "USD", "value": usd(txn["amount_inr"])}})
    # Match generated refunds back to their original sale (the fixture generator
    # uses the same amount and a refund date after the sale). For hand-authored
    # fixtures, fall back to a prior sale in the same month with enough balance.
    sales = [op for op in plan if op["kind"] == "order"]
    refunded: dict[str, float] = {}
    for op in plan:
        if op["kind"] == "refund":
            amount = float(op["amount"]["value"])
            candidates = [sale for sale in sales if sale["date"][:7] == op["date"][:7]
                          and sale["date"] <= op["date"]
                          and float(sale["payload"]["purchase_units"][0]["amount"]["value"])
                          - refunded.get(sale["ref"], 0.0) >= amount]
            exact = [sale for sale in candidates
                     if abs(float(sale["payload"]["purchase_units"][0]["amount"]["value"]) - amount) < 0.011
                     and not refunded.get(sale["ref"])]
            source = max(exact or candidates, key=lambda sale: (sale["date"], sale["ref"])) if candidates else None
            op["source_ref"] = source["ref"] if source else ""
            if source:
                refunded[source["ref"]] = refunded.get(source["ref"], 0.0) + amount
    for month in persona["monthly_summary"]:
        ref = f"{persona_id}-INV-{month['month']}"
        plan.append({
            "kind": "invoice", "ref": ref, "date": f"{month['month']}-01",
            "payload": {
                "detail": {
                    "invoice_number": ref,
                    "reference": ref,
                    "currency_code": "USD",
                    "note": f"{SEED_TAG}: {persona['display_name']} sales for {month['month']} "
                            f"({month['sales_inr']:.0f} INR)",
                    "invoice_date": f"{month['month']}-01",
                    "payment_term": {"term_type": "DUE_ON_RECEIPT"},
                },
                "primary_recipients": [_invoice_recipient(persona_id, month["month"])],
                "items": [{"name": f"Sales {month['month']}", "quantity": "1",
                           "unit_amount": {"currency_code": "USD", "value": usd(month["sales_inr"])}}],
            },
            "payment": {"currency_code": "USD", "value": usd(month["sales_inr"])},
        })
    return sorted(plan, key=lambda op: (op["date"], op["ref"]))


def summarize_plan(persona: dict, plan: list[dict]) -> dict:
    return {
        "persona": persona["persona_id"],
        "orders": sum(op["kind"] == "order" for op in plan),
        "refunds": sum(op["kind"] == "refund" for op in plan),
        "invoices": sum(op["kind"] == "invoice" for op in plan),
        "disputes_to_create": sum(op["kind"] == "order" and op["dispute"] for op in plan),
        "expenses_skipped": sum(t["type"] == "expense" for t in persona["transactions"]),
    }


def _invoice_id(body: dict) -> str:
    if body.get("id"):
        return str(body["id"])
    href = str(body.get("href") or "")
    return href.rstrip("/").split("/")[-1]


async def fetch_existing_refs(client: PayPalClient, start: date, end: date) -> set[str]:
    """Scan Transaction Search and the invoice list for items we seeded earlier."""
    refs: set[str] = set()
    window = start
    while window <= end:
        w_end = min(window + timedelta(days=SEARCH_WINDOW_DAYS), end)
        page = 1
        while True:
            body = await client.get("/v1/reporting/transactions", params={
                "start_date": f"{window.isoformat()}T00:00:00Z",
                "end_date": f"{w_end.isoformat()}T23:59:59Z",
                "page_size": str(PAGE_SIZE),
                "page": str(page),
            })
            for row in body.get("transaction_details", []):
                field = row.get("transaction_info", {}).get("custom_field") or ""
                if field.startswith(f"{SEED_TAG}:"):
                    refs.add(field.split(":", 1)[1])
            total_pages = int(body.get("total_pages") or 1)
            if page >= total_pages:
                break
            page += 1
        window = w_end + timedelta(days=1)
    page = 1
    while True:
        invoices = await client.get("/v2/invoicing/invoices", params={
            "page": str(page), "page_size": str(PAGE_SIZE), "total_required": "true",
        })
        for item in invoices.get("items", []):
            ref = item.get("detail", {}).get("reference") or item.get("detail", {}).get("invoice_number") or ""
            if "-INV-" in ref:  # seeded invoices are referenced <persona_id>-INV-<month>
                refs.add(ref)
        total_pages = int(invoices.get("total_pages") or 1)
        if page >= total_pages:
            break
        page += 1
    return refs


async def apply_plan(client: PayPalClient, plan: list[dict], existing: set[str],
                     buyer_email: Optional[str] = None) -> dict:
    report: dict = {"created": [], "skipped": [], "failed": [], "manual_disputes": [], "pending_approval": []}
    captures: dict[str, str] = {}  # sale ref -> capture id (for refunds)
    for op in plan:
        ref = op["ref"]
        if ref in existing:
            report["skipped"].append({"ref": ref, "reason": "already_seeded"})
            continue
        try:
            if op["kind"] == "order":
                payload = json.loads(json.dumps(op["payload"]))
                if buyer_email:
                    payload["payment_source"]["paypal"]["email_address"] = buyer_email
                order = await client.post("/v2/checkout/orders", json=payload,
                                          request_id=_request_id("order", ref))
                if order.get("id"):
                    # A request-ID replay may return the original create response.
                    # Read the resource again so an order approved since the prior run
                    # can proceed to capture.
                    latest = await client.get(f"/v2/checkout/orders/{order['id']}")
                    order = {**order, **latest}
                if order.get("status") != "APPROVED":
                    approve_url = next((link.get("href") for link in order.get("links", [])
                                        if link.get("rel") in {"approve", "payer-action"}), None)
                    report["pending_approval"].append({"ref": ref, "id": order.get("id"),
                                                        "approve_url": approve_url})
                    if op.get("dispute"):
                        report["manual_disputes"].append({
                            "ref": ref, "order_id": order.get("id"),
                            "hint": "Approve the order first. The sandbox Disputes API then requires buyer "
                                    "consent and a PayPal-Auth-Assertion; see docs/SEEDING.md.",
                        })
                    continue
                captured = await client.post(f"/v2/checkout/orders/{order['id']}/capture", json={},
                                             request_id=_request_id("capture", ref))
                capture_id = captured["purchase_units"][0]["payments"]["captures"][0]["id"]
                captures[op["ref"]] = capture_id
                report["created"].append({"ref": ref, "id": order["id"], "kind": "order"})
                if op.get("dispute"):
                    if not buyer_email:
                        report["manual_disputes"].append({
                            "ref": ref, "order_id": order["id"], "capture_id": capture_id,
                            "hint": "Set --buyer-email and complete buyer consent for DISPUTE_CREATE, or "
                                    "create the case in the sandbox Resolution Center.",
                        })
                        continue
                    try:
                        assertion = _buyer_assertion(client.client_id, buyer_email)
                        await client.post_multipart("/v1/customer/disputes", fields={
                            "input": json.dumps({
                                "disputed_transactions": [{"buyer_transaction_id": capture_id}],
                                "reason": "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
                                "dispute_amount": op["payload"]["purchase_units"][0]["amount"],
                                "extensions": {
                                    "merchant_contacted": True,
                                    "merchant_contacted_outcome": "NO_RESPONSE",
                                    "merchandize_dispute_properties": {"issue_type": "PRODUCT"},
                                },
                            }),
                        }, headers={"PayPal-Auth-Assertion": assertion},
                           request_id=_request_id("dispute", ref))
                        report["created"].append({"ref": ref, "capture": capture_id, "kind": "dispute"})
                    except PayPalError as exc:
                        report["manual_disputes"].append({
                            "ref": ref, "order_id": order["id"], "capture_id": capture_id,
                            "error": str(exc),
                            "hint": "Check buyer consent, DISPUTE_CREATE scope, and sandbox dispute eligibility; "
                                    "otherwise create this case in the sandbox Resolution Center.",
                        })
            elif op["kind"] == "refund":
                capture_id = captures.get(op["source_ref"], "")
                if not capture_id:
                    report["skipped"].append({"ref": ref, "reason": "no_seeded_capture_in_source_month"})
                    continue
                await client.post(f"/v2/payments/captures/{capture_id}/refund", json={"amount": op["amount"]},
                                  request_id=_request_id("refund", ref))
                report["created"].append({"ref": ref, "capture": capture_id, "kind": "refund"})
            elif op["kind"] == "invoice":
                invoice = await client.post("/v2/invoicing/invoices", json=op["payload"],
                                            request_id=_request_id("invoice", ref))
                invoice_id = _invoice_id(invoice)
                await client.post(f"/v2/invoicing/invoices/{invoice_id}/send",
                                  json={"send_to_invoicer": False, "send_to_recipient": False},
                                  request_id=_request_id("invoice-send", ref))
                # This records an external payment for the invoice. It is not a PayPal
                # sale and will not create a Transaction Search payment row.
                await client.post(f"/v2/invoicing/invoices/{invoice_id}/payments",
                                  json={"amount": op["payment"], "method": "BANK_TRANSFER",
                                        "note": f"{SEED_TAG}: {ref}"},
                                  request_id=_request_id("invoice-payment", ref))
                report["created"].append({"ref": ref, "id": invoice_id, "kind": "invoice"})
        except PayPalError as exc:
            report["failed"].append({"ref": ref, "error": str(exc), "status": exc.status})
    return report


async def run(persona_names: list[str], apply: bool = False,
              client_factory: Optional[ClientFactory] = None,
              buyer_email: Optional[str] = None) -> dict:
    personas = [(name, load_persona(name)) for name in persona_names]
    plans = {name: build_seed_plan(persona) for name, persona in personas}
    report = {"mode": "apply" if apply else "dry-run", "personas": {}}
    factory = client_factory or PayPalClient
    for name, persona in personas:
        entry = summarize_plan(persona, plans[name])
        if not apply:
            entry["note"] = "dry-run: no API calls made; re-run with --apply to seed"
            report["personas"][name] = entry
            continue
        dates = [op["date"] for op in plans[name]]
        async with factory() as client:
            existing = await fetch_existing_refs(client, date.fromisoformat(min(dates)), date.today())
            entry["already_seeded"] = len(existing)
            entry.update(await apply_plan(client, plans[name], existing, buyer_email=buyer_email))
        report["personas"][name] = entry
    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the PayPal sandbox with persona data (dry-run by default).")
    parser.add_argument("--persona", default=",".join(PERSONAS),
                        help=f"comma-separated persona names (default: {','.join(PERSONAS)})")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="actually create the sandbox items")
    mode.add_argument("--dry-run", action="store_true", help="print the plan only (default)")
    parser.add_argument("--buyer-email", help="PayPal sandbox personal account email for order approval/disputes")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    names = [n.strip().lower() for n in args.persona.split(",") if n.strip()]
    if args.apply and not args.buyer_email:
        parser.error("--apply requires --buyer-email for the sandbox personal account; dry-run needs no credentials")
    report = asyncio.run(run(names, apply=args.apply, buyer_email=args.buyer_email))
    print(json.dumps(report, indent=2))
    return 1 if any(p.get("failed") for p in report["personas"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())

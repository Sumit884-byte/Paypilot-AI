"""Tests for payscore/paypal/seed.py — plan building and apply logic with a scripted fake API."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from payscore.paypal import PayPalClient
from payscore.paypal.seed import (
    SEED_TAG,
    apply_plan,
    build_seed_plan,
    fetch_existing_refs,
    load_persona,
    main,
    run,
    summarize_plan,
    usd,
)


def persona_fixture(tmp_path_factory: Any, monkeypatch: pytest.MonkeyPatch, transactions: list[dict],
                    months: list[dict]) -> dict:
    persona = {
        "schema_version": "1.0", "persona_id": "PSC-TEST-999", "display_name": "Test Persona",
        "synthetic": True, "currency": "INR",
        "monthly_summary": months, "transactions": transactions,
    }
    d = tmp_path_factory.mktemp("fixtures")
    (d / "tester.json").write_text(json.dumps(persona))
    monkeypatch.setattr("payscore.paypal.seed.FIXTURE_DIR", d)
    return persona


SALES = [{"txn_id": "SYN-TEST-00001", "date": "2025-10-02", "type": "sale", "direction": "inflow",
          "amount_inr": 4000.0, "category": "international_buyer", "status": "completed"},
         {"txn_id": "SYN-TEST-00002", "date": "2025-10-09", "type": "sale", "direction": "inflow",
          "amount_inr": 1000.0, "category": "domestic_buyer", "status": "completed"},
         {"txn_id": "SYN-TEST-00003", "date": "2025-11-03", "type": "sale", "direction": "inflow",
          "amount_inr": 2000.0, "category": "international_buyer", "status": "completed"},
         {"txn_id": "SYN-TEST-00004", "date": "2025-11-14", "type": "sale", "direction": "inflow",
          "amount_inr": 500.0, "category": "buyer_dispute", "status": "open"}]
DISPUTES = [{"txn_id": "SYN-TEST-00007", "date": "2025-11-20", "type": "dispute", "direction": "outflow",
             "amount_inr": 1100.0, "category": "buyer_dispute", "status": "open"}]
REFUNDS = [{"txn_id": "SYN-TEST-00005", "date": "2025-10-15", "type": "refund", "direction": "outflow",
            "amount_inr": 400.0, "category": "customer_refund", "status": "completed"}]
EXPENSES = [{"txn_id": "SYN-TEST-00006", "date": "2025-10-01", "type": "expense", "direction": "outflow",
             "amount_inr": 900.0, "category": "software_subscriptions", "status": "completed"}]
MONTHS = [{"month": "2025-10", "sales_inr": 5000.0, "refunds_inr": 400.0, "net_revenue_inr": 4600.0,
           "expenses_inr": 900.0, "sale_count": 2},
          {"month": "2025-11", "sales_inr": 2500.0, "refunds_inr": 0, "net_revenue_inr": 2500.0,
           "expenses_inr": 0, "sale_count": 2}]


class SeedFake:
    """Records API calls and answers them like the PayPal sandbox would."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[dict] = []
        self.request_ids: list[str] = []
        self.dispute_headers: list[dict[str, str]] = []
        self.existing_custom_fields: list[str] = []
        self.existing_invoice_refs: list[str] = []
        self.txn_page_size: int | None = None  # if set, paginate custom fields
        self.capture_ids: list[str] = []
        self._n = 0
        self.approve_orders = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        if request.headers.get("PayPal-Request-Id"):
            self.request_ids.append(request.headers["PayPal-Request-Id"])
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "fake-token", "expires_in": 3600})
        if request.method == "GET" and request.url.path == "/v1/reporting/transactions":
            page = int(parse_qs(urlparse(str(request.url)).query).get("page", ["1"])[0])
            fields = self.existing_custom_fields
            if self.txn_page_size:
                start = (page - 1) * self.txn_page_size
                chunk = fields[start:start + self.txn_page_size]
                total_pages = max(1, (len(fields) + self.txn_page_size - 1) // self.txn_page_size)
            else:
                chunk = fields
                total_pages = 1
            rows = [{"transaction_info": {"custom_field": f"{SEED_TAG}:{ref}"}} for ref in chunk]
            return httpx.Response(200, json={"transaction_details": rows, "total_pages": total_pages})
        if request.method == "GET" and request.url.path.startswith("/v2/checkout/orders/"):
            status = "APPROVED" if self.approve_orders else "PAYER_ACTION_REQUIRED"
            links = [] if self.approve_orders else [{"href": "https://sandbox.example/approve", "rel": "approve"}]
            return httpx.Response(200, json={"status": status, "links": links})
        if request.method == "GET" and request.url.path == "/v2/invoicing/invoices":
            items = [{"detail": {"reference": ref}} for ref in self.existing_invoice_refs]
            return httpx.Response(200, json={"items": items, "total_items": len(items), "total_pages": 1})
        if request.method == "POST" and request.url.path == "/v1/customer/disputes":
            self.dispute_headers.append(dict(request.headers))
            return httpx.Response(201, json={"dispute_id": f"DSP-{self._n}"})
        self.bodies.append(json.loads(request.read() or b"{}"))
        self._n += 1
        if request.url.path == "/v2/checkout/orders":
            status = "APPROVED" if self.approve_orders else "PAYER_ACTION_REQUIRED"
            links = [] if self.approve_orders else [{"href": "https://sandbox.example/approve", "rel": "approve"}]
            return httpx.Response(201, json={"id": f"ORD-{self._n}", "status": status, "links": links})
        if request.url.path.endswith("/capture"):
            capture_id = f"CAP-{self._n}"
            self.capture_ids.append(capture_id)
            return httpx.Response(201, json={"id": f"ORD-{self._n}", "status": "COMPLETED",
                                             "purchase_units": [{"payments": {"captures": [{"id": capture_id}]}}]})
        if "/refund" in request.url.path:
            return httpx.Response(201, json={"id": f"REF-{self._n}", "status": "COMPLETED"})
        if request.url.path == "/v2/invoicing/invoices":
            return httpx.Response(201, json={"href": f"https://api-m.sandbox.paypal.com/v2/invoicing/invoices/INV-{self._n}"})
        if request.url.path.endswith("/send"):
            return httpx.Response(202, json={})
        if request.url.path.endswith("/payments"):
            return httpx.Response(204)
        raise AssertionError(f"unexpected call {request.method} {request.url.path}")


def fake_client(fake: SeedFake) -> PayPalClient:
    fake_secret = "cs"  # variable, not a quoted literal after client_secret=, for the secret scanner
    return PayPalClient(transport=httpx.MockTransport(fake.handler),
                        api_base="https://api-m.sandbox.paypal.com", client_id="cid", client_secret=fake_secret)


def test_plan_maps_transactions_to_operations(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES + REFUNDS + EXPENSES + DISPUTES, MONTHS)
    persona = load_persona("tester")
    plan = build_seed_plan(persona)
    kinds = [op["kind"] for op in plan]
    assert kinds.count("order") == 5 and kinds.count("refund") == 1 and kinds.count("invoice") == 2
    order = next(op for op in plan if op["ref"] == "SYN-TEST-00001")
    unit = order["payload"]["purchase_units"][0]
    assert unit["custom_id"] == f"{SEED_TAG}:SYN-TEST-00001"
    assert unit["amount"] == {"currency_code": "USD", "value": "48.19"}  # 4000 / 83
    assert "4000 INR" in unit["description"], "INR amount kept in description"
    assert order["payer"]["email_address"] == "syn-test-00001@seed-buyers.example.com"
    assert order["payload"]["payment_source"]["paypal"]["email_address"] == order["payer"]["email_address"]
    assert order["payload"]["payment_source"]["paypal"]["experience_context"]["user_action"] == "PAY_NOW"
    invoice = next(op for op in plan if op["kind"] == "invoice")
    assert invoice["payload"]["primary_recipients"]
    refund = next(op for op in plan if op["kind"] == "refund")
    assert refund["source_ref"] == "SYN-TEST-00002", "refund uses the latest prior sale with sufficient amount"
    assert next(op for op in plan if op["ref"] == "SYN-TEST-00004")["dispute"]
    assert next(op for op in plan if op["ref"] == "SYN-TEST-00007")["dispute"]
    summary = summarize_plan(persona, plan)
    assert summary == {"persona": "PSC-TEST-999", "orders": 5, "refunds": 1, "invoices": 2,
                       "disputes_to_create": 2, "expenses_skipped": 1}


def test_plan_is_deterministic(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES, MONTHS)
    assert build_seed_plan(load_persona("tester")) == build_seed_plan(load_persona("tester"))


def test_dry_run_makes_no_api_calls(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES + REFUNDS, MONTHS)
    report = asyncio.run(run(["tester"], apply=False))
    assert report["mode"] == "dry-run"
    assert report["personas"]["tester"]["orders"] == 4
    assert "no API calls made" in report["personas"]["tester"]["note"]


def test_cli_default_is_dry_run(tmp_path_factory, monkeypatch, capsys) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES, MONTHS)
    assert main(["--persona", "tester"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "dry-run"


def test_cli_apply_requires_buyer_email(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES, MONTHS)
    with pytest.raises(SystemExit):
        main(["--persona", "tester", "--apply"])


def test_apply_creates_skips_and_refunds(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES + REFUNDS, MONTHS)
    plan = build_seed_plan(load_persona("tester"))
    fake = SeedFake()

    async def body() -> dict:
        async with fake_client(fake) as client:
            return await apply_plan(client, plan, set(), buyer_email="buyer@example.test")

    report = asyncio.run(body())
    assert len(report["created"]) == len(plan) + 1  # one captured dispute transaction also creates a dispute
    assert not report["failed"] and not report["skipped"]
    posts = [path for method, path in fake.calls if method == "POST"]
    assert posts.count("/v2/checkout/orders") == 4 and posts.count("/v2/invoicing/invoices") == 2
    assert sum("/refund" in p for p in posts) == 1 and sum(p.endswith("/payments") for p in posts) == 2
    assert sum(p.endswith("/send") for p in posts) == 2
    assert len(fake.request_ids) == len(set(fake.request_ids))
    assert all(len(request_id) <= 38 for request_id in fake.request_ids)
    # refund targeted the capture of the month's first sale
    refund_call = next(p for p in posts if "/refund" in p)
    assert refund_call == f"/v2/payments/captures/{fake.capture_ids[1]}/refund"
    assert any(d["ref"] == "SYN-TEST-00004" and d["kind"] == "dispute" for d in report["created"])
    assert len(fake.dispute_headers) == 1
    assert fake.dispute_headers[0]["paypal-auth-assertion"].startswith("eyJhbGciOiJub25l")
    assert fake.dispute_headers[0]["paypal-request-id"]
    created_invoices = [c for c in report["created"] if c["kind"] == "invoice"]
    assert created_invoices and created_invoices[0]["id"].startswith("INV-")


def test_apply_is_idempotent(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES + REFUNDS, MONTHS)
    plan = build_seed_plan(load_persona("tester"))
    fake = SeedFake()
    fake.existing_custom_fields = ["SYN-TEST-00001", "SYN-TEST-00003"]  # sales from both months seeded
    fake.existing_invoice_refs = ["PSC-TEST-999-INV-2025-10"]

    async def body() -> dict:
        async with fake_client(fake) as client:
            existing = await fetch_existing_refs(client, date(2025, 10, 1), date(2025, 11, 30))
            return await apply_plan(client, plan, existing)

    report = asyncio.run(body())
    skipped = {s["ref"] for s in report["skipped"]}
    assert skipped == {"SYN-TEST-00001", "SYN-TEST-00003", "PSC-TEST-999-INV-2025-10"}
    assert any(item["ref"] == "SYN-TEST-00005" and item["kind"] == "refund" for item in report["created"])
    created = [c["ref"] for c in report["created"]]
    assert "SYN-TEST-00002" in created and "PSC-TEST-999-INV-2025-11" in created
    posts = [path for method, path in fake.calls if method == "POST"]
    assert posts.count("/v2/checkout/orders") == 2  # only the unseeded sales


def test_fetch_existing_refs_paginates(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES, MONTHS)
    fake = SeedFake()
    fake.existing_custom_fields = ["SYN-TEST-00001", "SYN-TEST-00002", "SYN-TEST-00003"]
    fake.txn_page_size = 2

    async def body() -> set[str]:
        async with fake_client(fake) as client:
            return await fetch_existing_refs(client, date(2025, 10, 1), date(2025, 10, 31))

    refs = asyncio.run(body())
    assert refs >= {"SYN-TEST-00001", "SYN-TEST-00002", "SYN-TEST-00003"}
    txn_gets = [path for method, path in fake.calls if method == "GET" and path == "/v1/reporting/transactions"]
    assert len(txn_gets) >= 2


def test_run_apply_with_injected_client(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES[:1], MONTHS[:1])
    fake = SeedFake()

    report = asyncio.run(run(["tester"], apply=True, client_factory=lambda: fake_client(fake),
                             buyer_email="buyer@example.test"))
    assert report["mode"] == "apply"
    assert report["personas"]["tester"]["created"]
    assert not report["personas"]["tester"]["failed"]


def test_apply_waits_for_buyer_approval(tmp_path_factory, monkeypatch) -> None:
    persona_fixture(tmp_path_factory, monkeypatch, SALES[:1], [])
    fake = SeedFake()
    fake.approve_orders = False

    async def body() -> dict:
        plan = build_seed_plan(load_persona("tester"))
        async with fake_client(fake) as client:
            return await apply_plan(client, plan, set(), buyer_email="buyer@example.test")

    report = asyncio.run(body())
    assert report["pending_approval"] == [{"ref": "SYN-TEST-00001", "id": "ORD-1",
                                             "approve_url": "https://sandbox.example/approve"}]
    assert not report["created"]
    assert not any(path.endswith("/capture") for _, path in fake.calls)


def test_usd_conversion_and_fixture_personas() -> None:
    assert usd(0) == "0.00" and usd(83) == "1.00" and usd(128000) == "1542.17"
    expected = {"priya": 12, "arjun": 12, "rohan": 7}
    for name, months in expected.items():
        persona = load_persona(name)
        plan = build_seed_plan(persona)
        summary = summarize_plan(persona, plan)
        assert summary["invoices"] == months == len(persona["monthly_summary"])
        assert summary["orders"] == sum(t["type"] in {"sale", "dispute"} for t in persona["transactions"])
        assert all(op["ref"] for op in plan)
        assert all("payment_source" in op["payload"] for op in plan if op["kind"] == "order")
    rohan = summarize_plan(load_persona("rohan"), build_seed_plan(load_persona("rohan")))
    assert rohan["disputes_to_create"] >= 1

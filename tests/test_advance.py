from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from payscore.paypal.advance import (
    ADVANCES,
    apply_invoice_payment,
    draft_reminder_message,
    router,
)


def _app():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_advance_state():
    ADVANCES.clear()
    yield
    ADVANCES.clear()


def test_outstanding_invoices_returns_demo_rows():
    client = _app()
    res = client.get("/invoices/outstanding")
    assert res.status_code == 200
    data = res.json()
    assert data["sandbox"] is True
    assert len(data["invoices"]) == 2
    assert data["total_outstanding_inr"] == 70000


def test_create_advance_capped_at_fraction():
    client = _app()
    res = client.post("/advance", json={
        "applicant_id": "PSC-ADV-001",
        "invoice_ids": ["INV-PRIYA-OPEN-1", "INV-PRIYA-OPEN-2"],
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "open"
    assert data["invoice_total_inr"] == 70000.0
    assert data["advance_amount_inr"] == 42000.0  # 0.60 * 70000
    assert len(data["invoice_ids"]) == 2


def test_reminder_uses_tone_template_and_llm_fallback(monkeypatch):
    # Without LLM key, should fall back to templates
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    msg = draft_reminder_message("Elena Marsh", "INV-TEST-1", "firm")
    assert "Elena Marsh" in msg
    assert "INV-TEST-1" in msg

    # Mock LLM configured
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    msg_llm = draft_reminder_message("Meera Iyer", "INV-TEST-2", "formal")
    assert "formal reminder" in msg_llm or "Dear Meera Iyer" in msg_llm


def test_reminder_sends_and_generates_payment_link_and_qr():
    client = _app()
    res = client.post("/invoices/INV-PRIYA-OPEN-1/remind", json={"tone": "warm"})
    assert res.status_code == 200
    data = res.json()
    assert data["invoice_id"] == "INV-PRIYA-OPEN-1"
    assert "Elena Marsh" in data["message"]
    assert data["qr_url"].startswith("https://api.qrserver.com")
    assert "https://www.sandbox.paypal.com/invoice/p/#INV-PRIYA-OPEN-1" == data["payment_link"]


def test_invoice_payment_applies_to_advance(monkeypatch):
    # Create an advance first
    from payscore.paypal.advance import ADVANCES
    ADVANCES.clear()
    ADVANCES["ADV-TEST"] = {
        "advance_id": "ADV-TEST",
        "applicant_id": "PSC-TEST",
        "invoice_ids": ["INV-TEST-PAID"],
        "status": "open",
    }
    applied = apply_invoice_payment("INV-TEST-PAID")
    assert applied is not None
    assert applied["status"] == "repaid"
    assert applied["repaid_invoices"] == ["INV-TEST-PAID"]


def test_invoice_payment_partially_repaid():
    ADVANCES.clear()
    ADVANCES["ADV-PARTIAL"] = {
        "advance_id": "ADV-PARTIAL",
        "invoice_ids": ["INV-A", "INV-B"],
        "status": "open",
    }
    first = apply_invoice_payment("INV-A")
    assert first["status"] == "partially_repaid"
    second = apply_invoice_payment("INV-B")
    assert second["status"] == "repaid"

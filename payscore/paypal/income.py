"""Aggregates PayPal history into the documented income-profile response."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from .client import PayPalClient

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "personas"
PAYMENTS_PATH = "/v1/reporting/transactions"
DISPUTES_PATH = "/v1/customer/disputes"
INVOICES_PATH = "/v2/invoicing/invoices"
INR_PER_CURRENCY = {"INR": 1.0, "USD": 83.0}


def _shift_month(value: date, delta: int) -> date:
    index = value.year * 12 + value.month - 1 + delta
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _amount(obj: dict) -> float:
    value = obj.get("value", 0) if isinstance(obj, dict) else 0
    return float(value or 0)


def _transaction_parts(item: dict) -> tuple[dict, dict]:
    return item.get("transaction_info") or {}, item.get("payer_info") or {}


def _completed(info: dict) -> bool:
    return str(info.get("transaction_status", "S")).upper() in {"S", "SUCCESS", "COMPLETED"}


async def _pages(client: PayPalClient, path: str, token: str, params: dict,
                 result_key: str) -> list[dict]:
    collected: list[dict] = []
    page = 1
    while True:
        payload = await client.get(path, params={**params, "page": page}, bearer_token=token)
        rows = payload.get(result_key, []) or []
        collected.extend(row for row in rows if isinstance(row, dict))
        total_pages = int(payload.get("total_pages") or 0)
        if not rows or (total_pages and page >= total_pages) or (not total_pages and len(rows) < int(params.get("page_size", 100))):
            break
        page += 1
    return collected


async def paypal_profile(client: PayPalClient, token: str, *, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    start = _shift_month(today.replace(day=1), -11)
    end = today
    start_iso = datetime.combine(start, datetime.min.time(), timezone.utc).isoformat().replace("+00:00", "Z")
    end_iso = datetime.combine(end, datetime.max.time(), timezone.utc).isoformat().replace("+00:00", "Z")
    transactions = await _pages(client, PAYMENTS_PATH, token, {
        "start_date": start_iso, "end_date": end_iso, "page_size": 100,
    }, "transaction_details")
    disputes = await _pages(client, DISPUTES_PATH, token, {"page_size": 100}, "items")
    invoices = await _pages(client, INVOICES_PATH, token,
                            {"page_size": 100, "total_required": "true"}, "items")

    return build_profile(transactions, disputes, invoices, start=start, end=end, source="paypal")


def build_profile(transactions: list[dict], disputes: list[dict], invoices: list[dict], *,
                  start: date, end: date, source: str) -> dict:
    months = [(_shift_month(start.replace(day=1), offset).strftime("%Y-%m"), 0.0)
              for offset in range(12)]
    month_values = dict(months)
    sales: list[tuple[date, float]] = []
    refunds = 0
    clients: set[str] = set()
    client_sales: dict[str, float] = {}
    sale_count = 0
    dispute_count = 0

    for item in transactions:
        info, payer = _transaction_parts(item)
        occurred = _date(info.get("transaction_initiation_date") or info.get("transaction_updated_date"))
        if not occurred or not start <= occurred <= end or not _completed(info):
            continue
        event = str(info.get("transaction_event_code") or "")
        amount_obj = info.get("transaction_amount") or {}
        currency = str(amount_obj.get("currency_code", "INR")).upper()
        rate = INR_PER_CURRENCY.get(currency)
        if rate is None:
            continue
        amount = _amount(amount_obj) * rate
        month_key = occurred.strftime("%Y-%m")
        if month_key not in month_values:
            continue
        is_refund = event in {"T1107", "T1115", "T1120"} or info.get("transaction_type") == "refund"
        is_sale = (info.get("transaction_type") == "sale" or event in {"T0000", "T0001", "T0002", "T0003"}
                   or (not event and str(info.get("transaction_debit_credit_code", "CR")).upper() == "CR"))
        if is_refund:
            refunds += 1
            month_values[month_key] -= abs(amount)
        elif is_sale:
            sale_count += 1
            month_values[month_key] += amount
            sales.append((occurred, amount))
            client_id = (payer.get("account_id") or payer.get("email_address") or
                         info.get("paypal_account_id") or info.get("payer_id"))
            if client_id:
                cid = str(client_id)
                clients.add(cid)
                client_sales[cid] = client_sales.get(cid, 0.0) + amount

    for dispute in disputes:
        occurred = _date(dispute.get("create_time") or dispute.get("dispute_time") or dispute.get("update_time"))
        if occurred and start <= occurred <= end:
            dispute_count += 1

    monthly = [{"month": month, "income_inr": round(value, 2)} for month, value in month_values.items()]
    dated = sorted(day for day, _ in sales)
    longest_gap = max(((b - a).days for a, b in zip(dated, dated[1:])), default=0)
    populated = list(month_values.values())
    prior, latest = populated[-2:]
    trend = "increasing" if latest > prior else "decreasing" if latest < prior else "stable"
    outstanding = 0.0
    invoice_count = 0
    turnaround_days: list[int] = []
    late_invoice_count = 0
    paid_invoice_count = 0

    for invoice in invoices:
        status = str(invoice.get("status", "")).upper()
        if status in {"SENT", "UNPAID", "OVERDUE", "PARTIALLY_PAID"}:
            invoice_count += 1
            amount = invoice.get("amount") or {}
            due = invoice.get("due_amount") or invoice.get("remaining_balance") or amount
            currency = str(due.get("currency_code", "INR")).upper()
            outstanding += _amount(due) * INR_PER_CURRENCY.get(currency, 0.0)
        elif status in {"PAID", "MARKED_AS_PAID"}:
            paid_invoice_count += 1
            detail = invoice.get("detail") or invoice
            inv_date = _date(detail.get("invoice_date") or invoice.get("invoice_date") or invoice.get("create_time"))
            term = detail.get("payment_term") or {}
            due_date = _date(term.get("due_date") or detail.get("due_date") or invoice.get("due_date"))
            payments = invoice.get("payments") or {}
            txn_records = payments.get("transactions") or []
            paid_date = None
            if txn_records and isinstance(txn_records, list):
                paid_date = _date(txn_records[0].get("payment_date"))
            if not paid_date:
                paid_date = _date(invoice.get("paid_date") or invoice.get("update_time"))
            if inv_date and paid_date and paid_date >= inv_date:
                turnaround_days.append((paid_date - inv_date).days)
            if due_date and paid_date and paid_date > due_date:
                late_invoice_count += 1

    total_sales_amount = sum(s[1] for s in sales)
    top_client_share = (
        round(max(client_sales.values()) / total_sales_amount, 4)
        if (client_sales and total_sales_amount > 0) else None
    )
    avg_turnaround = (
        round(sum(turnaround_days) / len(turnaround_days), 1)
        if turnaround_days else None
    )
    late_rate = (
        round(late_invoice_count / paid_invoice_count, 4)
        if paid_invoice_count else None
    )

    return {
        "currency": "INR", "window_start": start.isoformat(), "window_end": end.isoformat(),
        "total_income_12m_inr": round(sum(populated), 2), "monthly_income_12m": monthly,
        "distinct_client_count_12m": len(clients),
        "top_client_revenue_share_12m": top_client_share,
        "avg_client_turnaround_days_12m": avg_turnaround,
        "late_payment_rate_12m": late_rate,
        "refund_rate_12m": round(min(refunds / sale_count, 1.0), 4) if sale_count else 0.0,
        "dispute_rate_12m": round(min(dispute_count / sale_count, 1.0), 4) if sale_count else 0.0,
        "longest_income_gap_days_12m": longest_gap, "income_trend_12m": trend,
        "outstanding_invoices_inr": round(outstanding, 2), "outstanding_invoice_count": invoice_count,
        "source": source,
    }


def fixture_profile(persona: str = "priya", *, today: date | None = None) -> dict:
    if persona not in {"priya", "arjun", "rohan"}:
        persona = "priya"
    data = json.loads((FIXTURES / f"{persona}.json").read_text(encoding="utf-8"))
    today = today or datetime.now(timezone.utc).date()
    start = _shift_month(today.replace(day=1), -11)
    transactions = []
    for txn in data.get("transactions", []):
        kind = txn.get("type")
        transactions.append({"transaction_info": {
            "transaction_initiation_date": txn.get("date"), "transaction_status": "S",
            "transaction_type": kind,
            "transaction_debit_credit_code": "CR" if kind == "sale" else "DR",
            "transaction_amount": {"currency_code": "INR", "value": txn.get("amount_inr", 0)},
        }, "payer_info": {"account_id": txn.get("client_id") or txn.get("category", "fixture-client")}})
    disputes = [{"create_time": txn.get("date")} for txn in data.get("transactions", [])
                if txn.get("type") == "dispute"]
    return build_profile(transactions, disputes, [], start=start, end=today, source="fixture")

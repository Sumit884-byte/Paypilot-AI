"""One-page Income Passport PDF builder (no third-party writer dependency).

Produces a selectable-text PDF using Helvetica, matching the project's existing
minimal PDF approach in ``tests/pdf_factory.py``, with a clearer layout for demos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _esc(text: str) -> str:
    safe = text.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _fmt_inr(value: Any) -> str:
    if value is None:
        return "Missing"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "Missing"
    return f"INR {amount:,.0f}"


def _cls_label(classification: str | None) -> str:
    mapping = {
        "verified_aggregate": "Verified aggregate",
        "fixture_aggregate": "Fixture aggregate (demo)",
        "derived": "Derived",
        "sandbox_ledger": "Sandbox ledger",
        "missing": "Missing",
        "disclosure": "Disclosure",
        "demo_persona": "Demo persona",
        "linked_paypal": "Linked PayPal",
    }
    return mapping.get(classification or "", classification or "Unspecified")


def build_passport_pdf(
    *,
    passport_reference: str,
    issued_at: datetime,
    expires_at: datetime,
    snapshot: dict[str, Any],
) -> bytes:
    borrower = snapshot.get("borrower") or {}
    income = snapshot.get("income_summary") or {}
    financial = snapshot.get("financial_summary") or {}
    verification = snapshot.get("verification") or {}
    repayment = financial.get("repayment") or {}

    lines: list[tuple[float, float, str, int]] = []  # x, y, text, font_size

    def add(x: float, y: float, text: str, size: int = 10) -> None:
        lines.append((x, y, text, size))

    # Header band content
    add(40, 748, "PayScore", 18)
    add(40, 728, "Income Passport", 14)
    add(40, 710, f"Reference  {passport_reference}", 9)
    add(320, 748, f"Issued  {issued_at.strftime('%Y-%m-%d %H:%M UTC')}", 8)
    add(320, 734, f"Expires {expires_at.strftime('%Y-%m-%d %H:%M UTC')}", 8)
    add(320, 720, f"Status  {verification.get('status', 'unknown')}", 8)

    add(40, 688, "Borrower", 11)
    add(40, 672, f"Name: {borrower.get('display_name', 'Unavailable')}", 9)
    add(40, 658, f"Applicant ref: {borrower.get('applicant_ref', 'Unavailable')}", 9)
    add(40, 644, f"Classification: {_cls_label(borrower.get('classification'))}", 9)
    add(320, 672, f"Verification: {verification.get('status', 'unknown')}", 9)
    add(320, 658, f"Method: {verification.get('method', 'Unavailable')}", 9)
    add(320, 644, f"Evidence: {verification.get('evidence_source', 'Unavailable')}", 9)

    add(40, 618, "Income summary", 11)
    total = income.get("total_verified_income_inr") or {}
    avg = income.get("average_monthly_income_inr") or {}
    consistency = (income.get("income_consistency") or {}).get("value") or {}
    period = (income.get("income_period") or {}).get("value") or {}
    months = income.get("months_with_income") or {}
    clients = income.get("distinct_client_count_12m") or {}

    y = 600
    income_rows = [
        ("Total income (12m)", _fmt_inr(total.get("value")), _cls_label(total.get("classification"))),
        ("Avg monthly income", _fmt_inr(avg.get("value")), _cls_label(avg.get("classification"))),
        (
            "Income consistency",
            f"{consistency.get('label', 'missing')}"
            + (f" (CV {consistency.get('cv')})" if consistency.get("cv") is not None else ""),
            _cls_label((income.get("income_consistency") or {}).get("classification")),
        ),
        (
            "Income period",
            f"{period.get('window_start', '?')} to {period.get('window_end', '?')}",
            _cls_label((income.get("income_period") or {}).get("classification")),
        ),
        ("Months with income", str(months.get("value") if months.get("value") is not None else "Missing"),
         _cls_label(months.get("classification"))),
        ("Distinct clients (12m)", str(clients.get("value") if clients.get("value") is not None else "Missing"),
         _cls_label(clients.get("classification"))),
    ]
    for label, value, classification in income_rows:
        add(48, y, label, 8)
        add(200, y, value, 8)
        add(360, y, classification, 8)
        y -= 14

    add(40, y - 8, "Financial summary", 11)
    y -= 26
    refund = financial.get("refund_rate_12m") or {}
    dispute = financial.get("dispute_rate_12m") or {}
    gap = financial.get("longest_income_gap_days_12m") or {}
    outstanding = financial.get("outstanding_invoices_inr") or {}

    def pct(val: Any) -> str:
        if val is None:
            return "Missing"
        try:
            return f"{float(val) * 100:.1f}%"
        except (TypeError, ValueError):
            return "Missing"

    fin_rows = [
        ("Refund rate (12m)", pct(refund.get("value")), _cls_label(refund.get("classification"))),
        ("Dispute rate (12m)", pct(dispute.get("value")), _cls_label(dispute.get("classification"))),
        ("Longest income gap", (
            f"{gap.get('value')} days" if gap.get("value") is not None else "Missing"
        ), _cls_label(gap.get("classification"))),
        ("Outstanding invoices", _fmt_inr(outstanding.get("value")),
         _cls_label(outstanding.get("classification"))),
        (
            "Repayment ledger",
            (
                f"{repayment.get('ledger_entry_count', 0)} entries; "
                f"deductions={repayment.get('total_revenue_share_deductions_recorded')}"
                if repayment.get("classification") == "sandbox_ledger"
                else "Missing"
            ),
            _cls_label(repayment.get("classification")),
        ),
    ]
    for label, value, classification in fin_rows:
        add(48, y, label, 8)
        add(200, y, str(value)[:42], 8)
        add(360, y, classification, 8)
        y -= 14

    add(40, y - 10, "Verification notes", 11)
    y -= 28
    note = verification.get("disclaimer") or ""
    # Word-wrap disclaimer
    words = note.split()
    chunk: list[str] = []
    for word in words:
        trial = (" ".join(chunk + [word])).strip()
        if len(trial) > 92:
            add(48, y, " ".join(chunk), 7)
            y -= 11
            chunk = [word]
        else:
            chunk.append(word)
    if chunk:
        add(48, y, " ".join(chunk), 7)
        y -= 14

    add(48, y, "Txn-level descriptions and bank credentials are intentionally omitted.", 7)
    y -= 12
    add(48, y, "PayScore provides decision-support insights, not guaranteed credit approval.", 7)

    add(40, 52, "Footer: Demo / sandbox document. Not a regulated credit report. Verify at /verify/income-passport/{token}.", 7)
    add(40, 38, "Classifications distinguish verified aggregates, fixture demo data, derived metrics, and missing fields.", 7)

    # Build content stream with a simple header rectangle (non-text).
    ops: list[str] = [
        # Header bar
        "0.00 0.44 0.73 rg",
        "40 700 532 60 re f",
        # Reset fill for text
        "1 1 1 rg",
    ]
    for x, y, text, size in lines:
        if y >= 700:
            ops.append("1 1 1 rg")
        else:
            ops.append("0.12 0.19 0.26 rg")
        ops.append("BT")
        ops.append(f"/F1 {size} Tf")
        ops.append(f"1 0 0 1 {x:.1f} {y:.1f} Tm ({_esc(text)}) Tj")
        ops.append("ET")

    for rule_y in (630, 470):
        ops.extend(["0.86 0.88 0.89 RG", "0.5 w", f"40 {rule_y} m 572 {rule_y} l S"])

    stream = "\n".join(ops).encode("latin-1", "replace")
    return _assemble_pdf(stream)


def _assemble_pdf(stream: bytes) -> bytes:
    objects: list[tuple[int, bytes]] = []
    # 1 catalog, 2 pages, 3 content, 4 page, 5 font
    objects.append((3, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
    objects.append((
        4,
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 3 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
    ))
    objects.append((5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objects.append((2, b"<< /Type /Pages /Count 1 /Kids [4 0 R] >>"))
    objects.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    objects.sort(key=lambda item: item[0])

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (objects[-1][0] + 1)
    for number, body in objects:
        offsets[number] = len(out)
        out.extend(f"{number} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    size = objects[-1][0] + 1
    out.extend(f"xref\n0 {size}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for number in range(1, size):
        out.extend(f"{offsets[number]:010d} 00000 n \n".encode())
    out.extend(f"trailer << /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(out)

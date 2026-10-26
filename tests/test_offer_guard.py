"""Offer guard prices cash flows, parses PDFs, and does not invent an RBI list."""

import json

import httpx

from payscore.finance import level_payment
from payscore.offer_pdf import extract_labeled_fields, merge_extractions
from payscore.rbi_directory import clear_directory_cache, match_lender, parse_rbi_html
from tests.pdf_factory import build_blank_pdf, build_text_pdf

SAMPLE_HTML = """
<html><body>
<p>Reserve Bank of India digital lending apps</p>
<table>
<tr><th>NBFC</th><th>Name of the digital lending app</th></tr>
<tr><td>Acme Finance Limited</td><td>Acme Pay</td></tr>
</table>
</body></html>
"""


def test_zero_fee_effective_apr_matches_advertised_and_fee_opens_a_gap(client):
    plain = client.post("/offer-guard", json={
        "advertised_apr_pct": 18, "processing_fee_pct": 0, "principal_inr": 50000,
        "term_months": 12, "lender_name": "Example NBFC",
    }).json()
    assert plain["comparison_status"] == "within_tolerance"
    assert plain["red_flag"] is False
    assert abs(plain["calculation"]["effective_annual_pct"] - 18) < 0.05
    assert plain["calculation"]["method"] == "monthly_irr_effective_annual"
    priced = client.post("/offer-guard", json={
        "advertised_apr_pct": 18, "processing_fee_pct": 4, "principal_inr": 50000, "term_months": 12,
    }).json()
    assert priced["red_flag"] is True
    assert priced["comparison_status"] == "advertised_below_calculated"
    assert priced["estimated_real_apr_pct"] > 18
    assert priced["directory"]["confirmed_violation"] is False
    assert priced["rbi_directory_match"] == "unverified"
    assert "bank" not in str(priced["directory"]["warning"]).lower() or "not a regulatory finding" in priced["directory"]["warning"]


def test_one_period_and_fee_that_consumes_principal(client):
    one = client.post("/offer-guard", json={
        "advertised_apr_pct": 0, "processing_fee_pct": 0, "principal_inr": 1000,
        "term_months": 1, "installment_inr": 1000,
    }).json()
    assert abs(one["calculation"]["effective_annual_pct"]) < 0.05
    consumed = client.post("/offer-guard", json={
        "advertised_apr_pct": 10, "processing_fee_pct": 0, "principal_inr": 1000,
        "term_months": 12, "processing_fee_inr": 1000,
    }).json()
    assert consumed["estimated_real_apr_pct"] is None
    assert any("positive" in warning for warning in consumed["warnings"])


def test_valid_pdf_flags_a_misleading_advertised_apr(client):
    instalment = level_payment(100000, 0.24, 12, 12)
    pdf = build_text_pdf([
        "Lender: Sample Finance",
        "Sanctioned loan amount: INR 100000",
        "Loan term: 12 months",
        "Interest rate: 24% fixed",
        "Advertised APR: 10%",
        "Processing fee: 10%",
        f"Instalment: INR {instalment:.2f}",
        "Repayment frequency: monthly",
        "Penalty: INR 500 late fee",
    ])
    response = client.post("/offer-guard/upload", files={"file": ("offer.pdf", pdf, "application/pdf")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["red_flag"] is True
    assert body["fields"]["principal_inr"]["value"] == 100000
    assert body["fields"]["principal_inr"]["verified"] is False
    assert body["calculation"]["arithmetic_checks"][0]["check"] == "installment_matches_nominal_rate"
    assert body["calculation"]["arithmetic_checks"][0]["consistent"] is True
    assert body["extraction"]["llm_status"] == "unavailable"
    assert any(item["item"] == "Contingent charges disclosed" and item["ok"] for item in body["kfs_checklist"])


def test_malformed_scanned_and_rejected_uploads(client, monkeypatch, tmp_path):
    bad = client.post("/offer-guard/upload", files={"file": ("offer.pdf", b"not a pdf", "application/pdf")})
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_pdf"
    assert "not a pdf" not in bad.text
    scanned = client.post("/offer-guard/upload", files={"file": ("scan.pdf", build_blank_pdf(), "application/pdf")})
    assert scanned.status_code == 200
    body = scanned.json()
    assert body["fields"]["principal_inr"]["status"] == "missing"
    assert body["extraction"]["ocr_status"] in {"unavailable", "completed", "not_needed"}
    if body["extraction"]["text_chars"] < 40:
        assert body["estimated_real_apr_pct"] is None
    wrong = client.post("/offer-guard/upload", files={"file": ("notes.txt", b"%PDF-1.4", "text/plain")})
    assert wrong.status_code == 400 and wrong.json()["error"] == "invalid_type"
    monkeypatch.setattr("payscore.offer_pdf.MAX_PAGES", 0)
    too_many = client.post("/offer-guard/upload", files={"file": ("offer.pdf", build_text_pdf(["Lender: A"]), "application/pdf")})
    assert too_many.status_code == 400 and too_many.json()["error"] == "too_many_pages"
    monkeypatch.setattr("payscore.offer_pdf.MAX_UPLOAD_BYTES", 20)
    too_big = client.post("/offer-guard/upload", files={"file": ("offer.pdf", build_text_pdf(["Lender: A"]), "application/pdf")})
    assert too_big.status_code == 400 and too_big.json()["error"] == "file_too_large"
    monkeypatch.setattr("payscore.offer_pdf.MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
    monkeypatch.setattr("payscore.offer_pdf.MAX_PAGES", 10)
    traversal = tmp_path / "secret.pdf"
    response = client.post(
        "/offer-guard/upload",
        files={"file": ("../secret.pdf", build_text_pdf(["Lender: Sample Finance", "Sanctioned loan amount: INR 1000", "Loan term: 1 months"]), "application/pdf")},
    )
    assert response.status_code == 200
    assert not traversal.exists()
    assert "secret.pdf" not in response.text


def test_llm_is_not_called_unless_external_use_is_enabled(client, monkeypatch):
    from payscore.offer_pdf import llm_extract

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.delenv("PAYSCORE_OFFER_LLM", raising=False)
    monkeypatch.delenv("PAYSCORE_OFFER_LLM_ALLOW_EXTERNAL", raising=False)

    def explode(*_args, **_kwargs):
        raise AssertionError("LLM was contacted")

    monkeypatch.setattr(httpx.Client, "post", explode)
    direct = llm_extract("Sanctioned loan amount: INR 2000")
    assert direct["status"] == "unavailable"
    assert "external_llm_disabled" in direct["reason"]
    monkeypatch.undo()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    pdf = build_text_pdf(["Lender: Sample Finance", "Sanctioned loan amount: INR 2000", "Loan term: 2 months"])
    response = client.post("/offer-guard/upload", files={"file": ("offer.pdf", pdf, "application/pdf")})
    assert response.status_code == 200
    assert "external_llm_disabled" in response.json()["extraction"]["llm_reason"]


def test_llm_disagreement_is_not_treated_as_fact():
    rules = extract_labeled_fields("Sanctioned loan amount: INR 10000\nLoan term: 6 months\n")
    llm = {"status": "ok", "fields": {"principal_inr": 99999, "term_months": 6}}
    merged = merge_extractions(rules, llm)
    assert merged["principal_inr"]["status"] == "ambiguous"
    assert merged["principal_inr"]["value"] is None
    assert merged["principal_inr"]["verified"] is False
    assert merged["term_months"]["value"] == 6
    assert merged["term_months"]["verified"] is False


def test_directory_parser_and_unavailable_source(monkeypatch):
    entries = parse_rbi_html(SAMPLE_HTML)
    assert entries == [{"nbfc_name": "Acme Finance Limited", "app_name": "Acme Pay"}]
    assert parse_rbi_html("<html><body>digital lending <a>Invented App</a></body></html>") == []
    found = match_lender("Acme Pay", {"entries": entries, "source_url": "https://www.rbi.org.in/example", "retrieved_at": "2026-10-25", "load_status": "test_fixture", "source_name": "fixture"})
    assert found["rbi_directory_match"] == "match"
    assert found["confirmed_violation"] is False
    missed = match_lender("Totally Different Lender", {"entries": entries, "source_url": "https://www.rbi.org.in/example", "retrieved_at": "2026-10-25", "load_status": "test_fixture", "source_name": "fixture"})
    assert missed["rbi_directory_match"] == "no_match"
    assert missed["confirmed_violation"] is False
    monkeypatch.setenv("PAYSCORE_RBI_FETCH", "false")
    clear_directory_cache()
    unverified = match_lender("Example NBFC")
    assert unverified["rbi_directory_match"] == "unverified"
    assert unverified["confirmed_violation"] is False
    assert unverified["entries_loaded"] == 0


def test_labeled_parser_leaves_unlabeled_numbers_missing():
    fields = extract_labeled_fields("Please pay 99999 soon.\n")
    assert fields["principal_inr"]["status"] == "missing"
    assert json.dumps(fields).count("99999") == 0

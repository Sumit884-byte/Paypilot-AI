"""Read a loan-offer PDF locally. Uploaded bytes are never executed.

An external LLM is used only when PAYSCORE_OFFER_LLM and
PAYSCORE_OFFER_LLM_ALLOW_EXTERNAL are both enabled and OPENAI_API_KEY is set.
That path sends offer text to the configured provider, so it must be used only
with synthetic or public samples. LLM numbers stay unverified.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

import httpx

from .offer_analysis import FIELD_NAMES, analyse, blank, given

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
MIN_TEXT_CHARS = 40

_NUMBER = r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"

# Prompt-injection guard: hidden adversarial text in a loan PDF must never reach
# the LLM or be treated as part of the offer. Default on so the demo is safe.
_INJECTION = [
    (re.compile(r"ignore\s+(all\s+)?previous\s+(instructions|directives)", re.I), "ignore_previous_instructions"),
    (re.compile(r"disregard\s+(all\s+)?(previous\s+)?(instructions|directives)", re.I), "disregard_instructions"),
    (re.compile(r"system\s+(prompt|override|instruction)", re.I), "system_override"),
    (re.compile(r"jailbreak", re.I), "jailbreak"),
    (re.compile(r"reveal\s+your\s+(system\s+)?prompt", re.I), "reveal_system_prompt"),
    (re.compile(r"print\s+your\s+instructions", re.I), "print_instructions"),
    (re.compile(r"you\s+are\s+now\s+(a\s+)?(different\s+)?ai", re.I), "role_reassignment"),
    (re.compile(r"forget\s+(everything|all)\s+(above|before)", re.I), "forget_prior_context"),
]


def guard_enabled() -> bool:
    """On unless explicitly disabled (set PAYSCORE_PDF_INJECTION_GUARD=false)."""
    return os.getenv("PAYSCORE_PDF_INJECTION_GUARD", "true").strip().lower() in {"1", "true", "yes", "on"}


def scan_injection(text: str) -> tuple[bool, list[str]]:
    """Return (found, reasons) for hidden adversarial prompt text in the document."""
    if not guard_enabled():
        return False, []
    reasons = [label for pattern, label in _INJECTION if pattern.search(text)]
    return bool(reasons), reasons


class PdfRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _collapse_numbers(values: list[float]) -> tuple[Optional[float], str]:
    if not values:
        return None, "missing"
    unique = []
    for value in values:
        if not any(abs(value - seen) <= max(0.01, abs(seen) * 1e-6) for seen in unique):
            unique.append(value)
    if len(unique) > 1:
        return None, "ambiguous"
    return unique[0], "extracted"


def _collapse_text(values: list[str]) -> tuple[Optional[str], str]:
    cleaned = [value.strip() for value in values if value and value.strip()]
    if not cleaned:
        return None, "missing"
    unique = []
    for value in cleaned:
        if value.casefold() not in {item.casefold() for item in unique}:
            unique.append(value)
    if len(unique) > 1:
        return None, "ambiguous"
    return unique[0][:160], "extracted"


def extract_labeled_fields(text: str) -> dict[str, dict[str, Any]]:
    """Label parser. Bare numbers without one of these labels are left missing."""
    buckets: dict[str, list[Any]] = {name: [] for name in FIELD_NAMES}
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        low = line.casefold()
        if re.search(r"^(lender|nbfc|regulated entity)\b", low):
            part = re.split(r"[:\-]", line, maxsplit=1)
            if len(part) == 2:
                buckets["lender_name"].append(part[1])
            continue
        if re.search(r"\b(apr|annual percentage rate|annualised percentage rate|annualized percentage rate)\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["advertised_apr_pct"].append(_number(found[0]))
            continue
        if re.search(r"\b(interest rate|rate of interest|nominal rate|roi)\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["nominal_interest_rate_pct"].append(_number(found[0]))
            if "floating" in low:
                buckets["rate_type"].append("floating")
            elif "fixed" in low:
                buckets["rate_type"].append("fixed")
            continue
        if re.search(r"\b(processing fee|processing charges)\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                number = _number(found[0])
                if "%" in line or "percent" in low:
                    buckets["processing_fee_pct"].append(number)
                else:
                    buckets["processing_fee_inr"].append(number)
            continue
        if re.search(r"\b(sanctioned loan amount|loan amount|principal amount|principal)\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["principal_inr"].append(_number(found[0]))
            continue
        if re.search(r"\b(tenure|tenor|loan term|term)\b", low) and re.search(r"\bmonths?\b", low):
            found = re.findall(r"([0-9]{1,3})", line)
            if found:
                buckets["term_months"].append(float(found[0]))
            continue
        if re.search(r"\b(instalments?|installments?|emi)\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["installment_inr"].append(_number(found[0]))
            continue
        if re.search(r"\b(other upfront|other charges)\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["other_upfront_charges_inr"].append(_number(found[0]))
            continue
        if re.search(r"\binsurance\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["insurance_inr"].append(_number(found[0]))
            continue
        if re.search(r"\b(net disbursed|net amount|amount disbursed)\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["net_disbursed_inr"].append(_number(found[0]))
            continue
        if re.search(r"\b(total amount payable|total repayable|total amount to be paid)\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["total_repayable_inr"].append(_number(found[0]))
            continue
        if re.search(r"\b(penal|penalty|late fee)\b", low):
            buckets["penalty_note"].append(line[:160])
            found = re.findall(_NUMBER, line)
            if found:
                buckets["penal_charge_inr"].append(_number(found[0]))
            continue
        if re.search(r"\bbounce\b", low):
            found = re.findall(_NUMBER, line)
            if found:
                buckets["bounce_charge_inr"].append(_number(found[0]))
            continue
        if re.search(r"\b(repayment frequency|instalment frequency|installment frequency)\b", low):
            for label in ("monthly", "weekly", "quarterly"):
                if label in low:
                    buckets["repayment_frequency"].append(label)
                    break
    fields: dict[str, dict[str, Any]] = {}
    for name in FIELD_NAMES:
        values = buckets[name]
        if name in {"lender_name", "penalty_note", "rate_type", "repayment_frequency"}:
            value, status = _collapse_text([str(item) for item in values])
        else:
            value, status = _collapse_numbers([float(item) for item in values])
            if name == "term_months" and value is not None:
                value = int(value)
        if status == "missing":
            fields[name] = blank("pdf_text")
        else:
            note = "Read from a labeled line in the PDF text. Not audited." if status == "extracted" else "More than one labeled value disagreed, so none was used."
            fields[name] = given(value, "pdf_text", status, note)
    return fields


_BOUNDS: dict[str, tuple[float, float]] = {
    "principal_inr": (1, 1_000_000_000),
    "term_months": (1, 360),
    "installment_inr": (1, 1_000_000_000),
    "nominal_interest_rate_pct": (0, 500),
    "advertised_apr_pct": (0, 100),
    "processing_fee_pct": (0, 50),
    "processing_fee_inr": (0, 1_000_000_000),
    "other_upfront_charges_inr": (0, 1_000_000_000),
    "insurance_inr": (0, 1_000_000_000),
    "penal_charge_inr": (0, 1_000_000_000),
    "bounce_charge_inr": (0, 1_000_000_000),
    "net_disbursed_inr": (0, 1_000_000_000),
    "total_repayable_inr": (1, 1_000_000_000),
}


def validate_field_ranges(fields: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    checked = {}
    for name, field in fields.items():
        bounds = _BOUNDS.get(name)
        value = field.get("value")
        if bounds and value is not None:
            low, high = bounds
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not (low <= float(value) <= high):
                checked[name] = given(None, field.get("source") or "pdf_text", "rejected", "Value was outside the supported range and was dropped.")
                continue
        checked[name] = field
    return checked


def merge_extractions(rules: dict[str, dict[str, Any]], llm: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Prefer labeled text. An LLM-only value stays unverified and is never called a fact."""
    merged = {name: dict(field) for name, field in rules.items()}
    if not llm or llm.get("status") != "ok":
        return validate_field_ranges(merged)
    llm_fields = llm.get("fields") or {}
    for name in FIELD_NAMES:
        proposed = llm_fields.get(name)
        if proposed is None:
            continue
        current = merged.get(name) or blank("pdf_text")
        if current.get("status") == "extracted" and _same(current.get("value"), proposed):
            current = dict(current)
            current["source"] = "pdf_text+llm"
            current["note"] = "Labeled text and the LLM agreed. The value is still not an audited fact."
            current["verified"] = False
            merged[name] = current
        elif current.get("status") == "extracted":
            merged[name] = given(
                None, "conflict", "ambiguous",
                "Labeled text and the LLM disagreed, so the value was not used.",
            )
        elif current.get("status") in {"missing", "ambiguous"}:
            merged[name] = given(
                proposed, "llm", "unverified_llm",
                "LLM extraction only. Not a verified fact.",
            )
    return validate_field_ranges(merged)


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, str) or isinstance(right, str):
        return str(left).strip().casefold() == str(right).strip().casefold()
    try:
        return abs(float(left) - float(right)) <= max(0.05, abs(float(left)) * 0.001)
    except (TypeError, ValueError):
        return False


def llm_status() -> dict[str, str]:
    allow = _env_on("PAYSCORE_OFFER_LLM") and _env_on("PAYSCORE_OFFER_LLM_ALLOW_EXTERNAL")
    key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
    if allow and key_present:
        return {"status": "configured", "reason": "external_llm_enabled"}
    reasons = []
    if not allow:
        reasons.append("external_llm_disabled")
    if not key_present:
        reasons.append("api_key_missing")
    return {"status": "unavailable", "reason": "+".join(reasons)}


def llm_extract(text: str) -> dict[str, Any]:
    state = llm_status()
    if state["status"] != "configured":
        return {"status": "unavailable", "reason": state["reason"], "fields": {}}
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {name: {"type": ["number", "string", "null"]} for name in FIELD_NAMES},
        "required": list(FIELD_NAMES),
    }
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract loan-offer fields into JSON. Use null when the document does not state the value. "
                    "Do not calculate, infer, or invent figures. Numbers must be plain JSON numbers."
                ),
            },
            {"role": "user", "content": text[:8000]},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "loan_offer", "strict": True, "schema": schema}},
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                base + "/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return {"status": "error", "reason": "llm_request_failed", "fields": {}}
    fields = {}
    if not isinstance(parsed, dict):
        return {"status": "error", "reason": "llm_response_not_object", "fields": {}}
    for name in FIELD_NAMES:
        raw = parsed.get(name)
        if raw is None or raw == "":
            fields[name] = None
            continue
        if name in {"lender_name", "penalty_note", "rate_type", "repayment_frequency"}:
            fields[name] = str(raw)[:160]
            continue
        try:
            number = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            fields[name] = None
            continue
        fields[name] = int(number) if name == "term_months" else number
    return {"status": "ok", "reason": None, "fields": fields, "verified": False}


def _page_text(path: Path) -> tuple[str, dict[str, Any]]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise PdfRejected("encrypted_pdf", "Encrypted PDFs are not accepted.")
        page_count = len(reader.pages)
    except PdfRejected:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfRejected("invalid_pdf", "The file could not be read as a PDF.") from exc
    if page_count < 1:
        raise PdfRejected("invalid_pdf", "The PDF has no pages.")
    if page_count > MAX_PAGES:
        raise PdfRejected("too_many_pages", f"PDFs are limited to {MAX_PAGES} pages.")
    try:
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfRejected("invalid_pdf", "Text could not be read from the PDF.") from exc
    return text, {"page_count": page_count, "text_chars": len(text.strip())}


def try_ocr(path: Path) -> tuple[str, dict[str, Any]]:
    """OCR is optional. Missing binaries are reported; they are not replaced with guessed terms."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return "", {"ocr_status": "unavailable", "ocr_reason": "pytesseract_or_pdf2image_not_installed"}
    try:
        images = convert_from_path(str(path), dpi=200, first_page=1, last_page=min(3, MAX_PAGES))
        text = "\n".join(pytesseract.image_to_string(image) for image in images)
    except Exception:
        return "", {"ocr_status": "unavailable", "ocr_reason": "ocr_runtime_failed"}
    if len(text.strip()) < MIN_TEXT_CHARS:
        return "", {"ocr_status": "completed", "ocr_reason": "no_text_recognised", "ocr_text_chars": len(text.strip())}
    return text, {"ocr_status": "completed", "ocr_reason": None, "ocr_text_chars": len(text.strip())}


def analyse_pdf_path(path: Path) -> dict[str, Any]:
    text, meta = _page_text(path)
    meta["ocr_status"] = "not_needed"
    if meta["text_chars"] < MIN_TEXT_CHARS:
        ocr_text, ocr_meta = try_ocr(path)
        meta.update(ocr_meta)
        if ocr_text:
            text = ocr_text
            meta["text_chars"] = len(ocr_text.strip())
            meta["text_source"] = "ocr"
        else:
            meta["text_source"] = "pdf_text"
    else:
        meta["text_source"] = "pdf_text"

    injection_found, injection_reasons = scan_injection(text)
    meta["injection_detected"] = injection_found
    meta["injection_reasons"] = injection_reasons

    rules = extract_labeled_fields(text)
    if injection_found:
        for field in rules.values():
            field["status"] = "rejected"
            field["note"] = ("Extraction blocked: hidden adversarial (prompt-injection) text "
                             "detected in the document; nothing was sent to the LLM.")
        llm = {"status": "blocked_injection", "reason": "prompt_injection_guard", "fields": {}}
    else:
        if meta.get("text_source") == "ocr":
            for field in rules.values():
                if field["status"] == "extracted":
                    field["status"] = "low_confidence"
                    field["source"] = "ocr"
                    field["note"] = "OCR text. Low confidence and not audited."
        llm = llm_extract(text) if meta["text_chars"] >= MIN_TEXT_CHARS else llm_status()
        if llm.get("status") != "ok":
            llm = {**llm_status(), "fields": {}} if "fields" not in llm else llm

    fields = merge_extractions(rules, llm if llm.get("status") == "ok" else None)
    result = analyse(fields, input_mode="pdf")
    result["injection_detected"] = injection_found
    result["injection_reasons"] = injection_reasons
    result["extraction"] = {
        "page_count": meta["page_count"],
        "text_chars": meta["text_chars"],
        "text_source": meta.get("text_source"),
        "ocr_status": meta.get("ocr_status"),
        "ocr_reason": meta.get("ocr_reason"),
        "injection_detected": injection_found,
        "injection_reasons": injection_reasons,
        "llm_status": llm.get("status"),
        "llm_reason": llm.get("reason"),
    }
    return result


def analyse_upload(blob: bytes, filename: str) -> dict[str, Any]:
    safe_name = Path(filename or "").name
    if "\x00" in (filename or "") or Path(safe_name).suffix.casefold() != ".pdf":
        raise PdfRejected("invalid_type", "Upload a PDF file. Other file types are not parsed.")
    if not blob.startswith(b"%PDF"):
        raise PdfRejected("invalid_pdf", "The file does not start with a PDF header.")
    if len(blob) > MAX_UPLOAD_BYTES:
        raise PdfRejected("file_too_large", "The PDF exceeds the 5 MB upload limit.")
    handle = tempfile.NamedTemporaryFile(prefix="payscore-offer-", suffix=".pdf", delete=False)
    temp_path = Path(handle.name)
    try:
        handle.write(blob)
        handle.close()
        return analyse_pdf_path(temp_path)
    finally:
        handle.close()
        try:
            temp_path.unlink()
        except OSError:
            pass

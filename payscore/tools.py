"""Plain-Python entry points shared by the CLI and the MCP server.

They call the same code as the HTTP API, in-process, so no server needs to be running. Every tool here is
analysis only: none of them creates a payout, subscription, order, or any other money movement.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from .affordability import AffordabilityRequest, assess
from .copilot_agent import handle_chat
from .counterfactual import analyse_counterfactual
from .model import DEFAULT_MODEL_DIR, Scorer
from .model_card import _metadata_payload
from .offer_analysis import analyse, manual_fields
from .offer_guard import OfferGuardRequest
from .offer_pdf import MAX_UPLOAD_BYTES, PdfRejected, analyse_upload
from .pay_later import PayLaterRequest, compare
from .paypal.income import fixture_profile
from .schema import ScoreRequest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "personas"
PERSONAS = ("priya", "arjun", "rohan")


class ToolInputError(ValueError):
    """Bad input from the caller, with a message fit to show them."""


def _validated(model: type, payload: dict[str, Any]):
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in exc.errors())
        raise ToolInputError(problems) from None


@lru_cache(maxsize=1)
def scorer() -> Scorer:
    model_dir = os.getenv("PAYSCORE_MODEL_DIR") or DEFAULT_MODEL_DIR
    allow_fallback = os.getenv("PAYSCORE_ALLOW_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}
    return Scorer.from_dir(model_dir, allow_fallback=allow_fallback)


def _persona(name: str) -> dict[str, Any]:
    key = name.strip().lower()
    if key not in PERSONAS:
        raise ToolInputError(f"Unknown persona '{name}'. Choose one of: {', '.join(PERSONAS)}.")
    return json.loads((FIXTURES / f"{key}.json").read_text(encoding="utf-8"))


def _application(applicant: str) -> ScoreRequest:
    """A persona name, or a path to a JSON file holding a score request (or a persona with `model_input`)."""
    path = Path(applicant).expanduser()
    if applicant.strip().lower() in PERSONAS:
        payload = _persona(applicant)["model_input"]
    elif path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        payload = data.get("model_input", data)
    else:
        raise ToolInputError(f"'{applicant}' is neither a persona ({', '.join(PERSONAS)}) nor a JSON file.")
    return _validated(ScoreRequest, payload)


def list_personas() -> list[dict[str, Any]]:
    """The synthetic demo personas, with their story and loan request."""
    out = []
    for key in PERSONAS:
        data = _persona(key)
        scenario = data.get("scenario") or {}
        out.append({
            "persona": key,
            "applicant_id": data["persona_id"],
            "name": data["display_name"],
            "business": (data.get("profile") or {}).get("description"),
            "requested_amount_inr": scenario.get("requested_amount_inr"),
            "requested_term_months": scenario.get("requested_term_months"),
            "synthetic": True,
        })
    return out


def score(applicant: str) -> dict[str, Any]:
    """PayScore (300-850), risk band, eligibility, and TreeSHAP drivers for a persona or request file."""
    return scorer().score(_application(applicant))


def what_if(applicant: str) -> dict[str, Any]:
    """Model-scored changes the applicant could make that would raise their score."""
    return analyse_counterfactual(scorer(), _application(applicant))


def income_profile(persona: str) -> dict[str, Any]:
    """12-month income profile built from the persona's synthetic transactions."""
    _persona(persona)
    return fixture_profile(persona.strip().lower())


def check_offer(advertised_apr_pct: float, principal_inr: float, term_months: int,
                processing_fee_pct: float = 0, lender_name: str = "Unknown lender") -> dict[str, Any]:
    """Compare a loan's advertised APR with the effective annual cost of its cash flows (monthly IRR)."""
    req = _validated(OfferGuardRequest, {
        "advertised_apr_pct": advertised_apr_pct, "processing_fee_pct": processing_fee_pct,
        "principal_inr": principal_inr, "term_months": term_months, "lender_name": lender_name,
    })
    return analyse(manual_fields(req.model_dump()), input_mode="manual")


def check_offer_pdf(path: str) -> dict[str, Any]:
    """Extract terms from a loan-offer PDF, price them, and flag hidden prompt-injection text."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise ToolInputError(f"No file at {path}.")
    if file.stat().st_size > MAX_UPLOAD_BYTES:
        raise ToolInputError(f"The PDF is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    try:
        return analyse_upload(file.read_bytes(), file.name)
    except PdfRejected as exc:
        raise ToolInputError(exc.message) from None


def compare_pay_later(purchase_amount: float, advertised_apr_pct: float, term_months: int,
                      processing_fee_pct: float = 0, market: str = "IN",
                      lender_name: str = "Unknown lender") -> dict[str, Any]:
    """Price a purchase with a loan offer and with PayPal Pay Later; rank by cost of credit."""
    return compare(_validated(PayLaterRequest, {
        "purchase_amount": purchase_amount, "market": market, "advertised_apr_pct": advertised_apr_pct,
        "processing_fee_pct": processing_fee_pct, "term_months": term_months, "lender_name": lender_name,
    }))


def affordability(requested_amount_inr: float, monthly_income_inr: Optional[float] = None,
                  essential_expenses_inr: Optional[float] = None, tenure_months: Optional[int] = None,
                  annual_interest_rate_pct: Optional[float] = None,
                  existing_monthly_debt_payments_inr: Optional[float] = None) -> dict[str, Any]:
    """Instalment burden and stressed cash flow for a loan amount. Missing inputs are reported, not guessed."""
    payload = {k: v for k, v in {
        "requested_amount_inr": requested_amount_inr, "monthly_income_inr": monthly_income_inr,
        "essential_expenses_inr": essential_expenses_inr, "tenure_months": tenure_months,
        "annual_interest_rate_pct": annual_interest_rate_pct,
        "existing_monthly_debt_payments_inr": existing_monthly_debt_payments_inr,
    }.items() if v is not None}
    return assess(_validated(AffordabilityRequest, payload).model_dump())


def ask_copilot(message: str, persona: str = "priya") -> dict[str, Any]:
    """Ask the PayScore copilot. A payout request returns an approval card only; nothing is executed."""
    if not message.strip():
        raise ToolInputError("The message is empty.")
    return handle_chat(message, _persona(persona)["persona_id"], scorer())


def model_card() -> dict[str, Any]:
    """Model metadata, metrics on the synthetic test split, and excluded sensitive attributes."""
    return _metadata_payload(scorer())

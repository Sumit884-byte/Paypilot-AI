"""Validate offer terms and compare an advertised APR with an IRR-based cost.

Nothing in this module treats an extracted or model-generated number as an audited fact.
`verified` stays false. Arithmetic can show that figures are consistent with each other.
"""

from __future__ import annotations

from typing import Any, Optional

from .finance import (
    CalculationError,
    effective_annual_rate,
    level_payment,
    level_payment_from_effective_annual,
)
from .rbi_directory import match_lender

DISCLAIMER = (
    "Sandbox estimate. The effective annualised cost is an IRR of the cash flows we could use. "
    "It is not a certified Key Facts Statement review, not legal advice, and not an RBI decision."
)
KFS_SOURCE = (
    "Checklist headings follow the Reserve Bank of India Key Facts Statement for Loans & Advances "
    "(circular RBI/2024-25/18, DOR.STR.REC.13/13.03.00/2024-25, 15 April 2024). A gap means the "
    "text or form we saw did not contain that item. It is not a finding that the lender broke the circular."
)
DISCREPANCY_PERCENTAGE_POINTS = 1.0
USABLE = {"user_supplied", "extracted", "unverified_llm", "low_confidence"}
DISCLOSED = {"user_supplied", "extracted"}
FIELD_NAMES = (
    "lender_name", "principal_inr", "term_months", "installment_inr", "nominal_interest_rate_pct",
    "advertised_apr_pct", "processing_fee_pct", "processing_fee_inr", "other_upfront_charges_inr",
    "insurance_inr", "penalty_note", "penal_charge_inr", "bounce_charge_inr", "net_disbursed_inr",
    "total_repayable_inr", "rate_type", "repayment_frequency",
)


def blank(source: str = "none") -> dict[str, Any]:
    return {"value": None, "status": "missing", "source": source, "verified": False, "note": ""}


def given(value: Any, source: str, status: str = "user_supplied", note: str = "") -> dict[str, Any]:
    return {"value": value, "status": status, "source": source, "verified": False, "note": note}


def usable(field: Optional[dict[str, Any]]) -> bool:
    return bool(field) and field.get("status") in USABLE and field.get("value") is not None


def value_of(fields: dict[str, dict[str, Any]], name: str) -> Any:
    field = fields.get(name) or blank()
    return field.get("value") if usable(field) else None


def manual_fields(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map the manual form onto the shared field records. Omitted optionals stay missing."""
    source = "manual"
    fields = {name: blank(source) for name in FIELD_NAMES}
    fields["lender_name"] = given(payload.get("lender_name") or "Unknown lender", source)
    fields["principal_inr"] = given(payload.get("principal_inr"), source)
    fields["term_months"] = given(payload.get("term_months"), source)
    fields["advertised_apr_pct"] = given(payload.get("advertised_apr_pct"), source)
    fields["processing_fee_pct"] = given(payload.get("processing_fee_pct", 0), source)
    for name in (
        "installment_inr", "nominal_interest_rate_pct", "processing_fee_inr",
        "other_upfront_charges_inr", "insurance_inr", "penal_charge_inr", "bounce_charge_inr",
        "net_disbursed_inr", "total_repayable_inr",
    ):
        if payload.get(name) is not None:
            fields[name] = given(payload.get(name), source)
    if payload.get("other_upfront_charges_inr") is None:
        fields["other_upfront_charges_inr"] = given(0, source, note="Manual form defaulted other upfront charges to zero.")
    return fields


def _upfront_fees(fields: dict[str, dict[str, Any]], principal: float, warnings: list[str]) -> float:
    fee_inr = value_of(fields, "processing_fee_inr")
    fee_pct = value_of(fields, "processing_fee_pct")
    processing = 0.0
    if fee_inr is not None and fee_pct is not None:
        expected = principal * float(fee_pct) / 100.0
        if abs(expected - float(fee_inr)) > max(1.0, principal * 0.005):
            warnings.append(
                "Processing-fee percent and rupee amount disagree. The rupee amount was used, and neither figure is marked verified."
            )
        processing = float(fee_inr)
    elif fee_inr is not None:
        processing = float(fee_inr)
    elif fee_pct is not None:
        processing = principal * float(fee_pct) / 100.0
    other = float(value_of(fields, "other_upfront_charges_inr") or 0)
    insurance = float(value_of(fields, "insurance_inr") or 0)
    if value_of(fields, "insurance_inr") is not None:
        warnings.append("Insurance was treated as an upfront charge in the cash flows because a figure was supplied.")
    return processing + other + insurance


def _kfs_item(item: str, ok: bool, status: str, detail: str) -> dict[str, Any]:
    return {"item": item, "ok": bool(ok), "status": status, "detail": detail}


def _disclosed(field: Optional[dict[str, Any]]) -> tuple[bool, str]:
    if field and field.get("status") in DISCLOSED and field.get("value") is not None:
        return True, field["status"]
    if not field or field.get("status") == "missing":
        return False, "missing"
    if field.get("status") == "ambiguous":
        return False, "ambiguous"
    if field.get("status") in {"unverified_llm", "low_confidence"}:
        return False, field["status"]
    if field.get("status") == "rejected":
        return False, "rejected"
    return False, field.get("status") or "missing"


def kfs_checklist(fields: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    amount_ok, amount_status = _disclosed(fields.get("principal_inr"))
    term_ok, term_status = _disclosed(fields.get("term_months"))
    instalment_ok, instalment_status = _disclosed(fields.get("installment_inr"))
    rate_ok, rate_status = _disclosed(fields.get("nominal_interest_rate_pct"))
    type_ok, type_status = _disclosed(fields.get("rate_type"))
    fee_ok = _disclosed(fields.get("processing_fee_inr"))[0] or _disclosed(fields.get("processing_fee_pct"))[0]
    fee_status = "disclosed" if fee_ok else "missing"
    apr_ok, apr_status = _disclosed(fields.get("advertised_apr_pct"))
    net_ok, net_status = _disclosed(fields.get("net_disbursed_inr"))
    total_ok, total_status = _disclosed(fields.get("total_repayable_inr"))
    freq_ok, freq_status = _disclosed(fields.get("repayment_frequency"))
    contingent = _disclosed(fields.get("penalty_note"))[0] or _disclosed(fields.get("penal_charge_inr"))[0] or _disclosed(fields.get("bounce_charge_inr"))[0]
    return [
        _kfs_item("Sanctioned loan amount", amount_ok, amount_status, "RBI KFS item: sanctioned loan amount."),
        _kfs_item("Loan term", term_ok, term_status, "RBI KFS item: loan term."),
        _kfs_item("Instalment amount disclosed", instalment_ok, instalment_status,
                  "A calculated instalment is not treated as a disclosure."),
        _kfs_item("Interest rate", rate_ok, rate_status, "Nominal or stated interest rate, separate from APR."),
        _kfs_item("Interest rate type (fixed or floating)", type_ok, type_status, "RBI KFS asks for the rate type."),
        _kfs_item("Processing or upfront fee disclosed", fee_ok, fee_status, "Fee percent or fee amount."),
        _kfs_item("Annual percentage rate disclosed", apr_ok, apr_status, "Disclosure of an APR figure, not confirmation that it matches the cash flows."),
        _kfs_item("Net disbursed amount disclosed", net_ok, net_status, "Calculated net proceeds do not count as disclosure."),
        _kfs_item("Total amount payable disclosed", total_ok, total_status, "Calculated total does not count as disclosure."),
        _kfs_item("Repayment frequency disclosed", freq_ok, freq_status, "The calculator assumes monthly only when a frequency is absent."),
        _kfs_item("Contingent charges disclosed", contingent, "disclosed" if contingent else "missing",
                  "Penalties and bounce charges. These are excluded from the IRR because they are uncertain."),
    ]


def analyse(fields: dict[str, dict[str, Any]], *, input_mode: str) -> dict[str, Any]:
    warnings: list[str] = []
    assumptions = [
        "Effective annualised cost = (1 + r) ^ 12 - 1, where r is the monthly IRR of net proceeds and the level instalment.",
        "Net proceeds = principal minus processing fee, other upfront charges, and insurance when those figures are usable.",
        "Contingent penalties and bounce charges are reported and are not included in the IRR.",
        "No extracted or LLM value is marked verified. Agreement between a label parser and arithmetic is a consistency check only.",
        KFS_SOURCE,
        DISCLAIMER,
    ]
    if any(field.get("status") == "unverified_llm" for field in fields.values()):
        warnings.append("At least one cash-flow input came only from an LLM and is not a verified fact.")
    if any(field.get("status") == "low_confidence" for field in fields.values()):
        warnings.append("At least one figure came from OCR and is low confidence.")
    principal = value_of(fields, "principal_inr")
    term = value_of(fields, "term_months")
    frequency = value_of(fields, "repayment_frequency") or "monthly"
    if value_of(fields, "repayment_frequency") is None:
        assumptions.append("Repayment frequency was not disclosed. The IRR uses monthly periods.")
        frequency = "monthly"
    elif str(frequency).casefold() != "monthly":
        warnings.append("Only monthly cash flows are calculated. A non-monthly frequency was not converted.")
        frequency = "monthly"

    calculation: dict[str, Any] = {
        "method": "monthly_irr_effective_annual",
        "formula": "(1 + r)^12 - 1, r solves NPV(net proceeds, monthly instalments) = 0",
        "pricing_basis": None,
        "installment_inr": None,
        "installment_source": None,
        "upfront_fees_inr": None,
        "net_proceeds_inr": None,
        "effective_annual_pct": None,
        "effective_annual_pct_display": None,
        "advertised_apr_pct": value_of(fields, "advertised_apr_pct"),
        "difference_percentage_points": None,
        "discrepancy_threshold_percentage_points": DISCREPANCY_PERCENTAGE_POINTS,
        "red_flag": False,
        "comparison_status": "not_compared",
        "excluded_from_cashflows": ["contingent_penalties", "bounce_charges"],
        "arithmetic_checks": [],
    }
    lender = value_of(fields, "lender_name") or "Unknown lender"
    directory = match_lender(str(lender))
    if principal is None or term is None:
        warnings.append("Principal or tenure is missing, so the effective cost was not calculated.")
        return _package(fields, calculation, warnings, assumptions, directory, input_mode)

    principal = float(principal)
    term = int(term)
    upfront = _upfront_fees(fields, principal, warnings)
    net = principal - upfront
    calculation["upfront_fees_inr"] = round(upfront, 2)
    calculation["net_proceeds_inr"] = round(net, 2)
    if net <= 0:
        warnings.append("Upfront charges are not smaller than principal, so there is no positive amount received to price.")
        return _package(fields, calculation, warnings, assumptions, directory, input_mode)

    stated_net = value_of(fields, "net_disbursed_inr")
    if stated_net is not None and abs(float(stated_net) - net) > max(1.0, 0.01 * principal):
        warnings.append("The stated net disbursed amount does not match principal minus the upfront charges we used.")
        calculation["arithmetic_checks"].append({"check": "net_disbursed", "consistent": False})
    elif stated_net is not None:
        calculation["arithmetic_checks"].append({"check": "net_disbursed", "consistent": True})

    nominal = value_of(fields, "nominal_interest_rate_pct")
    advertised = value_of(fields, "advertised_apr_pct")
    stated_instalment = value_of(fields, "installment_inr")
    formula_instalment = None
    if nominal is not None:
        try:
            formula_instalment = level_payment(principal, float(nominal) / 100.0, term, 12)
            calculation["pricing_basis"] = "nominal_reducing_balance"
        except CalculationError as exc:
            warnings.append(str(exc))
    elif advertised is not None and stated_instalment is None:
        try:
            formula_instalment = level_payment_from_effective_annual(principal, float(advertised) / 100.0, term, 12)
            calculation["pricing_basis"] = "advertised_apr_as_effective"
            assumptions.append(
                "The advertised APR was the only rate, so the instalment was built to match that effective annual rate "
                "before fees. Fees then raise the IRR above the advertised figure when they reduce net proceeds."
            )
        except CalculationError as exc:
            warnings.append(str(exc))

    instalment = None
    if stated_instalment is not None:
        instalment = float(stated_instalment)
        calculation["installment_source"] = fields["installment_inr"]["status"]
        if formula_instalment is not None and nominal is not None:
            tolerance = max(2.0, 0.02 * formula_instalment)
            consistent = abs(instalment - formula_instalment) <= tolerance
            calculation["arithmetic_checks"].append({
                "check": "installment_matches_nominal_rate",
                "consistent": consistent,
                "formula_installment_inr": round(formula_instalment, 2),
                "tolerance_inr": round(tolerance, 2),
            })
            if not consistent:
                warnings.append(
                    "The stated instalment does not match the reducing-balance instalment from the nominal rate. "
                    "The stated instalment was used because it is the cash flow, and it was not rewritten."
                )
        calculation["pricing_basis"] = calculation["pricing_basis"] or "stated_installment"
    elif formula_instalment is not None:
        instalment = formula_instalment
        calculation["installment_source"] = "calculated"
    else:
        warnings.append("No instalment, nominal rate, or advertised APR was usable, so the effective cost was not calculated.")
        return _package(fields, calculation, warnings, assumptions, directory, input_mode)

    calculation["installment_inr"] = round(instalment, 2)
    stated_total = value_of(fields, "total_repayable_inr")
    expected_total = instalment * term
    if stated_total is not None:
        consistent = abs(float(stated_total) - expected_total) <= max(2.0, 0.01 * expected_total)
        calculation["arithmetic_checks"].append({"check": "total_repayable_matches_installments", "consistent": consistent})
        if not consistent:
            warnings.append("The stated total amount payable does not match instalment times tenure. Contingent charges were not added to that comparison.")

    try:
        effective = effective_annual_rate(net, instalment, term, 12)
    except CalculationError as exc:
        warnings.append(str(exc))
        return _package(fields, calculation, warnings, assumptions, directory, input_mode)
    effective_pct = effective * 100.0
    calculation["effective_annual_pct"] = round(effective_pct, 4)
    calculation["effective_annual_pct_display"] = round(effective_pct, 2)
    if advertised is None:
        calculation["comparison_status"] = "not_compared"
        calculation["red_flag"] = False
        warnings.append("No advertised APR was usable, so no discrepancy flag was raised.")
    else:
        gap = effective_pct - float(advertised)
        calculation["difference_percentage_points"] = round(gap, 4)
        if gap >= DISCREPANCY_PERCENTAGE_POINTS:
            calculation["comparison_status"] = "advertised_below_calculated"
            calculation["red_flag"] = True
            warnings.append(
                "The calculated effective annualised cost exceeds the advertised APR by at least "
                f"{DISCREPANCY_PERCENTAGE_POINTS:.0f} percentage point. This is a potential warning, not a legal determination."
            )
        elif gap <= -DISCREPANCY_PERCENTAGE_POINTS:
            calculation["comparison_status"] = "advertised_above_calculated"
            calculation["red_flag"] = False
            warnings.append("The advertised APR is higher than the calculated effective cost. The figures still were not audited.")
        else:
            calculation["comparison_status"] = "within_tolerance"
            calculation["red_flag"] = False
    return _package(fields, calculation, warnings, assumptions, directory, input_mode)


def _missing_names(fields: dict[str, dict[str, Any]]) -> list[str]:
    return [name for name, field in fields.items() if field.get("status") in {"missing", "ambiguous", "rejected", "unverified_llm", "low_confidence"} and name != "penalty_note"]


def _package(fields, calculation, warnings, assumptions, directory, input_mode) -> dict[str, Any]:
    advertised = value_of(fields, "advertised_apr_pct")
    fee_pct = value_of(fields, "processing_fee_pct")
    return {
        "input_mode": input_mode,
        "advertised_apr_pct": advertised,
        "estimated_real_apr_pct": calculation.get("effective_annual_pct_display"),
        "processing_fee_pct": fee_pct,
        "red_flag": bool(calculation.get("red_flag")),
        "comparison_status": calculation.get("comparison_status"),
        "kfs_checklist": kfs_checklist(fields),
        "kfs_source": KFS_SOURCE,
        "rbi_directory_match": directory["rbi_directory_match"],
        "directory": directory,
        "fields": fields,
        "missing_or_unverified_fields": _missing_names(fields),
        "calculation": calculation,
        "warnings": warnings,
        "assumptions": assumptions,
        "sandbox": True,
        "disclaimer": DISCLAIMER,
    }

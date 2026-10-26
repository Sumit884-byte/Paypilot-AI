import json

import pytest
from conftest import ROOT
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from payscore.export_schema import persona_schema, request_schema
from payscore.schema import ScoreRequest


def test_example_request_valid(example_request):
    assert ScoreRequest.model_validate(example_request).applicant_id == "PSC-EXAMPLE-001"


def test_optional_fields_may_be_omitted(example_request):
    minimal = {k: example_request[k] for k in (
        "applicant_id", "age_years", "employment_type", "monthly_income_inr",
        "requested_loan_amount_inr", "requested_term_months")}
    req = ScoreRequest.model_validate(minimal)
    assert req.revenue_volatility_cv is None


@pytest.mark.parametrize("field,value", [
    ("age_years", 17), ("age_years", 101), ("employment_type", "astronaut"),
    ("monthly_income_inr", -1), ("monthly_income_inr", float("nan")),
    ("requested_loan_amount_inr", 0), ("requested_term_months", 0), ("requested_term_months", 361),
    ("refund_rate_90d", 1.5), ("dispute_rate_12m", -0.1), ("active_months_12m", 13),
    ("applicant_id", ""), ("applicant_id", "has space"), ("applicant_id", "a@b.com"),
    ("prior_defaults_count", -1), ("revenue_volatility_cv", float("inf")),
])
def test_invalid_values_rejected(example_request, field, value):
    with pytest.raises(ValidationError):
        ScoreRequest.model_validate({**example_request, field: value})


def test_unknown_field_rejected(example_request):
    with pytest.raises(ValidationError):
        ScoreRequest.model_validate({**example_request, "full_name": "X"})


@pytest.mark.parametrize("missing", ["applicant_id", "age_years", "employment_type", "monthly_income_inr",
                                     "requested_loan_amount_inr", "requested_term_months"])
def test_required_fields(example_request, missing):
    body = dict(example_request)
    body.pop(missing)
    with pytest.raises(ValidationError):
        ScoreRequest.model_validate(body)


def test_committed_schemas_match_code():
    """schema/*.json must be regenerated whenever the pydantic model changes."""
    on_disk_req = json.loads((ROOT / "schema" / "score_request.schema.json").read_text())
    on_disk_persona = json.loads((ROOT / "schema" / "persona.schema.json").read_text())
    assert on_disk_req == request_schema()
    assert on_disk_persona == persona_schema()


def test_schemas_are_valid_json_schema():
    Draft202012Validator.check_schema(request_schema())
    Draft202012Validator.check_schema(persona_schema())

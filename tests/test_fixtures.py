import json
import re
from datetime import date

import pytest
from conftest import PERSONA_FILES
from jsonschema import Draft202012Validator

from payscore.build_fixtures import PERSONAS, build_persona
from payscore.derive import derive_metrics, months_before, months_between
from payscore.export_schema import persona_schema
from payscore.schema import ScoreRequest

NAMES = {"priya", "arjun", "rohan"}


def test_three_persona_files_exist():
    assert {p.stem for p in PERSONA_FILES} == NAMES


@pytest.mark.parametrize("name", sorted(NAMES))
def test_persona_validates_against_schema(personas, name):
    errors = list(Draft202012Validator(persona_schema()).iter_errors(personas[name]))
    assert not errors, errors[0].message


@pytest.mark.parametrize("name", sorted(NAMES))
def test_persona_is_marked_synthetic(personas, name):
    p = personas[name]
    assert p["synthetic"] is True
    assert "fictional" in p["display_name"].lower()
    assert p["model_input"]["applicant_id"].startswith("PSC-")
    assert all(t["txn_id"].startswith("SYN-") for t in p["transactions"])


@pytest.mark.parametrize("name", sorted(NAMES))
def test_model_input_is_valid_score_request(personas, name):
    ScoreRequest.model_validate(personas[name]["model_input"])


@pytest.mark.parametrize("name", sorted(NAMES))
def test_model_input_consistent_with_transactions(personas, name):
    p = personas[name]
    derived = derive_metrics(p["transactions"], date.fromisoformat(p["as_of_date"]))
    for k, v in derived.items():
        assert p["model_input"][k] == v, k


@pytest.mark.parametrize("name", sorted(NAMES))
def test_scenario_matches_model_input(personas, name):
    p = personas[name]
    assert p["scenario"]["requested_amount_inr"] == p["model_input"]["requested_loan_amount_inr"]
    assert p["scenario"]["requested_term_months"] == p["model_input"]["requested_term_months"]


@pytest.mark.parametrize("name", sorted(NAMES))
def test_no_future_or_invalid_transactions(personas, name):
    p = personas[name]
    as_of = date.fromisoformat(p["as_of_date"])
    ids = [t["txn_id"] for t in p["transactions"]]
    assert len(ids) == len(set(ids))
    for t in p["transactions"]:
        assert date.fromisoformat(t["date"]) < as_of
        assert t["amount_inr"] > 0
        assert t["type"] in {"sale", "refund", "dispute", "expense"}


def test_fixtures_are_reproducible(tmp_path):
    """Committed fixtures must equal a fresh deterministic rebuild."""
    for spec in PERSONAS:
        rebuilt = json.loads(json.dumps(build_persona(spec)))
        on_disk = json.loads((next(p for p in PERSONA_FILES if p.name == spec["file"])).read_text(encoding="utf-8"))
        assert rebuilt == on_disk, spec["file"]


def test_pii_free():
    """Fixtures must contain no emails / phone-like strings."""
    for f in PERSONA_FILES:
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
        assert not re.search(r"\b\d{10}\b", text)


def test_months_helpers():
    assert months_before(date(2026, 1, 15), 3) == ["2025-10", "2025-11", "2025-12"]
    assert months_between(date(2023, 8, 1), date(2026, 10, 1)) == 38

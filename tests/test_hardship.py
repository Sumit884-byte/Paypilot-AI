"""Hardship agent (Person A, Task 1): flags ~2 weeks of no income, drafts relief,
never applies it without approval."""

from datetime import datetime, timedelta, timezone

from payscore.copilot_agent import handle_chat
from payscore.hardship import get_hardship, propose_relief, record_income
from payscore.model import Scorer


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_no_income_for_two_weeks_flags_hardship_and_drafts_relief():
    applicant = "PSC-HARDSHIP-001"
    record_income(applicant, 10000.0, _days_ago(15), "evt-old")
    record_income(applicant, 10000.0, _days_ago(1), "evt-new")
    case = get_hardship(applicant)
    assert case["status"] == "flagged"
    assert case["reason"] == "no_income_for_14_days"
    assert case["gap_days"] == 14
    assert case["requires_approval"] is True
    assert case["applied"] is False
    assert case["offer"]["kind"] in {"payment_holiday", "reduce_revenue_share"}
    assert case["offer"]["llm_agent"] == "local_template"
    assert case["offer"]["verified"] is False


def test_short_gap_does_not_flag():
    applicant = "PSC-HARDSHIP-002"
    record_income(applicant, 10000.0, _days_ago(3), "evt-a")
    record_income(applicant, 10000.0, _days_ago(1), "evt-b")
    assert get_hardship(applicant)["status"] == "none"


def test_silence_without_new_payment_flags_hardship():
    """A 14-day silence is flagged even when no new payment arrives (backdated event)."""
    applicant = "PSC-HARDSHIP-003"
    record_income(applicant, 10000.0, _days_ago(15), "evt-silent")
    case = get_hardship(applicant)
    assert case["status"] == "flagged"
    assert case["reason"] == "no_income_for_15_days"
    assert case["gap_days"] >= 14
    assert case["requires_approval"] is True
    assert case["applied"] is False
    assert case["offer"]["kind"] in {"payment_holiday", "reduce_revenue_share"}


def test_propose_relief_is_approval_gated_no_op():
    applicant = "PSC-HARDSHIP-003"
    record_income(applicant, 10000.0, _days_ago(15), "evt-old")
    record_income(applicant, 10000.0, _days_ago(1), "evt-new")
    proposal = propose_relief(applicant, "payment_holiday")
    assert proposal["status"] == "proposed"
    assert proposal["requires_approval"] is True
    assert proposal["applies_to"] == "subscription"
    assert propose_relief(applicant, "nonsense")["status"] == "invalid_kind"


def test_copilot_flags_hardship_and_requires_approval(client):
    applicant = "PSC-HARDSHIP-004"
    record_income(applicant, 10000.0, _days_ago(15), "evt-old")
    record_income(applicant, 10000.0, _days_ago(1), "evt-new")
    result = handle_chat("I haven't been paid in two weeks", applicant, Scorer.from_dir("models"))
    assert result["tools"][0]["label"] == "hardship.review"
    assert result["approval"]["required"] is True
    assert result["analysis"]["result"]["status"] == "flagged"


def test_hardship_endpoint_returns_case(client):
    applicant = "PSC-HARDSHIP-005"
    record_income(applicant, 10000.0, _days_ago(15), "evt-old")
    record_income(applicant, 10000.0, _days_ago(1), "evt-new")
    got = client.get(f"/repayment/hardship/{applicant}").json()
    assert got["applicant_id"] == applicant
    assert got["status"] == "flagged"
    listed = client.get("/repayment/hardship").json()
    assert any(c["applicant_id"] == applicant for c in listed["cases"])


def test_duplicate_event_id_is_ignored():
    from payscore.hardship import INCOME_EVENTS

    applicant = "PSC-HARDSHIP-006"
    record_income(applicant, 10000.0, _days_ago(15), "evt-dup")
    record_income(applicant, 10000.0, _days_ago(1), "evt-new")
    record_income(applicant, 10000.0, _days_ago(15), "evt-dup")  # webhook retry
    assert len(INCOME_EVENTS[applicant]) == 2

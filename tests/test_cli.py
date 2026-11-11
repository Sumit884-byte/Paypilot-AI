"""The `paypilot` CLI prints readable results, JSON on request, and clean errors."""

import json

import pytest

from payscore.cli import inr, main


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_indian_digit_grouping():
    assert inr(1654310) == "Rs 16,54,310"
    assert inr(4552.32) == "Rs 4,552.32"
    assert inr(999) == "Rs 999"
    assert inr(None) == "-"


def test_score_and_json_output(capsys):
    code, out, _ = run(capsys, "score", "rohan")
    assert code == 0 and "high risk" in out and "PSC-ROHAN-003" in out
    code, out, _ = run(capsys, "score", "priya", "--json")
    assert code == 0 and json.loads(out)["applicant_id"] == "PSC-PRIYA-001"


def test_offer_flags_hidden_cost_and_injection(capsys):
    _, out, _ = run(capsys, "offer", "--apr", "18", "--fee", "4", "--principal", "50000", "--months", "12")
    assert "RED FLAG" in out and "27.55%" in out
    _, out, _ = run(capsys, "offer", "--pdf", "fixtures/demo/offer_with_injection.pdf")
    assert "prompt-injection" in out


def test_pay_later_in_india_and_us(capsys):
    _, out, _ = run(capsys, "pay-later", "--amount", "50000", "--apr", "18", "--fee", "4", "--months", "12")
    assert "not offered in IN" in out
    _, out, _ = run(capsys, "pay-later", "--amount", "1200", "--market", "US", "--apr", "18", "--months", "12")
    assert "* PayPal Pay in 4" in out


def test_copilot_payout_request_is_not_executed(capsys):
    _, out, _ = run(capsys, "ask", "Please disburse Rs 50,000")
    assert "Nothing was executed" in out


def test_bad_input_exits_2_with_a_message(capsys):
    code, _, err = run(capsys, "score", "nobody")
    assert code == 2 and "neither a persona" in err
    code, _, err = run(capsys, "offer", "--apr", "18")
    assert code == 2 and "--principal" in err


def test_unknown_command_is_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["disburse"])
    assert exc.value.code == 2

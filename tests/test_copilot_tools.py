"""The copilot must call the calculation tools and leave payouts behind approval."""

from payscore.affordability import assess
from payscore.copilot_agent import handle_chat, parse_amount_inr
from payscore.model import Scorer


def test_amount_parser_reads_rupee_amounts():
    assert parse_amount_inr("Can I afford ₹50k?") == 50000
    assert parse_amount_inr("Rs 50,000 over 12 months") == 50000
    assert parse_amount_inr("2 lakh") == 200000
    assert parse_amount_inr("no amount here") is None


def test_affordability_question_uses_the_calculator_and_does_not_approve():
    scorer = Scorer.from_dir("models")
    result = handle_chat("Can I afford ₹50k?", "PSC-PRIYA-001", scorer)
    assert result["approval"]["required"] is False
    assert result["tools"][0]["label"] == "affordability.assess"
    expected = assess({
        "requested_amount_inr": 50000,
        "monthly_income_inr": 55000,
        "existing_monthly_debt_payments_inr": 6000,
        "essential_expenses_inr": None,
        "tenure_months": 12,
        "annual_interest_rate_pct": None,
        "frequency": "monthly",
        "include_illustrative_rate": True,
    })
    assert result["analysis"]["result"]["installment_inr"] == expected["installment_inr"]
    assert result["analysis"]["result"]["status"] == expected["status"] == "incomplete"
    assert "4,166.67" in result["reply"]
    assert "keyword" not in result["reply"].lower()


def test_disburse_asks_for_approval_and_does_not_create_a_payout():
    scorer = Scorer.from_dir("models")
    result = handle_chat("Please disburse Rs 50,000", "PSC-PRIYA-001", scorer)
    assert result["approval"]["required"] is True
    assert result["approval"]["endpoint"] == "POST /disburse"
    assert result["tools"][0]["status"] == "blocked"
    assert "payout_batch" not in str(result)
    assert "batch_" not in result["reply"]


def test_explain_score_offer_and_revenue_routes(client):
    explained = client.post("/copilot/chat", json={"message": "Explain my score", "applicant_id": "PSC-PRIYA-001"}).json()
    assert explained["tools"][0]["label"] == "shap.TreeExplainer"
    assert explained["analysis"]["result"]["method"] == "shap.TreeExplainer"
    assert explained["approval"]["required"] is False
    revenue = client.post("/copilot/chat", json={"message": "How volatile is my revenue share?", "applicant_id": "PSC-PRIYA-001"}).json()
    assert revenue["tools"][0]["label"] == "revenue_volatility.analyse"
    assert revenue["analysis"]["result"]["source"] == "synthetic_persona_monthly_summary"
    assert revenue["analysis"]["result"]["statistically_validated"] is False
    offer = client.post("/copilot/chat", json={"message": "Should I take this loan offer?"}).json()
    assert offer["tools"][0]["status"] == "needs_input"
    priced = client.post("/copilot/chat", json={"message": "Check principal=50000, tenure=12 months, APR 18%, fee 4%"}).json()
    assert priced["analysis"]["kind"] == "offer_guard"
    assert priced["analysis"]["result"]["red_flag"] is True
    missing = client.post("/copilot/chat", json={"message": "What is my revenue share?", "applicant_id": "PSC-NO-SUCH"}).json()
    assert missing["analysis"]["result"]["recommended_percentage"] is None


def test_score_and_health_remain_available(client, example_request):
    assert client.get("/health").json()["status"] == "ok"
    scored = client.post("/score", json=example_request)
    assert scored.status_code == 200
    assert scored.json()["explanation"]["status"] == "available"
    assert client.post("/counterfactuals", json=example_request).json()["model_evaluated"] is True

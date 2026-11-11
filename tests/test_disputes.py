"""Dispute helper (Person A, Task 3): list open chargebacks via MCP (labeled local
fallback without a server) and draft borrower-protective responses. Never sends."""

from payscore.disputes import OPEN_DISPUTES, draft_response, list_open_chargebacks
from payscore.paypal import linked_accounts


def test_list_open_chargebacks_uses_local_fallback_without_mcp(monkeypatch):
    monkeypatch.delenv("DISPUTES_MCP_ENDPOINT", raising=False)
    payload = list_open_chargebacks("PSC-PRIYA-001")
    assert payload["source"] == "local_fallback"
    assert payload["mcp_error"] is None
    assert len(payload["disputes"]) == 1
    assert payload["disputes"][0]["dispute_id"] == "DP-1001"


def test_draft_response_is_borrower_protective_and_not_sent(monkeypatch):
    monkeypatch.delenv("DISPUTES_LLM", raising=False)
    monkeypatch.delenv("DISPUTES_LLM_ALLOW_EXTERNAL", raising=False)
    dispute = OPEN_DISPUTES["PSC-PRIYA-001"][0]
    drafted = draft_response(dispute, "PSC-PRIYA-001")
    assert drafted["draft_source"] == "local_template"
    assert drafted["verified"] is False
    assert "5050" in drafted["draft"]
    assert "revenue-share" in drafted["draft"]
    assert "has not been sent" in drafted["draft"]
    assert drafted["llm_status"] == "unavailable"


def test_dispute_endpoints(client, monkeypatch):
    monkeypatch.delenv("DISPUTES_MCP_ENDPOINT", raising=False)
    listed = client.get("/paypal/disputes/PSC-PRIYA-001").json()
    assert listed["source"] == "local_fallback"
    assert listed["disputes"][0]["dispute_id"] == "DP-1001"

    drafted = client.post("/paypal/disputes/draft", json={
        "applicant_id": "PSC-PRIYA-001", "dispute_id": "DP-1001",
    }).json()
    assert drafted["draft_source"] == "local_template"
    assert "DP-1001" in drafted["draft"]

    missing = client.post("/paypal/disputes/draft", json={
        "applicant_id": "PSC-PRIYA-001", "dispute_id": "DP-NOPE",
    })
    assert missing.status_code == 404

    invalid = client.post("/paypal/disputes/draft", json={
        "applicant_id": "bad id!", "dispute_id": "DP-1001",
    })
    assert invalid.status_code == 422


def test_disputes_list_and_draft_use_linked_account(client, monkeypatch):
    """List and draft must resolve the same PayPal account when this browser has one linked."""
    from payscore.paypal import routes

    monkeypatch.delenv("DISPUTES_MCP_ENDPOINT", raising=False)
    linked_accounts.LINKED_ACCOUNTS.clear()
    try:
        linked_accounts.store_account("linked-user", {"access_token": "tok"})
        linked_accounts.LINKED_ACCOUNTS["linked-user"]["paypal_account_id"] = "PSC-PRIYA-001"
        monkeypatch.setattr(routes, "linked_account_id", lambda request: "linked-user")

        listed = client.get("/paypal/disputes/PSC-OTHER-001").json()
        assert listed["source"] == "local_fallback"
        assert listed["disputes"][0]["dispute_id"] == "DP-1001"

        drafted = client.post("/paypal/disputes/draft", json={
            "applicant_id": "PSC-OTHER-001", "dispute_id": "DP-1001",
        }).json()
        assert drafted["draft_source"] == "local_template"
        assert "DP-1001" in drafted["draft"]
    finally:
        linked_accounts.LINKED_ACCOUNTS.clear()


def test_another_browsers_link_is_never_used(client, monkeypatch):
    """An account linked on the server must not answer for a browser that did not link it."""
    monkeypatch.delenv("DISPUTES_MCP_ENDPOINT", raising=False)
    linked_accounts.LINKED_ACCOUNTS.clear()
    try:
        linked_accounts.store_account("someone-else", {"access_token": "tok"})
        linked_accounts.LINKED_ACCOUNTS["someone-else"]["paypal_account_id"] = "PSC-PRIYA-001"
        assert client.get("/paypal/disputes/PSC-OTHER-001").json()["disputes"] == []
    finally:
        linked_accounts.LINKED_ACCOUNTS.clear()

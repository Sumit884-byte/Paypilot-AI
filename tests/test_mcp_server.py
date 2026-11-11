"""The MCP server works end to end over stdio, as Claude Desktop or Claude Code would run it."""

import asyncio
import json
import sys

from conftest import ROOT
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED_TOOLS = {
    "list_personas", "score_applicant", "what_if", "income_profile", "check_loan_offer", "check_loan_offer_pdf",
    "compare_pay_later", "check_affordability", "ask_copilot", "model_card",
}


def _payload(result):
    assert not result.is_error, result.content
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data) if set(data) == {"result"} else data
    return json.loads(result.content[0].text)


async def _session_checks():
    params = StdioServerParameters(command=sys.executable, args=["-m", "payscore.mcp_server"], cwd=str(ROOT))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        assert init.server_info.name == "paypilot"

        listed = (await session.list_tools()).tools
        assert {t.name for t in listed} == EXPECTED_TOOLS
        # nothing exposed over MCP may move money
        assert all(t.annotations and t.annotations.read_only_hint for t in listed)
        assert not {t.name for t in listed} & {"disburse", "create_payout", "repayment", "subscribe"}

        personas = _payload(await session.call_tool("list_personas", {}))
        assert [p["persona"] for p in personas] == ["priya", "arjun", "rohan"]

        rohan = _payload(await session.call_tool("score_applicant", {"applicant": "rohan"}))
        assert rohan["risk_band"] == "high" and 300 <= rohan["score"] <= 850

        offer = _payload(await session.call_tool("check_loan_offer", {
            "advertised_apr_pct": 18, "principal_inr": 50000, "term_months": 12, "processing_fee_pct": 4}))
        assert offer["red_flag"] is True

        pdf = _payload(await session.call_tool("check_loan_offer_pdf", {
            "path": str(ROOT / "fixtures" / "demo" / "offer_with_injection.pdf")}))
        assert pdf["injection_detected"] is True

        payout = _payload(await session.call_tool("ask_copilot", {"message": "Please disburse Rs 50,000"}))
        assert payout["approval"]["required"] is True and "payout_batch" not in json.dumps(payout)

        bad = await session.call_tool("score_applicant", {"applicant": "nobody"})
        assert bad.is_error and "neither a persona" in bad.content[0].text


def test_mcp_server_over_stdio():
    asyncio.run(_session_checks())

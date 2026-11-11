"""PayScore MCP server: the same analysis tools as the `paypilot` CLI, for Claude and other MCP clients.

    python -m payscore.mcp_server        (or: paypilot mcp)

Runs over stdio. Every tool is read-only analysis on synthetic or user-supplied data: none creates a payout,
subscription, order, or any other money movement, and a payout request to the copilot returns an approval
card only.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__, tools

Persona = Literal["priya", "arjun", "rohan"]
Applicant = Annotated[str, Field(description="Persona name (priya, arjun, rohan) or a path to a score-request JSON file")]

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

server = MCPServer(
    name="paypilot",
    title="Paypilot AI (PayScore)",
    version=__version__,
    instructions=(
        "Cash-flow credit analysis for India's online sellers and freelancers, on synthetic sandbox data. "
        "Start with list_personas. Scores are model estimates on synthetic data, not lending decisions. "
        "No tool moves money; payout requests only return an approval card."
    ),
)


def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except tools.ToolInputError as exc:
        raise ToolError(str(exc)) from None


@server.tool(annotations=READ_ONLY)
def list_personas() -> list[dict[str, Any]]:
    """List the synthetic demo personas with their business story and loan request."""
    return _call(tools.list_personas)


@server.tool(annotations=READ_ONLY)
def score_applicant(applicant: Applicant) -> dict[str, Any]:
    """PayScore (300-850), risk band, payout eligibility and limit, and TreeSHAP drivers."""
    return _call(tools.score, applicant)


@server.tool(annotations=READ_ONLY)
def what_if(applicant: Applicant) -> dict[str, Any]:
    """Changes to the loan request or finances that the model scores higher, re-scored on the trained model."""
    return _call(tools.what_if, applicant)


@server.tool(annotations=READ_ONLY)
def income_profile(persona: Persona) -> dict[str, Any]:
    """12-month income profile: total, monthly series, trend, clients, refund and dispute rates, longest gap."""
    return _call(tools.income_profile, persona)


@server.tool(annotations=READ_ONLY)
def check_loan_offer(
    advertised_apr_pct: Annotated[float, Field(ge=0, le=100, description="Advertised APR, percent")],
    principal_inr: Annotated[float, Field(gt=0, description="Loan amount in INR")],
    term_months: Annotated[int, Field(ge=1, le=360)],
    processing_fee_pct: Annotated[float, Field(ge=0, le=50, description="Upfront fee, percent")] = 0,
    lender_name: str = "Unknown lender",
) -> dict[str, Any]:
    """Advertised APR vs the effective annual cost of the cash flows (monthly IRR), plus an RBI KFS checklist."""
    return _call(tools.check_offer, advertised_apr_pct, principal_inr, term_months, processing_fee_pct, lender_name)


@server.tool(annotations=READ_ONLY)
def check_loan_offer_pdf(
    path: Annotated[str, Field(description="Path to a text-based loan-offer PDF on this machine")],
) -> dict[str, Any]:
    """Extract and price loan terms from a local PDF; flags hidden prompt-injection text and blocks extraction."""
    return _call(tools.check_offer_pdf, path)


@server.tool(annotations=READ_ONLY)
def compare_pay_later(
    purchase_amount: Annotated[float, Field(gt=0, description="Purchase amount in the market's currency")],
    advertised_apr_pct: Annotated[float, Field(ge=0, le=100, description="The loan offer's advertised APR")],
    term_months: Annotated[int, Field(ge=1, le=360, description="The loan offer's term")],
    processing_fee_pct: Annotated[float, Field(ge=0, le=50)] = 0,
    market: Annotated[str, Field(min_length=2, max_length=2, description="Buyer country code, e.g. IN or US")] = "IN",
    lender_name: str = "Unknown lender",
) -> dict[str, Any]:
    """Loan offer vs PayPal Pay in 4 / Pay Monthly (published US terms) for one purchase; not offered in India."""
    return _call(tools.compare_pay_later, purchase_amount, advertised_apr_pct, term_months, processing_fee_pct,
                 market, lender_name)


@server.tool(annotations=READ_ONLY)
def check_affordability(
    requested_amount_inr: Annotated[float, Field(gt=0)],
    monthly_income_inr: Annotated[float | None, Field(ge=0)] = None,
    essential_expenses_inr: Annotated[float | None, Field(ge=0)] = None,
    existing_monthly_debt_payments_inr: Annotated[float | None, Field(ge=0)] = None,
    tenure_months: Annotated[int | None, Field(ge=1, le=360)] = None,
    annual_interest_rate_pct: Annotated[float | None, Field(ge=0, le=500)] = None,
) -> dict[str, Any]:
    """Instalment burden and stressed cash flow for a loan amount. Missing inputs are reported, never guessed."""
    return _call(tools.affordability, requested_amount_inr, monthly_income_inr, essential_expenses_inr,
                 tenure_months, annual_interest_rate_pct, existing_monthly_debt_payments_inr)


@server.tool(annotations=READ_ONLY)
def ask_copilot(message: str, persona: Persona = "priya") -> dict[str, Any]:
    """Ask the copilot about income, affordability, score, offers, or disputes. Payout requests are not executed."""
    return _call(tools.ask_copilot, message, persona)


@server.tool(annotations=READ_ONLY)
def model_card() -> dict[str, Any]:
    """Model metadata, metrics on the synthetic test split, excluded sensitive attributes, and limitations."""
    return _call(tools.model_card)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()

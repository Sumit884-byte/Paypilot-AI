"""`paypilot` command line: PayScore analysis from a terminal, plus shortcuts to run the API and MCP server.

    paypilot personas
    paypilot score rohan
    paypilot offer --apr 18 --fee 4 --principal 50000 --months 12
    paypilot pay-later --amount 1200 --market US --apr 18 --fee 4 --months 12
    paypilot ask "Can I afford Rs 50k?" --persona priya

Add --json to any analysis command for machine-readable output. Nothing here moves money.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from . import __version__, tools

ROOT = Path(__file__).resolve().parent.parent


def inr(value: Any) -> str:
    """Indian digit grouping (12,34,567). Plain "Rs" so every Windows console can print it."""
    if value is None:
        return "-"
    whole, _, paise = f"{float(value):.2f}".partition(".")
    sign, digits = ("-", whole[1:]) if whole.startswith("-") else ("", whole)
    head, tail = digits[:-3], digits[-3:]
    while len(head) > 2:
        tail = f"{head[-2:]},{tail}"
        head = head[:-2]
    grouped = f"{head},{tail}" if head else tail
    return f"Rs {sign}{grouped}" + ("" if paise == "00" else f".{paise}")


def pct(value: Any) -> str:
    return "-" if value is None else f"{value}%"


def rows(pairs: list[tuple[str, Any]]) -> str:
    width = max(len(label) for label, _ in pairs)
    return "\n".join(f"  {label.ljust(width)}  {value}" for label, value in pairs)


# --- text output per command -------------------------------------------------------------------------

def show_personas(data: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"{p['persona']}  ({p['applicant_id']}, {p['name']})\n"
        f"  asks {inr(p['requested_amount_inr'])} over {p['requested_term_months']} months\n  {p['business']}"
        for p in data
    ) + "\n\nAll personas are synthetic."


def show_score(s: dict[str, Any]) -> str:
    drivers = s.get("drivers") or []
    lines = [
        f"PayScore {s['score']} ({s['risk_band']} risk), applicant {s['applicant_id']}",
        rows([
            ("Probability of default", f"{s['probability_of_default']:.2%}"),
            ("Eligible for payout", "yes" if s.get("disbursement_eligible") else "no"),
            ("Approved limit", inr(s.get("approved_amount_limit_inr"))),
        ]),
    ]
    if drivers:
        lines.append("Top drivers (TreeSHAP attributions, not causes):")
        for d in drivers[:5]:
            arrow = "lowers" if d.get("direction") == "lowers_risk" else "raises"
            lines.append(f"  - {d.get('label') or d.get('feature')}: {arrow} risk")
    if s.get("to_move_up"):
        lines.append(f"To move up: {s['to_move_up']}")
    lines.append(s.get("evaluation_caveat", ""))
    return "\n".join(line for line in lines if line)


def show_what_if(w: dict[str, Any]) -> str:
    if w.get("status") != "ok" or not w.get("suggestions"):
        return w.get("summary") or w.get("reason") or "No model-scored change raised the score."
    lines = [f"Current score {w.get('current_score')}. Changes the model scores higher:"]
    for s in w["suggestions"]:
        changes = "; ".join(c["description"] for c in s["changes"])
        lines.append(f"  - {s['estimated_score']} ({s['estimated_score_difference']:+}): {changes}")
    return "\n".join(lines)


def show_income(p: dict[str, Any]) -> str:
    months = "  ".join(f"{m['month']} {inr(m['income_inr'])}" for m in p["monthly_income_12m"][-3:])
    return "\n".join([
        f"Income profile, {p['window_start']} to {p['window_end']} ({p['source']} data)",
        rows([
            ("Income, 12 months", inr(p["total_income_12m_inr"])),
            ("Trend", p["income_trend_12m"]),
            ("Distinct clients", p["distinct_client_count_12m"]),
            ("Refund rate", f"{p['refund_rate_12m']:.1%}"),
            ("Dispute rate", f"{p['dispute_rate_12m']:.1%}"),
            ("Longest income gap", f"{p['longest_income_gap_days_12m']} days"),
        ]),
        f"Last 3 months: {months}",
    ])


def show_offer(o: dict[str, Any]) -> str:
    lines = []
    if o.get("injection_detected"):
        lines.append("WARNING: hidden prompt-injection text found in this PDF. Extraction was blocked.")
        lines += [f"  - {reason}" for reason in o.get("injection_reasons") or []]
    verdict = {
        "advertised_below_calculated": "RED FLAG: the advertised APR is below the real cost.",
        "advertised_above_calculated": "The advertised APR is above the calculated cost.",
        "within_tolerance": "The advertised APR matches the calculated cost (within 1 point).",
        "not_compared": "Not enough terms to compare.",
    }.get(o.get("comparison_status"), o.get("comparison_status") or "")
    lines += [verdict, rows([
        ("Advertised APR", pct(o.get("advertised_apr_pct"))),
        ("Effective annual cost", pct(o.get("estimated_real_apr_pct"))),
        ("Processing fee", pct(o.get("processing_fee_pct"))),
        ("Instalment", inr((o.get("calculation") or {}).get("installment_inr"))),
    ])]
    missing = [item["item"] for item in o.get("kfs_checklist") or [] if not item.get("ok")]
    if missing:
        lines.append("Key Fact Statement items missing: " + ", ".join(missing))
    lines.append("Estimate only, not a legal finding.")
    return "\n".join(lines)


def show_pay_later(r: dict[str, Any]) -> str:
    money = inr if r.get("currency") == "INR" else (lambda v: "-" if v is None else f"{r.get('currency') or ''} {v:,.2f}")
    lines = [f"Purchase {money(r['purchase_amount'])} in {r['market']}"]
    if r["pay_later_availability"] != "modelled":
        lines.append(r["availability_note"])
    for o in r["options"]:
        mark = "*" if (r.get("cheapest") or {}).get("id") == o["id"] else " "
        if o["eligible"]:
            lines.append(f" {mark} {o['name']}: {o['payments']} x {money(o['instalment'])} ({o['interval']}), "
                         f"cost of credit {money(o.get('cost_of_credit'))}, {o['effective_annual_pct']}% effective")
        else:
            lines.append(f"   {o['name']}: not eligible. {o['ineligible_reason']}")
    if r.get("summary"):
        lines.append(r["summary"])
    lines.append(f"* cheapest. Terms: {r['terms_source']['url']} (checked {r['terms_source']['retrieved']}).")
    return "\n".join(lines)


def show_affordability(a: dict[str, Any]) -> str:
    lines = [f"Status: {a.get('status')}"]
    lines += [f"  - {reason}" for reason in a.get("reasons") or []]
    if a.get("missing_inputs"):
        lines.append("Missing inputs: " + ", ".join(a["missing_inputs"]))
    return "\n".join(lines)


def show_copilot(c: dict[str, Any]) -> str:
    lines = [c["reply"]]
    tools_used = ", ".join(f"{t['label']} ({t.get('status')})" for t in c.get("tools") or [])
    if tools_used:
        lines.append(f"[tools: {tools_used}]")
    if (c.get("approval") or {}).get("required"):
        lines.append("Approval required. Nothing was executed; approve payouts in the web app.")
    return "\n".join(lines)


def show_model_card(m: dict[str, Any]) -> str:
    test = (m.get("metrics_by_split") or {}).get("test") or {}
    baseline = m.get("baseline_logistic_regression_test") or {}
    pairs = [("Model", f"{m.get('model_name')} {m.get('model_version')}"), ("Type", m.get("model_type"))]
    for key, label in (("roc_auc", "Test ROC-AUC"), ("pr_auc", "Test PR-AUC"), ("brier", "Test Brier"), ("ks", "Test KS")):
        if test.get(key) is not None:
            pairs.append((label, f"{test[key]:.3f}"))
    if baseline.get("roc_auc") is not None:
        pairs.append(("Logistic baseline ROC-AUC", f"{baseline['roc_auc']:.3f}"))
    excluded = (m.get("fairness") or {}).get("sensitive_attributes_excluded") or []
    if excluded:
        pairs.append(("Sensitive attributes excluded", ", ".join(excluded)))
    return "Model card\n" + rows(pairs) + f"\n{m.get('caveat') or ''}"


# --- argument parsing --------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paypilot", description="PayScore analysis from the terminal. Sandbox only.")
    parser.add_argument("--version", action="version", version=f"paypilot {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    as_json = argparse.ArgumentParser(add_help=False)
    as_json.add_argument("--json", action="store_true", help="print the raw JSON result")

    sub.add_parser("personas", parents=[as_json], help="list the synthetic demo personas")
    for name, helptext in (("score", "PayScore with TreeSHAP drivers"), ("what-if", "changes that would raise the score")):
        p = sub.add_parser(name, parents=[as_json], help=helptext)
        p.add_argument("applicant", help="persona name (priya, arjun, rohan) or a score-request JSON file")
    p = sub.add_parser("income", parents=[as_json], help="12-month income profile")
    p.add_argument("persona", choices=tools.PERSONAS)

    p = sub.add_parser("offer", parents=[as_json], help="real cost of a loan offer, from terms or a PDF")
    p.add_argument("--pdf", help="loan-offer PDF to extract terms from (also checks for prompt injection)")
    p.add_argument("--apr", type=float, help="advertised APR in percent")
    p.add_argument("--principal", type=float, help="loan amount in INR")
    p.add_argument("--months", type=int, help="term in months")
    p.add_argument("--fee", type=float, default=0, help="processing fee in percent (default 0)")
    p.add_argument("--lender", default="Unknown lender")

    p = sub.add_parser("pay-later", parents=[as_json], help="loan offer vs PayPal Pay Later for one purchase")
    p.add_argument("--amount", type=float, required=True, help="purchase amount in the market's currency")
    p.add_argument("--apr", type=float, required=True, help="the loan offer's advertised APR in percent")
    p.add_argument("--months", type=int, required=True, help="the loan offer's term in months")
    p.add_argument("--fee", type=float, default=0, help="the loan offer's processing fee in percent")
    p.add_argument("--market", default="IN", help="buyer country code; US terms are modelled (default IN)")
    p.add_argument("--lender", default="Unknown lender")

    p = sub.add_parser("afford", parents=[as_json], help="instalment burden for a loan amount")
    p.add_argument("--amount", type=float, required=True, help="loan amount in INR")
    p.add_argument("--income", type=float, help="monthly income in INR")
    p.add_argument("--expenses", type=float, help="monthly essential expenses in INR")
    p.add_argument("--debt", type=float, help="existing monthly debt payments in INR")
    p.add_argument("--months", type=int, help="tenure in months")
    p.add_argument("--rate", type=float, help="annual interest rate in percent")

    p = sub.add_parser("ask", parents=[as_json], help="ask the copilot a question")
    p.add_argument("message")
    p.add_argument("--persona", default="priya", choices=tools.PERSONAS)

    sub.add_parser("model-card", parents=[as_json], help="model metrics and responsible-AI notes")

    p = sub.add_parser("serve", help="run the HTTP API")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    sub.add_parser("dev", help="set up and run the API and the frontend (same as scripts/dev.py)")
    sub.add_parser("mcp", help="run the MCP server over stdio, for Claude and other MCP clients")
    return parser


def run_analysis(args: argparse.Namespace) -> tuple[Any, Callable[[Any], str]]:
    c = args.command
    if c == "personas":
        return tools.list_personas(), show_personas
    if c == "score":
        return tools.score(args.applicant), show_score
    if c == "what-if":
        return tools.what_if(args.applicant), show_what_if
    if c == "income":
        return tools.income_profile(args.persona), show_income
    if c == "offer":
        if args.pdf:
            return tools.check_offer_pdf(args.pdf), show_offer
        if None in (args.apr, args.principal, args.months):
            raise tools.ToolInputError("Give --pdf, or all of --apr, --principal and --months.")
        return tools.check_offer(args.apr, args.principal, args.months, args.fee, args.lender), show_offer
    if c == "pay-later":
        return tools.compare_pay_later(args.amount, args.apr, args.months, args.fee, args.market,
                                       args.lender), show_pay_later
    if c == "afford":
        return tools.affordability(args.amount, args.income, args.expenses, args.months, args.rate,
                                   args.debt), show_affordability
    if c == "ask":
        return tools.ask_copilot(args.message, args.persona), show_copilot
    return tools.model_card(), show_model_card


def main(argv: list[str] | None = None) -> int:
    # Unprintable characters must never crash the CLI on a narrow Windows console code page
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        import uvicorn
        uvicorn.run("payscore.api:app", host=args.host, port=args.port)
        return 0
    if args.command == "dev":
        return subprocess.call([sys.executable, str(ROOT / "scripts" / "dev.py")])
    if args.command == "mcp":
        from .mcp_server import main as serve_mcp
        serve_mcp()
        return 0

    try:
        result, show = run_analysis(args)
    except tools.ToolInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str) if args.json else show(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

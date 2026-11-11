# CLI and MCP server

PayScore's analysis is available without the web app: from a terminal with the `paypilot` command, and to Claude,
Cursor, Arka, or any MCP client through the `paypilot-mcp` server. Both call the same code as the HTTP API, in-process,
so the API does not need to be running.

**Analysis only.** No CLI command or MCP tool creates a payout, subscription, order, or any other money movement. A
payout request to the copilot returns an approval card and nothing is executed. Payouts stay in the web app, behind
explicit approval.

## Install

`python scripts/dev.py` (see the README) installs both commands into `.venv`. To install them on their own:

```bash
python -m venv .venv            # activate it for your shell (see the README)
pip install -r requirements.txt
pip install -e .
```

## CLI

```text
paypilot personas                                    list the synthetic demo personas
paypilot score rohan                                 PayScore, risk band, TreeSHAP drivers
paypilot what-if priya                               changes the model scores higher
paypilot income priya                                12-month income profile
paypilot offer --apr 18 --fee 4 --principal 50000 --months 12
paypilot offer --pdf fixtures/demo/offer_with_injection.pdf
paypilot pay-later --amount 1200 --market US --apr 18 --fee 4 --months 12
paypilot afford --amount 50000 --income 120000 --expenses 60000 --debt 0 --months 12 --rate 18
paypilot ask "Can I afford Rs 50k?" --persona rohan
paypilot model-card
paypilot serve | dev | mcp                           run the API, the full app, or the MCP server
```

- `score` and `what-if` take a persona (`priya`, `arjun`, `rohan`) or a path to a score-request JSON file.
- Add `--json` to any analysis command for machine-readable output.
- Bad input exits with code 2 and a message on stderr.
- Without activating `.venv`, run `.venv/bin/paypilot` (macOS, Linux) or `.venv\Scripts\paypilot` (Windows), or
  `python -m payscore.cli`.

## MCP server

Runs over stdio. Tools (all read-only):

| Tool | What it does |
|---|---|
| `list_personas` | The synthetic demo personas and their loan requests |
| `score_applicant` | PayScore, risk band, payout eligibility and limit, TreeSHAP drivers |
| `what_if` | Changes the model scores higher, re-scored on the trained model |
| `income_profile` | 12-month income, trend, clients, refund and dispute rates |
| `check_loan_offer` | Advertised APR vs effective annual cost, with an RBI Key Fact Statement checklist |
| `check_loan_offer_pdf` | The same from a local PDF, with prompt-injection detection |
| `compare_pay_later` | Loan offer vs PayPal Pay in 4 and Pay Monthly for one purchase |
| `check_affordability` | Instalment burden and stressed cash flow |
| `ask_copilot` | The copilot; payout requests return an approval card only |
| `model_card` | Metrics on the synthetic test split, excluded attributes, limitations |

### Connect a client

Use the **absolute path** to the server in `.venv`:

| OS | Command path |
|---|---|
| macOS / Linux | `/path/to/Paypilot-AI/.venv/bin/paypilot-mcp` |
| Windows | `C:\path\to\Paypilot-AI\.venv\Scripts\paypilot-mcp.exe` |

**Claude Code**

```bash
claude mcp add paypilot -- /path/to/Paypilot-AI/.venv/bin/paypilot-mcp
```

**Claude Desktop, Cursor, and Arka** all use the same `mcpServers` entry. Add it to the client's config file, then
restart the client:

```json
{
  "mcpServers": {
    "paypilot": {
      "command": "/path/to/Paypilot-AI/.venv/bin/paypilot-mcp",
      "args": []
    }
  }
}
```

On Windows, write the path with doubled backslashes in JSON:
`"C:\\path\\to\\Paypilot-AI\\.venv\\Scripts\\paypilot-mcp.exe"`.

| Client | Config file |
|---|---|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Cursor | `~/.cursor/mcp.json`, or `.cursor/mcp.json` in a project |
| Arka | `~/.config/arka/mcp.json`, then `arka mcp tools paypilot` |

The server reads the same environment variables as the API (`PAYSCORE_MODEL_DIR`, `PAYSCORE_ALLOW_FALLBACK`, and the
optional LLM flags in `.env.example`). Add them under `"env"` in the entry if you need non-default values.

## Tests

`tests/test_cli.py` covers the commands. `tests/test_mcp_server.py` starts the server as a subprocess, performs the
MCP handshake, checks that every tool is read-only, and calls the tools, as a real client would. Both run in CI on
Windows, macOS, and Linux.

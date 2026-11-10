# Remaining work: Person A and Person C

Re-checked against `main` at `c1d2c6c` on 10 Nov. Target submission is **11 Nov**.

**Every blocking item from the 9 Nov audit is fixed.** What's left is optional. Where a feature stays short of the
roadmap, the code and README already describe it accurately, so the video narration should match those descriptions.

## Fixed since the 9 Nov audit

| Owner | Item | How it was fixed |
|---|---|---|
| A | Injection result not shown on Offer Guard | Banner on `OfferGuard.tsx`, plus `fixtures/demo/offer_with_injection.pdf` for the video |
| A | Hardship flagged only after income resumed | `_flag_from_silence` in `payscore/hardship.py` checks against the current time |
| A | Rejected webhooks counted as income | `record_income` now runs after the missing-`event_id` check |
| A | List and draft used different dispute lookups | Both use `_disputes_account_id` in `payscore/paypal/routes.py` |
| A | Hardship offer was template-only | Optional LLM behind `HARDSHIP_LLM` and `HARDSHIP_LLM_ALLOW_EXTERNAL`; the template is the fallback |
| A | Disputes had no UI | Copilot intent: ask about a chargeback or dispute |
| C | Income Passport PDF had a placeholder link | Footer uses `PAYSCORE_FRONTEND_URL` and the real token |
| C | `/verify` proxy showed JSON in dev | API moved to `/api/verify/...`; the React page stays at `/verify/...` |
| C | Wrong Arjun/Rohan applicant IDs | Hard-coded maps replaced; `tests/test_persona_resolution.py` covers it |
| C | Model card not in AG Studio | `ModelCardWidget` added to `Cockpit.tsx` |
| C | No tamper detection on passports | HMAC-SHA256 over the snapshot when `PAYSCORE_PASSPORT_SIGNING_KEY` is set |

## Still short of the roadmap

These features are already described accurately in code and docs. Keep the video and submission text consistent with
those descriptions.

| Owner | Roadmap wording | What exists | Say |
|---|---|---|---|
| A | Dispute Helper "via MCP server" | JSON-RPC client to `DISPUTES_MCP_ENDPOINT` with a local fallback; `payscore/disputes.py` says it is not a full MCP server | "Pluggable dispute source", not "MCP server" |
| C | Negotiation "dual LLM agents, settling via Payouts" | Two rule-based agents; settlement is simulated (`paypal_payout: false`) | "Rule-based agents, simulated settlement" |

## Optional, if time allows

- **A:** a small Hardship page, or a card on Overview, that shows an open case and its relief offer. Today it appears
  only in Copilot.
- **A:** a real MCP server for disputes, using the `mcp` Python SDK with a `list_open_disputes` tool. Skip this unless
  everything else is done.
- **Deploy:** in Render, set `PAYSCORE_PASSPORT_SIGNING_KEY` if the video shows tamper detection. Without it, the
  passport has no content signature.

## Checks before merging

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run build && npm run lint
```

On 10 Nov: 256 tests passed, the build was clean, and lint showed 0 errors. Two known failures are not regressions:

- **`tests/test_no_secrets.py`:** a false positive from the untracked `NVIDIA-Nemotron-3.5-Transcribe-30B-A4B/` folder.
  Never commit that folder.
- **`ruff check payscore tests`:** 21 errors, all in the older `payscore/paypal/*` modules and their tests.

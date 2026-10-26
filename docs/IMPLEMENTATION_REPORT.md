# Week 2 and Week 3 implementation report

Source of truth is this project folder. The original upload `C:\Users\DELL\Desktop\Paypilot-AI-main.zip` was not modified. The packaged result is `C:\Users\DELL\Desktop\PayScore_Week2_Week3_Complete.zip`.

## Task 1 — SHAP explanations

| Requirement | Where |
| --- | --- |
| TreeSHAP on the trained LightGBM booster | `payscore/explain.py` (`shap.TreeExplainer`) |
| Same prediction as `/score` | `payscore/model.py` calls `explain_request` after `predict_pd` |
| Feature order matches training | `build_features` / `FEATURE_NAMES` |
| Top three raising and lowering factors, with label, contribution, direction, and description | `explain.py` |
| Contributions are log-odds, not causes | `causal_claim: false` and the description text |
| No silent heuristic if SHAP cannot be checked | reconstruction against raw score and `pred_contrib`; otherwise `status: unavailable` and empty drivers |
| API compatibility | `payscore/schema.py` keeps `drivers` and `to_move_up`; adds `explanation` and `counterfactual_preview` |
| `/explain` does not record a disbursement approval | `payscore/explain.py` router |
| Tests | `tests/test_explain_shap.py` |

## Task 2 — Counterfactuals

| Requirement | Where |
| --- | --- |
| Eligible changes only, re-scored on the trained model | `payscore/counterfactual.py` |
| Immutable identity and history rejected | same module; tests reject age, defaults, transaction count, and income edits |
| Unchanged proposal | score difference 0 |
| No remaining eligible move | `no_feasible_improvement` |
| Fallback model | `unavailable`; the search is not used |
| Endpoint | `POST /counterfactuals` |
| Score preview | `counterfactual_preview` on `POST /score` |
| UI | `frontend/src/pages/Score.tsx` |
| Tests | `tests/test_counterfactual.py` |

## Task 3 — Offer guard and PDF upload

| Requirement | Where |
| --- | --- |
| Manual entry preserved | `POST /offer-guard` in `payscore/offer_guard.py` |
| PDF upload, size, type, page count, path-safe temp file | `payscore/offer_pdf.py`, `POST /offer-guard/upload` |
| Label extraction | `extract_labeled_fields` |
| Optional LLM, off unless both flags and `OPENAI_API_KEY` are set | `llm_extract` |
| LLM values are not verified facts | `payscore/offer_analysis.py` (`unverified_llm`, disagreement becomes `ambiguous`) |
| OCR hook when text is too short | `try_ocr`; libraries are not installed, so status is `unavailable` |
| Effective annualised cost from cash-flow IRR | `payscore/finance.py` |
| Advertised APR compared with that cost | 1 percentage-point tolerance in `offer_analysis.py` |
| KFS checklist | RBI circular RBI/2024-25/18 cited in the checklist; a missing item is “not seen”, not a confirmed violation |
| RBI app list | `payscore/rbi_directory.py`, `reference/rbi_dla_snapshot.json` (empty, `retrieved_at` null) |
| UI | `frontend/src/pages/OfferGuard.tsx`, `frontend/src/lib/api.ts` `postForm` |
| Tests | `tests/test_offer_guard.py`, `tests/pdf_factory.py` |

## Task 4 — Affordability

| Requirement | Where |
| --- | --- |
| Level-payment instalment and IRR helpers | `payscore/finance.py` |
| Disposable cash, stress scenarios, pass / warn / fail / incomplete | `payscore/affordability.py` |
| No universal debt-service cutoff | fail only when post-payment cash is below the configured buffer (default 0) |
| Endpoint | `POST /affordability` |
| Copilot calls the function | `payscore/copilot_agent.py` |
| Tests | `tests/test_affordability.py`, `tests/test_copilot_tools.py` |

## Task 5 — Revenue-share volatility

| Requirement | Where |
| --- | --- |
| Mean, sample standard deviation, coefficient of variation, downside revenue | `payscore/revenue_volatility.py` |
| History from the request or persona `monthly_summary.net_revenue_inr` | `payscore/applicant_context.py` |
| Fewer than 3 observations | `insufficient_data`, no percentage |
| `statistically_validated` is always false | same module |
| Endpoint | `POST /revenue-volatility` |
| Tests | `tests/test_revenue_volatility.py` |

## Task 6 — Copilot tools

| Requirement | Where |
| --- | --- |
| One real function per question | `payscore/copilot_agent.py`, called from `payscore/copilot.py` |
| Disburse wording returns an approval card and does not create a payout | `test_disburse_asks_for_approval_and_does_not_create_a_payout` |
| Routers registered | `payscore/api.py` |
| Frontend tool line | `frontend/src/pages/Copilot.tsx` |
| Vite proxies | `frontend/vite.config.ts` |
| Tests | `tests/test_copilot_tools.py` |

Existing PayPal sandbox routes, auth, and money endpoints were left in place. The full suite, including those tests, passed after the changes.

## Task 7 and Task 8

Test commands and counts are in `docs/TEST_REPORT.md`. Setup, formulas, API examples, and limits are in `README.md`, `docs/API.md`, `docs/INTEGRATION.md`, and `.env.example`.

## Status

**Implemented and tested locally**

- TreeSHAP tied to the scored LightGBM prediction
- Model-rescored counterfactuals
- Manual and PDF offer analysis, IRR cost, KFS checklist
- Affordability stress test
- Revenue-share volatility from supplied observations
- Copilot routing into those functions
- Existing `/score`, health, and PayPal sandbox tests

**Partial**

- RBI directory: parser and fuzzy matcher are tested. The shipped snapshot has no lender names and no retrieval date, so the check returns `unverified`. `confirmed_violation` is always false. A live fetch runs only when `PAYSCORE_RBI_FETCH=true`, and only a page that contains a digital-lending table with NBFC and app columns is stored.
- OCR: the code path exists. `pytesseract` and `pdf2image` are not installed, so a scanned PDF is reported as OCR unavailable.
- LLM extraction: implemented and default-off. Tests prove it does not call the provider unless both `PAYSCORE_OFFER_LLM` and `PAYSCORE_OFFER_LLM_ALLOW_EXTERNAL` are true and a key is set. No live provider was called.

**Blocked**

- A current official RBI digital-lending-app list was not retrieved, so no names were added by hand.
- Scanned-PDF OCR needs Tesseract and Poppler on the machine.
- The revenue-share bands are a documented product rule, not a statistically validated model.
- The KFS checklist is a disclosure check against the cited circular, not a regulatory certification.

## Browser check

With the API on port 8000 and Vite on port 5173:

- PayScore for the Priya demo showed TreeSHAP factors and score 771, then eligible changes at estimated scores 801, 793, and 792.
- Offer guard on the default form (18% advertised, 4% fee, Rs 50,000, 12 months) showed effective annualised cost 27.55% and an unverified RBI source.
- Copilot “Can I afford ₹50k?” returned instalment Rs 4,166.67, status incomplete, tool `affordability`.
- “Explain my score” returned PayScore 771 and tool `explanation · available`.

The PDF file picker was not used in the browser. Upload behaviour is covered by `tests/test_offer_guard.py`. A disbursement sentence was not typed into the copilot in the browser; `test_disburse_asks_for_approval_and_does_not_create_a_payout` covers that path.

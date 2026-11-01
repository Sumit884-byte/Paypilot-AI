# Test report

Python: 3.12.10 in `.venv`. LightGBM 4.7.0, shap 0.54.1, pypdf 6.21.2, pytest 9.1.1, ruff 0.17.2.

On this Windows machine LightGBM could not load `lib_lightgbm.dll` until `vcomp140.dll` from the venv’s scikit-learn libs was copied next to that DLL inside `.venv` only. That file is not part of the project. A clean machine needs the Microsoft Visual C++ redistributable.

## Before the Week 2 and Week 3 source edits

Command, after the DLL copy and before feature code changes:

```text
.venv\Scripts\python.exe -m pytest -q --tb=line
```

Result: **157 passed, 1 warning in 33.62s**.

The warning is Starlette’s deprecation notice that `httpx` TestClient should move to `httpx2`.

## After the feature work

Same command, 26 October 2026:

```text
.venv\Scripts\python.exe -m pytest -q --tb=line
```

Result: **194 passed, 2 warnings in 51.10s**.

The second warning is SHAP noting that LightGBM binary TreeExplainer output has changed to a list of ndarray. This build still returns an array of shape `(1, 21)`, and `tests/test_explain_shap.py` checks it against `pred_contrib`.

New tests collected:

```text
.venv\Scripts\python.exe -m pytest -q --collect-only tests/test_explain_shap.py tests/test_counterfactual.py tests/test_offer_guard.py tests/test_affordability.py tests/test_revenue_volatility.py tests/test_copilot_tools.py
```

Result: **37 tests collected**. 157 existing + 37 new = 194. No existing test was deleted, skipped, or weakened.

| File | Tests |
| --- | --- |
| `tests/test_explain_shap.py` | 3 |
| `tests/test_counterfactual.py` | 6 |
| `tests/test_offer_guard.py` | 8 |
| `tests/test_affordability.py` | 9 |
| `tests/test_revenue_volatility.py` | 6 |
| `tests/test_copilot_tools.py` | 5 |

`npx tsc -b --pretty false` in `frontend` completed with exit code 0.

## Lint

`ruff check` on the new modules, `payscore/api.py`, `payscore/model.py`, `payscore/schema.py`, and the new tests: **all checks passed**.

`ruff check payscore tests` on the whole tree: **22 errors**, all in pre-existing PayPal modules and their tests (`payscore/paypal/*`, `tests/test_advance.py`, `tests/test_disbursements.py`, `tests/test_income_profile.py`, `tests/test_repayment.py`). They are import order, unused imports, one unused `prompt`, one long line, and one `zip` without `strict`. Those files were not restyled, so the sandbox integration stayed as it was. Ruff 0.17.2 is newer than the `ruff>=0.5` pin.

## What was not run

- No live PayPal payment, payout, or subscription. Existing PayPal tests use the sandbox client and fixtures and do not need credentials.
- No live OpenAI call. The offer LLM stays off unless `PAYSCORE_OFFER_LLM` and `PAYSCORE_OFFER_LLM_ALLOW_EXTERNAL` are both true.
- No live download of the RBI page. `PAYSCORE_RBI_FETCH` defaults to false, and the snapshot has no entries.
- OCR libraries are not installed, so a blank PDF is asserted as `ocr_status` unavailable or not needed, not as recognised text.
- No successful payout from the copilot UI against PayPal. Without credentials the real `POST /disburse` returned 503 `paypal_not_configured`. The success path was checked with that response mocked in the browser.

## Browser

API: `http://127.0.0.1:8000`. UI: `http://localhost:5173`.

Checked in the browser: demo login via “Tour the cockpit”, PayScore TreeSHAP for Priya (score 771) and the eligible-change list, manual offer analysis (advertised 18% versus effective 27.55%, RBI unverified), and copilot affordability plus “Explain my score” (`explanation · available`).

Follow-up pass, 1 November 2026, scripted in headless Chromium against the local API and UI:

- Income: the AG Grid transaction feed renders with no console errors and sorts by date. Before this pass it failed to create because no row model was registered.
- Offer guard: a labelled PDF selected through the file input posts to `/offer-guard/upload` and returned advertised 10% versus effective 55.7%. The new remove control returns the form to manual analysis, and a non-PDF is refused.
- Copilot: “Please disburse Rs 50,000” shows the approval card. Approve is refused until PayScore has run, Decline records the refusal, and a server failure leaves the card available to retry. A request with no amount shows the ₹50,000 default on the card. A double click on Approve sent one request.
- Copilot auto-send fires once per visit, and is cancelled if the input is edited first.

`npm run build` completes with no chunk warning. The 852 kB lazy-loaded AG Grid chunk sits under the 900 kB `chunkSizeWarningLimit`. `npm run lint` reports 0 errors and 7 warnings, none in the copilot page.

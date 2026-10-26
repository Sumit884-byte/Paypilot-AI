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
- The browser PDF file picker and a copilot disbursement sentence were not exercised in the UI. The API tests cover both.

## Browser

API: `http://127.0.0.1:8000`. UI: `http://localhost:5173`.

Checked in the browser: demo login via “Tour the cockpit”, PayScore TreeSHAP for Priya (score 771) and the eligible-change list, manual offer analysis (advertised 18% versus effective 27.55%, RBI unverified), and copilot affordability plus “Explain my score” (`explanation · available`).

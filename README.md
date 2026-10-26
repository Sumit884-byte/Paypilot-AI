# PayScore AI — Week 1 deliverables (AI component)

Early, **development-only** credit-scoring baseline for small online sellers/freelancers.
Everything runs on **synthetic / normalised data**. No PayPal API is called, no money moves, and the
score must not be used for real lending decisions.

## What is here

| Path | Purpose |
|---|---|
| `payscore/schema.py` | Pydantic input/output contract (`ScoreRequest`, `ScoreResponse`), all amounts in INR |
| `payscore/features.py` | Feature engineering shared by training and inference (single code path) |
| `payscore/synthetic.py` | **Synthetic** development dataset generator (seeded) |
| `payscore/homecredit.py` | Optional loader for Kaggle *Home Credit Default Risk* `application_train.csv` (data not included) |
| `payscore/train.py` | LightGBM training + metadata, plus a logistic-regression context baseline |
| `payscore/model.py` | Model loading, PD -> 300-850 score mapping, risk bands, labelled dev fallback |
| `payscore/predict.py` | CLI scoring of a JSON file |
| `payscore/api.py` | FastAPI app: `GET /health`, `POST /score` |
| `payscore/paypal/seed.py` | Dry-run-by-default CLI to seed PayPal sandbox from persona fixtures |
| `payscore/derive.py` | Reference derivation: transaction history -> model-input metrics |
| `payscore/build_fixtures.py`, `export_schema.py` | Regenerate persona fixtures / JSON Schemas |
| `models/` | Trained artifact (`payscore_lgbm.txt`) + `model_metadata.json` |
| `schema/` | `score_request.schema.json`, `persona.schema.json` |
| `fixtures/personas/` | 3 fictional personas (Priya, Arjun, Rohan) with transactions + `model_input` |
| `docs/` | `INTEGRATION.md`, `FEATURE_MAPPING.md`, `MODEL_CARD.md`, `PERSONAS.md`, `SEEDING.md` |
| `tests/` | pytest suite |

## Quick start (Python 3.10+; developed on 3.12)

```bash
pip install -r requirements.txt
python -m pytest -q                                   # run tests
python -m payscore.predict --input fixtures/personas/priya.json
uvicorn payscore.api:app --port 8000                  # then open http://localhost:8000/docs
python -m payscore.train                              # retrain on synthetic data (seed 42)
python -m payscore.build_fixtures && python -m payscore.export_schema   # regenerate fixtures/schemas
```

```bash
curl -s localhost:8000/score -H 'Content-Type: application/json' \
  -d @<(python -c "import json;print(json.dumps(json.load(open('fixtures/personas/priya.json'))['model_input']))")
```

## Score and risk bands

`probability_of_default` -> score = 600 + (50/ln 2)·ln(odds/12), clipped to **300-850** (600 pts = 12:1 good:bad odds, +50 pts doubles the odds).

| Score | Band |
|---|---|
| >= 720 | low |
| 650-719 | moderate |
| 560-649 | elevated |
| < 560 | high |

## API behaviour

* `422` `{"error":"validation_error","detail":[{field,message,type}]}` — invalid input; submitted values are **not** echoed back.
* `503` — no trained model and `PAYSCORE_ALLOW_FALLBACK=false`.
* If the model artifact is missing and fallback is allowed, a deterministic rule-of-thumb formula is used and is
  labelled `development_fallback` / `is_trained_model: false` in every response.
* Corrupt/incompatible artifacts fail loudly at start-up (never silently replaced by the fallback).
* CORS: local dev origins only by default (`PAYSCORE_CORS_ORIGINS`). See `.env.example`.

## Honest limitations (read before demoing)

1. The shipped model is trained on **synthetic data** whose labels come from a hand-written risk rule + noise.
   The reported test ROC-AUC of **0.855** comes from a split of that synthetic data. It only shows the pipeline works;
   it is **not** evidence of real-world credit-risk accuracy and is **not** a Home Credit or PayPal benchmark.
2. The Home Credit loader maps **6 of the model's 16 input columns, plus the ID**: `age_years`, `employment_type`,
   `monthly_income_inr`, `requested_loan_amount_inr`, `requested_term_months`, and `business_age_months` (only a proxy,
   derived from employment length). The other 10 inputs stay empty, and amounts are not converted to INR. It has only been
   tested on a small mock CSV; no real Home Credit data was used. A model trained on it would be weak on this problem and
   must not be described as validated on PayPal-style inputs.
3. No fairness/bias analysis, calibration on real outcomes, or explainability (SHAP/reason codes) yet.
4. Persona narratives are scenarios, not ground truth: the model is not tuned to match the stories. Measured scores are
   Priya 771 (*low*), Arjun 742 (*low*), Rohan 533 (*high*); ordering (Priya > Arjun > Rohan) is asserted in tests.
5. **All PayPal field mappings are PROVISIONAL and UNVERIFIED.** No PayPal API or sandbox was consulted or called; see the
   placeholder table in `docs/FEATURE_MAPPING.md`.

## Reference scores (committed model, committed fixtures)

| Persona | Score | Band | PD |
|---|---|---|---|
| Priya (stable seller) | 771 | low | 0.008 |
| Arjun (lumpy freelancer) | 742 | low | 0.012 |
| Rohan (thin history, big loan) | 533 | high | 0.17 |

## Setup, run, test (exact commands)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m payscore.train                              # optional: retrain (WRITES ./models by default; use --out-dir to avoid overwriting)
python -m payscore.predict --input fixtures/personas/priya.json
uvicorn payscore.api:app --port 8000
python -m pytest -q
ruff check .
```

Reproducibility (checked, with limits): retraining with the defaults (seed 42, `num_threads=1`) into a temporary directory produced a
`payscore_lgbm.txt` byte-identical to the committed one, in repeated runs and under two library sets (lightgbm 4.7.0 with
scikit-learn 1.8.0/pandas 3.0.2/numpy 2.4.4, and with scikit-learn 1.9.1/pandas 3.1.0/numpy 2.5.4), on Linux x86_64, Python 3.12.3.
`model_metadata.json` is **not** byte-identical because it records `trained_at_utc`; every other field matched. Other
platforms, Python versions or LightGBM versions were **not** tested, so do not assume identical output there.

Real Home Credit data (optional, **not** included, **not** run here): get `application_train.csv` from Kaggle (needs an account and
acceptance of the competition rules; check them for permitted use), then
`python -m payscore.train --source homecredit --homecredit-path /path/to/application_train.csv --out-dir models_hc`.
It never downloads anything.

## Environment variables (see `.env.example`; no secrets are needed)

| Variable | Default | Meaning |
|---|---|---|
| `PAYSCORE_MODEL_DIR` | `./models` | Directory with `payscore_lgbm.txt` + `model_metadata.json` |
| `PAYSCORE_ALLOW_FALLBACK` | `true` | Serve the labelled development fallback when no model exists (`false` -> 503) |
| `PAYSCORE_CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Allowed origins; `""` disables CORS; `*` allows all (avoid) |

## Example requests and responses (captured from a live `uvicorn` run)

`GET /health`
```json
{"status":"ok","model_loaded":true,"development_fallback_active":false,"model_type":"lightgbm","model_version":"0.1.0-synthetic-seed42","api_version":"0.1.0"}
```

`POST /score` with Priya's `model_input` -> `200`
```json
{
  "applicant_id": "PSC-PRIYA-001", "score": 771, "score_range": {"min": 300, "max": 850}, "risk_band": "low",
  "probability_of_default": 0.0077,
  "model": {"name": "payscore-lgbm-baseline", "version": "0.1.0-synthetic-seed42", "type": "lightgbm",
            "is_trained_model": true, "training_data": "synthetic_development_dataset"},
  "evaluation_caveat": "Model trained on a SYNTHETIC development dataset, not real Home Credit or PayPal data. Scores are for demonstration and integration testing only; not for real lending decisions.",
  "missing_inputs": []
}
```

Invalid body `{"applicant_id":"X1","age_years":15,"employment_type":"pilot","requested_term_months":0}` -> `422`
```json
{"error":"validation_error","detail":[
 {"field":"age_years","message":"Input should be greater than or equal to 18","type":"greater_than_equal"},
 {"field":"employment_type","message":"Input should be 'salaried', 'self_employed', 'freelancer', 'business_owner' or 'other'","type":"enum"},
 {"field":"monthly_income_inr","message":"Field required","type":"missing"},
 {"field":"requested_loan_amount_inr","message":"Field required","type":"missing"},
 {"field":"requested_term_months","message":"Input should be greater than or equal to 1","type":"greater_than_equal"}]}
```

With no model artifact (development fallback, all responses say so): `model.type` = `"development_fallback"`,
`is_trained_model` = `false`, caveat starts `DEVELOPMENT FALLBACK: ... NOT a trained-model prediction`. Fallback scores for the
personas: Priya 701 (moderate), Arjun 679 (moderate), Rohan 446 (high) - hand-set heuristic, not a model.

## Team handoff

See `docs/INTEGRATION.md` (how to call the API, provisional fields, frontend URL, implemented vs pending),
`docs/FEATURE_MAPPING.md` (field spec + PayPal placeholder table) and `docs/MODEL_CARD.md`.

## E2E smoke test (test freeze, before Nov 8)

`scripts/e2e_smoke.py` runs the full Person-2 flow against a deployed Render backend:

```bash
export PAYSCORE_API_URL=https://payscore-ai-api.onrender.com
export RUN_ADVANCE=1          # optional: enable invoice-advance (2.8) steps
python scripts/e2e_smoke.py
```

It prints PASS/FAIL per step and exits non-zero if any required step fails. Steps exercised:

| # | Step | Endpoint | Feature |
|---|------|----------|---------|
| 0 | Health | `GET /health` | service + model state |
| 1 | PayPal status | `GET /paypal/status` | sandbox credential check |
| 2 | Income profile | `GET /income-profile?persona=priya` | fixture / linked PayPal profile |
| 3 | Score | `POST /score` | LightGBM / fallback PayScore |
| 4 | Disburse | `POST /disburse` | sandbox payout (score ≥ 650) |
| 5 | Subscription | `POST /repayment/subscription` | fixed EMI schedule |
| 6 | One-off order | `POST /repayment/order` | JS SDK v6 `orderId` shape |
| 7 | Webhook (capture) | `POST /paypal/webhook` | `PAYMENT.CAPTURE.COMPLETED` → revenue share + rescore |
| 8 | Ledger + live score | `GET /repayment/status`, `GET /score/live` | verify updates |
| 9 | Invoice advance | `GET /invoices/outstanding`, `POST /advance`, `POST /invoices/{id}/remind` | 2.8 (if `RUN_ADVANCE=1`) |
| 10| Webhook (invoice paid) | `POST /paypal/webhook` | `INVOICING.INVOICE.PAID` → advance repayment |

Required env: `PAYSCORE_API_URL`. Optional: `PAYPAL_WEBHOOK_ID` (webhook steps skipped if unset), `RUN_ADVANCE=1` (advance steps).

### Deployed-on-Render checklist

Everything the smoke script hits is deployed via `render.yaml` (`payscore-ai-api` service, Python 3.12, free plan):

- `GET /health`, `GET /paypal/status`, `GET /paypal/auth/login`, `GET /paypal/auth/callback`
- `GET /paypal/public-config`, `GET /income-profile`
- `POST /score`, `GET /score/live`
- `POST /disburse`, `GET /disburse/{batch_id}`
- `POST /repayment/subscription`, `POST /repayment/order`, `POST /repayment/order/{id}/capture`
- `POST /repayment/revenue-share`, `GET /repayment/status`
- `POST /paypal/webhook` (signature verified via `PAYPAL_WEBHOOK_ID`)
- `GET /invoices/outstanding`, `POST /advance`, `POST /invoices/{id}/remind`
- `POST /offer-guard`, `POST /copilot/chat`

Set `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and `PAYPAL_WEBHOOK_ID` as Render synced secrets (never in git). Set `PAYSCORE_CORS_ORIGINS` to your deployed frontend origin.

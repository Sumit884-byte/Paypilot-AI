# Integration guide (Person 2: PayPal/backend, Person 3: frontend/agent)

The scoring API works today on **normalised mock input**. It never talks to PayPal and moves no money.

> **Read first:** the shipped model is trained on **synthetic data**. Its reported test AUC of 0.848 comes from that synthetic data
> and is **not** evidence of real-world credit-risk accuracy. All PayPal field mappings are **provisional and unverified**.

## 1. Run it locally

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn payscore.api:app --port 8000 --reload
# Swagger UI: http://localhost:8000/docs   OpenAPI JSON: http://localhost:8000/openapi.json
```

The repo ships a trained **synthetic-data** model in `models/`, so `/score` returns `model.type = "lightgbm"`. If `models/` is
empty/missing the API serves a **deterministic development fallback** (`model.type = "development_fallback"`,
`is_trained_model = false`) so you are never blocked. Set `PAYSCORE_ALLOW_FALLBACK=false` to get `503` instead.

## 2. Call `POST /score`

Request = a persona's `model_input` (see `fixtures/personas/*.json`) or any body valid against
`schema/score_request.schema.json`. Required: `applicant_id`, `age_years`, `employment_type`, `monthly_income_inr`,
`requested_loan_amount_inr`, `requested_term_months`. Everything else is optional (omit or `null` = unknown). Unknown fields -> 422.

```bash
curl -s -X POST http://localhost:8000/score -H 'Content-Type: application/json' \
  -d '{"applicant_id":"PSC-DEMO-1","age_years":30,"employment_type":"freelancer","monthly_income_inr":60000,
       "requested_loan_amount_inr":200000,"requested_term_months":12}'
```

Response (stable shape):

```json
{
  "applicant_id": "PSC-DEMO-1",
  "score": 700,
  "score_range": {"min": 300, "max": 850},
  "risk_band": "moderate",
  "probability_of_default": 0.02,
  "model": {"name": "...", "version": "...", "type": "lightgbm | development_fallback",
            "is_trained_model": true, "training_data": "synthetic_development_dataset | null"},
  "evaluation_caveat": "Always display this near the score.",
  "missing_inputs": ["avg_monthly_revenue_inr", "..."]
}
```

(The numbers above are illustrative of the *shape*; real values for the personas are in the README.)
Errors: `422 {"error":"validation_error","detail":[{"field","message","type"}]}`, `503 {"error":"model_unavailable","detail":"..."}`.
Other endpoints: `GET /health`, `GET /`.

**UI rule:** show `evaluation_caveat` and, when `is_trained_model` is false, a visible "development fallback" label.

## 3. Frontend / API URL

CORS is limited to `http://localhost:3000` and `http://localhost:5173` by default. For another origin start the API with
`PAYSCORE_CORS_ORIGINS=https://your-frontend.example` (comma-separated; `*` only for throwaway demos). Keep the API base URL in one
frontend config value (e.g. an env var such as `VITE_PAYSCORE_API_URL=http://localhost:8000`, or the equivalent for your framework).

## 4. Which fields are provisional (Person 2)

* **Every PayPal-side source is unverified.** See "Placeholder mapping" in `docs/FEATURE_MAPPING.md`.
* Most provisional: `avg_monthly_expenses_inr` (PayPal may not expose seller expenses), the sale/refund/dispute classification,
  history length (affects `revenue_volatility_cv`), and sandbox access/consent requirements.
* Fields that are always applicant-provided: age, employment type, income, requested amount/term, existing debt, prior defaults.
* `monthly_income_inr` is self-declared total monthly personal income; all amounts must be converted to INR before calling `/score`.
* Reference derivation code: `payscore/derive.py` (port these rules once the real source is known).

## 5. Implemented vs pending

| Implemented (Week 1) | Pending (later weeks / other people) |
|---|---|
| LightGBM baseline on **synthetic** data; train + inference scripts (model file reproduced byte-for-byte on Linux x86_64 / Python 3.12.3, see README) | Training/validation on the real Home Credit file (loader exists; data not available here) |
| Normalised schema + JSON Schemas, 3 fictional personas | Verified PayPal sandbox mapping (Person 2) |
| `/score`, `/health`, `/`, validation, CORS, labelled fallback, Swagger | Training on real Home Credit data |
| SHAP TreeExplainer on the trained LightGBM model (`POST /score`, `POST /explain`) | A retrieved RBI digital-lending-app snapshot (the shipped file is empty, so the check stays unverified) |
| Model-scored counterfactuals (`POST /counterfactuals`) | OCR of scanned PDFs unless pytesseract and pdf2image are installed |
| Offer guard IRR, PDF upload, KFS checklist (`POST /offer-guard`, `POST /offer-guard/upload`) | External LLM extraction unless both offer-guard flags and `OPENAI_API_KEY` are set |
| Affordability stress test (`POST /affordability`) and revenue-share volatility (`POST /revenue-volatility`) | Statistical validation of the revenue-share policy (explicitly not claimed) |
| Copilot tools that call those functions (`POST /copilot/chat`) | Automatic payouts (approval is still required) |
| 100+ unit tests with mock data only | Fairness review, calibration on real outcomes, auth/rate-limiting for any non-local deployment |

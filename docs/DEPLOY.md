# Deploying PayScore AI API to Render

The repo ships a [Render Blueprint](../render.yaml) that deploys the FastAPI app
(`payscore.api:app`) as a Python 3.12 web service with the health check wired to `GET /health`.
Everything runs against the **PayPal sandbox only** (see [SANDBOX_SETUP.md](SANDBOX_SETUP.md)
first — you need sandbox app credentials).

## 1. Push the repo to GitHub

Render deploys from a Git remote; push `main` (or the branch you want to deploy).

## 2. Create the service from the Blueprint

- Render dashboard → **New → Blueprint**, select the repo/branch. Render reads `render.yaml`.
- If the blueprint lives under a subdirectory, adjust `rootDir` in `render.yaml` to match.
- Click **Apply** — Render provisions the web service with:
  - runtime `python`, Python **3.12**
  - build: `pip install -r requirements.txt`
  - start: `uvicorn payscore.api:app --host 0.0.0.0 --port $PORT`
  - health check path: **`/health`** (deploy is marked live only once this returns 200)

## 3. Set the PayPal secrets

Blueprint-managed secrets are placeholders (`sync: false`). Fill them in
**Render dashboard → your service → Environment**:

- `PAYPAL_CLIENT_ID` — sandbox app client id
- `PAYPAL_CLIENT_SECRET` — sandbox app secret
- `PAYPAL_WEBHOOK_ID` — optional, only if webhook verification is used
- Leave `PAYPAL_MODE=sandbox` and `PAYPAL_API_BASE=https://api-m.sandbox.paypal.com` as-is.

Never paste real secrets into the blueprint file or commit them; the repo's
`tests/test_no_secrets.py` guards against that.

## 4. Verify

- Wait for the deploy to go live (health check passing).
- `curl https://<your-service>.onrender.com/paypal/status` →
  `{"paypal": "ok", "mode": "sandbox", ...}` means sandbox credentials work.
  A 503 with `code: "not_configured"` means the env vars are missing; `token_unavailable`
  means PayPal rejected the credentials or the token endpoint was unreachable.
- `curl https://<your-service>.onrender.com/health` → model/API info.

## 5. Notes

- Free plan instances spin down; the first request after idle time is slow. Upgrade the
  plan or use a ping monitor for demos.
- Webhooks require a publicly reachable HTTPS URL — the Render service URL works once
  deployed; register it in the PayPal developer dashboard (see SANDBOX_SETUP.md step 3).
- Deploys are triggered automatically on push to the connected branch.

# Paypilot AI frontend

React 18 + Vite + TypeScript + Tailwind CSS + Framer Motion shell for the PayPal AI hackathon.

## Run

```bash
cd frontend
npm install
npm run dev
```

The Vite server is on `http://localhost:5173` and proxies API calls to `http://127.0.0.1:8000`. Start the FastAPI app first:

```bash
uvicorn payscore.api:app --port 8000 --reload
```

Set `PAYSCORE_FRONTEND_URL=http://localhost:5173` on the API so browser OAuth returns to `/auth/callback`.

**Log in with PayPal** hits `GET /paypal/auth/login`. If sandbox credentials are missing, use **Tour the cockpit**.

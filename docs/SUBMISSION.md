# Submission checklist

Deadline: **12 Nov, 12:00 PM PT (13 Nov, 1:30 AM IST)**. Target: submit on 11 Nov.

## Links

Fill these in after deploying, then copy them into the README's "For judges" table.

| Item | Link |
|---|---|
| Repository | https://github.com/Sumit884-byte/Paypilot-AI |
| Frontend | `https://paypilot-web.onrender.com` (expected Render URL, not yet deployed) |
| Try as Priya | `<frontend>/try/priya` |
| Try as risky borrower | `<frontend>/try/rohan` |
| API health | `https://payscore-ai-api.onrender.com/health` (expected, not yet deployed) |
| Demo video | _to record_ |

## Before recording

- [ ] Deploy with `render.yaml` (New → Blueprint) and set the PayPal sandbox secrets in the dashboard.
- [ ] Open `/try/priya` and `/try/rohan` in a private window. Neither should ask for a login.
- [ ] Open the API URL once before recording. Render's free plan sleeps after inactivity, and the first request can take
      about a minute.
- [ ] Upload `fixtures/demo/offer_with_injection.pdf` on Offer Guard and confirm the injection banner appears.
- [ ] If the video shows passport tamper detection, set `PAYSCORE_PASSPORT_SIGNING_KEY` on the API first.

## Video shot list (about 3 minutes)

| Time | Shot |
|---|---|
| 0:00–0:15 | Problem: online sellers have income but no credit file. |
| 0:15–0:40 | `/try/priya`: income profile, PayScore 731, TreeSHAP drivers. |
| 0:40–1:00 | Toggle to "Risky borrower": Rohan scores 465, and the model card shows why scores are synthetic. |
| 1:00–1:30 | Offer Guard: advertised 18% vs effective 27.55%. Pay Later card: unavailable in India, then the US illustration with Pay in 4 as cheapest. |
| 1:30–1:45 | **Prompt-injection test (15 s):** upload `fixtures/demo/offer_with_injection.pdf` and show the banner. |
| 1:45–2:20 | Copilot: "Can I afford ₹50k?", then a disbursement request that waits for Approve. |
| 2:20–2:45 | Hardship and chargeback help in Copilot, Income Passport verification link, rule-based negotiation (simulated settlement). |
| 2:45–3:00 | Sandbox-only caveats and repo link. |

## Final checks (11 Nov)

- [ ] `pytest -q` passes on a clean clone.
- [ ] `npm run build` and `npm run lint` pass in `frontend/`.
- [ ] README links point at the deployed URLs and the video.
- [ ] `LICENSE` (MIT) is present.
- [ ] No secrets or large local files are committed (for example, model weights folders in the repo root).

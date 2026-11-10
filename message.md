# PayScore: Work Division & Master Roadmap (3 People)

**Hackathon Timeline:** 5 Nov 2026 – 11 Nov 2026  
**Deadline:** 12 Nov, 12:00 PM PT / 13 Nov, 1:30 AM IST (Target Submission: 11 Nov)[cite: 1, 2]

---

## 1. Individual Assignments

### Person A: Core AI, Workflows & Safety
* **Task 1: Hardship Agent (#1)**[cite: 1]
  * *Details:* Implement webhook detection for ~2 weeks of no income; trigger LLM agent to offer payment holiday or lower revenue-share[cite: 1].
  * *Tech / APIs:* Webhooks, Subscriptions, LLM Agent[cite: 1]
  * *Target Window:* 5–6 Nov[cite: 2]
* **Task 2: Prompt-Injection Guardrail (#4)**[cite: 1]
  * *Details:* Inject hidden adversarial prompt ("ignore previous instructions...") into loan PDF; ensure agent flags it cleanly for the demo[cite: 1].
  * *Tech / APIs:* LLM Guardrails[cite: 1]
  * *Target Window:* 7 Nov[cite: 2]
* **Task 3: Dispute Helper (#3)**[cite: 1]
  * *Details:* List open chargebacks via MCP server and generate LLM draft responses to protect borrower income/score[cite: 1].
  * *Tech / APIs:* MCP Server, LLM[cite: 1]
  * *Target Window:* 8–9 Nov[cite: 2]

---

### Person B: PayPal Integrations, Financial Engine & Video Lead
* **Task 1: Judge Demo Mode (#5)**[cite: 1]
  * *Details:* Create "Try as Priya" and "Try as risky borrower" sandbox toggles with zero login friction on hosted deployment[cite: 1].
  * *Tech / APIs:* Sandbox Accounts, Render / Hosting[cite: 1]
  * *Target Window:* 5 Nov (Priority Zero)[cite: 2]
* **Task 2: Pay Later Comparison Engine (#2)**[cite: 1]
  * *Details:* Add purchase loan offer guard that calculates and displays PayPal Pay Later cost to surface the cheapest alternative[cite: 1].
  * *Tech / APIs:* PayPal Pay Later API[cite: 1]
  * *Target Window:* 6–7 Nov[cite: 2]
* **Task 3: Submission & Video Production**[cite: 2]
  * *Details:* Record demo video (including the 15s prompt injection test highlight), write README, license repo, organize links[cite: 1, 2].
  * *Target Window:* 9–11 Nov[cite: 2]

---

### Person C: Frontend Cockpit, ML Visualization & Negotiation
* **Task 1: Model Card Widget (#8)**[cite: 1]
  * *Details:* Build AG Studio component displaying AUC, calibration charts, and excluded sensitive features in the dashboard[cite: 1].
  * *Tech / APIs:* AG Grid / AG Studio[cite: 1]
  * *Target Window:* 5–6 Nov[cite: 2]
* **Task 2: Agent-to-Agent Negotiation (#6)** *(Conditional / Ambitious)*[cite: 1]
  * *Details:* Build two-agent negotiation (Lender Agent terms vs. Priya's Agent counter) settling via Payouts[cite: 1].
  * *Tech / APIs:* PayPal Payouts, Dual LLM Agents[cite: 1]
  * *Target Window:* 6–8 Nov[cite: 2]
* **Task 3: Shareable Income Passport (#7)**[cite: 1]
  * *Details:* Generate 1-page verified income summary PDF with verification link for third-party view[cite: 1].
  * *Target Window:* 9 Nov[cite: 2]

---

## 2. Team Timeline & Dependencies

| Dates | Person A | Person B | Person C | Key Milestones |
|---|---|---|---|---|
| **5 Nov** | Must-Ship Polish | **#5 Judge Demo Mode**[cite: 1] | **#8 Model Card Widget**[cite: 1] | **#6 Go/No-Go Decision**[cite: 1, 2] |
| **6–7 Nov** | **#1 Hardship Agent**[cite: 1] | **#2 Pay Later Engine**[cite: 1] | **#6 Negotiation** *(or assist A/B)*[cite: 1, 2] | Core flow fully testable online |
| **8 Nov** | **#4 Injection Test**[cite: 1] | Integration Testing | **#6 Negotiation Settlement**[cite: 1] | Feature freeze for ambitious scope |
| **9–10 Nov** | **#3 Dispute Helper**[cite: 1] | **Video Recording**[cite: 2] | **#7 Income Passport**[cite: 1] | Video recorded & asset review |
| **11 Nov** | Documentation Review | **Final Submission**[cite: 2] | Repo Cleanup & License | Submit 1 day early[cite: 2] |

---

## 3. Strict Guardrails & Out of Scope

* **Do Not Add:** Voice / Hindi audio, Account Aggregator integration, Bryntum, extra persona flows beyond risky borrower[cite: 1].
* **5 Nov Go/No-Go Check:** If core outline items 1–5, 7, and 8 are not running end-to-end, drop **#6 Agent-to-Agent Negotiation** immediately and pivot Person C to assist Person A and B on Tasks #1, #2, and #8[cite: 1, 2].
# Ledgerline — Tasks

**How to use:** put your initials in `[ ]` → `[AB]` when you start, and `[x]` when merged to `main`.
Priority: **P0** = demo-critical · **P1** = only after P0 works · **P2** = pitch-only
Dependencies are noted as `← B3` (wait on, or mock, that task).

---

## 🚨 H0 — Everyone (first 30 minutes)
- [ ] Create GitHub repo `ledgerline` with the folder structure from PLAN.md §3 — **E**
- [ ] Shared AWS account/region (`us-east-1`), IAM users for all 5, **AWS Budgets alarm $25** — **E**
- [ ] Enable **Bedrock model access** (Claude) and verify one `InvokeModel` call — **B**
- [ ] Verify one **Textract AnalyzeExpense** call on a sample invoice — **B**
- [ ] Agree on and commit the **API contract** + `frontend/mocks/*.json` — **C + A** (everyone reviews)
- [ ] **Submit category form: Startup We'd Buy Tomorrow + Biggest Business Impact** — **E**
- [ ] Assign names to roles A–E in PLAN.md §7

---

## A — Frontend Lead
**P0**
- [A] A1. Next.js + Tailwind + shadcn scaffold, layout with sidebar (Dashboard, Inbox, Bills, Revenue, Library, Ask, Rules)
- [A] A2. `lib/api.ts` typed client with `USE_MOCKS` flag reading `mocks/*.json`
- [A] A3. **Upload dropzone** → `POST /documents/upload-url` → PUT to S3 → poll document status ← C2
- [A] A4. **Document detail**: PDF preview beside extracted fields, confidence badges, "Recognized vendor ✓" chip
- [A] A5. **Bills / Approvals** table with status pills; rule-hit reasons; Approve/Reject buttons → `/bills/{id}/decision` ← C5
- [A] A6. **Dashboard**: KPI cards (Revenue, Margin, Recurring %, Est. Practice Value), P&L chart, balance sheet + cash flow tabs ← D2
- [A] A7. **Revenue reconciliation** view: expected vs. actual, red variance flags ← D4
- [A] A8. **Ask your books** chat with clickable citation chips that open the doc ← D5
- [A] A9. **Library**: search/filter by type, vendor, date; "Export package" button ← D6
- [A] A10. Cognito login (Amplify UI) + role switcher for demo (Owner ↔ Partner) ← E4
- [ ] A11. Deploy to Amplify Hosting ← E2

**P1**
- [A] A12. Rules page: view rules; create a rule with a simple form ← C7
- [A] A13. Loading skeletons, empty states, toast notifications, live refresh after approval
- [A] A14. Card transactions page (CSV import) ← C9
- [A] A15. Profile settings panel with persistent dark mode toggle
- [AK] A16. Align Brightline demo vendor and switch frontend to deployed stack outputs

---

## B — Document AI
**P0**
- [x] B1. `classify` Lambda: Bedrock prompt → `{type, confidence}` across 5 doc types
- [x] B2. `extract_expense` Lambda: Textract **AnalyzeExpense** → raw fields + line items
- [x] B3. `extract_tables` Lambda: Textract **AnalyzeDocument (TABLES, FORMS)** for payout statements, void checks, W-9s
- [x] B4. `normalize` Lambda: Bedrock maps Textract output → our JSON schema (strict JSON, validated) + confidence
- [x] B5. `match_vendor` Lambda: exact/alias → fuzzy match (e.g. `rapidfuzz`); set `defaultGlAccount` from history; create the vendor if new ← C3
- [x] B6. Step Functions `IngestDocument` ASL: classify → branch → normalize → match → create Bill / RevenueLines → start `ApproveBill` ← C4
- [x] B7. EventBridge rule: S3 `Object Created` in `uploads/` → start `IngestDocument` ← E3
- [ ] B8. Test on **all seed docs** (E5); tune prompts until every demo doc extracts correctly
- [x] B9. Void check / W-9 → update vendor `hasVoidCheck`, `hasW9`, `bankLast4`

**P1**
- [ ] B10. Duplicate/suspicious vendor flag (same bank details, different vendor name)
- [ ] B11. Receipt ↔ card transaction matching (amount + date + merchant)
- [ ] B12. GL account suggestion with a reason string ("Matched prior invoices from this vendor")

---

## C — Backend & Workflows
**P0**
- [ ] C1. DynamoDB single table + `shared/ddb.py` helpers + `shared/models.py` (PLAN.md §4)
- [ ] C2. `POST /documents/upload-url`, `GET /documents`, `GET /documents/{id}`
- [ ] C3. `GET /vendors`; vendor repository used by B5
- [ ] C4. Bill creation helper (called from ingest) + `GET /bills?status=`
- [ ] C5. `POST /bills/{id}/decision` → `SendTaskSuccess` / `SendTaskFailure`
- [ ] C6. `evaluate_rules` Lambda: amount threshold, new-vendor-missing-docs, received-before-pay
- [ ] C7. `GET/POST /rules` + 3 default rules seeded
- [ ] C8. Step Functions `ApproveBill` ASL: evaluate → auto-approve OR `waitForTaskToken` → `post_ledger` → mark `scheduled` (mock pay) → EventBridge `LedgerUpdated`
- [ ] C9. `shared/ledger.py`: double-entry posting (`Dr Expense / Cr AP`; mock pay `Dr AP / Cr Cash`; payout `Dr Cash / Cr Revenue`) ← pair with D
- [ ] C10. API Gateway HTTP API + Cognito JWT authorizer + CORS ← E4

**P1**
- [ ] C11. `POST /transactions/import` (CSV) → ledger entries + categorization (Bedrock)
- [ ] C12. Gift/entertainment rule: flag card spend over a configurable limit
- [ ] C13. Audit trail endpoint: who approved what and when

---

## D — Financials & Insights
**P0**
- [ ] D1. Chart of accounts for an advisor practice (revenue: advisory, commission, trails; expenses: staff, rent, tech, LPL fees, marketing, compliance, T&E)
- [ ] D2. `GET /financials?period=`: P&L, balance sheet, cash flow (direct method) from ledger entries
- [ ] D3. KPIs: operating margin, recurring revenue %, revenue per client, expense ratio by category
- [ ] D4. `GET /revenue/reconciliation`: expected (from seeded fee schedule) vs. actual (payout lines) → variance flags with a reason
- [ ] D5. `POST /ask`: build context (period ledger summary + matching docs) → Bedrock with **Guardrails** → `{answer, citations}`
- [ ] D6. `POST /export`: ZIP of period documents + `ledger.csv` + `financials.json` → presigned URL
- [ ] D7. Valuation: `recurring_revenue_ttm × multiple` (low/mid/high), adjusted by recurring %, margin and concentration; return the `method` text for a UI tooltip
- [ ] D8. Create the Bedrock Guardrail (deny investment advice, mask PII) ← E

**P1**
- [ ] D9. "Why did X change?" variance explainer: compare periods, top 3 drivers
- [ ] D10. Peer benchmark card (static fictional benchmarks)

---

## E — Infra, Data & Pitch
**P0 — Infra**
- [ ] E1. SAM `template.yaml` skeleton: table, buckets, API, Cognito, state machines; `sam deploy` works for everyone
- [ ] E2. Amplify Hosting connected to the repo (`frontend/`)
- [ ] E3. S3 documents bucket with **Object Lock** (governance mode for the demo) + EventBridge notifications on; exports bucket
- [ ] E4. Cognito user pool + groups `owner`, `partner`, `ops`, `lpl_bookkeeper`; demo users
- [ ] E5. CloudTrail on; CloudWatch dashboard (nice screenshot for the AWS judges)

**P0 — Data**
- [ ] E6. Fictional practice **"Harbor Point Wealth"** (4 people, ~$250M AUM, ~180 clients); fee schedule for expected revenue
- [ ] E7. `seed/seed_ddb.py`: 6 months of ledger history, 8–10 vendors, default rules
- [ ] E8. `seed/generate_docs.py`: demo PDFs, all watermarked **"SAMPLE — FICTIONAL DATA"**
  - [ ] 2 invoices from the **same vendor** (vendor memory demo), one over $1,000
  - [ ] 1 invoice from a **new vendor** (missing W-9 → rule hit)
  - [ ] 1 void check + 1 W-9 for that vendor
  - [ ] 1 messy, scanned-looking receipt
  - [ ] 1 payout statement with **one trail $412 short** of expected
- [ ] E9. `seed/reset_demo.py`: one command restores the demo state

**P0 — Pitch**
- [ ] E10. Deck (8–10 slides): Hook → Problem → Solution → Demo → Why LPL acquires → AWS architecture → Business impact → Compliance → Team/ask
- [ ] E11. Demo script (PRD §6) timed to 3:00; assign who clicks and who talks
- [ ] E12. **Record backup demo video** by H21
- [ ] E13. Q&A prep doc: "Isn't this QuickBooks/Ramp?", "Why wouldn't LPL build it?", "How does it make money?", "What about security?", "Cost at scale?"
- [ ] E14. Ask LPL mentors the 3 open questions (PRD §10) and put any quotes on the slides

**P1**
- [ ] E15. Architecture diagram as a clean slide
- [ ] E16. Rough cost estimate per practice per month (Textract pages + Bedrock tokens + Lambda) for the "cost-aware" talking point

---

## 🔗 Integration checkpoints
- [ ] **H2:** contract frozen; all mocks render in the UI; SAM deploys
- [ ] **H6:** real upload → Bill appears in UI (A + B + C)
- [ ] **H12:** 2nd invoice auto-matches vendor; approval → ledger; reconciliation flags (B + C + D)
- [ ] **H16:** 🔒 **FEATURE FREEZE** — full demo runs end to end on real AWS
- [ ] **H21:** backup video recorded; reset script works
- [ ] **H23:** 3 timed rehearsals done; submitted

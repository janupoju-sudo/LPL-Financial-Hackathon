# Ledgerline — Tasks

**Status updated Oct 2, 2026 (verified against main, AWS and merged PRs).**

**How to use:** put your initials in `[ ]` → `[AB]` when you start, and `[x]` when merged to `main`.
Priority: **P0** = demo-critical · **P1** = only after P0 works · **P2** = pitch-only
Dependencies are noted as `← B3` (wait on, or mock, that task).

---

## 🚨 H0 — Everyone (first 30 minutes)
- [ ] Create GitHub repo `ledgerline` with the folder structure from PLAN.md §3 — **E**
- [ ] Shared AWS account/region (`us-east-1`), IAM users for all 5, **AWS Budgets alarm $25** — **E**
- [ ] Enable **Bedrock model access** (Claude) and verify one `InvokeModel` call — **B**
- [ ] Verify one **Textract AnalyzeExpense** call on a sample invoice — **B**
- [x] Agree on and commit the **API contract** + `frontend/mocks/*.json` — **C + A** (everyone reviews)
- [ ] **Submit category form: Startup We'd Buy Tomorrow + Biggest Business Impact** — **E**
- [ ] Assign names to roles A–E in PLAN.md §7 — _PLAN.md §7 still has placeholder names_

---

## A — Frontend Lead
**P0**
- [x] A1. Next.js + Tailwind + shadcn scaffold, layout with sidebar (Dashboard, Inbox, Bills, Revenue, Library, Ask, Rules)
- [x] A2. `lib/api.ts` typed client with `USE_MOCKS` flag reading `mocks/*.json`
- [x] A3. **Upload dropzone** → `POST /documents/upload-url` → PUT to S3 → poll document status ← C2
- [x] A4. **Document detail**: PDF preview beside extracted fields, confidence badges, "Recognized vendor ✓" chip
- [x] A5. **Bills / Approvals** table with status pills; rule-hit reasons; Approve/Reject buttons → `/bills/{id}/decision` ← C5
- [x] A6. **Dashboard**: KPI cards (Revenue, Margin, Recurring %, Est. Practice Value), P&L chart, balance sheet + cash flow tabs ← D2
- [x] A7. **Revenue reconciliation** view: expected vs. actual, red variance flags ← D4
- [x] A8. **Ask your books** chat with clickable citation chips that open the doc ← D5
- [x] A9. **Library**: search/filter by type, vendor, date; "Export package" button ← D6
- [x] A10. Cognito login (Amplify UI) + role switcher for demo (Owner ↔ Partner) ← E4 — _live mode uses the signed-in role; switching = sign out / sign in as Raj_
- [x] A11. Deploy to Amplify Hosting ← E2 — _live at https://main.d1ci8xrur0a8sr.amplifyapp.com, auto-deploys on merge to main_

**P1**
- [x] A12. Rules page: view rules; create a rule with a simple form ← C7
- [x] A13. Loading skeletons, empty states, toast notifications, live refresh after approval
- [x] A14. Card transactions page (CSV import) ← C9
- [x] A15. Profile settings panel with persistent dark mode toggle
- [x] A16. Align Brightline demo vendor and switch frontend to deployed stack outputs
- [x] A17. Combine Inbox and Library into Documents: Upload action, All documents / Needs review / Processing / Vendors views, summary counts, search and filters; counts filter and scroll to results
- [x] A18. Remove header mode badge, role control, bell shortcut, and sidebar connection/authentication text

**A validation:** Local live Cognito sign-in, Documents views, upload controls, summary filtering/scrolling, and desktop/mobile layouts have been browser-checked. Full live upload/approval and CSV import validation remains part of the integration checkpoints. Header role controls were removed at Akshaya's request; Cognito group-based roles remain.


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
- [ ] B8. Test on **all seed docs** (E5); tune prompts until every demo doc extracts correctly — _ingest ran live once (PNG → needs_review); demo PDFs not yet uploaded live_
- [x] B9. Void check / W-9 → update vendor `hasVoidCheck`, `hasW9`, `bankLast4`

**P1**
- [ ] B10. Duplicate/suspicious vendor flag (same bank details, different vendor name)
- [x] B11. Receipt ↔ card transaction matching (amount + date + merchant) — _built into C11's import (amount + date window)_
- [ ] B12. GL account suggestion with a reason string ("Matched prior invoices from this vendor")

---

## C — Backend & Workflows
**P0**
- [x] C1. DynamoDB single table + `shared/ddb.py` helpers (+ `shared/repo.py` in place of `models.py`) (PLAN.md §4)
- [x] C2. `POST /documents/upload-url`, `GET /documents`, `GET /documents/{id}`
- [x] C3. `GET /vendors`; vendor repository used by B5
- [x] C4. Bill creation helper (called from ingest) + `GET /bills?status=`
- [x] C5. `POST /bills/{id}/decision` → resumes the task (reject → `MarkRejected`); role check, no self-approval, atomic
- [x] C6. `evaluate_rules` Lambda: amount threshold, new-vendor-missing-docs, received-before-pay (+ duplicate invoice → block)
- [x] C7. `GET/POST /rules` (+ `PATCH`) + 4 default rules seeded
- [x] C8. Step Functions `ApproveBill` ASL: evaluate → auto-approve OR `waitForTaskToken` → `post_ledger` → mark `scheduled` (mock pay) → EventBridge `LedgerUpdated`
- [x] C9. `shared/ledger.py`: double-entry posting (`Dr Expense / Cr AP`; mock pay `Dr AP / Cr Cash`; payout `Dr Cash / Cr Revenue`), per line in int cents, atomic + idempotent ← paired with D
- [x] C10. API Gateway HTTP API + Cognito JWT authorizer + CORS ← E4

**P1**
- [x] C11. `POST /transactions/import` (CSV) → ledger entries + categorization (vendor memory + merchant keywords, not Bedrock) + receipt matching (#23)
- [ ] C12. Gift/entertainment rule: flag card spend over a configurable limit
- [J] C13. Audit trail: every bill's `audit[]` (who did what, when) via `GET /bills/{id}`; no separate endpoint yet

**Also done (C)**
- [x] C14. `POST /bills/{id}/confirm` (human review of low-confidence bills) + `POST /bills/{id}/receive`
- [x] C15. Object Lock retention applied per upload (`LockDocumentFunction`)
- [x] C16. Revenue lines + fee schedule helpers (`repo.put_revenue_lines`) for D's reconciliation
- [x] C17. Hold-for-documents loop: W-9/void check arrival → `VendorUpdated` → held bills resume automatically
- [x] C18. Template owner: wired D's resources (financials, ask, export, guardrail) and B's ingest; Ask IAM for Bedrock (#13); optional `IngestModelId` (#14)
- [x] C19. Cognito self-signup disabled (#16)
- [x] C20. Frontend live-mode adapter for C's API field names (#29)
- [x] C21. `POST /documents/{id}/resolve`: close out Needs Review documents (#35)

---

## D — Financials & Insights
**P0**
- [x] D1. Chart of accounts for an advisor practice (revenue: advisory, commission, trails; expenses: staff, rent, tech, LPL fees, marketing, compliance, T&E)
- [x] D2. `GET /financials?period=`: P&L, balance sheet, cash flow (direct method) from ledger entries
- [x] D3. KPIs: operating margin, recurring revenue %, revenue per client, expense ratio by category
- [x] D4. `GET /revenue/reconciliation`: expected (from seeded fee schedule) vs. actual (payout lines) → variance flags with a reason
- [x] D5. `POST /ask`: build context (period ledger summary + matching docs) → Bedrock with **Guardrails** → `{answer, citations}`
- [x] D6. `POST /export`: ZIP of period documents + `ledger.csv` + `financials.json` → presigned URL
- [x] D7. Valuation: `recurring_revenue_ttm × multiple` (low/mid/high), adjusted by recurring %, margin and concentration; return the `method` text for a UI tooltip
- [x] D8. Create the Bedrock Guardrail (deny investment advice, mask PII) ← E — _live, 7/7 checks pass (`scripts/check_guardrail.py`)_

**P1**
- [x] D9. "Why did X change?" variance explainer: compare periods, top 3 drivers — _covered by Ask: compares the period with the previous one and names the biggest drivers_
- [ ] D10. Peer benchmark card (static fictional benchmarks)

---

## E — Infra, Data & Pitch
**P0 — Infra**
- [x] E1. SAM `template.yaml` skeleton: table, buckets, API, Cognito, state machines; `sam deploy` works for everyone — _stack `ledgerline-dev` deployed_
- [x] E2. Amplify Hosting connected to the repo (`frontend/`)
- [x] E3. S3 documents bucket with **Object Lock** (governance mode for the demo) + EventBridge notifications on; exports bucket
- [x] E4. Cognito user pool + groups `owner`, `partner`, `ops`, `lpl_bookkeeper`; demo users — _4 demo logins created; self-signup disabled_
- [ ] E5. CloudTrail on; CloudWatch dashboard (nice screenshot for the AWS judges) — _CloudTrail is on (hackathon account trail); **CloudWatch dashboard not built**_

**P0 — Data**
- [x] E6. Fictional practice **"Harbor Point Wealth"** (4 people, ~$250M AUM, ~180 clients); fee schedule for expected revenue
- [x] E7. `seed/seed_ddb.py`: 6 months of ledger history, 8–10 vendors, default rules — _12 months of history + Q3 margin drop; 5 vendors; 12 history bills via `seed_bills.py`; seeded live_
- [x] E8. `seed/generate_docs.py`: demo PDFs, all watermarked **"SAMPLE — FICTIONAL DATA"**
  - [x] 2 invoices from the **same vendor** (vendor memory demo), one over $1,000
  - [x] 1 invoice from a **new vendor** (missing W-9 → rule hit)
  - [x] 1 void check + 1 W-9 for that vendor
  - [x] 1 messy, scanned-looking receipt
  - [x] 1 payout statement with **one trail $412 short** of expected
- [x] E9. `seed/reset_demo.py`: one command restores the demo state — _`backend/scripts/reset_demo.py`; tests pass since the seed fix (#37)_

**P0 — Pitch**
- [ ] E10. Deck (8–10 slides): Hook → Problem → Solution → Demo → Why LPL acquires → AWS architecture → Business impact → Compliance → Team/ask
- [ ] E11. Demo script (PRD §6) timed to 3:00; assign who clicks and who talks — _financial part (Revenue → Dashboard → Ask → Export) drafted by D_
- [ ] E12. **Record backup demo video** by H21
- [ ] E13. Q&A prep doc: "Isn't this QuickBooks/Ramp?", "Why wouldn't LPL build it?", "How does it make money?", "What about security?", "Cost at scale?" — _reconciliation / AI accuracy / citations / limitations Q&A drafted by D_
- [ ] E14. Ask LPL mentors the 3 open questions (PRD §10) and put any quotes on the slides

**P1**
- [ ] E15. Architecture diagram as a clean slide
- [ ] E16. Rough cost estimate per practice per month (Textract pages + Bedrock tokens + Lambda) for the "cost-aware" talking point

---

## 🔗 Integration checkpoints
- [x] **H2:** contract frozen; all mocks render in the UI; SAM deploys
- [ ] **H6:** real upload → Bill appears in UI (A + B + C) — _**next up**: upload the Orion $450 invoice on the live site_
- [ ] **H12:** 2nd invoice auto-matches vendor; approval → ledger; reconciliation flags (B + C + D)
- [ ] **H16:** 🔒 **FEATURE FREEZE** — full demo runs end to end on real AWS
- [ ] **H21:** backup video recorded; reset script works
- [ ] **H23:** 3 timed rehearsals done; submitted

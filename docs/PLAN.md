# Ledgerline — Technical & Execution Plan

## 1. Guiding principles
1. **One complete loop beats five half-features.** Upload → extract → approve → ledger → dashboard must work end to end by the midpoint.
2. **Contracts first, mocks second, real third.** Freeze the API shapes in the first 2 hours. The frontend builds against mock JSON while the backend builds the real thing.
3. **Serverless everything.** No servers to manage, pay-per-use, and an easy "cost-aware" story for judges.
4. **Seed data is a feature.** A believable fictional practice with realistic documents makes or breaks the demo.
5. **Record a backup demo video** before the final hours. Live demos fail.

## 2. Architecture

```
                    ┌──────────────────────────────┐
  Browser (Next.js) │  Amplify Hosting + Cognito    │
                    └──────────────┬───────────────┘
                                   │ HTTPS (JWT)
                          ┌────────▼────────┐
                          │  API Gateway    │
                          └────────┬────────┘
                                   │
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                     ▼
       Lambda: api-*        Lambda: ask           Lambda: export
       (CRUD, approve)      (Bedrock Q&A)         (ZIP + CSV)
              │                    │                     │
              ▼                    ▼                     ▼
        ┌───────────┐       ┌────────────┐        ┌────────────┐
        │ DynamoDB  │◄──────┤  Bedrock   │        │ S3 exports │
        │ (ledger)  │       │ + Guardrail│        └────────────┘
        └─────▲─────┘       └─────▲──────┘
              │                   │
   ┌──────────┴───────────────────┴─────────────┐
   │ Step Functions: IngestDocument              │
   │  classify → extract → normalize → match     │
   │  → create Bill / RevenueLines               │
   │ Step Functions: ApproveBill                 │
   │  evaluate rules → waitForTaskToken → post   │
   └──────────▲─────────────────────────────────┘
              │ EventBridge (S3 Object Created)
       ┌──────┴───────┐        ┌───────────┐
       │ S3 documents │───────►│ Textract  │
       │ (Object Lock)│        │ Expense / │
       └──────────────┘        │ Tables    │
                               └───────────┘
   CloudTrail + CloudWatch on everything · AWS Budgets alarm
```

### AWS services and why ("right service for the right reason")

| Service | Why |
|---|---|
| **S3 + Object Lock** | Document library; tamper-proof records retention; presigned uploads |
| **Textract AnalyzeExpense** | Purpose-built to read invoices and receipts (vendor, totals, line items) |
| **Textract AnalyzeDocument (TABLES)** | Payout statements and void checks |
| **Bedrock (Claude)** | Classify documents, normalize to a schema, categorize GL accounts, Q&A |
| **Bedrock Guardrails** | No investment advice; mask PII in answers |
| **Step Functions** | Visual, auditable workflows; `waitForTaskToken` = native human approval |
| **EventBridge** | S3 upload → start ingest; `LedgerUpdated` events |
| **Lambda (Python 3.12)** | All business logic |
| **API Gateway (HTTP API)** | REST API with Cognito JWT authorizer |
| **DynamoDB** | Single-table: practices, vendors, bills, ledger, rules |
| **Cognito** | Auth plus groups: `owner`, `ops`, `lpl_bookkeeper` |
| **Amplify Hosting** | Deploy the Next.js frontend from git |
| **CloudTrail / CloudWatch / Budgets** | Audit, observability, cost guardrail |

> ⚠️ **Do first (H0):** confirm **Bedrock model access** for a Claude model in the chosen region (e.g. `us-east-1`) and a Textract call working. These are the two things most likely to block you.

## 3. Tech stack
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts
- **Backend:** Python 3.12 Lambdas, **AWS SAM** (`template.yaml`) for infrastructure as code
- **Repo:** one monorepo, GitHub, `main` protected; feature branches; merge often

```
ledgerline/
├── frontend/                # Next.js app
│   ├── app/(dashboard)/...
│   ├── lib/api.ts           # typed client; MOCK mode flag
│   └── mocks/*.json         # contract fixtures (source of truth for H0–H6)
├── backend/
│   ├── template.yaml        # SAM: all AWS resources
│   ├── functions/
│   │   ├── api/             # bills, vendors, rules, approvals, documents
│   │   ├── ingest/          # classify, extract, normalize, match
│   │   ├── approve/         # evaluate_rules, post_ledger
│   │   ├── financials/      # statements, kpis, valuation, reconciliation
│   │   ├── ask/             # Bedrock Q&A
│   │   └── export/
│   ├── statemachines/       # *.asl.json
│   └── shared/              # ddb.py, models.py, ledger.py
├── seed/
│   ├── generate_docs.py     # fake invoices/payouts → PDFs (SAMPLE watermark)
│   ├── seed_ddb.py          # practice, chart of accounts, 6 months of history
│   └── docs/                # generated demo PDFs
└── pitch/                   # deck, demo script, backup video
```

## 4. Data model (DynamoDB single table `ledgerline`)

| Entity | PK | SK | Key attributes |
|---|---|---|---|
| Practice | `PRACTICE#p1` | `META` | name, owner, aum, clientCount |
| Vendor | `PRACTICE#p1` | `VENDOR#v123` | name, aliases[], defaultGlAccount, hasW9, hasVoidCheck, bankLast4, lastSeen |
| Document | `PRACTICE#p1` | `DOC#d123` | s3Key, type (`invoice\|receipt\|void_check\|w9\|payout_statement`), status, confidence, extracted{} |
| Bill | `PRACTICE#p1` | `BILL#b123` | vendorId, docId, amount, dueDate, glAccount, status (`pending_review\|pending_approval\|approved\|rejected\|scheduled`), taskToken |
| Rule | `PRACTICE#p1` | `RULE#r1` | name, condition {field, op, value}, action (`require_approval\|require_docs\|block`), approverRole |
| LedgerEntry | `PRACTICE#p1` | `LEDGER#2026-09#e123` | date, account, debit, credit, sourceDocId, memo |
| RevenueLine | `PRACTICE#p1` | `REV#2026-09#x1` | source (`advisory\|commission\|trail`), expected, actual, variance, docId |
| Account | `PRACTICE#p1` | `COA#6100` | name, type (`asset\|liability\|equity\|revenue\|expense`) |

**Ledger:** simple double-entry. An approved bill posts `Dr Expense / Cr Accounts Payable`, and "paid" (mocked) posts `Dr AP / Cr Cash`. A payout posts `Dr Cash / Cr Revenue`. Statements are computed from ledger entries.

**Valuation (clearly labeled an estimate):** `recurring_revenue_ttm × multiple`, with the multiple adjusted by recurring %, margin and client concentration. Show the formula in a tooltip, because judges like transparency.

## 5. API contract (freeze by H2)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/documents/upload-url` | `{filename, contentType}` | `{documentId, uploadUrl}` |
| GET | `/documents?type=&q=` | — | `[{id, type, filename, status, vendorName, amount, createdAt}]` |
| GET | `/documents/{id}` | — | `{id, type, status, confidence, extracted, viewUrl, billId?}` |
| GET | `/bills?status=` | — | `[{id, vendor, amount, dueDate, glAccount, status, ruleHits[]}]` |
| POST | `/bills/{id}/decision` | `{decision: "approve"\|"reject", comment}` | `{id, status}` |
| GET | `/vendors` | — | `[{id, name, defaultGlAccount, hasW9, hasVoidCheck, billCount}]` |
| GET / POST | `/rules` | `{name, condition, action, approverRole}` | `[Rule]` |
| GET | `/revenue/reconciliation?period=2026-09` | — | `{expected, actual, variance, lines:[...], flags:[...]}` |
| GET | `/financials?period=2026-Q3` | — | `{pnl, balanceSheet, cashFlow, kpis:{margin, recurringPct, revPerClient}, valuation:{low, mid, high, method}}` |
| POST | `/ask` | `{question}` | `{answer, citations:[{documentId, label, snippet}]}` |
| POST | `/export` | `{period}` | `{downloadUrl}` |
| POST | `/transactions/import` (P1) | CSV | `{imported, categorized, matchedReceipts}` |

The frontend keeps `mocks/*.json` matching these shapes exactly and flips `NEXT_PUBLIC_USE_MOCKS=false` once each endpoint is live.

## 6. Key flows

**Ingest (Step Functions `IngestDocument`):**
1. `classify`: Bedrock on the first page's text, returning one of the document types.
2. Branch: invoice/receipt → Textract **AnalyzeExpense**; payout/void check/W-9 → **AnalyzeDocument (TABLES, FORMS)**.
3. `normalize`: Bedrock maps the Textract output to our JSON schema plus a confidence score.
4. `match_vendor`: exact or alias match in DynamoDB, then fuzzy match. If it's a new vendor, create it with `hasW9=false`.
5. Create a **Bill** (or **RevenueLines** for payouts → run reconciliation).
6. If confidence < 0.8, status is `pending_review`. Otherwise start `ApproveBill`.

**Approve (Step Functions `ApproveBill`):**
1. `evaluate_rules`: return rule hits, e.g. `amount > 1000 → require_approval(partner)` or `vendor.hasW9 == false → require_docs`.
2. No hits → auto-approve. Hits → `waitForTaskToken` (store the token on the Bill).
3. UI `POST /bills/{id}/decision` → Lambda calls `SendTaskSuccess` / `SendTaskFailure`.
4. `post_ledger` → mark `scheduled` (mock payment) → emit `LedgerUpdated`.

**Ask:** pull the period's ledger summary plus the top matching documents (simple keyword or metadata filter) into the prompt, with Guardrails on. Return the answer and the cited document IDs. No vector DB is needed, which is a deliberate cost-aware choice (mention Bedrock Knowledge Bases as the scale path).

## 7. Team split (5 people)

| Role | Owner | Owns | Main AWS |
|---|---|---|---|
| **A — Frontend Lead** | _name_ | All UI: upload, library, bills/approvals, dashboard, ask, polish | Amplify, Cognito (client) |
| **B — Document AI** | _name_ | Ingest pipeline: classify, extract, normalize, vendor memory, payout parsing | Textract, Bedrock, Step Functions (ingest) |
| **C — Backend & Workflows** | _name_ | API, data model, rules engine, approvals, ledger posting | API Gateway, Lambda, DynamoDB, Step Functions (approve), EventBridge |
| **D — Financials & Insights** | _name_ | Statements, KPIs, valuation, reconciliation, Ask-your-books, export | Lambda, Bedrock + Guardrails, S3 |
| **E — Infra, Data & Pitch** (suggest: Jay) | _name_ | SAM skeleton, deploy, Cognito, Object Lock, seed data + demo docs, deck, demo script, backup video, judging Q&A prep | SAM, S3 Object Lock, CloudTrail, Budgets |

**Pairing at integration points:**
- B ↔ C at H6 (ingest creates Bills that the approval flow picks up)
- C ↔ D at H10 (ledger entries feed the statements)
- A ↔ everyone continuously (swap mock to real per endpoint)
- E reviews the demo flow with everyone at each checkpoint

## 8. Timeline (relative hours; adjust to the official end time)

| Hours | Milestone | Exit criteria |
|---|---|---|
| **H0–H2** | **Setup & contracts** | Repo up; SAM deploys a hello-world; Bedrock + Textract calls verified; API contract and mocks frozen; **category form submitted** (Startup We'd Buy + Business Impact) |
| **H2–H6** | **Vertical slice v0** | Upload PDF → S3 → ingest → Bill visible in UI (even if extraction is rough) |
| **H6–H12** | **Core loop** | Vendor memory works on a 2nd invoice; rules → approval → ledger; payout reconciliation returns flags |
| **H12–H16** | **Insights** | Dashboard with real statements and valuation; Ask with citations; export ZIP |
| **H16–H18** | **Feature freeze** 🔒 | No new features after this. P1s only if the P0 loop is rock solid |
| **H18–H21** | **Polish & harden** | Seeded demo data reset script; error states; loading states; UI polish; **record backup demo video** |
| **H21–H24** | **Pitch** | Deck final; 3 full rehearsals with a timer; Q&A prep; submit |

**Sleep plan:** stagger it. Never have everyone offline at once; keep at least 2 people awake per shift during H12–H20.

## 9. Communication
- One Discord/Slack channel plus a `#blockers` channel. Post a blocker within 20 minutes of being stuck.
- **Checkpoint standups** at H2, H6, H12, H16, H20: 5 minutes each covering done, next and blocked.
- `TASKS.md` is the source of truth: put your initials on a task when you start it and check it off when merged.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Bedrock model access not enabled | Request at H0; fall back to another available Bedrock model |
| Textract output messy | Bedrock normalize step plus a confidence threshold → `pending_review` UI |
| Integration hell late | Contracts at H2; vertical slice by H6; merge to `main` at least every 2 hours |
| Live demo fails | Seed reset script plus recorded backup video by H21 |
| Scope creep | Feature freeze at H16; P1/P2 are pitch-only unless P0 is done |
| AWS cost surprise | AWS Budgets alarm at $25; Textract on demo docs only |
| Judges ask "isn't this QuickBooks/Ramp?" | Advisor-specific wedge: payout reconciliation, practice valuation, records compliance, LPL Business Solutions integration |

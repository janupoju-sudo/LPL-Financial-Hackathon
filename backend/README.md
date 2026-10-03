# Ledgerline backend: API, workflows, ledger (role C)

## Operations dashboard and nine-vendor demo seed (E5/E7)

`template.yaml` includes an `OperationsDashboard` CloudWatch resource. The normal
SAM deployment creates it and exports `OperationsDashboardName` and
`OperationsDashboardUrl`. Its name includes the stack and region because
CloudWatch dashboards are account-global. It displays the last three hours of
HTTP API request/error/latency metrics, errors for every stack Lambda, key demo
Lambda invocation/duration metrics, ingest and approval execution outcomes and
duration, and DynamoDB read/write throttling. The body uses explicit stack
resource references and 48 existing service metric series. It does not enable
detailed API metrics, custom metrics, alarms, log queries, or CloudTrail.

No data can mean no recent traffic; it is not a health check. Approval execution
duration includes time waiting for a human. After the deployment owner updates
the stack, open the dashboard output URL and run the coordinated demo to see
real metrics. CloudTrail remains a separate part of E5; this change does not
complete that work.

`scripts/seed.py` now defines nine fictional vendors. It preserves the original
four workflow names and Brightline's initial missing-document state. The
compliance consultant matches the history seed, with four additional vendors
covering technology, payroll, office supplies and travel. Repeated runs add
missing vendors without changing existing vendor IDs, aliases, bank suffixes,
onboarding flags or bill counts; additional user-created vendors are retained.

For an existing demo practice, the live-account owner can coordinate and run:

```bash
cd backend
python scripts/seed.py --table ledgerline-dev --practice p1 --vendors-only
```

This command writes vendor rows in the selected practice only. It does not
rewrite META, rules, ledger history, documents or September payout data. A
normal seed without `--vendors-only` retains its existing META/rule behavior.
Do not run either against the shared AWS account without team coordination.

Local checks: `python -m unittest discover -s backend/tests -p test_seed_vendors.py`
and `python -m unittest discover -s backend/tests -p test_operations_dashboard.py`.
With backend development dependencies installed, also run `cfn-lint backend/template.yaml`.

Serverless on AWS: **API Gateway (HTTP API) + Lambda (Python 3.12) + DynamoDB + Step Functions + S3 Object Lock + EventBridge + Cognito**, all defined in `template.yaml` (AWS SAM).

## Deploy (from your Mac)

```bash
brew install aws-sam-cli awscli        # once
aws configure                          # region us-east-1
cd backend
sam build && sam deploy --guided       # first time; stack name ledgerline-dev
# sam build needs Python 3.12 on your Mac (brew install python@3.12) because src/requirements.txt
# installs the anthropic SDK; or use `sam build --use-container` with Docker running.
# When prompted for BedrockModelId, enter the exact model ID enabled for this account.
# Do not accept a default: the parameter is required for Ask and document classification.
python scripts/seed.py --table ledgerline-dev
python scripts/seed_ddb.py --table ledgerline-dev  # history through Aug 2026
# Before a live September demo, add normal September expenses only:
python scripts/seed_ddb.py --table ledgerline-dev --live-sept
# Only if the live payout upload failed and no September payout exists:
python scripts/seed_ddb.py --table ledgerline-dev --include-sept
python scripts/demo_users.py --user-pool-id <UserPoolId> --client-id <UserPoolClientId>
```
Stack outputs give you `ApiUrl`, `UserPoolId`, `UserPoolClientId`, `DocsBucketName`,
`CreateBillFunctionArn`, and `IngestDocumentStateMachineArn`.

The template includes B's ingest Lambda functions and upload EventBridge trigger. The
trigger starts the ingest state machine for new objects under `uploads/`; it does not
run for processing results written under `processing/`.

```bash
curl -H "Authorization: Bearer $TOKEN_OWNER" "$API/bills?status=pending_approval"
```

## Run tests (no AWS needed)

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
cfn-lint template.yaml
```

## Bill lifecycle

```
create_bill ─┬─ confidence < 0.8 or no vendor ──> pending_review ── POST /bills/{id}/confirm ──┐
             └─ otherwise ──────────────────────────────────────────────────────────────────────┤
                                                                                                 ▼
                         ┌──────────────── ApproveBill (Step Functions) ─────────────────────────┐
                         │ EvaluateRules ─┬─ auto_approve ─────────────────► PostLedger ─► SchedulePayment ─► LedgerUpdated
                         │                ├─ needs_approval ─► pending_approval ─ approve ─┘          (mock ACH)
                         │                ├─ on_hold ───────► pending_docs ─ docs arrive / received ─► EvaluateRules (loop)
                         │                └─ blocked ───────► rejected
                         └───────────────────────────────────────────────────────────────────────┘
```
Statuses: `pending_review · processing · pending_docs · pending_approval · approved · scheduled · rejected`

Default rules (seeded; editable at `/rules`):

| Rule | Action |
|---|---|
| Duplicate invoice (same vendor + invoice #) | **block** |
| Vendor missing W-9 or void check | **hold** (resumes automatically when docs arrive) |
| Amount > $1,000 | **require_approval** by `partner` (owner can always approve) |
| `requiresReceipt` and not received | **hold** until `POST /bills/{id}/receive` |

Controls: no self-approval (uploader ≠ approver), one decision per task token (atomic), full audit trail on every bill, idempotent ledger posting, Object Lock retention on every upload.

## API (all routes need `Authorization: Bearer <Cognito ID token>`)

All four Cognito roles can read the shared practice financials, bills and documents. Write access is role-based: owner has full access (but cannot approve a bill they uploaded); ops can upload, review low-confidence fields/documents, mark goods received and import card transactions; partner can decide bills routed to Partner; `lpl_bookkeeper` is read-only. Rule changes are owner-only.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/documents/upload-url` | `{filename, contentType}` (pdf/png/jpeg/tiff) | owner/ops; `{documentId, uploadUrl, s3Key, requiredHeaders}`: PUT the file to `uploadUrl` **with the same Content-Type** |
| GET | `/documents` | `?type=&q=` | `[{documentId, type, filename, status, vendorName, amount, billId, locked, createdAt}]` |
| GET | `/documents/{id}` | | full doc + `viewUrl` (presigned, 15 min) |
| POST | `/documents/{id}/resolve` | `{resolution: "dismiss" \| "accept", note?}` | owner/ops; closes a `needs_review` document: `dismiss` → `dismissed` (not a financial record; file stays in the library), `accept` → `processed`; records `review` + audit. 409 if not `needs_review`, already resolved, or it has a bill (use `/bills/{id}/confirm`). |
| GET | `/vendors` | | `[{vendorId, name, defaultGlAccount, hasW9, hasVoidCheck, bankLast4, billCount, bankDetailReviewRequired, possibleDuplicateVendorNames}]`; a last-four match is only a review candidate, not proof of a shared account |
| GET | `/bills` | `?status=pending_approval,pending_docs` | bill summaries (newest first), including `glAccountReason` when supplied by ingest |
| GET | `/bills/{id}` | | full bill incl. `glAccountReason`, `ruleHits`, `requiredApprovers`, `payment`, `audit[]` |
| POST | `/bills/{id}/decision` | `{decision: "approve"\|"reject", comment}` | owner or configured approver (Partner for partner-routed bills); uploader cannot approve; `{billId, status: "processing"}`; poll the bill for the final status |
| POST | `/bills/{id}/confirm` | `{amount?, vendorName?\|vendorId?, glAccount?, dueDate?, invoiceNumber?, invoiceDate?}` | owner/ops; confirms low-confidence fields and starts workflow |
| POST | `/bills/{id}/receive` | | owner/ops; marks received and resumes a held bill |
| GET | `/rules` | | rules (defaults seeded on first call) |
| POST | `/rules` | `{name, condition, action, approverRole?, priority?, reason?}` | owner only |
| PATCH | `/rules/{id}` | e.g. `{"enabled": false}` | owner only |
| POST | `/transactions/import` | raw CSV (`Content-Type: text/csv`): `Date, Description, Amount` (+ optional `Transaction ID`); sample in `scripts/sample_card_transactions.csv` | owner/ops; `{imported, alreadyImported, skipped, categorized, matchedReceipts, transactions[]}` with `categoryReason`; matches receipts on merchant + exact amount + date within 5 days; posts `j-card-<txnId>` (Dr expense / Cr 2100), idempotent |
| GET | `/financials` | `?period=2026-Q3` (or `2026-09`, `2026`) | `{period, pnl:{revenue, expenses, netIncome, monthly[6], categories, revenueLines, expenseLines}, balanceSheet:{assets, liabilities, equity, ...Lines}, cashFlow:{operating, investing, financing, net, ...}, kpis:{margin, recurringPct, revPerClient, expenseRatios, previous}, valuation:{low, mid, high, method, ...}}`; percentages 0–100, matching `frontend/lib/types.ts` (D) |
| GET | `/revenue/reconciliation` | `?period=2026-09` | `{period, expected, actual, variance, lines:[{id, label, source, ref, expected, actual, variance, status, docId, reason?}], flags:[{id, reason, docId, lineId, status, severity}]}`; `status` = ok/short/over/missing/unexpected (D) |
| POST | `/ask` | `{question}` | `{answer, citations:[{documentId, label, snippet}], period}` (D) |
| POST | `/export` | `{period}` | `{downloadUrl, documents, ledgerLines, missing}`; `downloadUrl` valid 15 min (D) |

Money in the API is **dollars**. Money in the ledger is **integer cents**.

## Role E demo seed modes

Run checks locally with `python scripts/seed_ddb.py --check --live-sept` or
`python scripts/seed_ddb.py --check --include-sept`; `--check` never calls AWS.
The live seed includes September's baseline operating expenses and payment
journals, but does not create September payout journals or `REV#2026-09#` rows.
That leaves the payout available for ingestion and reconciliation.

`--include-sept` is a separate fallback for a failed live upload. It adds the same
September baseline expenses plus the fictional $2,478 contract 4471 payment and
four revenue lines. Before writing fallback data, the script checks for existing
September `REV#` rows and payout journals; if either exists, it skips the fallback
payout. Never use fallback mode as the live-seed mode. The two flags are mutually
exclusive. Rent and compliance journals for July onward cite the lease amendment
and month-specific consultant invoice; legacy July/August aggregate expense rows
are detected and rejected rather than duplicated.

### Reset demo records (E9)

Pause uploads first and wait until all Step Functions executions for the selected
practice are terminal. The script also refuses to execute while bills are in
`processing`, `pending_approval`, `pending_docs`, or the intermediate `approved`
state; it does not cancel workflows.

Preview the selected practice before applying the reset:

```bash
cd backend
python scripts/reset_demo.py --table ledgerline-dev --practice p1
python scripts/reset_demo.py --table ledgerline-dev --practice p1 --execute
```

The default is read-only; mutations require the explicit `--execute`, `--table`,
and `--practice` arguments. The reset removes that practice's bills, uploaded
demo document records, ledger postings linked to those bills/documents, and all
September 2026 revenue-line records, including live/fallback payout entries. It
preserves META, rules, supporting `seed-sources/` document records, seeded
historical journals/revenue, and September baseline expense/payment journals.
Brightline's W-9/void-check flags are reset to missing and its demo bank suffix is
removed. The operation is practice-scoped and safe to repeat.

S3 objects are never deleted or overwritten; Object Lock retention remains in
force. Old uploads may remain in S3 without DynamoDB references. The reset does
not invoke `seed.py` or `seed_ddb.py`.

### One-time compliance migration for PR #28

A normal demo reset preserves seeded compliance entries and therefore does not
unblock PR #28 on a table populated by PR #27. Use the separate migration mode
to replace only the known combined July-September 2026 $5,650 compliance accruals
and payments with $3,100 base and $2,550 consultant accruals/payments. The consultant
entries cite that month's $2,550 invoice. Totals and all other ledger entries stay
unchanged; no reseed is required to complete this replacement.

After PR #28 and the reset PR are merged, the live-account owner pauses uploads
and confirms all ingest/approval executions are terminal, then reviews:

```bash
cd backend
python scripts/reset_demo.py --table ledgerline-dev --practice p1 --migrate-compliance
```

Only the live-account owner applies the reviewed migration by adding `--execute`.
The replacement is transactional per month and safe to resume. It rejects wrong
amounts, missing invoice metadata, mixed/partial journal layouts, older aggregate
expense layouts, and ledger changes after planning. It does not clear demo bills,
documents, payouts, rules, vendors, or S3 objects, and never invokes the seed.
The seed owner can subsequently rerun their usual seed/upload command; it will
skip the already-posted split journals. Use the normal reset mode separately for
rehearsals. The bill-status guard does not inspect Step Functions, so operator
confirmation that workflows have stopped is still required.

---

## Contract for B (Document AI / ingest)

1. **Uploads land at** `uploads/<practiceId>/<documentId>/<filename>` in `DocsBucketName`. The SAM template already routes S3 `Object Created` events under `uploads/` to `IngestDocument`; `LockDocumentFunction` also listens and applies Object Lock retention, so you don't need to handle either trigger.
2. **Update the document** as you go: `repo.update_document(practice_id, document_id, type="invoice", status="extracting"|"processed"|"needs_review", confidence=0.93, extracted={...})`. Types: `invoice · receipt · void_check · w9 · payout_statement · unknown`.
3. **Canonical normalized fields** (omitted optional values are `null`; invoice and receipt amounts are dollars, payout `actual` is integer cents):
   - Invoice / receipt: `{type, confidence, vendorConfidence, vendorName, amount, invoiceNumber, invoiceDate, dueDate, glAccount, lineItems:[{description, amount}]}`. Both confidences are 0–1; the bill uses the lower of overall and vendor confidence, so a vendor confidence below `0.8` routes to human review even when the total is clear.
   - W-9 / void check: `{type, confidence, vendorName, hasW9, hasVoidCheck, bankLast4}`. `hasW9` / `hasVoidCheck` are derived from the document type; `bankLast4` is the final four digits when present.
   - Payout statement: `{type, confidence, period, revenueLines:[{id, source, ref?, label, actual, docId}]}`. `source` is `advisory | commission | trail | other`; `ref` is present when a contract/product reference can be extracted.
4. **Invoices/receipts → invoke `CreateBillFunction`** (ARN in outputs; the SAM state machine policy already grants this invocation) with:
   ```json
   {"practiceId":"p1","documentId":"doc_..","vendorId":"ven_..","vendorName":"Orion Software LLC",
    "amount":1850.00,"invoiceNumber":"INV-2041","invoiceDate":"2026-09-28","dueDate":"2026-10-28",
    "glAccount":"6300","lineItems":[...],"confidence":0.93}
   ```
   Pass `vendorId` if your matcher found one, otherwise just `vendorName` (exact/alias match, else auto-create). The vendor's `defaultGlAccount` is used when you omit `glAccount`. Returns `{billId, status, isDuplicate}`.
5. **Vendor helpers** (`shared/repo.py`): `list_vendors`, `find_vendor_by_name`, `create_vendor`, `add_vendor_alias` (call this after a fuzzy match so next time it's exact; this is the "vendor memory").
6. **W-9 / void check →** `repo.record_vendor_docs(practice_id, vendor_id, has_w9=True, has_void_check=True, bank_last4="6789", document_id=doc_id)`. This emits `VendorUpdated`, and any bills on hold for that vendor resume automatically. Both documents are required by the default vendor-doc rule; a bill remains held until both flags are true.
7. **Payout statements** save actual payout lines and post the extracted totals to the ledger. The $412 expected-vs-actual shortfall is flagged by D's reconciliation endpoint; B does not create a separate ingest review item solely for a shortfall.

## Contract for D (Financials), agreed format

- **Ledger lines**: one item per line, `SK = LEDGER#<yyyy-mm>#<journalId>#<lineNo>`, fields `journalId, lineNo, date, account, debit, credit (int cents), sourceDocId, memo, sourceType, sourceId`. Journals are written atomically and must balance (`shared/ledger.py`).
- **Read**: `ddb.get_ledger_entries(practice_id, start_date, end_date)` returns lines with int cents, sorted. `ddb.get_practice(practice_id)` returns META with `clientCount`, `top10Share`, `aum`, `name` (seeded by `scripts/seed.py`).
- **What the workflow posts**: bill approved `j-<billId>-accrual` (Dr `glAccount` / Cr 2000); mock payment `j-<billId>-payment` (Dr 2000 / Cr 1000). `sourceDocId` = the bill's documentId.
- **Payouts**: `ledger.post_journal(p, f"j-payout-{doc_id}", date, ledger.payout_lines({"advisory": 41000, "commission": 3200.5, "trail": 1875.25}), memo, source_doc_id=doc_id)`. Card spend: `ledger.card_spend_lines(amount, "6700")`.
- **Revenue lines (D4)**: ingest (B) stores payout statement lines with `repo.put_revenue_lines(p, "2026-09", doc_id, [{"source": "trail", "ref": "4471", "label": "...", "actual": 247800}])` (`actual` in int cents; ids derived from `doc_id`, so re-ingesting overwrites). Financials reads them with `ddb.get_revenue_lines(p, "2026-09")` (also accepts `2026-Q3` / `2026`).
- **Fee schedule**: lives on the practice META item as `feeSchedule` (amounts/aum in int cents, `annualRate` as a fraction) and comes back from `ddb.get_practice(p)`. `scripts/seed.py` writes a sample one; E may replace it.
- **COA** is in `shared/coa.py` (your codes). `Bill.glAccount` is validated as 6xxx.
- **`/financials` route**: once your code is under `src/financials/`, Jay adds `FinancialsFunction` to `template.yaml` (he owns that file, so send him anything else you need). The `LedgerUpdated` event on the `ledgerline-<stage>` bus fires after every posting if you want to cache.

**D's code** is in `src/financials` (statements, KPIs, valuation, reconciliation), `src/ask` (Claude on Bedrock + guardrail) and `src/export`. Its AWS resources (3 functions, `ExportsBucket`, the Bedrock Guardrail) are in `infra/d-resources.yaml`, ready to paste into `template.yaml`. `python3 dev_server.py` serves D's four routes on localhost:8787 from sample data, no AWS needed. After deploy: `GUARDRAIL_ID=... GUARDRAIL_VERSION=1 python3 scripts/check_guardrail.py`.

## Contract for A (Frontend)

- Log in with Cognito (`UserPoolId`, `UserPoolClientId`); send the **ID token** as `Authorization: Bearer ...`. Role = Cognito group (`owner`, `partner`, `ops`, `lpl_bookkeeper`) for the role switcher.
- Upload = `POST /documents/upload-url` → `PUT uploadUrl` with `Content-Type` → poll `GET /documents/{id}` until `billId` appears.
- After `POST /bills/{id}/decision`, the status is `processing` for about a second, then `scheduled`/`rejected`. Poll `GET /bills/{id}`.
- Show `ruleHits[].reason` as the "why it was routed" chips, `glAccountReason` beside the category, and `audit[]` in the side drawer.

## Events (bus `ledgerline-<stage>`)
`VendorUpdated` · `BillAwaitingAction` · `BillRejected` · `LedgerUpdated`

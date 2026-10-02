# Ledgerline backend: API, workflows, ledger (role C)

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
python scripts/seed_ddb.py --table ledgerline-dev  # 12 months of history; leaves Sep 2026 for the live demo
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

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/documents/upload-url` | `{filename, contentType}` (pdf/png/jpeg/tiff) | `{documentId, uploadUrl, s3Key, requiredHeaders}`: PUT the file to `uploadUrl` **with the same Content-Type** |
| GET | `/documents` | `?type=&q=` | `[{documentId, type, filename, status, vendorName, amount, billId, locked, createdAt}]` |
| GET | `/documents/{id}` | | full doc + `viewUrl` (presigned, 15 min) |
| GET | `/vendors` | | `[{vendorId, name, defaultGlAccount, hasW9, hasVoidCheck, bankLast4, billCount}]` |
| GET | `/bills` | `?status=pending_approval,pending_docs` | bill summaries (newest first) |
| GET | `/bills/{id}` | | full bill incl. `ruleHits`, `requiredApprovers`, `payment`, `audit[]` |
| POST | `/bills/{id}/decision` | `{decision: "approve"\|"reject", comment}` | `{billId, status: "processing"}`; poll the bill for the final status |
| POST | `/bills/{id}/confirm` | `{amount?, vendorName?\|vendorId?, glAccount?, dueDate?, invoiceNumber?, invoiceDate?}` | starts workflow |
| POST | `/bills/{id}/receive` | | marks received, resumes a held bill |
| GET | `/rules` | | rules (defaults seeded on first call) |
| POST | `/rules` | `{name, condition, action, approverRole?, priority?, reason?}` | owner only |
| PATCH | `/rules/{id}` | e.g. `{"enabled": false}` | owner only |
| GET | `/financials` | `?period=2026-Q3` (or `2026-09`, `2026`) | `{period, pnl:{revenue, expenses, netIncome, monthly[6], categories, revenueLines, expenseLines}, balanceSheet:{assets, liabilities, equity, ...Lines}, cashFlow:{operating, investing, financing, net, ...}, kpis:{margin, recurringPct, revPerClient, expenseRatios, previous}, valuation:{low, mid, high, method, ...}}`; percentages 0–100, matching `frontend/lib/types.ts` (D) |
| GET | `/revenue/reconciliation` | `?period=2026-09` | `{period, expected, actual, variance, lines:[{id, label, source, ref, expected, actual, variance, status, docId, reason?}], flags:[{id, reason, docId, lineId, status, severity}]}`; `status` = ok/short/over/missing/unexpected (D) |
| POST | `/ask` | `{question}` | `{answer, citations:[{documentId, label, snippet}], period}` (D) |
| POST | `/export` | `{period}` | `{downloadUrl, documents, ledgerLines, missing}`; `downloadUrl` valid 15 min (D) |

Money in the API is **dollars**. Money in the ledger is **integer cents**.

---

## Contract for B (Document AI / ingest)

1. **Uploads land at** `uploads/<practiceId>/<documentId>/<filename>` in `DocsBucketName`. The SAM template already routes S3 `Object Created` events under `uploads/` to `IngestDocument`; `LockDocumentFunction` also listens and applies Object Lock retention, so you don't need to handle either trigger.
2. **Update the document** as you go: `repo.update_document(practice_id, document_id, type="invoice", status="extracting"|"processed"|"needs_review", confidence=0.93, extracted={...})`. Types: `invoice · receipt · void_check · w9 · payout_statement · unknown`.
3. **Invoices/receipts → invoke `CreateBillFunction`** (ARN in outputs; the SAM state machine policy already grants this invocation) with:
   ```json
   {"practiceId":"p1","documentId":"doc_..","vendorId":"ven_..","vendorName":"Orion Software LLC",
    "amount":1850.00,"invoiceNumber":"INV-2041","invoiceDate":"2026-09-28","dueDate":"2026-10-28",
    "glAccount":"6300","lineItems":[...],"confidence":0.93}
   ```
   Pass `vendorId` if your matcher found one, otherwise just `vendorName` (exact/alias match, else auto-create). The vendor's `defaultGlAccount` is used when you omit `glAccount`. Returns `{billId, status, isDuplicate}`.
4. **Vendor helpers** (`shared/repo.py`): `list_vendors`, `find_vendor_by_name`, `create_vendor`, `add_vendor_alias` (call this after a fuzzy match so next time it's exact; this is the "vendor memory").
5. **W-9 / void check →** `repo.record_vendor_docs(practice_id, vendor_id, has_w9=True, has_void_check=True, bank_last4="6789", document_id=doc_id)`. This emits `VendorUpdated`, and any bills on hold for that vendor resume automatically.

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
- Show `ruleHits[].reason` as the "why it was routed" chips, and `audit[]` in the side drawer.

## Events (bus `ledgerline-<stage>`)
`VendorUpdated` · `BillAwaitingAction` · `BillRejected` · `LedgerUpdated`

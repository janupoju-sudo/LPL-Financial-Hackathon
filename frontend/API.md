# Frontend API contract

Fixtures live in `mocks/*.json`; TypeScript types are in `lib/types.ts`. IDs are encoded in URLs. Live requests carry `Authorization: Bearer <Cognito ID token>` per C's frontend handoff. Amounts use dollars; margin, recurring revenue and expense ratios use 0–1 (nullable when their denominator is unavailable). Dates use ISO strings. Errors should return a non-2xx status and a readable message.

| Method | Endpoint | Request | Response |
| --- | --- | --- | --- |
| POST | `/documents/upload-url` | `{filename, contentType}` | `{documentId, uploadUrl}` |
| PUT | Presigned upload URL | Raw file, matching Content-Type | Success status |
| GET | `/documents` | — | `Document[]` (list metadata) |
| GET | `/documents/{id}` | — | `Document` with `confidence`, `extracted`, `viewUrl`, optional `billId` |
| GET | `/bills` | — | `Bill[]` with string `ruleHits[]`; optional `docId` for source links |
| POST | `/bills/{id}/decision` | `{decision: "approve" \| "reject", comment}` | `{id, status}` |
| GET | `/vendors` | — | `Vendor[]` |
| GET | `/rules` | — | `Rule[]` |
| POST | `/rules` | `{name, condition:{field,op,value}, action, approverRole}` | `Rule[]` |
| GET | `/financials?period=2026-Q3` | — | `Financials` |
| GET | `/revenue/reconciliation?period=2026-09` | — | `Reconciliation` |
| POST | `/ask` | `{question}` | `{answer, citations:[{documentId,label,snippet}], period}` |
| POST | `/export` | `{period}` | `{downloadUrl, documents, ledgerLines, missing}` for a ZIP; counts are numbers, `missing` is a filename array |
| POST | `/transactions/import` | Raw CSV, `Content-Type: text/csv` | `{imported,categorized,matchedReceipts}` |

The canonical financials contract matches D's supplied handoff (PRs #1 and #2):

- Top-level `period`.
- `pnl:{period,revenue,totalRevenue,expenses,totalExpenses,operatingIncome}`; revenue and expense lines are `{account,name,amount}` arrays.
- `balanceSheet:{asOf,assets,totalAssets,liabilities,totalLiabilities,equity,totalEquity}`; sections are account-line arrays, with a nullable account for earnings.
- `cashFlow:{period,beginningCash,operating,netOperating,financing,netFinancing,netChange,endingCash}`; activity lines are `{label,amount}` arrays.
- `kpis:{margin,recurringPct,revPerClient,expenseRatios:[{account,name,ratio}],previous:{period,totalRevenue,margin,recurringPct}}`.
- `valuation:{low,mid,high,method,recurringRevenueTtm,multiples:{low,mid,high}}`; `method` is the tooltip text.

The P&L chart shows the selected period's totals. D's endpoint does not return a monthly trend; the frontend does not fabricate one.

Current main subsequently adopted the earlier frontend shape: numeric statement totals, `*Lines` arrays, 0–100 percentages and flag `reason` rather than `message`. `lib/contracts.ts` converts that response into the canonical shape above. Percentage conversion is selected by the P&L shape, not by testing whether a value exceeds 1, so 0.5% is handled correctly. Dollar values and valuation metadata are preserved. Current main supplies optional monthly history; this view still displays the canonical period totals.

Reconciliation is `{period,expected,actual,variance,lines,flags}`. Lines have `{id,label,source,ref,expected,actual,variance,status,docId,reason?}`. Status is `ok | short | over | missing | unexpected`. `ref` and `docId` may be null. Flags have `{lineId,status,severity,message}`; the source document is resolved through the line with matching `id`. Missing sources display a message instead of an invalid document link.

Polling recognizes document statuses `processed`, `completed`, `ready`, `pending_review`, `pending_approval` as complete, and `failed`/`error` as failure. It polls every 2 seconds for 60 attempts; a timeout tells the user to check the Library. The frontend refreshes practice data after upload and decisions; ledger recomputation should be available when the decision response returns.

The backend must enforce role authorization, approval eligibility and required vendor documents. Owner/Partner selection in mock mode is a demonstration tool and is not sent as a live authorization claim. Mock rule evaluation, AI extraction, payment, valuation and chat are illustrative. Remaining C integration work (structured rule hits, held/review statuses, confirm/receive actions and asynchronous decision polling) is described in `docs/handoffs/A-frontend.md` and should be handled in a separate frontend task.

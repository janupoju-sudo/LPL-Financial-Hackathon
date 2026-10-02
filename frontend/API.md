# Frontend API contract

Fixtures live in `mocks/*.json`; TypeScript types are in `lib/types.ts`. IDs are encoded in URLs. Live requests carry `Authorization: Bearer <Cognito access token>`. Amounts use dollars, percentages use 0–100, dates use ISO strings. Errors should return a non-2xx status and a readable message.

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
| POST | `/ask` | `{question}` | `{answer, citations:[{documentId,label,snippet}]}` |
| POST | `/export` | `{period}` | `{downloadUrl}` for a ZIP |
| POST | `/transactions/import` | Raw CSV, `Content-Type: text/csv` | `{imported,categorized,matchedReceipts}` |

Financial statement substructures were unspecified in the supplied plan. The fixtures define the proposed contract: `pnl:{revenue,expenses,netIncome,monthly:[{month,revenue,expenses}],categories:[{name,amount}]}`, `balanceSheet:{assets,liabilities,equity}`, `cashFlow:{operating,investing,financing,net}`, `kpis:{margin,recurringPct,revPerClient}`, `valuation:{low,mid,high,method}`. Reconciliation `lines` have `{id,source,label,expected,actual,variance,docId}`; `flags` have `{id,reason,docId}`. Backend teams should align these fields before switching modes.

Polling recognizes document statuses `processed`, `completed`, `ready`, `pending_review`, `pending_approval` as complete, and `failed`/`error` as failure. It polls every 2 seconds for 60 attempts; a timeout tells the user to check the Library. The frontend refreshes practice data after upload and decisions; ledger recomputation should be available when the decision response returns.

The backend must enforce role authorization, approval eligibility and required vendor documents. Owner/Partner selection in mock mode is a demonstration tool and is not sent as a live authorization claim. Mock rule evaluation, AI extraction, payment, valuation and chat are illustrative. Real extraction review/editing needs an agreed write endpoint.

# Handoff → A (Frontend)

The backend for the core loop is built and tested: upload → bill → rules → approval → ledger → mock payment. Keep building against your mocks until Jay deploys, then switch `NEXT_PUBLIC_USE_MOCKS=false`. **The response shapes match PLAN.md §5**, with a few extra fields.

## 1. Connect
**Ownership:** Role E owns connecting and administering Amplify Hosting (E2), as assigned in [E's handoff](E-infra-data-pitch.md). Akshaya (A) owns the frontend environment configuration, build and deployed UI validation (A11). Jay owns the SAM stack and supplies its outputs. The repository connection is still unconfirmed until E provides the Amplify app/URL.

- `NEXT_PUBLIC_API_URL` = `ApiUrl` from the [deploy outputs](README.md)
- Cognito: `UserPoolId` + `UserPoolClientId` (Amplify UI `<Authenticator>` works)
- Live environment: `NEXT_PUBLIC_USE_MOCKS=false` and `NEXT_PUBLIC_LOCAL_API=false`. Apply the three stack output values to `frontend/.env.local` for local testing and to the Amplify app's build environment. Restart/rebuild after changing public environment variables; deployed bundles embed them at build time.
- Every request: `Authorization: Bearer <ID token>` (ID token, not access token)
- Role = Cognito group, from `cognito:groups` in the ID token: `owner` · `partner` · `ops` · `lpl_bookkeeper`

**Demo logins** (password `Demo!2345`, demo pool only):

| Who | Email | Role | Use in demo |
|---|---|---|---|
| Maya | maya@harborpoint.example | owner | Dashboard, uploads, can approve anything |
| Raj | raj@harborpoint.example | partner | Approves bills over $1,000 |
| Dev | dev@harborpoint.example | ops | Uploads and reviews; **can't approve** |
| Priya | priya@lpl-demo.example | lpl_bookkeeper | Optional LPL view |

**Role switcher tip:** keep two sessions (Maya + Raj) and swap tokens. Logging out mid-demo is slow.

## 2. Upload flow (Inbox page)
1. `POST /documents/upload-url` `{filename, contentType}` → `{documentId, uploadUrl, requiredHeaders}`
2. `PUT uploadUrl` with the file body and **exactly** `Content-Type: <same contentType>`. Otherwise S3 rejects the signature.
3. Poll `GET /documents/{documentId}` every ~1.5s. Show `status` (`uploaded → extracting → processed / needs_review`) until `billId` appears, then link to the bill.

Allowed types: `application/pdf`, `image/png`, `image/jpeg`, `image/tiff`.

## 3. Bills & approvals
| Status | Show as | Tab |
|---|---|---|
| `pending_review` | Needs review (low-confidence extraction) | Needs Review |
| `processing` | Spinner (workflow running, ~1s) | — |
| `pending_docs` | On hold | Pending |
| `pending_approval` | Waiting for approval | Pending Approval |
| `approved` | Approved | — |
| `scheduled` | Scheduled (mock ACH) | Scheduled |
| `rejected` | Rejected (show `rejectionReason`) | — |

- **Why it was routed:** render `ruleHits[].reason` as chips ("Amount is over $1,000", "Vendor is missing a W-9 or void check").
- **Who can approve:** `requiredApprovers` (owner can always approve). Hide or disable the button for others. The API also enforces it.
- **Approve/Reject:** `POST /bills/{id}/decision` `{decision, comment}` → `processing`. Poll `GET /bills/{id}` until `scheduled` or `rejected`.
- **Errors to handle nicely:** `403` (wrong role, or approving a bill you uploaded, i.e. segregation of duties: a good demo line), `409` (someone already decided).
- **Audit drawer:** `audit[]` = `{at, actor, action, detail}`, oldest first.
- **Needs Review form:** `POST /bills/{id}/confirm` with any corrected fields: `amount, vendorName | vendorId, glAccount (6xxx), dueDate, invoiceNumber, invoiceDate`.
- **Received button** (for held bills): `POST /bills/{id}/receive`.
- `payment` on a scheduled bill: `{method: "ACH (mock)", scheduledFor, confirmation, bankLast4}`.

## 4. Other pages
- **Library:** `GET /documents?type=&q=`; `GET /documents/{id}` returns `viewUrl` (PDF preview, valid 15 min) and `locked: true` once Object Lock is applied. Show a 🔒 badge, judges like it.
- **Vendors tab:** `GET /vendors`. Show W-9 / void check ✓/✗ and `billCount` ("Recognized vendor" = `billCount > 1`).
- **Rules (P1):** `GET /rules`; owner can `POST /rules` and `PATCH /rules/{id}` `{"enabled": false}`.
- **Dashboard / Revenue / Ask / Export:** these come from D (`/financials`, reconciliation, ask, export), not from these endpoints.

## 5. Money
API amounts are **dollars** (numbers like `1850.0`). Format with `Intl.NumberFormat("en-US", {style: "currency", currency: "USD"})`.

**Questions or blockers →** ping Jay with the request and the response body.

**Demo naming:** the new marketing vendor is **Brightline Marketing**, matching `backend/scripts/seed.py`. Frontend mock invoices, bills, citations and vendor-document upload filenames use Brightline (`brightline-w9.pdf`, `brightline-void-check.pdf`).

# Ledgerline

The AI back office for independent advisor practices. The frontend runs against fictional Harbor Point Wealth fixtures by default.

## Run locally

Requires Node.js 20.9+ and npm.

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:3000. On Windows, `npm.cmd` avoids PowerShell execution-policy restrictions on `npm.ps1`.

## Frontend scope (Task A)

- Next.js App Router, TypeScript, Tailwind, shadcn-compatible Button, Recharts, responsive sidebar.
- Typed API client and contract fixtures in `frontend/mocks/`.
- Upload dropzone, presigned S3 PUT, bounded status polling, PDF/image preview, extracted fields, confidence and recognized-vendor badges.
- Bills with status filters, rule reasons, Owner/Partner decisions and financial refresh.
- Dashboard KPIs, P&L chart, balance sheet and cash flow tabs, transparent valuation estimate.
- Revenue reconciliation and source links; Ask chat with clickable document citations.
- Library search and type/vendor/date filters, vendor memory, downloadable ZIP export.
- Cognito Amplify Authenticator in live mode; demo role switcher in mock mode.
- Rules list and creation, loading skeletons, empty states, notifications; CSV import wired to the live endpoint.
- Amplify Hosting build configuration in `amplify.yml`.

## Demo flow

1. Inbox → upload a PDF invoice. Mock mode uses Advent sample fields; it retains the uploaded file for preview and does not perform actual AI extraction.
2. Switch to Partner view → approve Advent's bill. Its status changes to Scheduled (simulated payment) and the dashboard updates.
3. Brightline's bill is blocked until both a file named `brightline-w9.pdf` and a file named `brightline-void-check.pdf` have been uploaded. Mock mode assigns these documents to Brightline. Then approve the bill.
4. Revenue → inspect the seeded $412 trail shortfall; click the statement.
5. Dashboard → view statements and estimated valuation. Ask → use the Q3 margin suggestion and open citations.
6. Library → export a ZIP with documents, `ledger.csv`, and `financials.json`.

Demo state is in browser memory and resets on reload. The fixture financial period is Q3 2026; reconciliation is September 2026. Mock chat uses a fixed answer. Mock rule creation stores rules for display; the simulated workflow uses predefined rules. Demo export includes the full demo library and scheduled-bill ledger entries, with seeded financial history clearly identified. Low-confidence fields are displayed for Ops review; saving corrections requires a backend document-update contract, which was not supplied.

## Connect the backend

Copy `frontend/.env.example` to `frontend/.env.local`, set the API URL and Cognito pool/client IDs, and set `NEXT_PUBLIC_USE_MOCKS=false`. Restart the dev server. Live mode requires sign-in and uses the Cognito access token; the demo role switcher is disabled. Authorization must be enforced by the backend; hiding buttons is only a UI convenience.

Endpoint paths and request/response types are documented in [frontend/API.md](frontend/API.md). Provide CORS on API Gateway and the upload bucket for your frontend origin and the presigned PUT Content-Type header. Document detail must return a browser-readable presigned `viewUrl`. Set the Cognito app client to a public client without a client secret.

## Deploy

Task E must provision Amplify Hosting, Cognito and API Gateway. Connect this repository in Amplify, select monorepo app root `frontend`, and use the root `amplify.yml`. Configure the `NEXT_PUBLIC_*` environment variables in Amplify before building; they are embedded during build. Redeploy after changing them. No AWS deployment has been performed by this implementation.

## Verify

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

Regenerate watermarked seed PDFs with `node scripts/generate-samples.mjs`.

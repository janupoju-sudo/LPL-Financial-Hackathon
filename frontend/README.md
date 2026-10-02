# Ledgerline frontend

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:3000. Mock mode is enabled by default. The role switcher is for demo sessions only. Copy `.env.example` to `.env.local`, set the API and Cognito values, and set `NEXT_PUBLIC_USE_MOCKS=false` to use AWS.

## D's local endpoints (no AWS)

The dev server is already in main; switching to D's branch is unnecessary. Install its Python dependencies and start it from the repo root:

```powershell
python -m venv frontend/.venv
frontend/.venv/Scripts/python.exe -m pip install boto3
frontend/.venv/Scripts/python.exe backend/dev_server.py
```

Configure `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_USE_MOCKS=false
NEXT_PUBLIC_LOCAL_API=true
NEXT_PUBLIC_API_URL=http://localhost:8787
```

Start or restart the frontend with `npm.cmd run dev`. Dashboard, Revenue, Ask and Export now call D's real Python handlers on sample data, without a Cognito session. Local API mode accepts loopback hosts only. Uploads, approvals, vendor data and rules are unavailable; source metadata comes from D's fixture list, and no source previews are claimed. Unknown citation IDs report that their source is unavailable. The local Ask answer is canned unless the backend's `USE_BEDROCK=1` is set. Run `npm.cmd run test:local` with the Python server running to verify all four endpoints and the ZIP download.

Set `NEXT_PUBLIC_LOCAL_API=false` when connecting AWS so normal Cognito authentication applies. Set `NEXT_PUBLIC_USE_MOCKS=true` and `NEXT_PUBLIC_LOCAL_API=false` to return to the fully simulated demo.

API response shapes are documented in [API.md](API.md). D's financials, reconciliation, Ask and export responses match PRs #1 and #2, now under `backend/src/`. All money is in dollars; percentages are ratios from 0–1, rendered as percentages in the UI. Nullable KPIs display a dash.

P&L charts use selected-period totals. Balance sheet and cash flow tabs display account/activity arrays and totals. Reconciliation flags resolve source documents through `lineId`; missing payouts with no `docId` display a message. Export notifications show document/ledger counts and missing filenames. `lib/contracts.ts` also supports current main's subsequent switch to numeric statement totals, percentage points, and flag `reason` fields, while retaining the supplied canonical contract in mocks and UI types.

Mock extraction and chat use sample fields and context. Uploads retain your file for preview. Invoice approval updates the demo financials. A W-9 and void check with filenames containing `northstar-w9` and `northstar-void-check` unblock the Northstar demo bill. Mock state resets on reload. Newly created demo rules are displayed; the sample workflow uses predefined rules. CSV import requires a live endpoint. The export is a ZIP of the demo library, scheduled-bill ledger entries and seeded financials; missing files are reported.

Live requests use Cognito ID tokens per C's handoff. Remaining C integration work includes structured rule hits, `pending_docs`/`processing` statuses, confirm/receive actions and decision polling; see `docs/handoffs/A-frontend.md`. The frontend scaffolding and D contract integration are ready for review; the entire live workflow still needs this separate integration work and E's deployment.

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run typecheck
```

Run build and typecheck sequentially: Next regenerates `.next/types` during build. Sample PDFs can be regenerated using `node scripts/generate-samples.mjs`.

For Amplify Hosting, E should set app root `frontend`, use `npm ci` before `npm run build`, and publish `.next`. Environment values must be configured before the build. No AWS infrastructure is changed by this frontend branch.

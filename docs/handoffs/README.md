# Handoffs from C (Backend & Workflows)

Branch: `C/Backend-and-Workflows` · Full API + contracts: [`backend/README.md`](../../backend/README.md)

| Teammate | Doc | What they need from the backend |
|---|---|---|
| A: Frontend | [A-frontend.md](A-frontend.md) | API URL, login, endpoints, statuses, polling |
| B: Document AI | [B-document-ai.md](B-document-ai.md) | Where uploads land, how to create bills, vendor memory, payouts |
| D: Financials | [D-financials.md](D-financials.md) | Ledger format, read helpers, folder move, `/financials` route |
| E: Infra, Data & Pitch | [E-infra-data-pitch.md](E-infra-data-pitch.md) | What's already built, seeding, demo users, AWS talking points |

**One rule for everyone:** Jay owns `backend/template.yaml`. Send him the resources you need added instead of editing it, so we don't fight merge conflicts on the one file everyone touches.

**Deploy outputs** (Jay fills these in after `sam deploy`):

| Output | Value |
|---|---|
| `ApiUrl` | `https://ftvp1nm03k.execute-api.us-east-1.amazonaws.com` |
| `UserPoolId` | `us-east-1_2xeTJpaCX` |
| `UserPoolClientId` | `o0p82o95ae8t9mspf1dkd335o` |
| `DocsBucketName` | `_pending_` |
| `TableName` | `ledgerline-dev` |
| `CreateBillFunctionArn` | `_pending_` |
| `EventBusName` | `ledgerline-dev` |

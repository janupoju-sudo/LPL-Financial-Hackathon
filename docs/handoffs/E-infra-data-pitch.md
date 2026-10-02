# Handoff → E (Infra, Data & Pitch)

**Good news: a lot of your infra list is already built** in `backend/template.yaml`. Skip those and put the time into demo data and the pitch.

## Already built (don't rebuild)
| TASKS.md | Status | Notes |
|---|---|---|
| E1 SAM skeleton | ✅ Done | One stack: `ledgerline-<stage>`. Jay deploys it |
| E3 S3 Object Lock bucket + EventBridge | ✅ Done | Every upload gets GOVERNANCE retention automatically (`RetentionDays`, default 1 day) |
| E4 Cognito + groups + demo users | ✅ Done | Groups `owner, partner, ops, lpl_bookkeeper`; `scripts/demo_users.py` creates the 4 demo logins |
| E7 (part) base seed | ✅ Done | `scripts/seed.py`: practice META, fee schedule, 4 vendors, default rules |
| E2 Amplify Hosting | ⬜ Yours | Connect repo `frontend/` |
| E5 CloudTrail + CloudWatch dashboard | ⬜ Yours | Not in the template yet; send Jay a snippet or set up in console |
| AWS Budgets alarm ($25) | ⬜ Yours | Console is fine |

**Template rule:** Jay owns `template.yaml`. Send him anything you need added.

## Seed data you build on
`scripts/seed.py` writes this. Keep names consistent in your demo PDFs:

| Vendor | GL | W-9 / void check | Demo role |
|---|---|---|---|
| Orion Software LLC | 6300 Technology | ✅ / ✅ (bank …4821) | **Vendor memory**: two invoices, one $450 (auto-approves) and one $1,850 (needs Raj) |
| Seaport Office Partners | 6200 Rent | ✅ / ✅ | Rent history |
| LPL Financial | 6400 Platform fees | ✅ / ✅ | Platform fee history |
| Brightline Marketing | 6500 Marketing | ❌ / ❌ | **New vendor**: invoice goes on hold → upload W-9 + void check → un-blocks |

Practice META: Harbor Point Wealth (fictional), 180 clients, top-10 share 22%, `feeSchedule` (cents). Your E8 payout PDF should underpay the **VA trail, contract …4471** so reconciliation flags it.

**Ledger history (E7):** write journals with `ledger.post_journal(...)` so they're balanced and in D's format. See `backend/README.md` → "Contract for D". Use integer cents via the line helpers (`bill_accrual_lines`, `payout_lines`, …).

## Demo reset (E9)
- Object Lock means the stored version of each upload **can't be permanently removed or overwritten for `RetentionDays`**. That's the point (books and records). For resets, **delete DynamoDB items and leave S3 alone**. Old files just sit there, unreferenced.
- Reset = delete `BILL#`, `DOC#`, `LEDGER#`, `REV#` items under `PRACTICE#p1`, re-run `seed.py` + your history seed. Leave `RULE#` and `VENDOR#` (or reset vendors' `hasW9/hasVoidCheck` for Brightline).

## Talking points for the deck (verified in code)
- **Right AWS service for the job:** Step Functions `waitForTaskToken` = native human approval; EventBridge decouples "W-9 arrived" from "un-hold the bill"; S3 Object Lock = tamper-proof books and records; DynamoDB transactions = a journal can never be half-written.
- **Controls a compliance team would ask for:** segregation of duties (uploader can't approve), one decision per approval (atomic), full audit trail per bill, duplicate-invoice blocking, every AI extraction below 80% confidence goes to a human.
- **Cost-aware:** fully serverless and pay-per-request. Idle cost ≈ $0.
- **Screenshot to grab:** a Step Functions execution graph of a bill going EvaluateRules → WaitForApproval → PostLedger → SchedulePayment.

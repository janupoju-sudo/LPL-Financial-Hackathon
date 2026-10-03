# Ledgerline — Product Requirements Document

> **The AI back office for independent advisor practices.**
> Payables, receivables, cards, documents, and live financial statements in one place, built for how advisors actually earn money.

LPL Financial University Hackathon · Theme: *Startup from the Future: Build the Startup LPL Would Want to Buy*
Target categories: **Startup We'd Buy Tomorrow** + **Biggest Business Impact** (plus automatic **Best Use of AWS**)

---

## 1. Problem

LPL supports 32,000+ independent advisors. Each one runs a small business, with staff, rent, software, marketing, LPL platform fees, quarterly advisory-fee revenue and commission payouts.

Advisors are excellent at managing *clients'* money and usually poor at managing their *own* practice's finances:

- **Scattered tools.** Invoices sit in email, receipts in phones, statements in bank portals, books in QuickBooks, files in SharePoint or Dropbox. Nothing is connected.
- **Manual approvals.** One person pays every bill. There are no rules, no audit trail, and no "only pay once received" checks.
- **Unreconciled revenue.** Commission and advisory payouts are hard to check against what *should* have been paid, so missing trails go unnoticed.
- **No idea what the practice is worth.** When an advisor wants a loan, a succession deal or to sell, it takes months to clean up the books before anyone can value the practice.

**LPL already sells a fix for this, delivered by people.** It offers Bookkeeping Services (industry-trained bookkeepers working from commission statements) and CFO Solutions (business specialists for benchmarking, succession and capital). Both need people and don't scale to 32,000 practices.

## 2. Solution

Ledgerline is an AI-native practice finance platform:

1. **Smart document library.** Drop in any invoice, receipt, void check, W-9 or LPL payout statement. The AI classifies it, extracts it, remembers the vendor and pre-fills everything. Every file is stored tamper-proof and can be exported anytime.
2. **Payables with approval workflows.** No-code rules such as "> $1,000 needs the senior partner", "new vendor requires a W-9 and void check first" and "pay only after marked received". Approvals happen in one tap.
3. **Revenue reconciliation.** Commission and advisory payouts are matched against expected revenue, and gaps are flagged automatically.
4. **Live financial statements.** P&L, balance sheet and cash flow update as documents arrive.
5. **Practice health and valuation.** Recurring revenue %, operating margin, revenue per client, and an estimated practice value, always ready for succession or lending conversations.
6. **Ask your books.** Plain-English Q&A ("Why did my margin drop in Q3?") with citations to the underlying documents.

**It builds advisors up instead of replacing them.** Ledgerline gives every advisor CFO-level insight into their own business. LPL's human bookkeepers and CFO specialists handle the exceptions, so they can serve 10x more practices.

## 3. Users

| Persona | Description | Core job-to-be-done |
|---|---|---|
| **Maya — Lead Advisor / Owner** | Runs a 4-person practice, about $250M AUM | "When I'm planning my next 5 years, I want to know what my practice earns and is worth, so I can hire, borrow or plan succession with confidence." |
| **Dev — Operations Associate** | Handles bills, vendors and filing | "When an invoice arrives, I want it entered, routed and filed automatically, so I stop chasing approvals and paperwork." |
| **Priya — LPL Bookkeeper / CFO Specialist** | Serves dozens of practices | "When I review a practice, I want clean, categorized books with exceptions flagged, so I spend my time on advice, not data entry." |

## 4. Why LPL acquires Ledgerline (the pitch)

1. **It scales an existing revenue line.** Bookkeeping and CFO Solutions become software-led, with people handling the exceptions. Same headcount, many more advisors served.
2. **Faster succession and lending.** LPL puts capital into liquidity and succession deals every quarter. Always-clean books mean practices can be valued in days instead of months.
3. **Retention.** An advisor whose entire back office runs on LPL-connected infrastructure has a strong reason to stay.
4. **Recruiting.** "Bring your practice to LPL and your back office runs itself." Competing firms can't match this.
5. **It fits Latitude.** It slots into LPL's unified platform vision alongside ClientWorks and Cyan.

## 5. Scope

### P0: must ship for the demo
- [ ] Upload invoice → AI classifies and extracts fields → creates a Bill; receipts are matched to card charges instead of creating payables
- [ ] **Vendor memory**: a second invoice from the same vendor auto-matches and pre-fills category and GL account
- [ ] Rule-based **approval workflow** (amount threshold + new-vendor document check) with approve/reject in the UI
- [ ] Approved bill → posts to ledger → marked "Scheduled" (payment is **mocked**)
- [ ] Upload a **sample LPL-style payout statement** → revenue lines extracted → reconciled vs. expected → variance flagged
- [ ] **Dashboard**: P&L, simple balance sheet, cash flow, KPIs, estimated practice value
- [ ] **Ask your books** with source citations
- [ ] **Document library** with search and an "Export package" (ZIP of documents + CSV ledger)
- [ ] Deployed on AWS with a live URL

### P1: nice to have
- [ ] Card transaction import (CSV) with auto-categorization and receipt matching
- [ ] Gift and entertainment flag against a configurable limit (FINRA Rule 3220; verify the current threshold)
- [ ] Duplicate / suspicious vendor bank-detail detection (fraud flag)
- [ ] Role-based views: Owner, Ops, LPL Bookkeeper (Cognito groups)
- [ ] No-code rule builder UI (create or edit rules, not just view them)

### P2: stretch, mention in the pitch only
- Plaid sandbox bank linking
- QuickBooks sync
- Benchmarking against peer practices
- Multi-practice view for LPL bookkeepers

### Out of scope
- Real money movement (payments are mocked; money transmission is regulated)
- Real client PII or real LPL data (all seed data is fictional)
- Tax filing

## 6. Demo script (3 minutes)

1. **Hook (20s):** "Maya manages $250M for her clients, and can't tell you what her own practice is worth."
2. **Upload (30s):** Drop a messy PDF invoice. Fields appear. "Ledgerline recognized this vendor from last month and pre-filled the GL account."
3. **Workflow (30s):** It's over $1,000, so it routes to the senior partner. Switch to the partner view and approve in one click. It posts to the ledger.
4. **Revenue (30s):** Drop the payout statement. "One trail payment is $412 short of expected. Flagged."
5. **Dashboard (30s):** The P&L, margin and **estimated practice value** update live.
6. **Ask (20s):** "Why did my margin drop in Q3?" The answer comes with clickable citations.
7. **Close (20s):** Export the package. "LPL already sells this as a people-delivered service. Ledgerline makes it software that scales to 32,000 practices. That's why LPL should buy us."

## 7. Success metrics (pitch framing; projections, not measured)

| Metric | Target story |
|---|---|
| Time to process an invoice | ~10 min manual → <30 sec |
| Days to a valuation-ready set of books | Months → same day |
| Bookkeeper capacity | Practices served per bookkeeper, ~10x |
| Revenue leakage caught | Missing payouts flagged automatically |
| Advisor retention | Back-office lock-in (qualitative) |

## 8. Compliance and trust by design

- **Books and records:** documents stored in S3 with **Object Lock** (WORM) plus CloudTrail audit logs, aligned with broker-dealer recordkeeping expectations (SEC 17a-4).
- **Human in the loop:** the AI proposes and a human approves. No bill posts without a rule pass or an approval.
- **Explainability:** every AI answer cites its source documents, and every extraction shows a confidence score. Low confidence goes to human review.
- **Guardrails:** Bedrock Guardrails block investment advice and PII leakage in Q&A.
- **Least privilege:** Cognito roles and scoped IAM per Lambda.

## 9. Judging alignment

| Category | How we win it |
|---|---|
| **Startup We'd Buy Tomorrow** | Clear value proposition; LPL already monetizes this; plugs into Latitude; differentiated (advisor-specific: payouts and valuation) |
| **Biggest Business Impact** | 32K practices; scales an existing revenue line; speeds succession capital; retention and recruiting lever |
| **Best Use of AWS** | Textract AnalyzeExpense (built for invoices), Step Functions (human-approval workflows), Bedrock + Guardrails, S3 Object Lock (records), serverless and pay-per-use (cost-aware), live demo |

## 10. Open questions to ask LPL mentors
1. How many advisors use Bookkeeping or CFO Solutions today, and is demand outpacing the team?
2. What do advisors complain about most on the practice-finance side?
3. What does a practice valuation for a succession deal require today, and how long does it take?

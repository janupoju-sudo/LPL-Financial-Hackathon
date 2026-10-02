# Handoff → D (Financials)

Everything you asked for is on `C/Backend-and-Workflows`, in **your** ledger format. Two moves are needed on your branch before we merge.

## Done for you
| You asked for | Where | Notes |
|---|---|---|
| Ledger: one item per line, int cents, `journalId`, `sourceDocId` | `shared/ledger.py` | Journals written atomically, balance-checked before write |
| Your chart of accounts | `shared/coa.py` | Same codes and names; bills only accept 6xxx |
| Bill approved: Dr `glAccount` / Cr 2000 | `workflow/post_ledger.py` | `journalId = j-<billId>-accrual` |
| Mock payment: Dr 2000 / Cr 1000 | `workflow/schedule_payment.py` | `j-<billId>-payment` |
| Payout: Dr 1000 / Cr 4100, 4200, 4300 | `ledger.payout_lines(...)` | One journal, one credit per revenue type (B calls it) |
| Card spend (P1): Dr expense / Cr 2100 | `ledger.card_spend_lines(...)` | |
| `get_ledger_entries(practice_id, start, end)` | `shared/ddb.py` | Int cents, sorted by date / journal / line |
| `get_practice(practice_id)` | `shared/ddb.py` | `clientCount`, `top10Share`, `feeSchedule` |
| `get_revenue_lines(practice_id, period)` | `shared/ddb.py` | `REV#<yyyy-mm>#…`; also accepts `2026-Q3` / `2026` |
| Fee schedule on META | `scripts/seed.py` | Copied from your fixtures; E can replace |

**Small additions to your spec (nothing renamed):**
- SK is `LEDGER#2026-09#<journalId>#001` (line number on the end). `begins_with LEDGER#2026-09` still works.
- Journal ids are predictable (`j-<billId>-accrual`, `j-<billId>-payment`, `j-payout-<docId>`) so a retried workflow step can't double-post.
- Extra fields on each line: `lineNo`, `sourceType`, `sourceId`.
- `META.aum` is **dollars**; `aum` inside `feeSchedule` is **cents** (your format).

## Needed on your branch
**1. Move your code into `backend/src/`.** The deploy only packages `src/`, and there can only be one `shared` package.
- `backend/functions/financials/*` → `backend/src/financials/*`
- Tests: `from functions.financials import …` → `from financials import …` (`pytest.ini` already sets `pythonpath = src`)
- Delete `backend/shared/` and `backend/functions/`

**2. One `coa.py`.** Keep your `Account` dataclass version (the `recurring`/`cash` flags are better) as `src/shared/coa.py`, and add what the workflow code uses:
```python
CREDIT_CARD_PAYABLE = "2100"
DEFAULT_EXPENSE = "6900"
REVENUE_ACCOUNTS = {"advisory": "4100", "commission": "4200", "trail": "4300", "other": "4900"}

def is_valid(code) -> bool:   return str(code) in ACCOUNTS
def is_expense(code) -> bool: return is_valid(code) and ACCOUNTS[str(code)].type == "expense"
def name(code) -> str:        return ACCOUNTS[str(code)].name if is_valid(code) else "Unknown"
def kind(code) -> str:        return ACCOUNTS[str(code)].type if is_valid(code) else "unknown"
```
Then run `pytest -q` in `backend/`. All backend tests plus yours should pass together.

## The `/financials` route
Jay adds it to `template.yaml` once your code is under `src/financials/`. The handler will be:
```python
entries  = ddb.get_ledger_entries(practice_id, "0000-01-01", period_end)  # full history: balance sheet + TTM
practice = ddb.get_practice(practice_id)
return build_financials(entries, period, practice)
```
Tell Jay if you'd rather fetch a narrower range, and what routes you want for reconciliation, ask and export.

**Freshness:** a `LedgerUpdated` event fires on the `ledgerline-<stage>` bus after every posting, if you want to cache or precompute.

## Merge order
1. Jay pushes `C/Backend-and-Workflows` → merged to `main`
2. You rebase `d/financials-core` onto `main` and make the two moves above
3. `.gitignore` conflicts trivially (we both added `__pycache__`), so keep both

"""E7: ledger history for Harbor Point Wealth, on top of scripts/seed.py.

    python scripts/seed.py     --table ledgerline-dev     # practice, vendors, rules (run first)
    python scripts/seed_ddb.py --check                    # show the numbers, no AWS
    python scripts/seed_ddb.py --table ledgerline-dev     # write the history

Twelve complete months, Sep 2025 through Aug 2026, in D's agreed format
(backend/README.md, "Contract for D"). Every journal balances and goes in as one
DynamoDB transaction.

September 2026 is deliberately EMPTY - no revenue, no expenses. The demo builds it
live: approving a bill posts the Sept expense, uploading the payout statement posts
the Sept revenue and the RevenueLines reconciliation reads. Seeding Sept here would
double-count against B's ingest and the $412 flag would not fire.

The window ends in August on purpose. A period ending Aug 2026 covers 12 full months,
so D's valuation reports a true trailing twelve months instead of annualizing a part
year. Point the dashboard at 2026-08 (or 2026-Q3 once the demo has filled September).
Pass --include-sept for a fallback that seeds Sept revenue if the live upload is
flaky on the day.

post_journal skips a journal id it has already written, so re-running is safe. To
change seeded history, delete the LEDGER# items first (scripts/reset_demo.py).
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ---------------------------------------------------------------------------
# The practice, in dollars. Revenue mirrors the feeSchedule in scripts/seed.py,
# so the dashboard and the reconciliation tell the same story.
# ---------------------------------------------------------------------------
MONTHLY_REVENUE = {           # -> 4100 advisory, 4200 commissions, 4300 trails
    "advisory": 182_400,      # recurring
    "commission": 14_200,     # NOT recurring - keeps recurring % honest, not 100%
    "trail": 6_150,           # recurring
}
VA_TRAIL_QUARTERLY = 2_890    # contract ...4471, billed in Mar/Jun/Sep/Dec
QUARTER_MONTHS = (3, 6, 9, 12)

MONTHLY_EXPENSES = {
    "6100": 86_000,   # staff and payroll
    "6200": 9_800,    # rent and occupancy
    "6300": 7_400,    # technology
    "6400": 21_500,   # LPL platform fees
    "6500": 5_200,    # marketing
    "6600": 3_100,    # compliance and licensing
    "6700": 2_900,    # travel and entertainment
    "6900": 1_800,    # other
}

# Seasonality, so the P&L chart has a shape instead of a flat line.
SEASONAL = {
    "6500": {1: 1.8, 9: 1.8, 12: 0.7},        # campaigns in Jan and Sep
    "6700": {5: 2.2, 10: 2.2, 1: 0.5, 2: 0.5},  # conference season
}
DECEMBER_BONUS = 25_000       # added to 6100 in December
MONTHLY_DISTRIBUTION = 30_000  # owner draw: equity, so it does not touch margin
OPENING_CASH = 150_000

START = (2025, 9)
END = (2026, 8)          # Sept 2026 is left empty for the live demo
SEPT_DEMO = (2026, 9)


def months(first, last):
    y, m = first
    while (y, m) <= last:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(y, m):
    return date(y + (m == 12), 1 if m == 12 else m + 1, 1).toordinal() - 1


def expenses_for(m):
    out = {}
    for acct, base in MONTHLY_EXPENSES.items():
        amount = base * SEASONAL.get(acct, {}).get(m, 1.0)
        if acct == "6100" and m == 12:
            amount += DECEMBER_BONUS
        out[acct] = round(amount, 2)
    return out


def build(include_sept=False):
    """Every journal as (journal_id, date_iso, lines, memo). No AWS."""
    from shared import coa, ledger

    out = []
    first_y, first_m = START
    opening = date(first_y, first_m, 1).replace(day=1).toordinal() - 1
    out.append((
        "j-opening-balance", date.fromordinal(opening).isoformat(),
        [{"account": coa.CASH, "debit": ledger.to_cents(OPENING_CASH)},
         {"account": "3000", "credit": ledger.to_cents(OPENING_CASH)}],
        "Opening balance",
    ))

    for y, m in months(START, END):
        d = date.fromordinal(month_end(y, m)).isoformat()
        tag = f"{y}-{m:02d}"

        rev = dict(MONTHLY_REVENUE)
        if m in QUARTER_MONTHS:
            rev["trail"] += VA_TRAIL_QUARTERLY
        out.append((f"j-payout-{tag}", d, ledger.payout_lines(rev),
                    f"LPL payout statement {tag}"))

        exp = expenses_for(m)
        total = sum(ledger.to_cents(v) for v in exp.values())
        lines = [{"account": a, "debit": ledger.to_cents(v)} for a, v in sorted(exp.items())]
        lines.append({"account": coa.ACCOUNTS_PAYABLE, "credit": total})
        out.append((f"j-expenses-{tag}", d, lines, f"Operating expenses {tag}"))
        out.append((f"j-exp-paid-{tag}", d,
                    [{"account": coa.ACCOUNTS_PAYABLE, "debit": total},
                     {"account": coa.CASH, "credit": total}],
                    f"Paid operating expenses {tag}"))

        out.append((f"j-distribution-{tag}", d,
                    [{"account": "3100", "debit": ledger.to_cents(MONTHLY_DISTRIBUTION)},
                     {"account": coa.CASH, "credit": ledger.to_cents(MONTHLY_DISTRIBUTION)}],
                    f"Owner distribution {tag}"))

    if include_sept:
        y, m = SEPT_DEMO
        d = date.fromordinal(month_end(y, m)).isoformat()
        rev = dict(MONTHLY_REVENUE)
        rev["trail"] += VA_TRAIL_QUARTERLY
        out.append((f"j-payout-{y}-{m:02d}", d, ledger.payout_lines(rev),
                    f"LPL payout statement {y}-{m:02d} (seeded fallback)"))
    return out


def check(include_sept=False):
    """Print what the dashboard will show, using D's real code. No AWS."""
    os.environ.setdefault("TABLE_NAME", "unused-for-check")
    from shared import ledger
    from financials import kpis, statements, valuation

    entries = []
    for jid, d, lines, memo in build(include_sept):
        entries.extend(ledger.build_journal(jid, d, lines, memo))
    print(f"{len(entries)} ledger lines across {len(build(include_sept))} journals, all balanced.\n")

    as_of = date(2026, 8, 31)
    for period in ("2026-07", "2026-08", "2026-Q2"):
        pnl = statements.profit_and_loss(entries, period)
        k = kpis.compute(pnl, 180)
        print(f"  {period:9} revenue ${pnl['totalRevenue']/100:>12,.0f}   "
              f"expenses ${pnl['totalExpenses']/100:>11,.0f}   "
              f"margin {k['margin']:.1%}   recurring {k['recurringPct']:.1%}")

    pnl = statements.profit_and_loss(entries, "2026-08")
    k = kpis.compute(pnl, 180)
    v = valuation.estimate(entries, as_of, k["recurringPct"], k["margin"], 0.22)
    print(f"\n  Estimated practice value  ${v['low']/100:,.0f} - ${v['high']/100:,.0f}"
          f"   (mid ${v['mid']/100:,.0f})")
    print(f"  Multiples {v['multiples']}")
    print(f"  Method: {v['method']}\n")

    bs = statements.balance_sheet(entries, as_of)
    diff = bs["totalAssets"] - (bs["totalLiabilities"] + bs["totalEquity"])
    print(f"  Balance sheet: assets ${bs['totalAssets']/100:,.0f} = "
          f"liabilities ${bs['totalLiabilities']/100:,.0f} + equity ${bs['totalEquity']/100:,.0f}"
          f"   {'BALANCED' if diff == 0 else f'OFF BY {diff}'}")
    if not include_sept:
        print("\n  September 2026 is empty on purpose - the demo fills it live.")
        print("  Use --include-sept as a fallback if the upload is flaky on the day.")
    return diff == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table")
    ap.add_argument("--practice", default="p1")
    ap.add_argument("--check", action="store_true", help="show the numbers, write nothing")
    ap.add_argument("--include-sept", action="store_true",
                    help="also seed September 2026 revenue (fallback if the live upload fails)")
    a = ap.parse_args()

    if a.check or not a.table:
        ok = check(a.include_sept)
        if not a.table:
            print("\nPass --table <name> to write.")
        sys.exit(0 if ok else 1)

    os.environ["TABLE_NAME"] = a.table
    from shared import ledger
    journals = build(a.include_sept)
    for jid, d, lines, memo in journals:
        ledger.post_journal(a.practice, jid, d, lines, memo, source_type="seed")
    print(f"Posted {len(journals)} journals to {a.table} for practice {a.practice}.")
    print("Re-running is safe: existing journal ids are skipped.")


if __name__ == "__main__":
    main()

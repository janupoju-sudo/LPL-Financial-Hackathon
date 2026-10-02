"""Builds the GET /financials response (PLAN.md §5) from ledger entries.

Response: {pnl, balanceSheet, cashFlow, kpis:{margin, recurringPct, revPerClient, ...},
           valuation:{low, mid, high, method, ...}}
Money in the response is in dollars (2 decimals); ratios are 0–1.
"""

from . import kpis, periods, statements, valuation

# Keys whose values are cents internally and dollars in the response.
_MONEY_KEYS = {
    "amount", "totalRevenue", "totalExpenses", "operatingIncome",
    "totalAssets", "totalLiabilities", "totalEquity",
    "beginningCash", "netOperating", "netFinancing", "netChange", "endingCash",
    "revPerClient", "low", "mid", "high", "recurringRevenueTtm",
}


def to_dollars(obj):
    if isinstance(obj, dict):
        return {k: (round(v / 100, 2) if k in _MONEY_KEYS and isinstance(v, int) else to_dollars(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_dollars(v) for v in obj]
    return obj


def build_financials(entries, period: str, practice: dict | None = None) -> dict:
    """practice: the Practice META item, e.g. {"clientCount": 180, "top10Share": 0.22}."""
    practice = practice or {}
    statements.check_balanced(entries)
    _, end = periods.parse(period)

    pnl = statements.profit_and_loss(entries, period)
    prev_pnl = statements.profit_and_loss(entries, periods.previous(period))
    k = kpis.compute(pnl, practice.get("clientCount"))
    prev_k = kpis.compute(prev_pnl, practice.get("clientCount"))
    k["previous"] = {"period": prev_pnl["period"], "totalRevenue": prev_pnl["totalRevenue"],
                     "margin": prev_k["margin"], "recurringPct": prev_k["recurringPct"]}

    return to_dollars({
        "period": period,
        "pnl": pnl,
        "balanceSheet": statements.balance_sheet(entries, end),
        "cashFlow": statements.cash_flow(entries, period),
        "kpis": k,
        "valuation": valuation.estimate(entries, end, k["recurringPct"], k["margin"],
                                        practice.get("top10Share")),
    })

"""Builds the GET /financials response from ledger entries.

The shape follows the frontend's contract (frontend/API.md, lib/types.ts):
  pnl:          {revenue, expenses, netIncome, monthly:[{month, period, revenue, expenses}],
                 categories:[{name, account, amount}], revenueLines, expenseLines}
  balanceSheet: {asOf, assets, liabilities, equity, assetLines, liabilityLines, equityLines}
  cashFlow:     {operating, investing, financing, net, beginningCash, endingCash,
                 operatingLines, financingLines}
  kpis:         {margin, recurringPct, revPerClient, expenseRatios, previous}
  valuation:    {low, mid, high, method, recurringRevenueTtm, multiples}
Money is dollars (2 decimals). Percentages are 0–100 (1 decimal), as the frontend expects.
The *Lines fields carry the per-account detail behind each total.
"""

from datetime import date

from . import kpis, periods, statements, valuation

MONTHS_IN_CHART = 6


def _usd(cents) -> float | None:
    return None if cents is None else round(cents / 100, 2)


def _pct(ratio) -> float | None:
    return None if ratio is None else round(ratio * 100, 1)


def _lines(lines) -> list[dict]:
    return [{**l, "amount": _usd(l["amount"])} for l in lines]


def _monthly(entries, end: date) -> list[dict]:
    out, y, m = [], end.year, end.month
    for _ in range(MONTHS_IN_CHART):
        p = statements.profit_and_loss(entries, f"{y}-{m:02d}")
        out.append({"month": date(y, m, 1).strftime("%b"), "period": f"{y}-{m:02d}",
                    "revenue": _usd(p["totalRevenue"]), "expenses": _usd(p["totalExpenses"])})
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def build_financials(entries, period: str, practice: dict | None = None) -> dict:
    """practice: the Practice META item, e.g. {"clientCount": 180, "top10Share": 0.22}."""
    practice = practice or {}
    statements.check_balanced(entries)
    _, end = periods.parse(period)

    pnl = statements.profit_and_loss(entries, period)
    prev_pnl = statements.profit_and_loss(entries, periods.previous(period))
    bs = statements.balance_sheet(entries, end)
    cf = statements.cash_flow(entries, period)
    k = kpis.compute(pnl, practice.get("clientCount"))
    prev_k = kpis.compute(prev_pnl, practice.get("clientCount"))
    val = valuation.estimate(entries, end, k["recurringPct"], k["margin"], practice.get("top10Share"))

    return {
        "period": period,
        "pnl": {
            "revenue": _usd(pnl["totalRevenue"]),
            "expenses": _usd(pnl["totalExpenses"]),
            "netIncome": _usd(pnl["operatingIncome"]),
            "monthly": _monthly(entries, end),
            "categories": [{"name": l["name"], "account": l["account"], "amount": _usd(l["amount"])}
                           for l in sorted(pnl["expenses"], key=lambda l: -l["amount"])],
            "revenueLines": _lines(pnl["revenue"]),
            "expenseLines": _lines(pnl["expenses"]),
        },
        "balanceSheet": {
            "asOf": bs["asOf"],
            "assets": _usd(bs["totalAssets"]),
            "liabilities": _usd(bs["totalLiabilities"]),
            "equity": _usd(bs["totalEquity"]),
            "assetLines": _lines(bs["assets"]),
            "liabilityLines": _lines(bs["liabilities"]),
            "equityLines": _lines(bs["equity"]),
        },
        "cashFlow": {
            "operating": _usd(cf["netOperating"]),
            "investing": 0.0,  # an advisory practice has no investing activity in this ledger
            "financing": _usd(cf["netFinancing"]),
            "net": _usd(cf["netChange"]),
            "beginningCash": _usd(cf["beginningCash"]),
            "endingCash": _usd(cf["endingCash"]),
            "operatingLines": _lines(cf["operating"]),
            "financingLines": _lines(cf["financing"]),
        },
        "kpis": {
            "margin": _pct(k["margin"]),
            "recurringPct": _pct(k["recurringPct"]),
            "revPerClient": _usd(k["revPerClient"]),
            "expenseRatios": [{**r, "ratio": _pct(r["ratio"])} for r in k["expenseRatios"]],
            "previous": {"period": prev_pnl["period"], "revenue": _usd(prev_pnl["totalRevenue"]),
                         "margin": _pct(prev_k["margin"]), "recurringPct": _pct(prev_k["recurringPct"])},
        },
        "valuation": {
            "low": _usd(val["low"]), "mid": _usd(val["mid"]), "high": _usd(val["high"]),
            "method": val["method"],
            "recurringRevenueTtm": _usd(val["recurringRevenueTtm"]),
            "multiples": val["multiples"],
        },
    }

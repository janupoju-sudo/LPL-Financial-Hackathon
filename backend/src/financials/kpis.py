"""Practice KPIs from a P&L (task D3)."""

from shared import coa


def _ratio(n, d):
    return round(n / d, 4) if d else None


def compute(pnl: dict, client_count: int | None = None) -> dict:
    rev = pnl["totalRevenue"]
    recurring = sum(l["amount"] for l in pnl["revenue"] if coa.get(l["account"]).recurring)
    return {
        "margin": _ratio(pnl["operatingIncome"], rev),
        "recurringPct": _ratio(recurring, rev),
        # Cents for the period, not annualized.
        "revPerClient": round(rev / client_count) if client_count else None,
        "expenseRatios": [
            {"account": l["account"], "name": l["name"], "ratio": _ratio(l["amount"], rev)}
            for l in sorted(pnl["expenses"], key=lambda l: -l["amount"])
        ],
    }

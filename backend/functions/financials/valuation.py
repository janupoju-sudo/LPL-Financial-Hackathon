"""Estimated practice value (task D7). An estimate for conversation, not an appraisal.

value = recurring revenue over the trailing 12 months × a multiple,
where the multiple starts from a base range and moves with recurring %,
operating margin and client concentration.
"""

from datetime import date, timedelta

from shared import coa

BASE_MULTIPLES = (2.0, 2.3, 2.6)  # low, mid, high


def _adjustments(recurring_pct, margin, top10_share):
    adj = []
    if recurring_pct is not None and recurring_pct >= 0.80:
        adj.append((+0.2, f"recurring revenue {recurring_pct:.0%} (≥ 80%)"))
    if margin is not None:
        if margin >= 0.30:
            adj.append((+0.1, f"operating margin {margin:.0%} (≥ 30%)"))
        elif margin < 0.20:
            adj.append((-0.2, f"operating margin {margin:.0%} (< 20%)"))
    if top10_share is not None and top10_share > 0.25:
        adj.append((-0.3, f"top 10 clients are {top10_share:.0%} of revenue (> 25%)"))
    return adj


def recurring_ttm(entries, as_of: date) -> tuple[int, int]:
    """Recurring revenue (cents) for the 12 months ending as_of, annualized
    if the ledger has revenue in fewer months. Returns (amount, months_covered)."""
    start = date(as_of.year - 1, as_of.month, 1) + timedelta(days=32)
    start = start.replace(day=1)
    total, months = 0, set()
    for e in entries:
        d = date.fromisoformat(e["date"])
        if not start <= d <= as_of:
            continue
        acct = coa.get(e["account"])
        if acct.type == "revenue":
            months.add((d.year, d.month))
        if acct.recurring:
            total += int(e.get("credit", 0)) - int(e.get("debit", 0))
    n = len(months)
    if n and n < 12:
        total = round(total * 12 / n)
    return total, n


def estimate(entries, as_of: date, recurring_pct, margin, top10_share=None) -> dict:
    ttm, months = recurring_ttm(entries, as_of)
    adj = _adjustments(recurring_pct, margin, top10_share)
    shift = sum(a for a, _ in adj)
    low, mid, high = (round(m + shift, 2) for m in BASE_MULTIPLES)

    basis = "trailing 12 months" if months >= 12 else f"{months} months annualized to 12"
    parts = [f"Recurring revenue ${ttm / 100:,.0f} ({basis}) × {low}–{high}× multiple."]
    parts.append(f"Base multiple {BASE_MULTIPLES[0]}–{BASE_MULTIPLES[2]}×"
                 + (", adjusted for " + "; ".join(
                     f"{r} {a:+.1f}" for a, r in adj) if adj else "") + ".")
    parts.append("An estimate for planning conversations, not an appraisal.")

    return {
        "low": round(ttm * low),
        "mid": round(ttm * mid),
        "high": round(ttm * high),
        "recurringRevenueTtm": ttm,
        "multiples": {"low": low, "mid": mid, "high": high},
        "method": " ".join(parts),
    }

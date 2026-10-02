"""Revenue reconciliation: what LPL paid vs. what the fee schedule says it should have (task D4).

Fee schedule item (seeded by E, one list on the practice):
    {"id": "va-4471", "label": "Variable annuity trail, contract …4471",
     "source": "trail", "ref": "4471",
     "basis": "aum", "aum": 115600000, "annualRate": 0.01,   # aum in cents
     "frequency": "quarterly", "billingMonths": [3, 6, 9, 12]}
  or a flat amount:
    {"id": "adv-q", "label": "Advisory fees", "source": "advisory",
     "basis": "fixed", "amount": 18240000, "frequency": "monthly"}

Payout line (written by B3 from the payout statement, the RevenueLine item):
    {"id": "x1", "source": "trail", "ref": "4471", "label": "...",
     "actual": 247800, "docId": "d3"}

All amounts are integer cents in and out of compute(); response() converts to dollars.
"""

from . import periods

# A gap smaller than this is rounding, not a problem.
TOLERANCE_CENTS = 100  # $1
TOLERANCE_PCT = 0.005  # 0.5%

_MONTHS_PER = {"monthly": 1, "quarterly": 3, "annual": 12}


def _months(period: str) -> list[int]:
    start, end = periods.parse(period)
    return list(range(start.month, end.month + 1)) if start.year == end.year else []


def expected_for(item: dict, period: str) -> int:
    """Expected cents from one schedule item in the period (0 if not billed then)."""
    freq = item.get("frequency", "monthly")
    billing = item.get("billingMonths") or (list(range(1, 13)) if freq == "monthly" else [3, 6, 9, 12])
    hits = sum(1 for m in _months(period) if m in billing)
    if not hits:
        return 0
    if item["basis"] == "aum":
        per_bill = item["aum"] * item["annualRate"] * _MONTHS_PER[freq] / 12
    else:
        per_bill = item["amount"]
    return round(per_bill * hits)


def _key(x: dict) -> tuple:
    return (x.get("source"), x.get("ref") or x.get("label"))


def _reason(item: dict | None, expected: int, actual: int) -> str:
    if item is None:
        return "Not on the fee schedule. Check what this payment is for."
    if actual == 0:
        return "Expected on this statement but not paid."
    if item.get("basis") == "aum" and item.get("aum"):
        freq_share = _MONTHS_PER[item.get("frequency", "monthly")] / 12
        bills = max(1, round(expected / (item["aum"] * item["annualRate"] * freq_share)))
        paid_rate = actual / (item["aum"] * freq_share * bills)
        return (f"Paid at {paid_rate:.2%} vs. {item['annualRate']:.2%} scheduled "
                f"on ${item['aum'] / 100:,.0f}. Check the contract.")
    return f"Paid ${actual / 100:,.2f} vs. ${expected / 100:,.2f} expected."


def compute(schedule: list[dict], payout_lines: list[dict], period: str) -> dict:
    paid = {}
    for p in payout_lines:
        k = _key(p)
        paid.setdefault(k, {**p, "actual": 0})["actual"] += int(p["actual"])

    lines, flags = [], []

    def add(item, label, source, ref, expected, actual, doc):
        variance = actual - expected
        tol = max(TOLERANCE_CENTS, round(abs(expected) * TOLERANCE_PCT))
        if item is None:
            status = "unexpected"
        elif actual == 0 and expected:
            status = "missing"
        elif abs(variance) <= tol:
            status = "ok"
        else:
            status = "short" if variance < 0 else "over"
        line = {"id": item["id"] if item else f"unscheduled-{len(lines)}", "label": label,
                "source": source, "ref": ref, "expected": expected, "actual": actual,
                "variance": variance, "status": status, "docId": doc}
        if status != "ok":
            line["reason"] = _reason(item, expected, actual)
            flags.append({"lineId": line["id"], "status": status,
                          "severity": "high" if status in ("short", "missing") else "medium",
                          "message": f"{label}: {status}, {variance / 100:+,.2f}. {line['reason']}"})
        lines.append(line)

    for item in schedule:
        exp = expected_for(item, period)
        got = paid.pop(_key(item), None)
        if not exp and not got:
            continue
        add(item, item["label"], item["source"], item.get("ref"), exp,
            got["actual"] if got else 0, got.get("docId") if got else None)

    for p in paid.values():  # paid but not on the schedule
        add(None, p.get("label") or p.get("ref") or "Unlabeled payment", p.get("source"),
            p.get("ref"), 0, p["actual"], p.get("docId"))

    expected = sum(l["expected"] for l in lines)
    actual = sum(l["actual"] for l in lines)
    return {"period": period, "expected": expected, "actual": actual,
            "variance": actual - expected, "lines": lines, "flags": flags}


def response(schedule, payout_lines, period) -> dict:
    """GET /revenue/reconciliation body (PLAN.md §5), money in dollars."""
    r = compute(schedule, payout_lines, period)
    d = lambda c: round(c / 100, 2)
    return {**r, "expected": d(r["expected"]), "actual": d(r["actual"]), "variance": d(r["variance"]),
            "lines": [{**l, "expected": d(l["expected"]), "actual": d(l["actual"]),
                       "variance": d(l["variance"])} for l in r["lines"]]}

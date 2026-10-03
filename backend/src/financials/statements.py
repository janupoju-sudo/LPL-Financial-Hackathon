"""P&L, balance sheet and cash flow built from ledger entries (task D2).

A ledger entry is one line of a double-entry journal:
    {"journalId": "j-123", "date": "2026-09-30", "account": "4100",
     "debit": 0, "credit": 1824000, "sourceDocId": "d3", "memo": "..."}
Amounts are integer cents. Every journal's debits equal its credits.
Everything here works in cents; api.py converts to dollars at the edge.
"""

from collections import defaultdict
from datetime import date

from shared import coa
from . import periods


def _d(entry) -> date:
    return date.fromisoformat(entry["date"])


def _net(entry) -> int:
    """Debit minus credit, in cents."""
    return int(entry.get("debit", 0)) - int(entry.get("credit", 0))


def _line(code: str, amount: int) -> dict:
    return {"account": code, "name": coa.get(code).name, "amount": amount}


def in_range(entries, start: date, end: date):
    return [e for e in entries if start <= _d(e) <= end]


def check_balanced(entries) -> None:
    """Raise if any journal's debits and credits differ."""
    totals = defaultdict(int)
    for e in entries:
        totals[e["journalId"]] += _net(e)
    bad = {j: t for j, t in totals.items() if t}
    if bad:
        raise ValueError(f"Unbalanced journals (debit − credit, cents): {bad}")


def _expense_categories(by_acct) -> list[dict]:
    """One line per expense category with its total, and `children` with the sub-account breakdown.

    Money posted straight to a category code (older history) shows as that category's "General"
    line when the category also has sub-account activity.
    """
    groups = defaultdict(dict)
    for code, v in by_acct.items():
        if coa.get(code).type == "expense" and v:
            groups[coa.category(code)][code] = v
    out = []
    for cat in sorted(groups):
        amounts = groups[cat]
        subs = sorted(c for c in amounts if c != cat)
        children = [_line(c, amounts[c]) for c in subs]
        if subs and cat in amounts:
            children.insert(0, {"account": cat, "name": "General", "amount": amounts[cat]})
        out.append({**_line(cat, sum(amounts.values())), "children": children})
    return out


def profit_and_loss(entries, period: str) -> dict:
    start, end = periods.parse(period)
    by_acct = defaultdict(int)
    for e in in_range(entries, start, end):
        by_acct[e["account"]] += _net(e)

    revenue = [_line(c, -v) for c, v in sorted(by_acct.items())
               if coa.get(c).type == "revenue" and v]
    expenses = _expense_categories(by_acct)
    total_rev = sum(l["amount"] for l in revenue)
    total_exp = sum(l["amount"] for l in expenses)
    return {
        "period": period,
        "revenue": revenue,
        "totalRevenue": total_rev,
        "expenses": expenses,
        "totalExpenses": total_exp,
        "operatingIncome": total_rev - total_exp,
    }


def balance_sheet(entries, as_of: date) -> dict:
    by_acct = defaultdict(int)
    for e in entries:
        if _d(e) <= as_of:
            by_acct[e["account"]] += _net(e)

    def section(kind, sign):
        return [_line(c, sign * v) for c, v in sorted(by_acct.items())
                if coa.get(c).type == kind and v]

    assets = section("asset", 1)
    liabilities = section("liability", -1)
    equity = section("equity", -1)
    # Revenue and expense accounts aren't closed out, so their running
    # total shows up in equity as earnings to date.
    earnings = -sum(v for c, v in by_acct.items()
                    if coa.get(c).type in ("revenue", "expense"))
    if earnings:
        equity.append({"account": None, "name": "Earnings to date", "amount": earnings})

    return {
        "asOf": as_of.isoformat(),
        "assets": assets,
        "totalAssets": sum(l["amount"] for l in assets),
        "liabilities": liabilities,
        "totalLiabilities": sum(l["amount"] for l in liabilities),
        "equity": equity,
        "totalEquity": sum(l["amount"] for l in equity),
    }


# Direct-method labels, keyed by the account on the other side of the cash line.
def _cash_category(code: str) -> tuple[str, str]:
    acct = coa.get(code)
    if acct.type == "revenue" or code == "1100":
        return "operating", "Collections from payouts and clients"
    if code in (coa.ACCOUNTS_PAYABLE, "2100"):
        return "operating", "Payments to vendors"
    if code in ("6100", "2200"):
        return "operating", "Payroll paid"
    if acct.type == "equity":
        return "financing", "Owner contributions and distributions"
    return "operating", "Other operating payments"


def cash_flow(entries, period: str) -> dict:
    start, end = periods.parse(period)
    cash_codes = {a.code for a in coa.CHART if a.cash}

    beginning = sum(_net(e) for e in entries
                    if e["account"] in cash_codes and _d(e) < start)

    journals = defaultdict(list)
    for e in in_range(entries, start, end):
        journals[e["journalId"]].append(e)

    buckets = {"operating": defaultdict(int), "financing": defaultdict(int)}
    for lines in journals.values():
        cash_delta = sum(_net(e) for e in lines if e["account"] in cash_codes)
        if not cash_delta:
            continue
        others = [e for e in lines if e["account"] not in cash_codes]
        # Classify by the biggest non-cash line in the journal.
        counter = max(others, key=lambda e: abs(_net(e)))["account"]
        section, label = _cash_category(counter)
        buckets[section][label] += cash_delta

    def rows(section):
        return [{"label": k, "amount": v} for k, v in sorted(buckets[section].items())]

    net = sum(sum(b.values()) for b in buckets.values())
    return {
        "period": period,
        "beginningCash": beginning,
        "operating": rows("operating"),
        "netOperating": sum(buckets["operating"].values()),
        "financing": rows("financing"),
        "netFinancing": sum(buckets["financing"].values()),
        "netChange": net,
        "endingCash": beginning + net,
    }

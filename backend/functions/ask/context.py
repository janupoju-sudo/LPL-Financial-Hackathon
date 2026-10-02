"""Builds the context for "Ask your books" (task D5): which period the question is
about, the ledger summary for it, and the documents worth citing.

No vector database: a keyword and metadata filter over the practice's own
documents is enough at this size. Bedrock Knowledge Bases is the scale path.
"""

import re
from datetime import date

from shared import coa
from functions.financials import kpis, periods, statements

MAX_DOCS = 6

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
_STOP = set("a an and are as at be by did do does for from how i in is it me my of on or "
            "our the this to was we what when where which who why with".split())


def pick_period(question: str, entries, today: date) -> str:
    """The period a question is about. Falls back to the latest quarter with ledger data."""
    q = question.lower()
    year_m = re.search(r"\b(20\d\d)\b", q)
    year = int(year_m[1]) if year_m else None

    if m := re.search(r"\bq([1-4])\b", q):
        n = int(m[1])
        y = year or (today.year if 3 * n - 2 <= today.month else today.year - 1)
        return f"{y}-Q{n}"
    for name, num in _MONTHS.items():
        if re.search(rf"\b{name}\b|\b{name[:3]}\b", q):
            y = year or (today.year if num <= today.month else today.year - 1)
            return f"{y}-{num:02d}"
    if year or "this year" in q or "ytd" in q:
        return str(year or today.year)

    last = max((date.fromisoformat(e["date"]) for e in entries), default=today)
    return f"{last.year}-Q{(last.month - 1) // 3 + 1}"


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def ledger_summary(entries, period: str) -> tuple[str, list[str]]:
    """Plain-text P&L for the period vs. the previous one, and the accounts that moved most."""
    prev = periods.previous(period)
    cur_pnl = statements.profit_and_loss(entries, period)
    prev_pnl = statements.profit_and_loss(entries, prev)
    cur_k, prev_k = kpis.compute(cur_pnl), kpis.compute(prev_pnl)

    amounts = {}
    for pnl, key in ((cur_pnl, "cur"), (prev_pnl, "prev")):
        for l in pnl["revenue"] + pnl["expenses"]:
            amounts.setdefault(l["account"], {"cur": 0, "prev": 0})[key] = l["amount"]

    rows = [f"Period {period} compared with {prev}. Amounts in dollars."]
    for code in sorted(amounts):
        a = amounts[code]
        rows.append(f"- {code} {coa.get(code).name}: {_money(a['cur'])} (was {_money(a['prev'])}, "
                    f"change {(a['cur'] - a['prev']) / 100:+,.0f})")
    pct = lambda r: "n/a" if r is None else f"{r:.1%}"
    rows += [
        f"- Total revenue: {_money(cur_pnl['totalRevenue'])} (was {_money(prev_pnl['totalRevenue'])})",
        f"- Total expenses: {_money(cur_pnl['totalExpenses'])} (was {_money(prev_pnl['totalExpenses'])})",
        f"- Operating margin: {pct(cur_k['margin'])} (was {pct(prev_k['margin'])})",
        f"- Recurring revenue share: {pct(cur_k['recurringPct'])} (was {pct(prev_k['recurringPct'])})",
    ]
    drivers = sorted(amounts, key=lambda c: -abs(amounts[c]["cur"] - amounts[c]["prev"]))[:3]
    return "\n".join(rows), drivers


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 2}


def pick_documents(question: str, documents, entries, period: str, drivers: list[str]) -> list[dict]:
    """Documents most likely to back an answer: keyword matches, plus documents
    behind the period's biggest movers."""
    start, end = periods.parse(period)
    q = _tokens(question)
    driver_docs = {e["sourceDocId"] for e in entries
                   if e.get("sourceDocId") and e["account"] in drivers
                   and start <= date.fromisoformat(e["date"]) <= end}

    scored = []
    for d in documents:
        hay = _tokens(" ".join(str(d.get(k) or "") for k in ("filename", "vendorName", "type")))
        score = 2 * len(q & hay) + (3 if d["id"] in driver_docs else 0)
        if score:
            scored.append((score, d.get("createdAt") or "", d))
    scored.sort(key=lambda s: s[1], reverse=True)  # newest first...
    scored.sort(key=lambda s: -s[0])  # ...within each score (sort is stable)
    return [d for _, _, d in scored[:MAX_DOCS]]


def doc_label(d: dict) -> str:
    return f"{d.get('vendorName') or d.get('filename')} ({d.get('type', 'document').replace('_', ' ')})"


def doc_snippet(d: dict) -> str:
    parts = [d.get("filename")]
    if d.get("amount") is not None:
        parts.append(f"${float(d['amount']):,.2f}")
    if d.get("createdAt"):
        parts.append(str(d["createdAt"])[:10])
    return " · ".join(p for p in parts if p)


def build(question: str, entries, documents, today: date) -> dict:
    period = pick_period(question, entries, today)
    summary, drivers = ledger_summary(entries, period)
    docs = pick_documents(question, documents, entries, period, drivers)
    doc_lines = [f"[{d['id']}] {doc_label(d)}: {doc_snippet(d)}" for d in docs] or ["(no matching documents)"]
    text = (f"LEDGER SUMMARY\n{summary}\n\nBIGGEST CHANGES: "
            + ", ".join(f"{c} {coa.get(c).name}" for c in drivers)
            + "\n\nDOCUMENTS (cite by the id in brackets)\n" + "\n".join(doc_lines))
    return {"period": period, "text": text, "documents": docs}

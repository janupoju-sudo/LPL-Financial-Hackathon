"""A small fictional ledger for Harbor Point Wealth, Apr–Sep 2026 (SAMPLE DATA).

Story baked in: margin drops in Q3 because rent goes up in July, a
compliance consultant starts, and a staff bonus is accrued in August.
"""

from itertools import count

_ids = count(1)

PRACTICE = {"name": "Harbor Point Wealth", "clientCount": 180, "top10Share": 0.22}


def _journal(day, lines, memo, doc=None):
    """lines: [(account, debit_dollars, credit_dollars)]"""
    jid = f"j-{next(_ids)}"
    return [{"journalId": jid, "date": day, "account": a,
             "debit": round(dr * 100), "credit": round(cr * 100),
             "sourceDocId": doc, "memo": memo} for a, dr, cr in lines]


def _bill(day, paid_day, account, amount, memo, doc=None):
    out = _journal(day, [(account, amount, 0), ("2000", 0, amount)], memo, doc)
    if paid_day:
        out += _journal(paid_day, [("2000", amount, 0), ("1000", 0, amount)], f"Pay: {memo}", doc)
    return out


# month -> (advisory, commissions, trails)
REVENUE = {
    4: (176_000, 13_500, 15_500), 5: (176_000, 13_500, 21_500), 6: (176_000, 13_500, 24_500),
    7: (182_400, 14_200, 19_400), 8: (182_400, 14_200, 17_400), 9: (182_400, 14_200, 21_400),
}


def sample_entries():
    e = _journal("2026-03-31", [("1000", 300_000, 0), ("3000", 0, 300_000)], "Opening balance")
    for m, (adv, com, trl) in REVENUE.items():
        mm = f"2026-{m:02d}"
        q3 = m >= 7
        e += _journal(f"{mm}-28", [("1000", adv + com + trl, 0), ("4100", 0, adv),
                                   ("4200", 0, com), ("4300", 0, trl)],
                      "LPL payout", doc=f"payout-{mm}")
        e += _journal(f"{mm}-25", [("6100", 77_000, 0), ("1000", 0, 77_000)], "Payroll")
        e += _bill(f"{mm}-01", f"{mm}-05", "6200", 9_800 if q3 else 7_400, "Summit Office Partners rent")
        e += _bill(f"{mm}-27", f"{mm}-28", "6400", 32_400 if q3 else 31_000, "LPL platform fees")
        e += _bill(f"{mm}-10", f"{mm}-20", "6300", 6_200, "Brightline IT Services")
        e += _bill(f"{mm}-12", f"{mm}-22", "6500", 5_400, "Northgate Marketing")
        e += _bill(f"{mm}-15", f"{mm}-25", "6700", 2_100 + 100 * m, "Client events")
        if q3:
            e += _bill(f"{mm}-17", f"{mm}-27", "6600", 850, "Clearpath Compliance")
    e += _journal("2026-06-30", [("3100", 40_000, 0), ("1000", 0, 40_000)], "Owner distribution")
    e += _journal("2026-08-31", [("6100", 11_000, 0), ("2200", 0, 11_000)], "Staff bonus accrual")
    e += _journal("2026-09-15", [("2200", 11_000, 0), ("1000", 0, 11_000)], "Staff bonus paid")
    # One September bill still open at quarter end.
    e += _bill("2026-09-29", None, "6300", 1_240, "Brightline IT Services INV-2291", doc="d1")
    return e

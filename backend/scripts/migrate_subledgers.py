"""Re-code existing ledger history from expense categories to sub-accounts (subledgers).

    python scripts/migrate_subledgers.py --table ledgerline-dev              # preview, writes nothing
    python scripts/migrate_subledgers.py --table ledgerline-dev --execute    # apply

New postings already use sub-accounts (shared/coa.py). This moves what was posted before that
change, so the P&L breakdown covers history too. Every journal keeps its id, date, memo, source
and total; only the expense lines change:

- j-expenses-<month> (seeded operating expenses): each category split over its sub-accounts with
  the seed's shares (scripts/seed_ddb.py SUBLEDGER_SPLIT, plus rent and compliance below)
- j-expense-rent-<month> -> 6210 Office rent; j-expense-compliance-base-<month> -> licensing and
  E&O insurance; j-expense-compliance-consultant-<month> -> 6630 Compliance consultants
- j-card-<txn> (imported card charges) -> re-categorized with the current merchant keywords
- vendor defaultGlAccount category codes -> the vendor's sub-account (vendor memory)

Each journal is rewritten in one DynamoDB transaction (old lines deleted, new lines written, all
conditional), so a journal is never half-migrated. Re-running finds nothing left to do.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

# Shares for categories the seed keeps on their category code.
EXTRA_SPLIT = {
    "6200": (("6210", 0.92), ("6220", 0.08)),
    "6600": (("6610", 0.40), ("6620", 0.35), ("6630", 0.25)),
}
COMPLIANCE_BASE_SPLIT = (("6610", 0.55), ("6620", 0.45))
WHOLE = {"j-expense-rent-": "6210", "j-expense-compliance-consultant-": "6630"}
VENDOR_DEFAULTS = {  # vendor name -> sub-account, matching scripts/seed.py
    "Orion Software LLC": "6310", "Seaport Office Partners": "6210", "LPL Financial": "6410",
    "Brightline Marketing": "6520", "Clearwater Compliance Advisors (FICTIONAL)": "6630",
    "Horizon Managed IT LLC": "6330", "Oakridge Payroll Services": "6110",
    "Pinecrest Office Supply LLC": "6910", "Waypoint Business Travel LLC": "6710",
}


def _split(cents, shares):
    out, left = [], cents
    for i, (code, share) in enumerate(shares):
        part = left if i == len(shares) - 1 else round(cents * share)
        left -= part
        out.append((code, part))
    return out


def _recode_line(journal_id, line, vendors):
    """Return [(account, cents)] replacing one expense debit line, or None to keep it."""
    from shared import coa
    import seed_ddb

    account, cents = str(line["account"]), int(line["debit"])
    if coa.get(account).parent or not coa.subaccounts(account):
        return None  # already a sub-account, or a category without sub-accounts
    for prefix, code in WHOLE.items():
        if journal_id.startswith(prefix):
            return [(code, cents)]
    if journal_id.startswith("j-expense-compliance-base-"):
        return _split(cents, COMPLIANCE_BASE_SPLIT)
    if journal_id.startswith("j-expenses-"):
        shares = seed_ddb.SUBLEDGER_SPLIT.get(account) or EXTRA_SPLIT.get(account)
        return _split(cents, shares) if shares else None
    if journal_id.startswith("j-card-"):
        from handlers.transactions import categorize

        memo = line.get("memo") or ""
        description = memo.partition("\nCategory reason: ")[0].removeprefix("Card: ")
        code = categorize(description, vendors)[0]
        return [(code, cents)] if coa.get(code).parent and coa.category(code) == account else None
    return None


def plan(ledger_items, vendors):
    """Journals to rewrite: [{journalId, old: [items], lines: [{account, debit|credit}]}]."""
    journals = {}
    for item in ledger_items:
        journals.setdefault(item["journalId"], []).append(item)
    out = []
    for jid, items in sorted(journals.items()):
        items = sorted(items, key=lambda i: int(i["lineNo"]))
        lines, changed = [], False
        for it in items:
            debit, credit = int(it.get("debit") or 0), int(it.get("credit") or 0)
            new = _recode_line(jid, it, vendors) if debit and str(it["account"]).startswith("6") else None
            if new is None:
                lines.append({"account": str(it["account"]), **({"debit": debit} if debit else {"credit": credit})})
            else:
                changed = True
                lines += [{"account": code, "debit": cents} for code, cents in new if cents]
        if changed:
            before = sum(int(i.get("debit") or 0) for i in items)
            assert sum(l.get("debit", 0) for l in lines) == before, jid
            out.append({"journalId": jid, "old": items, "lines": lines})
    return out


def apply(practice_id, rewrite):
    from shared import ddb, ledger

    first = rewrite["old"][0]
    built = ledger.build_journal(rewrite["journalId"], first["date"], rewrite["lines"], first.get("memo"),
                                 first.get("sourceDocId"), first.get("sourceType"), first.get("sourceId"))
    name = ddb.table().name
    s = lambda d: d  # the table resource's client serializes Python values itself, as post_journal relies on
    new_sks = {ledger.line_sk(line) for line in built}
    old_by_sk = {i["SK"]: i for i in rewrite["old"]}
    ops = [{"Delete": {"TableName": name, "Key": s({"PK": i["PK"], "SK": i["SK"]}),
                       "ConditionExpression": "account = :a",
                       "ExpressionAttributeValues": s({":a": i["account"]})}}
           for i in rewrite["old"] if i["SK"] not in new_sks]
    for line in built:
        item = {**line, "PK": ddb.pk(practice_id), "SK": ledger.line_sk(line),
                "createdAt": first.get("createdAt"), "migratedAt": ddb.now_iso()}
        put = {"TableName": name, "Item": s(ledger.to_ddb_keep_nulls(item))}
        prev = old_by_sk.get(item["SK"])
        if prev:  # overwrite only the exact line that was read
            put.update(ConditionExpression="account = :a", ExpressionAttributeValues=s({":a": prev["account"]}))
        else:
            put["ConditionExpression"] = "attribute_not_exists(SK)"
        ops.append({"Put": put})
    ddb.table().meta.client.transact_write_items(TransactItems=ops)


def vendor_updates(vendors):
    from shared import coa

    out = []
    for v in vendors:
        target, current = VENDOR_DEFAULTS.get(v.get("name")), str(v.get("defaultGlAccount") or "")
        if target and coa.is_expense(current) and not coa.get(current).parent and coa.category(target) == current:
            out.append((v, target))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--practice", default="p1")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    os.environ["TABLE_NAME"] = args.table
    from shared import coa, ddb, repo

    ledger_items = ddb.query_prefix(args.practice, "LEDGER#")
    vendors = repo.list_vendors(args.practice)
    rewrites, vupdates = plan(ledger_items, vendors), vendor_updates(vendors)
    by_code = {}
    for r in rewrites:
        for line in r["lines"]:
            if coa.get(line["account"]).parent:
                by_code[line["account"]] = by_code.get(line["account"], 0) + line.get("debit", 0)
    print(f"{len(rewrites)} journals to re-code ({len(ledger_items)} ledger lines read); "
          f"{len(vupdates)} vendor defaults to update.")
    for code in sorted(by_code):
        print(f"  {code} {coa.name(code):<28} ${by_code[code] / 100:>12,.2f}")
    for v, code in vupdates:
        print(f"  vendor {v['name']}: {v.get('defaultGlAccount')} -> {code}")
    if not args.execute:
        print("Preview only. Re-run with --execute to apply.")
        return
    # Vendors first: card charges categorized by vendor memory follow the vendor's new sub-account.
    for v, code in vupdates:
        repo.update_vendor(args.practice, v["vendorId"], defaultGlAccount=code)
    for r in plan(ledger_items, repo.list_vendors(args.practice)):
        apply(args.practice, r)
    print("Done.")


if __name__ == "__main__":
    main()

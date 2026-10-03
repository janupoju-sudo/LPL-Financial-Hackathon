"""migrate_subledgers.py re-codes category-coded history to sub-accounts without changing totals."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import migrate_subledgers as mig  # noqa: E402
from financials import statements  # noqa: E402
from shared import ddb, ledger, repo  # noqa: E402


def _post_old_history():
    # The layout live data has: monthly aggregate on category codes, rent/compliance journals, a card charge.
    ledger.post_journal("p1", "j-expenses-2026-08", "2026-08-31",
                        [{"account": "6100", "debit": 8_600_000}, {"account": "6700", "debit": 290_000},
                         {"account": "6200", "debit": 980_000}, {"account": "2000", "credit": 9_870_000}],
                        "Operating expenses 2026-08", source_type="seed")
    ledger.post_journal("p1", "j-expense-rent-2026-08", "2026-08-31",
                        [{"account": "6200", "debit": 1_220_000}, {"account": "2000", "credit": 1_220_000}],
                        "Rent expense 2026-08", source_doc_id="doc_lease", source_type="seed", source_id="doc_lease")
    ledger.post_journal("p1", "j-expense-compliance-base-2026-08", "2026-08-31",
                        [{"account": "6600", "debit": 310_000}, {"account": "2000", "credit": 310_000}],
                        "compliance-base 2026-08", source_type="seed")
    ledger.post_journal("p1", "j-card-t1", "2026-09-12",
                        [{"account": "6700", "debit": 42_000}, {"account": "2100", "credit": 42_000}],
                        "Card: DELTA AIR 0062345\nCategory reason: old", source_type="card", source_id="t1")


def _entries():
    return ddb.get_ledger_entries("p1", "2026-01-01", "2026-12-31")


def test_migration_recodes_and_keeps_totals(aws):
    _post_old_history()
    repo.create_vendor("p1", "Orion Software LLC", default_gl_account="6300")
    before = statements.profit_and_loss(_entries(), "2026-Q3")

    rewrites = mig.plan(ddb.query_prefix("p1", "LEDGER#"), repo.list_vendors("p1"))
    assert {r["journalId"] for r in rewrites} == {
        "j-expenses-2026-08", "j-expense-rent-2026-08", "j-expense-compliance-base-2026-08", "j-card-t1"}
    for r in rewrites:
        mig.apply("p1", r)
    for v, code in mig.vendor_updates(repo.list_vendors("p1")):
        repo.update_vendor("p1", v["vendorId"], defaultGlAccount=code)

    entries = _entries()
    statements.check_balanced(entries)
    after = statements.profit_and_loss(entries, "2026-Q3")
    assert after["totalExpenses"] == before["totalExpenses"]
    assert [(l["account"], l["amount"]) for l in after["expenses"]] == [(l["account"], l["amount"]) for l in before["expenses"]]
    travel = next(l for l in after["expenses"] if l["account"] == "6700")
    assert "Airfare" in [c["name"] for c in travel["children"]]
    assert "General" not in [c["name"] for l in after["expenses"] for c in l["children"]]
    rent = next(l for l in after["expenses"] if l["account"] == "6200")
    assert {c["account"] for c in rent["children"]} == {"6210", "6220"}
    card = [e for e in entries if e["journalId"] == "j-card-t1" and e["debit"]]
    assert [e["account"] for e in card] == ["6710"]
    assert card[0]["memo"].startswith("Card: DELTA AIR")
    assert repo.list_vendors("p1")[0]["defaultGlAccount"] == "6310"


def test_running_twice_finds_nothing(aws):
    _post_old_history()
    for r in mig.plan(ddb.query_prefix("p1", "LEDGER#"), []):
        mig.apply("p1", r)
    assert mig.plan(ddb.query_prefix("p1", "LEDGER#"), []) == []

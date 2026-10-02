import pytest

from shared import ddb, ledger


def test_cents_conversion():
    assert ledger.to_cents(1240) == 124000 and ledger.to_cents("45.105") == 4511 and ledger.to_cents(0.1) == 10


def test_unbalanced_journal_rejected():
    with pytest.raises(ledger.LedgerError):
        ledger.build_journal("j1", "2026-09-01", [{"account": "6300", "debit": 1000}, {"account": "2000", "credit": 900}], "x")


def test_float_amounts_rejected():
    with pytest.raises(ledger.LedgerError):
        ledger.build_journal("j1", "2026-09-01", [{"account": "6300", "debit": 10.5}, {"account": "2000", "credit": 10.5}], "x")


def test_unknown_account_rejected():
    with pytest.raises(ledger.LedgerError):
        ledger.build_journal("j1", "2026-09-01", ledger.bill_accrual_lines(10, "9999"), "x")


def test_post_idempotent_and_read_back_for_financials(aws):
    for _ in range(2):  # a Step Functions retry posts twice -> written once
        ledger.post_journal("p1", "j-b1-accrual", "2026-09-10", ledger.bill_accrual_lines(1240, "6300"),
                            "Brightline IT Services INV-2291", source_doc_id="d123")
    ledger.post_journal("p1", "j-b1-payment", "2026-09-20", ledger.bill_payment_lines(1240), "Mock ACH", "d123")
    ledger.post_journal("p1", "j-payout-1", "2026-09-30",
                        ledger.payout_lines({"advisory": 41000, "commission": 3200.50, "trail": 1875.25}),
                        "LPL payout Sep", source_doc_id="d999")
    ledger.post_journal("p1", "j-opening", "2026-06-30",
                        [{"account": "1000", "debit": 5000000}, {"account": "3000", "credit": 5000000}], "Opening")

    q3 = ddb.get_ledger_entries("p1", "2026-07-01", "2026-09-30")
    assert len(q3) == 2 + 2 + 4                                  # opening balance (June) excluded
    assert all(isinstance(l["debit"], int) and isinstance(l["credit"], int) for l in q3)
    line = next(l for l in q3 if l["journalId"] == "j-b1-accrual" and l["account"] == "6300")
    assert line == {"journalId": "j-b1-accrual", "lineNo": 1, "date": "2026-09-10", "account": "6300",
                    "debit": 124000, "credit": 0, "sourceDocId": "d123",
                    "memo": "Brightline IT Services INV-2291", "sourceType": None, "sourceId": None}

    bal = ledger.account_balances(q3)
    assert bal["6300"] == 124000 and bal["2000"] == 0
    assert bal["1000"] == 4607575 - 124000 and bal["4300"] == -187525
    assert sum(bal.values()) == 0

    sep_only = ddb.get_ledger_entries("p1", "2026-09-15", "2026-09-30")
    assert {l["journalId"] for l in sep_only} == {"j-b1-payment", "j-payout-1"}


def test_get_practice(aws):
    ddb.put_item("p1", "META", {"name": "Harbor Point Wealth", "clientCount": 180, "top10Share": 0.22})
    p = ddb.get_practice("p1")
    assert p["clientCount"] == 180 and p["top10Share"] == 0.22 and "PK" not in p


def test_revenue_lines_and_practice_meta(aws):
    from shared import ddb, repo
    ddb.put_item("p1", "META", {"clientCount": 180, "top10Share": 0.22, "feeSchedule": [
        {"id": "va-4471", "source": "trail", "ref": "4471", "basis": "aum",
         "aum": 115600000, "annualRate": 0.01, "frequency": "quarterly"}]})
    meta = ddb.get_practice("p1")
    item = meta["feeSchedule"][0]
    assert meta["clientCount"] == 180 and meta["top10Share"] == 0.22
    assert item["aum"] == 115600000 and isinstance(item["aum"], int) and item["annualRate"] == 0.01

    repo.put_revenue_lines("p1", "2026-09", "d3", [
        {"source": "advisory", "label": "Advisory fees", "actual": 18240000},
        {"source": "trail", "ref": "4471", "label": "VA trail 4471", "actual": 247800}])
    repo.put_revenue_lines("p1", "2026-08", "d2", [{"source": "advisory", "actual": 18240000}])
    repo.put_revenue_lines("p1", "2026-09", "d3", [   # re-ingest overwrites, no duplicates
        {"source": "advisory", "label": "Advisory fees", "actual": 18240000},
        {"source": "trail", "ref": "4471", "label": "VA trail 4471", "actual": 247800}])

    sep = ddb.get_revenue_lines("p1", "2026-09")
    assert [(l["id"], l["actual"], l["docId"]) for l in sep] == [("d3-01", 18240000, "d3"), ("d3-02", 247800, "d3")]
    assert all(isinstance(l["actual"], int) for l in sep)
    assert len(ddb.get_revenue_lines("p1", "2026-Q3")) == 3
    with pytest.raises(ValueError):
        repo.put_revenue_lines("p1", "2026-09", "d4", [{"source": "trail", "actual": 2478.00}])

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reset_demo
from shared import ddb, ledger, repo


def _put_document(practice_id, document_id, key, uploaded_by="demo-user"):
    return ddb.put_item(practice_id, f"DOC#{document_id}", {
        "documentId": document_id,
        "filename": f"{document_id}.pdf",
        "contentType": "application/pdf",
        "s3Key": key,
        "status": "processed",
        "type": "invoice",
        "uploadedBy": uploaded_by,
    })


def _seed_practice(practice_id):
    ddb.put_item(practice_id, "META", {"name": "Preserve me", "feeSchedule": [{"id": "schedule-1"}]})
    repo.put_rule(practice_id, {"ruleId": "rule-preserve", "name": "Preserve rule"})
    brightline = repo.create_vendor(
        practice_id,
        "Brightline Marketing",
        default_gl_account="6500",
        hasW9=True,
        hasVoidCheck=True,
        bankLast4="6789",
        billCount=1,
    )
    orion = repo.create_vendor(
        practice_id, "Orion Software LLC", default_gl_account="6300", hasW9=True, hasVoidCheck=True
    )

    _put_document(practice_id, "doc-source-history", "seed-sources/p1/doc-source-history/history.pdf",
                  uploaded_by="role-e-seed")
    _put_document(practice_id, "doc-source-fallback", "seed-sources/p1/doc-source-fallback/september.pdf",
                  uploaded_by="role-e-seed")
    _put_document(practice_id, "doc-live-bill", f"uploads/{practice_id}/doc-live-bill/invoice.pdf")
    _put_document(practice_id, "doc-live-receipt", f"uploads/{practice_id}/doc-live-receipt/receipt.pdf")
    _put_document(practice_id, "doc-live-payout", f"uploads/{practice_id}/doc-live-payout/payout.pdf")

    repo.put_bill(practice_id, {
        "billId": "bill_demo_1",
        "documentId": "doc-live-bill",
        "vendorId": brightline["vendorId"],
        "status": "scheduled",
        "amount": 450,
    })
    ledger.post_journal(
        practice_id, "j-bill_demo_1-accrual", "2026-09-10",
        ledger.bill_accrual_lines(450, "6500"), "Demo bill accrual",
        source_doc_id="doc-live-bill", source_type="bill", source_id="bill_demo_1",
    )
    ledger.post_journal(
        practice_id, "j-bill_demo_1-payment", "2026-09-20",
        ledger.bill_payment_lines(450), "Demo bill payment",
        source_doc_id="doc-live-bill", source_type="bill_payment", source_id="bill_demo_1",
    )
    ledger.post_journal(
        practice_id, "j-card-demo", "2026-09-21",
        ledger.card_spend_lines(20, "6700"), "Demo receipt-linked card spend",
        source_doc_id="doc-live-receipt", source_type="card", source_id="txn-demo",
    )
    ledger.post_journal(
        practice_id, "j-payout-doc-live-payout", "2026-09-30",
        ledger.payout_lines({"trail": 2_478}), "Live September payout",
        source_doc_id="doc-live-payout", source_type="payout", source_id="doc-live-payout",
    )
    ledger.post_journal(
        practice_id, "j-payout-2026-09", "2026-09-30",
        ledger.payout_lines({"trail": 2_478}), "Seeded fallback payout",
        source_doc_id="doc-source-fallback", source_type="seed", source_id="doc-source-fallback",
    )

    # These seed-owned entries and revenue lines are baseline, not demo cleanup targets.
    ledger.post_journal(
        practice_id, "j-payout-2026-08", "2026-08-31",
        ledger.payout_lines({"advisory": 100}), "August seeded history",
        source_doc_id="doc-source-history", source_type="seed", source_id="doc-source-history",
    )
    ledger.post_journal(
        practice_id, "j-expenses-2026-09", "2026-09-30",
        ledger.bill_accrual_lines(100, "6100"), "September baseline expense",
        source_type="seed",
    )
    ledger.post_journal(
        practice_id, "j-exp-paid-2026-09", "2026-09-30",
        ledger.bill_payment_lines(100), "September baseline expense payment",
        source_type="seed",
    )
    repo.put_revenue_lines(practice_id, "2026-08", "doc-source-history", [
        {"source": "advisory", "label": "August seeded revenue", "actual": 10_000}
    ])
    repo.put_revenue_lines(practice_id, "2026-09", "doc-live-payout", [
        {"source": "trail", "ref": "4471", "label": "Live payout", "actual": 247_800}
    ])
    repo.put_revenue_lines(practice_id, "2026-09", "doc-source-fallback", [
        {"source": "trail", "ref": "4471", "label": "Fallback payout", "actual": 247_800}
    ])
    return brightline, orion


def _items(practice_id, prefix):
    return ddb.query_prefix(practice_id, prefix)


def test_default_reset_is_a_dry_run(aws, capsys):
    _seed_practice("p1")
    before_bills = _items("p1", "BILL#")
    before_docs = _items("p1", "DOC#")
    before_ledger = _items("p1", "LEDGER#")
    before_revenue = _items("p1", "REV#")

    plan, deleted = reset_demo.reset_demo("p1")

    assert deleted is None
    assert len(plan["bills"]) == 1
    assert len(plan["demo_documents"]) == 3
    assert _items("p1", "BILL#") == before_bills
    assert _items("p1", "DOC#") == before_docs
    assert _items("p1", "LEDGER#") == before_ledger
    assert _items("p1", "REV#") == before_revenue

    reset_demo.print_preview(plan)
    assert "Dry-run reset preview" in capsys.readouterr().out


def test_execute_is_practice_scoped_and_preserves_baseline_and_sources(aws):
    brightline, orion = _seed_practice("p1")
    _seed_practice("p2")
    meta_before = ddb.get_item("p1", "META")
    rule_before = repo.get_rule("p1", "rule-preserve")
    august_revenue_before = ddb.get_revenue_lines("p1", "2026-08")
    p2_before = {
        prefix: _items("p2", prefix)
        for prefix in ("META", "RULE#", "VENDOR#", "BILL#", "DOC#", "LEDGER#", "REV#")
    }

    plan, deleted = reset_demo.reset_demo("p1", execute=True)

    assert deleted["bills"] == 1
    assert deleted["documents"] == 3
    assert deleted["revenue_lines"] == 2
    assert repo.list_bills("p1") == []
    assert {doc["documentId"] for doc in repo.list_documents("p1")} == {
        "doc-source-history", "doc-source-fallback"
    }
    assert ddb.get_item("p1", "META") == meta_before
    assert repo.get_rule("p1", "rule-preserve") == rule_before
    assert repo.get_vendor("p1", orion["vendorId"])["hasW9"] is True
    assert repo.get_vendor("p1", orion["vendorId"])["hasVoidCheck"] is True
    reset_brightline = repo.get_vendor("p1", brightline["vendorId"])
    assert reset_brightline["hasW9"] is False
    assert reset_brightline["hasVoidCheck"] is False
    assert reset_brightline["billCount"] == 0
    assert "bankLast4" not in reset_brightline

    p1_ledger = _items("p1", "LEDGER#")
    preserved_journals = {item["journalId"] for item in p1_ledger}
    assert preserved_journals == {
        "j-payout-2026-08", "j-expenses-2026-09", "j-exp-paid-2026-09"
    }
    assert ddb.get_revenue_lines("p1", "2026-08") == august_revenue_before
    assert ddb.get_revenue_lines("p1", "2026-09") == []
    for prefix, items in p2_before.items():
        assert _items("p2", prefix) == items


def test_repeated_execute_is_idempotent(aws):
    _seed_practice("p1")

    _, first_deleted = reset_demo.reset_demo("p1", execute=True)
    _, second_deleted = reset_demo.reset_demo("p1", execute=True)

    assert first_deleted["bills"] == 1
    assert first_deleted["documents"] == 3
    assert all(count == 0 for count in second_deleted.values())
    assert {doc["documentId"] for doc in repo.list_documents("p1")} == {
        "doc-source-history", "doc-source-fallback"
    }


@pytest.mark.parametrize("status", ["processing", "pending_approval", "pending_docs", "approved"])
def test_execute_refuses_active_bill_workflows_before_mutation(aws, status):
    _seed_practice("p1")
    repo.update_bill("p1", "bill_demo_1", set_fields={"status": status})
    docs_before = _items("p1", "DOC#")

    with pytest.raises(RuntimeError, match="Active bills must finish"):
        reset_demo.reset_demo("p1", execute=True)

    assert len(repo.list_bills("p1")) == 1
    assert _items("p1", "DOC#") == docs_before


def test_cli_requires_explicit_table_and_practice(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["reset_demo.py", "--execute"])

    with pytest.raises(SystemExit) as error:
        reset_demo.main()

    assert error.value.code == 2


def test_cli_without_execute_only_previews(aws, monkeypatch, capsys):
    _seed_practice("p1")
    before = {
        prefix: _items("p1", prefix)
        for prefix in ("BILL#", "DOC#", "LEDGER#", "REV#", "VENDOR#")
    }
    monkeypatch.setattr(sys, "argv", [
        "reset_demo.py", "--table", "ledgerline-test", "--practice", "p1"
    ])

    reset_demo.main()

    assert "Dry-run reset preview" in capsys.readouterr().out
    for prefix, items in before.items():
        assert _items("p1", prefix) == items
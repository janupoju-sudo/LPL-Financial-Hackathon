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


def _seed_combined_compliance(practice_id, month, amount=5_650):
    tag = f"2026-{month:02d}"
    entry_date = f"{tag}-{30 if month == 9 else 31}"
    document_id = f"doc_compliance_invoice_2026_{month:02d}"
    ddb.put_item(practice_id, f"DOC#{document_id}", {
        "documentId": document_id, "amount": 2_550, "type": "invoice",
        "s3Key": f"seed-sources/{practice_id}/{document_id}/invoice.pdf",
        "uploadedBy": "role-e-seed", "status": "processed",
    })
    ledger.post_journal(
        practice_id, f"j-expense-compliance-{tag}", entry_date,
        ledger.bill_accrual_lines(amount, "6600"), "Legacy combined compliance",
        source_doc_id=document_id, source_type="seed", source_id=document_id,
    )
    ledger.post_journal(
        practice_id, f"j-expense-paid-compliance-{tag}", entry_date,
        ledger.bill_payment_lines(amount), "Legacy combined compliance payment",
        source_doc_id=document_id, source_type="seed", source_id=document_id,
    )


def test_compliance_migration_preserves_totals_sources_and_other_practice(aws):
    _seed_practice("p1")
    _seed_practice("p2")
    for month in (7, 8, 9):
        _seed_combined_compliance("p1", month)
        _seed_combined_compliance("p2", month)
    before_ledger = _items("p1", "LEDGER#")
    balances_before = ledger.account_balances(before_ledger)
    preserved_before = {prefix: _items("p1", prefix)
                        for prefix in ("META", "DOC#", "BILL#", "VENDOR#", "RULE#", "REV#")}
    other_before = _items("p2", "LEDGER#")

    plan = reset_demo.build_compliance_migration_plan("p1")
    assert [month["period"] for month in plan["months"]] == ["2026-07", "2026-08", "2026-09"]
    assert _items("p1", "LEDGER#") == before_ledger  # preview is read-only
    assert reset_demo.execute_compliance_migration(plan) == ["2026-07", "2026-08", "2026-09"]

    after = _items("p1", "LEDGER#")
    assert ledger.account_balances(after) == balances_before
    assert _items("p2", "LEDGER#") == other_before
    for prefix, items in preserved_before.items():
        assert _items("p1", prefix) == items
    for month in (7, 8, 9):
        tag = f"2026-{month:02d}"
        assert not any(line["journalId"] in {
            f"j-expense-compliance-{tag}", f"j-expense-paid-compliance-{tag}"
        } for line in after)
        base = [line for line in after if line["journalId"] == f"j-expense-compliance-base-{tag}"]
        consultant = [line for line in after
                      if line["journalId"] == f"j-expense-compliance-consultant-{tag}"]
        assert sum(line["debit"] for line in base) == 310_000
        assert sum(line["debit"] for line in consultant) == 255_000
        assert all(line["sourceDocId"] is None for line in base)
        assert all(line["sourceDocId"] == f"doc_compliance_invoice_2026_{month:02d}"
                   for line in consultant)
    repeat = reset_demo.build_compliance_migration_plan("p1")
    assert repeat["months"] == []
    assert reset_demo.execute_compliance_migration(repeat) == []
    assert _items("p1", "LEDGER#") == after


def test_compliance_migration_preflights_all_months_before_any_write(aws):
    _seed_combined_compliance("p1", 7)
    _seed_combined_compliance("p1", 8, amount=5_000)
    before = _items("p1", "LEDGER#")
    with pytest.raises(RuntimeError, match="not the expected"):
        reset_demo.build_compliance_migration_plan("p1")
    assert _items("p1", "LEDGER#") == before


def test_compliance_migration_refuses_partial_or_mixed_journals(aws):
    _seed_combined_compliance("p1", 7)
    ledger.post_journal(
        "p1", "j-expense-compliance-base-2026-07", "2026-07-31",
        ledger.bill_accrual_lines(3_100, "6600"), "Partial split", source_type="seed",
    )
    before = _items("p1", "LEDGER#")
    with pytest.raises(RuntimeError, match="both combined and split"):
        reset_demo.build_compliance_migration_plan("p1")
    assert _items("p1", "LEDGER#") == before


def test_compliance_migration_requires_matching_consultant_document(aws):
    _seed_combined_compliance("p1", 7)
    ddb.update_item("p1", "DOC#doc_compliance_invoice_2026_07", set_fields={"amount": 3_100})
    with pytest.raises(RuntimeError, match="matching"):
        reset_demo.build_compliance_migration_plan("p1")


def test_compliance_migration_refuses_older_aggregate_layout(aws):
    ledger.post_journal(
        "p1", "j-expenses-2026-07", "2026-07-31",
        ledger.bill_accrual_lines(5_650, "6600"), "Old aggregate", source_type="seed",
    )
    with pytest.raises(RuntimeError, match="older aggregate"):
        reset_demo.build_compliance_migration_plan("p1")


def test_compliance_transaction_refuses_changed_rows_without_partial_deletion(aws):
    _seed_combined_compliance("p1", 7)
    plan = reset_demo.build_compliance_migration_plan("p1")
    row = next(line for line in plan["months"][0]["old"] if line["account"] == "6600")
    ddb.update_item("p1", row["SK"], set_fields={"debit": 565_001})
    before = _items("p1", "LEDGER#")
    with pytest.raises(RuntimeError, match="changed after preview"):
        reset_demo.execute_compliance_migration(plan)
    assert _items("p1", "LEDGER#") == before


def test_compliance_migration_refuses_active_workflows_and_cross_practice_plan(aws):
    _seed_combined_compliance("p1", 7)
    plan = reset_demo.build_compliance_migration_plan("p1")
    plan["months"][0]["new"][0]["PK"] = "PRACTICE#p2"
    before = _items("p1", "LEDGER#")
    with pytest.raises(RuntimeError, match="outside the selected practice"):
        reset_demo.execute_compliance_migration(plan)
    assert _items("p1", "LEDGER#") == before
    plan = reset_demo.build_compliance_migration_plan("p1")
    repo.put_bill("p1", {"billId": "active", "status": "pending_docs"})
    with pytest.raises(RuntimeError, match="Active bill workflows"):
        reset_demo.execute_compliance_migration(plan)
    assert _items("p1", "LEDGER#") == before


def test_compliance_migration_cli_defaults_to_preview_without_demo_cleanup(aws, monkeypatch, capsys):
    _seed_practice("p1")
    _seed_combined_compliance("p1", 7)
    before = {prefix: _items("p1", prefix) for prefix in ("DOC#", "BILL#", "LEDGER#", "REV#")}
    monkeypatch.setattr(sys, "argv", [
        "reset_demo.py", "--table", "ledgerline-test", "--practice", "p1", "--migrate-compliance"
    ])
    reset_demo.main()
    assert "Compliance migration preview" in capsys.readouterr().out
    for prefix, items in before.items():
        assert _items("p1", prefix) == items


def test_compliance_migration_resumes_after_an_interrupted_month(aws, monkeypatch):
    from botocore.exceptions import ClientError

    for month in (7, 8, 9):
        _seed_combined_compliance("p1", month)
    before_balances = ledger.account_balances(_items("p1", "LEDGER#"))
    client = ddb.table().meta.client
    real_transaction = client.transact_write_items
    calls = 0

    def interrupt_second_month(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ClientError({"Error": {"Code": "TransactionCanceledException"}}, "TransactWriteItems")
        return real_transaction(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(client, "transact_write_items", interrupt_second_month)
        with pytest.raises(RuntimeError, match="2026-08 changed"):
            reset_demo.execute_compliance_migration(reset_demo.build_compliance_migration_plan("p1"))
    repeat = reset_demo.build_compliance_migration_plan("p1")
    assert repeat["already_split"] == ["2026-07"]
    assert reset_demo.execute_compliance_migration(repeat) == ["2026-08", "2026-09"]
    assert ledger.account_balances(_items("p1", "LEDGER#")) == before_balances


def test_migration_unblocks_new_seed_without_duplicate_compliance(aws, monkeypatch):
    import seed_ddb

    for month in (7, 8, 9):
        _seed_combined_compliance("p1", month)
    with pytest.raises(RuntimeError, match="combined compliance"):
        seed_ddb.seed("p1", live_sept=True)
    reset_demo.execute_compliance_migration(reset_demo.build_compliance_migration_plan("p1"))
    # S3 uploads belong to the seed owner; this test exercises only ledger compatibility.
    monkeypatch.setattr(seed_ddb, "upload_source_pdfs", lambda documents, bucket: 0)
    seed_ddb.seed("p1", live_sept=True, docs_bucket="test-docs")
    seed_ddb.seed("p1", live_sept=True, docs_bucket="test-docs")
    for month in (7, 8, 9):
        entries = _items("p1", f"LEDGER#2026-{month:02d}#")
        assert sum(line["debit"] for line in entries if line["account"] == "6600") == 565_000
    assert ddb.get_revenue_lines("p1", "2026-09") == []

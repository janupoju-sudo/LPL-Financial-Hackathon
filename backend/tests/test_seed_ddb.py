from collections import defaultdict
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_ddb
from conftest import api_event
from handlers import documents as documents_handler
from shared import ddb, ledger, repo


def test_seed_source_keys_cannot_match_template_upload_trigger():
    documents = seed_ddb.source_documents("p1", include_sept=True)
    keys = [document["s3Key"] for document in documents]
    template = (Path(__file__).resolve().parents[1] / "template.yaml").read_text()

    assert len(keys) == 17
    assert "prefix: uploads/" in template
    assert all(key.startswith("seed-sources/p1/") for key in keys)
    assert all(not key.startswith("uploads/") for key in keys)


def test_expenses_are_year_aware_and_preserve_historical_values():
    june = seed_ddb.expenses_for(2026, 6)
    july = seed_ddb.expenses_for(2026, 7)
    september = seed_ddb.expenses_for(2026, 9)

    assert june["6200"] == 9_800
    assert june["6600"] == 3_100
    assert seed_ddb.expenses_for(2025, 12)["6100"] == 111_000
    assert july["6200"] == 12_200
    assert july["6600"] == 5_650
    assert september["6200"] == 12_200
    assert september["6600"] == 5_650
    assert september["6500"] == 9_360


def test_live_september_has_expenses_and_payments_but_no_payout_or_rev(aws):
    seed_ddb.seed("p1", live_sept=True)
    first_entries = ddb.get_ledger_entries("p1", "2026-09-01", "2026-09-30")
    seed_ddb.seed("p1", live_sept=True)
    second_entries = ddb.get_ledger_entries("p1", "2026-09-01", "2026-09-30")

    assert len(first_entries) == len(second_entries)
    journal_ids = {line["journalId"] for line in second_entries}
    assert "j-expense-rent-2026-09" in journal_ids
    assert "j-expense-paid-rent-2026-09" in journal_ids
    assert "j-expense-compliance-base-2026-09" in journal_ids
    assert "j-expense-paid-compliance-base-2026-09" in journal_ids
    assert "j-expense-compliance-consultant-2026-09" in journal_ids
    assert "j-expense-paid-compliance-consultant-2026-09" in journal_ids
    assert "j-payout-2026-09" not in journal_ids
    assert ddb.get_revenue_lines("p1", "2026-09") == []

    rent_line = next(line for line in second_entries
                     if line["journalId"] == "j-expense-rent-2026-09" and line["account"] == "6200")
    compliance_base_line = next(line for line in second_entries
                                if line["journalId"] == "j-expense-compliance-base-2026-09"
                                and line["account"] == "6600")
    compliance_consultant_line = next(
        line for line in second_entries
        if line["journalId"] == "j-expense-compliance-consultant-2026-09"
        and line["account"] == "6600"
    )
    assert rent_line["debit"] == 1_220_000
    assert compliance_base_line["debit"] == 310_000
    assert compliance_consultant_line["debit"] == 255_000
    assert rent_line["sourceDocId"] == seed_ddb.LEASE_DOC_ID
    assert compliance_base_line["sourceDocId"] is None
    assert compliance_consultant_line["sourceDocId"] == seed_ddb.compliance_doc_id(2026, 9)
    assert repo.get_document("p1", seed_ddb.LEASE_DOC_ID)["amount"] == 12_200
    compliance_doc = repo.get_document("p1", seed_ddb.compliance_doc_id(2026, 9))
    assert compliance_doc["status"] == "pending_upload"
    assert compliance_doc["amount"] == 2_550
    paid_compliance = next(
        line for line in second_entries
        if line["journalId"] == "j-expense-paid-compliance-consultant-2026-09"
    )
    assert paid_compliance["debit"] == 255_000
    assert paid_compliance["sourceDocId"] == compliance_doc["documentId"]


def test_document_detail_signs_seed_source_key(aws, monkeypatch):
    source_doc = seed_ddb.source_documents("p1")[0]
    ddb.put_item("p1", f"DOC#{source_doc['documentId']}", source_doc)
    signed = {}

    class FakeS3:
        def generate_presigned_url(self, operation, Params, ExpiresIn):
            signed.update(operation=operation, **Params)
            return "https://example.invalid/signed-source"

    monkeypatch.setattr(documents_handler, "s3", lambda: FakeS3())
    status, body = documents_handler.get_doc(
        api_event("GET /documents/{id}", path={"id": source_doc["documentId"]})
    )

    assert status == 200
    assert body["viewUrl"] == "https://example.invalid/signed-source"
    assert signed["operation"] == "get_object"
    assert signed["Key"] == source_doc["s3Key"]
    assert signed["Key"].startswith("seed-sources/")
    template = (Path(__file__).resolve().parents[1] / "template.yaml").read_text()
    documents_function = template.split("  DocumentsFunction:", 1)[1].split("\n  VendorsFunction:", 1)[0]
    assert "S3CrudPolicy: { BucketName: !Ref DocsBucket }" in documents_function


def test_fallback_persists_four_revenue_lines_and_is_idempotent(aws):
    seed_ddb.seed("p1", include_sept=True)
    first_entries = ddb.get_ledger_entries("p1", "2026-09-01", "2026-09-30")
    seed_ddb.seed("p1", include_sept=True)
    second_entries = ddb.get_ledger_entries("p1", "2026-09-01", "2026-09-30")

    assert len(first_entries) == len(second_entries)
    revenue = ddb.get_revenue_lines("p1", "2026-09")
    assert len(revenue) == 4
    assert sum(line["actual"] for line in revenue) == 20_522_800
    va_line = next(line for line in revenue if line.get("ref") == "4471")
    assert va_line["actual"] == 247_800
    reconciliation = seed_ddb._fallback_reconciliation()
    va_result = next(line for line in reconciliation["lines"] if line.get("ref") == "4471")
    assert (va_result["expected"], va_result["actual"], va_result["variance"]) == (289_000, 247_800, -41_200)

    payout_lines = [line for line in second_entries if line["journalId"] == "j-payout-2026-09"]
    assert payout_lines
    assert all(line["sourceDocId"] == seed_ddb.SEPT_PAYOUT_DOC_ID for line in payout_lines)
    assert repo.get_document("p1", seed_ddb.SEPT_PAYOUT_DOC_ID)["status"] == "pending_upload"


def test_fallback_skips_when_live_september_payout_exists(aws):
    seed_ddb.seed("p1", live_sept=True)
    repo.put_revenue_lines("p1", "2026-09", "doc_live_sep", [
        {"source": "trail", "ref": "4471", "label": "Live VA trail", "actual": 247_800}
    ])
    live_revenue = ddb.get_revenue_lines("p1", "2026-09")
    ledger.post_journal(
        "p1", "j-payout-doc_live_sep", "2026-09-30",
        ledger.payout_lines({"trail": 2_478}), "Live payout",
        source_doc_id="doc_live_sep", source_type="payout", source_id="doc_live_sep",
    )

    seed_ddb.seed("p1", include_sept=True)

    assert ddb.get_revenue_lines("p1", "2026-09") == live_revenue
    assert repo.get_document("p1", seed_ddb.SEPT_PAYOUT_DOC_ID) is None
    assert not any(line["journalId"] == "j-payout-2026-09"
                   for line in ddb.get_ledger_entries("p1", "2026-09-01", "2026-09-30"))


def test_seed_rejects_legacy_combined_compliance_journal(aws):
    ledger.post_journal(
        "p1", "j-expense-compliance-2026-07", "2026-07-31",
        ledger.bill_accrual_lines(5_650, "6600"), "Legacy combined compliance",
    )

    with pytest.raises(RuntimeError, match="combined compliance journals"):
        seed_ddb.seed("p1", live_sept=True)

    july_entries = ddb.get_ledger_entries("p1", "2026-07-01", "2026-07-31")
    assert {line["journalId"] for line in july_entries} == {"j-expense-compliance-2026-07"}


def test_offline_checks_do_not_touch_dynamodb(monkeypatch):
    def fail_if_used():
        raise AssertionError("offline check called DynamoDB")

    monkeypatch.setattr(ddb, "table", fail_if_used)
    assert seed_ddb.check(include_sept=True)


def test_built_journals_balance_and_source_ids_are_stable():
    journals = seed_ddb.build(include_sept=True)
    balances = defaultdict(lambda: [0, 0])
    source_ids = {journal_id: source_doc_id for journal_id, _, _, _, source_doc_id in journals}

    for journal_id, entry_date, lines, memo, source_doc_id in journals:
        built = ledger.build_journal(journal_id, entry_date, lines, memo, source_doc_id)
        for line in built:
            balances[journal_id][0] += line["debit"]
            balances[journal_id][1] += line["credit"]

    assert all(debits == credits for debits, credits in balances.values())
    assert source_ids["j-expense-rent-2026-07"] == seed_ddb.LEASE_DOC_ID
    assert source_ids["j-expense-compliance-base-2026-07"] is None
    assert source_ids["j-expense-compliance-consultant-2026-07"] == seed_ddb.compliance_doc_id(2026, 7)
    assert source_ids["j-payout-2026-07"] == seed_ddb.payout_doc_id(2026, 7)

    journal_lines = defaultdict(list)
    for journal_id, _, lines, _, _ in journals:
        journal_lines[journal_id] = lines
    for month in (7, 8, 9):
        tag = f"2026-{month:02d}"
        base_id = f"j-expense-compliance-base-{tag}"
        consultant_id = f"j-expense-compliance-consultant-{tag}"
        base_amount = next(line["debit"] for line in journal_lines[base_id] if line["account"] == "6600")
        consultant_amount = next(line["debit"] for line in journal_lines[consultant_id]
                                 if line["account"] == "6600")
        base_payment = next(line["debit"] for line in journal_lines[f"j-expense-paid-compliance-base-{tag}"]
                            if line["account"] == "2000")
        consultant_payment = next(
            line["debit"] for line in journal_lines[f"j-expense-paid-compliance-consultant-{tag}"]
            if line["account"] == "2000"
        )
        assert (base_amount, consultant_amount) == (310_000, 255_000)
        assert (base_payment, consultant_payment) == (310_000, 255_000)

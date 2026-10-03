#!/usr/bin/env python3
"""Preview or clear one practice's demo bills, uploads, and related postings.

This script never deletes S3 objects, cancels workflows, or reseeds data. Stop
uploads and wait for all Step Functions executions for the practice to reach a
terminal state before using --execute.
"""
import argparse
import os
import sys
from calendar import monthrange

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

ACTIVE_BILL_STATUSES = {"processing", "pending_approval", "pending_docs", "approved"}
FALLBACK_PAYOUT_JOURNALS = {"j-payout-2026-09"}
SEPTEMBER_REVENUE_PREFIX = "REV#2026-09#"


def _is_seed_source(document):
    return (document.get("s3Key", "").startswith("seed-sources/")
            or document.get("uploadedBy") == "role-e-seed")


def _bill_id(bill):
    return bill.get("billId") or bill.get("SK", "").removeprefix("BILL#")


def _document_id(document):
    return document.get("documentId") or document.get("SK", "").removeprefix("DOC#")


def _is_demo_journal(line, bill_ids, document_ids):
    journal_id = line.get("journalId", "")
    if journal_id in FALLBACK_PAYOUT_JOURNALS:
        return True
    if line.get("sourceId") in bill_ids or line.get("sourceDocId") in document_ids:
        return True
    if line.get("sourceType") == "payout" and line.get("date", "").startswith("2026-09"):
        return True
    if line.get("sourceType") == "card":
        return True  # imported card charges: no seed creates them, so they're all rehearsal data
    return any(journal_id.startswith(f"j-{bill_id}-") for bill_id in bill_ids)


def build_reset_plan(practice_id):
    """Read one practice's paginated prefixes and build a non-mutating plan."""
    if not practice_id or not practice_id.strip():
        raise ValueError("practice_id must not be empty")

    from shared import ddb, repo

    all_bills = ddb.query_prefix(practice_id, "BILL#")
    # History bills from scripts/seed_bills.py carry seeded=True and are part of the baseline.
    seeded_bills = [bill for bill in all_bills if bill.get("seeded")]
    bills = [bill for bill in all_bills if not bill.get("seeded")]
    documents = ddb.query_prefix(practice_id, "DOC#")
    source_documents = [document for document in documents if _is_seed_source(document)]
    demo_documents = [document for document in documents if not _is_seed_source(document)]
    document_ids = {_document_id(document) for document in demo_documents}
    bill_ids = {_bill_id(bill) for bill in bills}

    ledger_lines = ddb.query_prefix(practice_id, "LEDGER#")
    demo_ledger_lines = [
        line for line in ledger_lines if _is_demo_journal(line, bill_ids, document_ids)
    ]
    september_revenue = ddb.query_prefix(practice_id, SEPTEMBER_REVENUE_PREFIX)
    brightline = repo.find_vendor_by_name(practice_id, "Brightline Marketing")
    active_bills = [bill for bill in bills if bill.get("status") in ACTIVE_BILL_STATUSES]

    return {
        "practice_id": practice_id,
        "bills": bills,
        "seeded_bills": seeded_bills,
        "demo_documents": demo_documents,
        "source_documents": source_documents,
        "demo_ledger_lines": demo_ledger_lines,
        "september_revenue": september_revenue,
        "brightline": brightline,
        "active_bills": active_bills,
    }


def print_preview(plan):
    """Print a deletion summary without making any writes."""
    ledger_journals = {line.get("journalId") for line in plan["demo_ledger_lines"]}
    print(f"Dry-run reset preview for practice {plan['practice_id']}:")
    print(f"  Demo bills to delete: {len(plan['bills'])}")
    print(f"  Uploaded demo documents to delete: {len(plan['demo_documents'])}")
    print(f"  Related ledger lines to delete: {len(plan['demo_ledger_lines'])} "
          f"across {len(ledger_journals)} journals")
    card_journals = {line.get("journalId") for line in plan["demo_ledger_lines"] if line.get("sourceType") == "card"}
    print(f"    (of which imported card charges: {len(card_journals)} journals)")
    print(f"  September 2026 revenue lines to delete: {len(plan['september_revenue'])}")
    print(f"  Seeded history bills to preserve: {len(plan.get('seeded_bills', []))}")
    print(f"  Supporting source documents to preserve: {len(plan['source_documents'])}")
    if plan["brightline"]:
        print("  Brightline Marketing: restore missing W-9/void-check state")
    else:
        print("  Brightline Marketing vendor not found; no vendor state will be changed")
    if plan["active_bills"]:
        active_ids = ", ".join(_bill_id(bill) for bill in plan["active_bills"])
        print(f"  BLOCKED until active bills finish: {active_ids}")
    print("  S3 objects: preserved; no seed script or workflow will be invoked")


def execute_reset(plan):
    """Apply a previously built plan, deleting DynamoDB keys only."""
    from shared import ddb

    if plan["active_bills"]:
        active_ids = ", ".join(_bill_id(bill) for bill in plan["active_bills"])
        raise RuntimeError(f"Active bills must finish before reset: {active_ids}")

    practice_id = plan["practice_id"]
    partition_key = ddb.pk(practice_id)
    delete_groups = (
        plan["demo_ledger_lines"],
        plan["september_revenue"],
        plan["demo_documents"],
        plan["bills"],
    )
    for group in delete_groups:
        for item in group:
            if item.get("PK") != partition_key:
                raise RuntimeError("Reset plan contains an item outside the selected practice")

    deleted = {"ledger_lines": 0, "revenue_lines": 0, "documents": 0, "bills": 0}
    table = ddb.table()
    with table.batch_writer() as batch:
        for group_name, items in zip(deleted, delete_groups):
            for item in items:
                batch.delete_item(Key={"PK": partition_key, "SK": item["SK"]})
                deleted[group_name] += 1

    brightline = plan["brightline"]
    if brightline:
        ddb.update_item(
            practice_id,
            f"VENDOR#{brightline['vendorId']}",
            set_fields={
                "hasW9": False,
                "hasVoidCheck": False,
                "billCount": 0,
                "updatedAt": ddb.now_iso(),
            },
            remove=["bankLast4", "lastSeen"],
        )
    return deleted


def reset_demo(practice_id, execute=False):
    """Build the preview; mutate only when execute is explicitly true."""
    plan = build_reset_plan(practice_id)
    deleted = execute_reset(plan) if execute else None
    return plan, deleted


def _compliance_journals(practice_id, year, month, split):
    """Expected seed-owned records, independent of the seed script/uploader."""
    from shared import coa, ddb, ledger

    tag = f"{year}-{month:02d}"
    entry_date = f"{tag}-{monthrange(year, month)[1]:02d}"
    consultant_doc = f"doc_compliance_invoice_{year}_{month:02d}"
    components = (("compliance-base", 310_000, None),
                  ("compliance-consultant", 255_000, consultant_doc)) if split else (
                      ("compliance", 565_000, consultant_doc),)
    journals = {}
    for label, cents, document_id in components:
        for paid, lines in (
            (False, [{"account": "6600", "debit": cents},
                     {"account": coa.ACCOUNTS_PAYABLE, "credit": cents}]),
            (True, [{"account": coa.ACCOUNTS_PAYABLE, "debit": cents},
                    {"account": coa.CASH, "credit": cents}]),
        ):
            journal_id = f"j-expense-{'paid-' if paid else ''}{label}-{tag}"
            records = ledger.build_journal(
                journal_id, entry_date, lines, f"{'Paid ' if paid else ''}{label} {tag}",
                source_doc_id=document_id, source_type="seed", source_id=document_id,
            )
            journals[journal_id] = [
                {**record, "PK": ddb.pk(practice_id), "SK": ledger.line_sk(record)}
                for record in records
            ]
    return journals


def _journal_matches(actual, expected, check_source=True):
    fields = ("PK", "SK", "journalId", "lineNo", "date", "account", "debit", "credit", "sourceType")
    if check_source:
        fields += ("sourceDocId", "sourceId")
    actual = sorted(actual, key=lambda line: line.get("SK", ""))
    expected = sorted(expected, key=lambda line: line["SK"])
    return len(actual) == len(expected) and all(
        all(left.get(field) == right.get(field) for field in fields)
        for left, right in zip(actual, expected)
    )


def build_compliance_migration_plan(practice_id):
    """Preview only the known combined July-September 2026 seed journals."""
    from shared import ddb, repo

    if not practice_id or not practice_id.strip():
        raise ValueError("practice_id must not be empty")
    active_bills = [bill for bill in ddb.query_prefix(practice_id, "BILL#")
                    if bill.get("status") in ACTIVE_BILL_STATUSES]
    migrations, already_split = [], []
    for month in (7, 8, 9):
        tag = f"2026-{month:02d}"
        # Reject the older aggregate layout: it is not this migration's target.
        aggregate = ddb.query_prefix(practice_id, f"LEDGER#{tag}#j-expenses-{tag}#")
        if any(line.get("account") in {"6200", "6600"} for line in aggregate):
            raise RuntimeError(f"{tag} has an older aggregate expense layout; manual review required")
        old_expected = _compliance_journals(practice_id, 2026, month, split=False)
        new_expected = _compliance_journals(practice_id, 2026, month, split=True)
        old = {jid: ddb.query_prefix(practice_id, f"LEDGER#{tag}#{jid}#")
               for jid in old_expected}
        new = {jid: ddb.query_prefix(practice_id, f"LEDGER#{tag}#{jid}#")
               for jid in new_expected}
        has_old = any(old.values())
        has_new = any(new.values())
        if not has_old:
            if has_new:
                if not all(_journal_matches(new[jid], expected)
                           for jid, expected in new_expected.items()):
                    raise RuntimeError(f"{tag} has incomplete or incompatible split journals")
                already_split.append(tag)
            continue
        if has_new:
            raise RuntimeError(f"{tag} has both combined and split journals; manual review required")
        if not all(_journal_matches(old[jid], expected, check_source=False)
                   for jid, expected in old_expected.items()):
            raise RuntimeError(f"{tag} combined journals are incomplete or not the expected $5,650")
        document_id = f"doc_compliance_invoice_2026_{month:02d}"
        document = repo.get_document(practice_id, document_id)
        if not document or document.get("amount") != 2_550:
            raise RuntimeError(f"{tag} requires the matching $2,550 consultant document")
        migrations.append({
            "period": tag,
            "old": [line for journal in old.values() for line in journal],
            "new": [line for journal in new_expected.values() for line in journal],
        })
    return {"practice_id": practice_id, "months": migrations,
            "already_split": already_split, "active_bills": active_bills}


def print_compliance_migration_preview(plan):
    print(f"Compliance migration preview for practice {plan['practice_id']}:")
    for month in plan["months"]:
        print(f"  {month['period']}: replace combined $5,650 accrual/payment with "
              "$3,100 base + $2,550 consultant accruals/payments (totals unchanged)")
    print(f"  Months to migrate: {len(plan['months'])}; already split: {len(plan['already_split'])}")
    if plan["active_bills"]:
        print("  BLOCKED until active bill workflows finish")
    print("  Demo bills, documents, revenue, other ledger entries and S3: preserved")


def execute_compliance_migration(plan):
    """Atomically replace each month's balanced journals; no reseed is required."""
    from botocore.exceptions import ClientError
    from shared import ddb, ledger

    practice_id = plan["practice_id"]
    if plan["active_bills"] or any(
        bill.get("status") in ACTIVE_BILL_STATUSES
        for bill in ddb.query_prefix(practice_id, "BILL#")
    ):
        raise RuntimeError("Active bill workflows must finish before migration")
    # Validate the entire scope before making the first transaction.
    for month in plan["months"]:
        if any(line.get("PK") != ddb.pk(practice_id) for line in month["old"] + month["new"]):
            raise RuntimeError("Migration plan contains an item outside the selected practice")
    table = ddb.table()
    migrated = []
    for month in plan["months"]:
        operations = []
        for line in month["old"]:
            fields = ("journalId", "account", "debit", "credit", "date", "sourceType")
            operations.append({"Delete": {
                "TableName": table.name, "Key": {"PK": line["PK"], "SK": line["SK"]},
                "ConditionExpression": " AND ".join(f"#v{i} = :v{i}" for i in range(len(fields))),
                "ExpressionAttributeNames": {f"#v{i}": field for i, field in enumerate(fields)},
                "ExpressionAttributeValues": {f":v{i}": line[field] for i, field in enumerate(fields)},
            }})
        operations.extend({"Put": {
            "TableName": table.name, "Item": ledger.to_ddb_keep_nulls(line),
            "ConditionExpression": "attribute_not_exists(SK)",
        }} for line in month["new"])
        try:
            table.meta.client.transact_write_items(TransactItems=operations)
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                raise RuntimeError(
                    f"{month['period']} changed after preview; that month's migration made no changes. "
                    "Run a fresh preview; previously completed months are safe to repeat."
                ) from error
            raise
        migrated.append(month["period"])
    return migrated


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run by default; --execute deletes only selected-practice DynamoDB demo records."
    )
    parser.add_argument("--table", required=True, help="DynamoDB table name")
    parser.add_argument("--practice", required=True, help="practice ID to reset")
    parser.add_argument("--execute", action="store_true", help="apply the previewed DynamoDB deletions")
    parser.add_argument("--migrate-compliance", action="store_true",
                        help="replace legacy July-September combined compliance journals only; no demo cleanup")
    args = parser.parse_args()
    if not args.practice.strip():
        parser.error("--practice must not be empty")

    os.environ["TABLE_NAME"] = args.table
    try:
        if args.migrate_compliance:
            plan = build_compliance_migration_plan(args.practice)
            print_compliance_migration_preview(plan)
            if args.execute:
                migrated = execute_compliance_migration(plan)
                print(f"Migrated {len(migrated)} months: {', '.join(migrated) or 'none'}")
            else:
                print("No changes made. Add --execute to apply this migration.")
            return
        plan = build_reset_plan(args.practice)
        print_preview(plan)
        if not args.execute:
            print("No changes made. Add --execute to apply this reset.")
            return
        deleted = execute_reset(plan)
    except RuntimeError as error:
        parser.error(str(error))

    print("Reset complete:")
    for item_type, count in deleted.items():
        print(f"  Deleted {count} {item_type}")
    print("  Brightline Marketing onboarding restored: W-9 missing, void check missing")
    print("  S3 objects were not touched")


if __name__ == "__main__":
    main()

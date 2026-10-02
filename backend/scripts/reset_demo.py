#!/usr/bin/env python3
"""Preview or clear one practice's demo bills, uploads, and related postings.

This script never deletes S3 objects, cancels workflows, or reseeds data. Stop
uploads and wait for all Step Functions executions for the practice to reach a
terminal state before using --execute.
"""
import argparse
import os
import sys

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
    return any(journal_id.startswith(f"j-{bill_id}-") for bill_id in bill_ids)


def build_reset_plan(practice_id):
    """Read one practice's paginated prefixes and build a non-mutating plan."""
    if not practice_id or not practice_id.strip():
        raise ValueError("practice_id must not be empty")

    from shared import ddb, repo

    bills = ddb.query_prefix(practice_id, "BILL#")
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
    print(f"  September 2026 revenue lines to delete: {len(plan['september_revenue'])}")
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


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run by default; --execute deletes only selected-practice DynamoDB demo records."
    )
    parser.add_argument("--table", required=True, help="DynamoDB table name")
    parser.add_argument("--practice", required=True, help="practice ID to reset")
    parser.add_argument("--execute", action="store_true", help="apply the previewed DynamoDB deletions")
    args = parser.parse_args()
    if not args.practice.strip():
        parser.error("--practice must not be empty")

    os.environ["TABLE_NAME"] = args.table
    try:
        plan, deleted = reset_demo(args.practice, execute=args.execute)
        print_preview(plan)
        if not args.execute:
            print("No changes made. Add --execute to apply this reset.")
            return
    except RuntimeError as error:
        parser.error(str(error))

    print("Reset complete:")
    for item_type, count in deleted.items():
        print(f"  Deleted {count} {item_type}")
    print("  Brightline Marketing onboarding restored: W-9 missing, void check missing")
    print("  S3 objects were not touched")


if __name__ == "__main__":
    main()
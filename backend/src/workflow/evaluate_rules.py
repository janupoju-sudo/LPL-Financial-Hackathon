"""ApproveBill step 1: evaluate approval rules. Input {practiceId, billId}."""
from shared import repo
from shared.ddb import from_ddb
from shared.rules_engine import evaluate


def handler(event, context=None):
    practice_id, bill_id = event["practiceId"], event["billId"]
    bill = repo.get_bill(practice_id, bill_id)
    vendor = repo.get_vendor(practice_id, bill.get("vendorId")) or {}
    doc_type = bill.get("documentType") or (repo.get_document(practice_id, bill.get("documentId")) or {}).get("type")
    ctx = {
        "bill": {**bill, "isDuplicate": bool(bill.get("isDuplicate")), "documentType": doc_type},
        "vendor": {**vendor, "isNew": int(vendor.get("billCount", 0)) <= 1},
    }
    result = evaluate(repo.list_rules(practice_id), ctx)
    reasons = "; ".join(h["reason"] for h in result["hits"]) or "No rules triggered"
    action = "auto_approved" if result["decision"] == "auto_approve" else "rules_evaluated"
    repo.update_bill(
        practice_id, bill_id,
        set_fields={"ruleHits": result["hits"], "decision": result["decision"],
                    "requiredApprovers": result["requiredApprovers"]},
        audit=repo.audit_event("Rules engine", action, reasons),
    )
    return from_ddb(result)

"""Receipts skip the vendor W-9 / void check hold (live test: a cafe receipt was held for a W-9)."""
from conftest import api_event, body_of

from handlers import rules as rules_api
from shared import repo
from workflow import create_bill, evaluate_rules


def _doc(doc_type, name):
    doc = repo.create_document("p1", name, "application/pdf", f"uploads/p1/x/{name}", "user-ops")
    repo.update_document("p1", doc["documentId"], type=doc_type)
    return doc


def _bill(doc, vendor, amount, invoice):
    out = create_bill.handler({"documentId": doc["documentId"], "vendorName": vendor, "amount": amount,
                               "invoiceNumber": invoice, "confidence": 0.95})
    return out["billId"]


def _reasons(result):
    return [h["reason"] for h in result["hits"]]


def test_receipt_from_new_vendor_is_not_held_for_w9(aws):
    bill_id = _bill(_doc("receipt", "cafe.pdf"), "Riverside Cafe", 37.18, "RCPT-09122")
    assert repo.get_bill("p1", bill_id)["documentType"] == "receipt"
    result = evaluate_rules.handler({"practiceId": "p1", "billId": bill_id})
    assert result["decision"] == "auto_approve"
    assert "Vendor is missing a W-9 or void check" not in _reasons(result)


def test_invoice_from_new_vendor_is_still_held(aws):
    bill_id = _bill(_doc("invoice", "brightline.pdf"), "Brightline Marketing", 650, "INV-BRT-1")
    assert repo.get_bill("p1", bill_id)["documentType"] == "invoice"
    result = evaluate_rules.handler({"practiceId": "p1", "billId": bill_id})
    assert result["decision"] == "on_hold"
    assert _reasons(result) == ["Vendor is missing a W-9 or void check"]


def test_bill_created_before_the_field_falls_back_to_document_type(aws):
    bill_id = _bill(_doc("receipt", "old-receipt.pdf"), "Corner Deli", 23.15, "R-1")
    repo.update_bill("p1", bill_id, remove=["documentType"])          # as stored before this change
    assert "documentType" not in repo.get_bill("p1", bill_id)
    assert evaluate_rules.handler({"practiceId": "p1", "billId": bill_id})["decision"] == "auto_approve"


def test_other_rules_still_apply_to_receipts(aws):
    bill_id = _bill(_doc("receipt", "big-receipt.pdf"), "Marriott Boston", 1200, "R-2")
    result = evaluate_rules.handler({"practiceId": "p1", "billId": bill_id})
    assert result["decision"] == "needs_approval"
    assert _reasons(result) == ["Amount is over $1,000"]


def test_default_rule_condition_is_valid_and_served_by_api(aws):
    rules = body_of(rules_api.handler(api_event("GET /rules")))
    docs_rule = next(r for r in rules if r["ruleId"] == "rule_vendor_docs")
    assert {"field": "bill.documentType", "op": "neq", "value": "receipt"} in docs_rule["condition"]["all"]

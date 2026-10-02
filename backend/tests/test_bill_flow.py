"""End-to-end bill lifecycle, simulating what the ApproveBill state machine does."""
from conftest import api_event, body_of

from handlers import bills as bills_api
from handlers import rules as rules_api
from shared import ddb, ledger, repo
from workflow import (create_bill, evaluate_rules, mark_rejected, post_ledger,
                      resume_held_bills, schedule_payment, store_task_token)


def run_until_wait(practice, bill_id):
    """EvaluateRules -> Choice -> (wait | post+pay | reject), like the ASL."""
    result = evaluate_rules.handler({"practiceId": practice, "billId": bill_id})
    d = result["decision"]
    if d == "auto_approve":
        post_ledger.handler({"practiceId": practice, "billId": bill_id})
        schedule_payment.handler({"practiceId": practice, "billId": bill_id})
    elif d == "blocked":
        mark_rejected.handler({"input": {"practiceId": practice, "billId": bill_id, "evaluation": result}})
    else:
        store_task_token.handler({
            "practiceId": practice, "billId": bill_id, "taskToken": f"tok-{bill_id}",
            "waitingFor": "approval" if d == "needs_approval" else "documents",
            "requiredApprovers": result["requiredApprovers"],
        })
    return result


def setup_known_vendor():
    v = repo.create_vendor("p1", "Orion Software LLC", default_gl_account="6300", hasW9=True, hasVoidCheck=True)
    doc = repo.create_document("p1", "orion.pdf", "application/pdf", "uploads/p1/x/orion.pdf", "user-ops")
    return v, doc


def test_vendor_memory_and_auto_approve(aws):
    v, doc = setup_known_vendor()
    out = create_bill.handler({"documentId": doc["documentId"], "vendorName": "ORION SOFTWARE, LLC",
                               "amount": 450, "invoiceNumber": "INV-1", "invoiceDate": "2026-09-05",
                               "confidence": 0.95})
    assert out["status"] == "processing" and aws.started[-1]["billId"] == out["billId"]
    bill = repo.get_bill("p1", out["billId"])
    assert bill["vendorId"] == v["vendorId"] and bill["glAccount"] == "6300"   # remembered vendor + GL

    run_until_wait("p1", out["billId"])
    bill = repo.get_bill("p1", out["billId"])
    assert bill["status"] == "scheduled"
    assert ledger.account_balances(ddb.get_ledger_entries("p1", "2026-01-01", "2027-12-31"))["6300"] == 45000


def test_large_bill_partner_approval_and_permissions(aws):
    _, doc = setup_known_vendor()
    out = create_bill.handler({"documentId": doc["documentId"], "vendorName": "Orion Software LLC",
                               "amount": 1850, "invoiceNumber": "INV-2", "confidence": 0.9})
    run_until_wait("p1", out["billId"])
    assert repo.get_bill("p1", out["billId"])["status"] == "pending_approval"

    path = {"id": out["billId"]}
    r = bills_api.handler(api_event("POST /bills/{id}/decision", path, {"decision": "approve"},
                                    groups=("ops",), sub="user-ops2"))
    assert r["statusCode"] == 403                                   # ops can't approve

    r = bills_api.handler(api_event("POST /bills/{id}/decision", path, {"decision": "approve"},
                                    groups=("partner",), sub="user-ops"))
    assert r["statusCode"] == 403                                   # uploader can't self-approve

    r = bills_api.handler(api_event("POST /bills/{id}/decision", path, {"decision": "approve", "comment": "ok"},
                                    groups=("partner",), sub="user-partner"))
    assert r["statusCode"] == 200, body_of(r)
    token, output = aws.resumed[-1]
    assert token == f"tok-{out['billId']}" and output["decision"] == "approve"

    r = bills_api.handler(api_event("POST /bills/{id}/decision", path, {"decision": "approve"},
                                    groups=("partner",), sub="user-partner"))
    assert r["statusCode"] == 409                                   # token already consumed

    post_ledger.handler({"practiceId": "p1", "billId": out["billId"]})
    schedule_payment.handler({"practiceId": "p1", "billId": out["billId"]})
    detail = body_of(bills_api.handler(api_event("GET /bills/{id}", path)))
    assert detail["status"] == "scheduled" and "taskToken" not in detail
    assert [a["action"] for a in detail["audit"]][-3:] == ["approved", "posted", "scheduled"]


def test_new_vendor_hold_then_resume_on_docs(aws):
    doc = repo.create_document("p1", "new.pdf", "application/pdf", "k", "user-ops")
    out = create_bill.handler({"documentId": doc["documentId"], "vendorName": "Brightline Marketing",
                               "amount": 600, "invoiceNumber": "BL-9", "confidence": 0.92})
    run_until_wait("p1", out["billId"])
    bill = repo.get_bill("p1", out["billId"])
    assert bill["status"] == "pending_docs"

    repo.record_vendor_docs("p1", bill["vendorId"], has_w9=True, has_void_check=True, bank_last4="123456789")
    res = resume_held_bills.handler({"detail": {"practiceId": "p1", "vendorId": bill["vendorId"]}})
    assert res["resumed"] == [out["billId"]]
    assert aws.resumed[-1][1]["decision"] == "reevaluate"

    run_until_wait("p1", out["billId"])          # loops back to EvaluateRules
    bill = repo.get_bill("p1", out["billId"])
    assert bill["status"] == "scheduled" and bill["payment"]["bankLast4"] == "6789"


def test_duplicate_invoice_is_blocked(aws):
    _, doc = setup_known_vendor()
    first = create_bill.handler({"documentId": doc["documentId"], "vendorName": "Orion Software LLC",
                                 "amount": 300, "invoiceNumber": "DUP-1", "confidence": 0.99})
    second = create_bill.handler({"documentId": doc["documentId"], "vendorName": "Orion Software LLC",
                                  "amount": 300, "invoiceNumber": "DUP-1", "confidence": 0.99})
    assert second["isDuplicate"] and not first["isDuplicate"]
    run_until_wait("p1", second["billId"])
    bill = repo.get_bill("p1", second["billId"])
    assert bill["status"] == "rejected" and "already submitted" in bill["rejectionReason"]


def test_low_confidence_goes_to_review_then_confirm(aws):
    doc = repo.create_document("p1", "blurry.jpg", "image/jpeg", "k", "user-ops")
    out = create_bill.handler({"documentId": doc["documentId"], "vendorName": "Corner Cafe",
                               "amount": 42.5, "confidence": 0.55})
    assert out["status"] == "pending_review" and not aws.started

    r = bills_api.handler(api_event("POST /bills/{id}/confirm", {"id": out["billId"]},
                                    {"amount": 45.10, "glAccount": "6700"}))
    assert r["statusCode"] == 200, body_of(r)
    assert aws.started[-1]["billId"] == out["billId"]
    bill = repo.get_bill("p1", out["billId"])
    assert float(bill["amount"]) == 45.10 and bill["glAccountName"] == "Travel and entertainment"

    listed = body_of(bills_api.handler(api_event("GET /bills", query={"status": "processing"})))
    assert [b["billId"] for b in listed] == [out["billId"]]


def test_rules_api_seeds_defaults_and_owner_only_edits(aws):
    rules = body_of(rules_api.handler(api_event("GET /rules")))
    assert {r["ruleId"] for r in rules} >= {"rule_large_bill", "rule_vendor_docs"}

    r = rules_api.handler(api_event("PATCH /rules/{id}", {"id": "rule_large_bill"}, {"enabled": False},
                                    groups=("ops",)))
    assert r["statusCode"] == 403
    r = rules_api.handler(api_event("PATCH /rules/{id}", {"id": "rule_large_bill"}, {"enabled": False}))
    assert r["statusCode"] == 200 and body_of(r)["enabled"] is False

    new_rule = {"name": "T&E over $250 needs owner", "action": "require_approval", "approverRole": "owner",
                "condition": {"all": [{"field": "bill.glAccount", "op": "eq", "value": "6700"},
                                      {"field": "bill.amount", "op": "gt", "value": 250}]}}
    r = rules_api.handler(api_event("POST /rules", body=new_rule))
    assert r["statusCode"] == 201
    r = rules_api.handler(api_event("POST /rules", body={**new_rule, "action": "explode"}))
    assert r["statusCode"] == 400

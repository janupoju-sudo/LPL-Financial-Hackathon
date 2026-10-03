"""End-to-end bill lifecycle, simulating what the ApproveBill state machine does."""
from conftest import api_event, body_of

from handlers import bills as bills_api
from handlers import documents as documents_api
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
                               "confidence": 0.95,
                               "glAccountReason": "Matched vendor memory: Orion Software LLC uses expense account 6300."})
    assert out["status"] == "processing" and aws.started[-1]["billId"] == out["billId"]
    bill = repo.get_bill("p1", out["billId"])
    assert bill["vendorId"] == v["vendorId"] and bill["glAccount"] == "6300"   # remembered vendor + GL
    assert "vendor memory" in bill["glAccountReason"]
    detail = bills_api.handler(api_event("GET /bills/{id}", {"id": out["billId"]}))
    assert "vendor memory" in body_of(detail)["glAccountReason"]

    run_until_wait("p1", out["billId"])
    bill = repo.get_bill("p1", out["billId"])
    assert bill["status"] == "scheduled"
    assert ledger.account_balances(ddb.get_ledger_entries("p1", "2026-01-01", "2027-12-31"))["6300"] == 45000


def test_scheduler_retries_an_incomplete_claim_and_is_idempotent(aws):
    vendor, doc = setup_known_vendor()
    out = create_bill.handler({
        "documentId": doc["documentId"], "vendorId": vendor["vendorId"],
        "vendorName": vendor["name"], "amount": 450, "invoiceNumber": "RETRY-1",
        "confidence": 0.95,
    })
    evaluate_rules.handler({"practiceId": "p1", "billId": out["billId"]})
    post_ledger.handler({"practiceId": "p1", "billId": out["billId"]})
    repo.update_bill("p1", out["billId"], set_fields={"status": "scheduling"})

    first = schedule_payment.handler({"practiceId": "p1", "billId": out["billId"]})
    second = schedule_payment.handler({"practiceId": "p1", "billId": out["billId"]})
    bill = repo.get_bill("p1", out["billId"])
    assert first == second
    assert bill["status"] == "scheduled"
    assert len(ddb.get_ledger_entries("p1", "2026-01-01", "2027-12-31")) == 4


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
                                    groups=("lpl_bookkeeper",), sub="user-bookkeeper"))
    assert r["statusCode"] == 403                                   # bookkeeper is read-only
    repo.update_bill("p1", out["billId"], set_fields={"requiredApprovers": ["ops", "lpl_bookkeeper"]})
    for group in ("ops", "lpl_bookkeeper"):
        r = bills_api.handler(api_event("POST /bills/{id}/decision", path, {"decision": "approve"},
                                        groups=(group,), sub=f"user-{group}"))
        assert r["statusCode"] == 403                               # only owner/partner may ever approve
    repo.update_bill("p1", out["billId"], set_fields={"requiredApprovers": ["partner"]})

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

    path = {"id": out["billId"]}
    for group in ("partner", "lpl_bookkeeper"):
        denied = bills_api.handler(api_event("POST /bills/{id}/confirm", path,
                                             {"amount": 45.10, "glAccount": "6700"},
                                             groups=(group,)))
        assert denied["statusCode"] == 403

    self_review = bills_api.handler(api_event(
        "POST /bills/{id}/confirm", {"id": out["billId"]}, {"amount": 45.10, "glAccount": "6700"},
        groups=("ops",), sub="user-ops",
    ))
    assert self_review["statusCode"] == 403

    r = bills_api.handler(api_event("POST /bills/{id}/confirm", {"id": out["billId"]},
                                    {"amount": 45.10, "glAccount": "6700"}, groups=("ops",), sub="reviewer-ops"))
    assert r["statusCode"] == 200, body_of(r)
    assert aws.started[-1]["billId"] == out["billId"]
    bill = repo.get_bill("p1", out["billId"])
    assert float(bill["amount"]) == 45.10 and bill["glAccountName"] == "Travel and entertainment"

    listed = body_of(bills_api.handler(api_event("GET /bills", query={"status": "processing"})))
    assert [b["billId"] for b in listed] == [out["billId"]]


def test_marking_received_is_owner_or_ops_only(aws):
    vendor = repo.create_vendor("p1", "Brightline Marketing", hasW9=False, hasVoidCheck=False)
    doc = repo.create_document("p1", "brightline.pdf", "application/pdf", "k", "user-ops")
    out = create_bill.handler({"documentId": doc["documentId"], "vendorId": vendor["vendorId"],
                               "vendorName": vendor["name"], "amount": 600,
                               "invoiceNumber": "BL-RECEIVED", "confidence": 0.9})
    run_until_wait("p1", out["billId"])
    path = {"id": out["billId"]}

    for group in ("partner", "lpl_bookkeeper"):
        denied = bills_api.handler(api_event("POST /bills/{id}/receive", path, groups=(group,)))
        assert denied["statusCode"] == 403

    partner_reject = bills_api.handler(api_event("POST /bills/{id}/decision", path,
                                                 {"decision": "reject", "comment": "Not assigned"},
                                                 groups=("partner",), sub="user-partner"))
    assert partner_reject["statusCode"] == 403

    allowed = bills_api.handler(api_event("POST /bills/{id}/receive", path, groups=("ops",)))
    assert allowed["statusCode"] == 200
    assert repo.get_bill("p1", out["billId"])["received"] is True
    assert aws.resumed[-1][1]["decision"] == "reevaluate"


def test_uploader_can_withdraw_own_unposted_bill_but_not_someone_elses(aws):
    doc = repo.create_document("p1", "uncertain.pdf", "application/pdf", "k", "user-ops")
    out = create_bill.handler({
        "documentId": doc["documentId"], "vendorName": "Corner Cafe", "amount": 45.10,
        "confidence": 0.55,
    })
    path = {"id": out["billId"]}

    denied = bills_api.handler(api_event(
        "POST /bills/{id}/withdraw", path, {"reason": "wrong file"},
        groups=("ops",), sub="another-ops",
    ))
    assert denied["statusCode"] == 403

    result = bills_api.handler(api_event(
        "POST /bills/{id}/withdraw", path, {"reason": "wrong file"},
        groups=("ops",), sub="user-ops",
    ))
    assert result["statusCode"] == 200
    bill = repo.get_bill("p1", out["billId"])
    assert bill["status"] == "withdrawn"
    assert bill["audit"][-1]["action"] == "withdrawn"
    assert repo.get_document("p1", doc["documentId"])["status"] == "withdrawn"
    assert not ddb.get_ledger_entries("p1", "2026-01-01", "2027-12-31")


def test_uploader_can_withdraw_waiting_approval_and_workflow_marks_audit(aws):
    _, doc = setup_known_vendor()
    out = create_bill.handler({
        "documentId": doc["documentId"], "vendorName": "Orion Software LLC",
        "amount": 1850, "invoiceNumber": "WITHDRAW-1", "confidence": 0.92,
    })
    run_until_wait("p1", out["billId"])
    path = {"id": out["billId"]}

    result = bills_api.handler(api_event(
        "POST /bills/{id}/withdraw", path, {"reason": "wrong document"},
        groups=("ops",), sub="user-ops",
    ))
    assert result["statusCode"] == 200
    token, output = aws.resumed[-1]
    assert token == f"tok-{out['billId']}"
    assert output["decision"] == "withdraw"

    final = mark_rejected.handler({
        "input": {"practiceId": "p1", "billId": out["billId"], "approval": output}
    })
    assert final["status"] == "withdrawn"
    assert repo.get_bill("p1", out["billId"])["audit"][-1]["action"] == "withdrawn"
    assert repo.get_document("p1", doc["documentId"])["status"] == "withdrawn"


def test_owner_void_posts_audited_reversals_for_scheduled_mock_bill(aws):
    vendor, doc = setup_known_vendor()
    out = create_bill.handler({
        "documentId": doc["documentId"], "vendorId": vendor["vendorId"],
        "vendorName": vendor["name"], "amount": 450, "invoiceNumber": "VOID-1",
        "confidence": 0.95,
    })
    run_until_wait("p1", out["billId"])
    before = repo.get_bill("p1", out["billId"])
    assert before["status"] == "scheduled"

    denied = bills_api.handler(api_event(
        "POST /bills/{id}/void", {"id": out["billId"]}, {"reason": "uploaded in error"},
        groups=("ops",), sub="user-ops",
    ))
    assert denied["statusCode"] == 403
    assert repo.get_bill("p1", out["billId"])["status"] == "scheduled"

    result = bills_api.handler(api_event(
        "POST /bills/{id}/void", {"id": out["billId"]}, {"reason": "uploaded in error"},
        groups=("owner",), sub="user-owner",
    ))
    assert result["statusCode"] == 200, body_of(result)
    voided = repo.get_bill("p1", out["billId"])
    assert voided["status"] == "voided"
    assert voided["voidJournalIds"] == [
        f"j-{out['billId']}-void-accrual", f"j-{out['billId']}-void-payment"
    ]
    assert voided["audit"][-1]["action"] == "voided"
    lines = ddb.get_ledger_entries("p1", "2026-01-01", "2027-12-31")
    assert len(lines) == 8
    assert ledger.account_balances(lines) == {"6300": 0, "2000": 0, "1000": 0}
    assert not repo.is_duplicate_invoice("p1", vendor["vendorId"], "VOID-1")


def test_voiding_an_approved_bill_prevents_mock_payment(aws):
    vendor, doc = setup_known_vendor()
    out = create_bill.handler({
        "documentId": doc["documentId"], "vendorId": vendor["vendorId"],
        "vendorName": vendor["name"], "amount": 450, "invoiceNumber": "VOID-2",
        "confidence": 0.95,
    })
    evaluate_rules.handler({"practiceId": "p1", "billId": out["billId"]})
    post_ledger.handler({"practiceId": "p1", "billId": out["billId"]})
    assert repo.get_bill("p1", out["billId"])["status"] == "approved"

    result = bills_api.handler(api_event(
        "POST /bills/{id}/void", {"id": out["billId"]}, {"reason": "duplicate upload"},
        groups=("owner",), sub="user-owner",
    ))
    assert result["statusCode"] == 200
    assert schedule_payment.handler({"practiceId": "p1", "billId": out["billId"]})["status"] == "voided"
    bill = repo.get_bill("p1", out["billId"])
    assert bill["status"] == "voided"
    assert "paymentJournalId" not in bill


def test_only_owner_or_original_ops_uploader_can_withdraw_review_document(aws):
    doc = repo.create_document("p1", "unknown.pdf", "application/pdf", "k", "user-ops")
    repo.update_document("p1", doc["documentId"], type="unknown", status="needs_review")
    path = {"id": doc["documentId"]}

    denied = documents_api.handler(api_event(
        "POST /documents/{id}/withdraw", path, {"reason": "not a business document"},
        groups=("ops",), sub="other-ops",
    ))
    assert denied["statusCode"] == 403

    denied_bookkeeper = documents_api.handler(api_event(
        "POST /documents/{id}/withdraw", path, {"reason": "not a business document"},
        groups=("lpl_bookkeeper",), sub="user-bookkeeper",
    ))
    assert denied_bookkeeper["statusCode"] == 403

    result = documents_api.handler(api_event(
        "POST /documents/{id}/withdraw", path, {"reason": "not a business document"},
        groups=("ops",), sub="user-ops",
    ))
    assert result["statusCode"] == 200
    withdrawn = repo.get_document("p1", doc["documentId"])
    assert withdrawn["status"] == "withdrawn"
    assert withdrawn["audit"][-1]["action"] == "withdrawn"


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
    r = rules_api.handler(api_event("POST /rules", body={**new_rule, "approverRole": "ops"}))
    assert r["statusCode"] == 400


def test_approver_can_correct_category_invoice_and_due_date_when_approving(aws):
    _, doc = setup_known_vendor()
    out = create_bill.handler({"documentId": doc["documentId"], "vendorName": "Orion Software LLC",
                               "amount": 1850, "invoiceNumber": "INV-9", "confidence": 0.9})
    run_until_wait("p1", out["billId"])
    path = {"id": out["billId"]}

    r = bills_api.handler(api_event("POST /bills/{id}/decision", path,
                                    {"decision": "approve", "changes": {"amount": 10}},
                                    groups=("partner",), sub="user-partner"))
    assert r["statusCode"] == 400 and "send the bill back" in body_of(r)["error"].lower()

    r = bills_api.handler(api_event("POST /bills/{id}/decision", path, {"decision": "approve", "changes": {
        "glAccount": "6320", "invoiceNumber": "INV-9A", "dueDate": "2026-11-01"}},
        groups=("partner",), sub="user-partner"))
    assert r["statusCode"] == 200, body_of(r)
    bill = repo.get_bill("p1", out["billId"])
    assert (bill["glAccount"], bill["invoiceNumber"], bill["dueDate"]) == ("6320", "INV-9A", "2026-11-01")
    assert any(a["action"] == "edited" and "6320" in a["detail"] for a in bill["audit"])

    post_ledger.handler({"practiceId": "p1", "billId": out["billId"]})
    assert ledger.account_balances(ddb.get_ledger_entries("p1", "2026-01-01", "2027-12-31"))["6320"] == 185000

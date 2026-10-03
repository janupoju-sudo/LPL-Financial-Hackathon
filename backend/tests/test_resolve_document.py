"""POST /documents/{id}/resolve: close out a needs_review document (QA: no resolution path)."""
import json

from shared import repo
from handlers import documents

from conftest import api_event


def _needs_review(**extra):
    doc = repo.create_document("p1", "user-flow.png", "image/png", "uploads/p1/d/user-flow.png", "dev")
    repo.update_document("p1", doc["documentId"], type="unknown", status="needs_review", confidence=0.31,
                         extracted={"reviewReason": "Unknown document type"}, **extra)
    return doc["documentId"]


def _resolve(doc_id, body, groups=("ops",), sub="user-dev"):
    resp = documents.handler(api_event("POST /documents/{id}/resolve", path={"id": doc_id},
                                       body=body, groups=groups, sub=sub))
    return resp["statusCode"], json.loads(resp["body"])


def test_dismiss_marks_document_reviewed_with_audit(aws):
    doc_id = _needs_review()
    status, body = _resolve(doc_id, {"resolution": "dismiss", "note": "Process diagram, not a financial record"})
    assert status == 200
    assert body["status"] == "dismissed"
    assert body["review"]["resolution"] == "dismiss"
    assert body["review"]["by"] == "user-dev@harborpoint.example"
    assert body["review"]["note"] == "Process diagram, not a financial record"
    assert body["audit"][-1]["action"] == "review_dismissed"
    stored = repo.get_document("p1", doc_id)
    assert stored["status"] == "dismissed"
    assert stored["s3Key"]                               # file stays in the (Object Lock) library


def test_accept_marks_processed(aws):
    doc_id = _needs_review()
    status, body = _resolve(doc_id, {"resolution": "accept"}, groups=("ops",))
    assert status == 200
    assert body["status"] == "processed"
    assert body["review"]["resolution"] == "accept"


def test_only_needs_review_documents_and_only_once(aws):
    doc_id = _needs_review()
    assert _resolve(doc_id, {"resolution": "dismiss"})[0] == 200
    status, body = _resolve(doc_id, {"resolution": "accept"})
    assert status == 409
    assert "needs_review" in body["error"]


def test_document_with_pending_bill_points_to_bill_confirm(aws):
    doc_id = _needs_review(billId="bill-123")
    status, body = _resolve(doc_id, {"resolution": "accept"})
    assert status == 409
    assert "/bills/bill-123/confirm" in body["error"]


def test_validation_role_and_missing(aws):
    doc_id = _needs_review()
    assert _resolve(doc_id, {"resolution": "delete"})[0] == 400
    assert _resolve(doc_id, {})[0] == 400
    assert _resolve(doc_id, {"resolution": "dismiss", "note": "x" * 501})[0] == 400
    assert _resolve(doc_id, {"resolution": "dismiss"}, groups=("partner",))[0] == 403
    assert _resolve(doc_id, {"resolution": "dismiss"}, groups=("lpl_bookkeeper",))[0] == 403
    assert _resolve("doc-missing", {"resolution": "dismiss"})[0] == 404


def test_upload_url_is_owner_or_ops_only(aws, monkeypatch):
    class FakeS3:
        def generate_presigned_url(self, operation, Params, ExpiresIn):
            return "https://upload.example"

    monkeypatch.setattr(documents, "s3", lambda: FakeS3())
    event = api_event("POST /documents/upload-url", body={"filename": "invoice.pdf"})
    for group in ("partner", "lpl_bookkeeper"):
        denied = documents.handler({**event, "requestContext": {"authorizer": {"jwt": {"claims": {
            "sub": "user-denied", "cognito:groups": f"[{group}]",
        }}}}})
        assert denied["statusCode"] == 403

    for group in ("owner", "ops"):
        allowed = documents.handler({**event, "requestContext": {"authorizer": {"jwt": {"claims": {
            "sub": f"user-{group}", "email": f"{group}@harborpoint.example",
            "cognito:groups": f"[{group}]",
        }}}}})
        assert allowed["statusCode"] == 201


def test_concurrent_resolve_loses_conditional_write(aws, monkeypatch):
    doc_id = _needs_review()
    stale = repo.get_document("p1", doc_id)                 # what a second reviewer loaded earlier
    assert _resolve(doc_id, {"resolution": "dismiss"})[0] == 200
    monkeypatch.setattr(repo, "get_document", lambda p, d: stale)
    status, body = _resolve(doc_id, {"resolution": "accept"}, sub="user-priya")
    assert status == 409
    assert body["error"] == "Document was already resolved"
    monkeypatch.undo()
    assert repo.get_document("p1", doc_id)["review"]["resolution"] == "dismiss"

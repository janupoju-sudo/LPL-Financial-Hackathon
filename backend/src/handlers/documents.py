"""Documents API.

POST /documents/upload-url   -> presigned S3 PUT; upload lands at uploads/<practiceId>/<documentId>/<filename>
GET  /documents?type=&q=     -> library list
GET  /documents/{id}         -> detail + presigned view URL
POST /documents/{id}/resolve -> close out a needs_review document: {resolution: dismiss|accept, note?}
                                (owner, ops; a document with a bill is resolved via /bills/{id}/confirm)
"""
import os
import re

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from shared import config, repo
from shared.auth import get_caller, require_role
from shared.ddb import now_iso, public, update_item
from shared.http import HttpError, parse_body, path_param, query_param, router

ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
}

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _s3 = boto3.client(
            "s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return _s3


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "document")
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "document"
    return base[:120]


def upload_url(event):
    caller = get_caller(event)
    require_role(caller, "owner", "ops")
    body = parse_body(event)
    content_type = body.get("contentType", "application/pdf")
    if content_type not in ALLOWED_TYPES:
        raise HttpError(400, f"contentType must be one of {', '.join(ALLOWED_TYPES)}")
    filename = safe_filename(body.get("filename"))
    doc = repo.create_document(caller.practice_id, filename, content_type, s3_key="", uploaded_by=caller.sub)
    key = f"uploads/{caller.practice_id}/{doc['documentId']}/{filename}"
    repo.update_document(caller.practice_id, doc["documentId"], s3Key=key, uploadedByEmail=caller.email)
    url = s3().generate_presigned_url(
        "put_object",
        Params={"Bucket": config.DOCS_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=config.PRESIGN_EXPIRY_SECONDS,
    )
    return 201, {
        "documentId": doc["documentId"],
        "uploadUrl": url,
        "s3Key": key,
        "requiredHeaders": {"Content-Type": content_type},
    }


def list_docs(event):
    caller = get_caller(event)
    docs = repo.list_documents(caller.practice_id, query_param(event, "type"), query_param(event, "q"))
    keys = ("documentId", "type", "filename", "status", "vendorId", "vendorName", "amount",
            "billId", "confidence", "createdAt", "locked", "review")
    return 200, [{k: d.get(k) for k in keys if k in d} for d in map(public, docs)]


def get_doc(event):
    caller = get_caller(event)
    doc = repo.get_document(caller.practice_id, path_param(event, "id"))
    if not doc:
        raise HttpError(404, "Document not found")
    out = public(doc)
    if doc.get("s3Key"):
        out["viewUrl"] = s3().generate_presigned_url(
            "get_object", Params={"Bucket": config.DOCS_BUCKET, "Key": doc["s3Key"]},
            ExpiresIn=config.PRESIGN_EXPIRY_SECONDS,
        )
    return 200, out


RESOLUTIONS = {"dismiss": "dismissed", "accept": "processed"}


def resolve_doc(event):
    """dismiss = not a financial record (kept in the library, nothing posted);
    accept = the extracted fields are correct as shown."""
    caller = get_caller(event)
    require_role(caller, "owner", "ops")
    doc_id = path_param(event, "id")
    body = parse_body(event)
    resolution = body.get("resolution")
    if resolution not in RESOLUTIONS:
        raise HttpError(400, f"resolution must be one of {', '.join(RESOLUTIONS)}")
    note = str(body.get("note") or "").strip()
    if len(note) > 500:
        raise HttpError(400, "note must be 500 characters or fewer")

    doc = repo.get_document(caller.practice_id, doc_id)
    if not doc:
        raise HttpError(404, "Document not found")
    if doc.get("billId"):
        raise HttpError(409, f"This document has a bill; review it with POST /bills/{doc['billId']}/confirm")
    if doc.get("status") != "needs_review":
        raise HttpError(409, f"Only documents in needs_review can be resolved (status: {doc.get('status')})")

    review = {"resolution": resolution, "by": caller.label, "at": now_iso(), "note": note or None}
    try:
        # Conditional so two reviewers can't both resolve it (the second gets 409).
        updated = update_item(
            caller.practice_id, f"DOC#{doc_id}",
            set_fields={"status": RESOLUTIONS[resolution], "review": review, "updatedAt": review["at"]},
            append={"audit": [repo.audit_event(caller.label, f"review_{RESOLUTIONS[resolution]}", note)]},
            condition="#cur = :needs_review",
            extra_names={"#cur": "status"}, extra_values={":needs_review": "needs_review"},
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HttpError(409, "Document was already resolved")
        raise
    return 200, public(updated)


handler = router({
    "POST /documents/upload-url": upload_url,
    "GET /documents": list_docs,
    "GET /documents/{id}": get_doc,
    "POST /documents/{id}/resolve": resolve_doc,
})

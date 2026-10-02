"""Apply S3 Object Lock retention to every uploaded document (books-and-records).

Triggered by EventBridge `Object Created` for keys under uploads/<practiceId>/<documentId>/...
Runs alongside (not inside) the ingest pipeline. Retention is GOVERNANCE mode for the demo
so admins can still clean up; use COMPLIANCE mode in production.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus

import boto3

from shared import config, repo

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def handler(event, context=None):
    detail = event.get("detail", {})
    bucket = detail.get("bucket", {}).get("name", config.DOCS_BUCKET)
    key = unquote_plus(detail.get("object", {}).get("key", ""))
    parts = key.split("/")
    if len(parts) < 4 or parts[0] != "uploads":
        return {"skipped": key}
    practice_id, document_id = parts[1], parts[2]
    until = datetime.now(timezone.utc) + timedelta(days=config.RETENTION_DAYS)
    s3().put_object_retention(
        Bucket=bucket, Key=key,
        Retention={"Mode": "GOVERNANCE", "RetainUntilDate": until},
    )
    if repo.get_document(practice_id, document_id):
        repo.update_document(practice_id, document_id, locked=True,
                             retainUntil=until.isoformat(timespec="seconds"),
                             sizeBytes=detail.get("object", {}).get("size"))
    return {"locked": key, "retainUntil": until.isoformat()}

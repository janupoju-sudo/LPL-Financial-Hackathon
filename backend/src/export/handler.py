"""POST /export (D6). Body: {"period": "2026-Q3"} -> {downloadUrl, documents, ledgerLines, missing}.

Env: DOCS_BUCKET (shared config), EXPORTS_BUCKET.
"""

import os
from datetime import datetime, timezone

import boto3

from financials import api, periods
from shared import config, ddb, repo
from shared.auth import get_caller
from shared.http import HttpError, parse_body, router

from .package import build_zip

_s3 = None


def s3():
    global _s3
    _s3 = _s3 or boto3.client("s3")
    return _s3


def export_package(event):
    caller = get_caller(event)
    period = parse_body(event).get("period", "")
    try:
        _, end = periods.parse(period)
    except ValueError as e:
        raise HttpError(400, str(e))

    pid = caller.practice_id
    practice = ddb.get_practice(pid) or {}
    entries = ddb.get_ledger_entries(pid, "0000-01-01", end.isoformat())
    documents = repo.list_documents(pid)
    financials = api.build_financials(entries, period, practice)

    fetch = lambda key: s3().get_object(Bucket=config.DOCS_BUCKET, Key=key)["Body"].read()
    data, summary = build_zip(period, practice.get("name", "Practice"), documents, entries, financials, fetch)

    bucket = os.environ["EXPORTS_BUCKET"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"exports/{pid}/{period}-{stamp}.zip"
    s3().put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/zip")
    url = s3().generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key},
                                      ExpiresIn=config.PRESIGN_EXPIRY_SECONDS)
    return 200, {"downloadUrl": url, **summary}


handler = router({"POST /export": export_package})

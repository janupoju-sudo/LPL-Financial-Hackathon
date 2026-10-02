"""Lambda entry point for POST /export. Body: {"period": "2026-Q3"} -> {downloadUrl}.

Env vars: DOCUMENTS_BUCKET, EXPORTS_BUCKET (E3).
"""

import json
import os
from datetime import date, datetime, timezone

import boto3

from functions.financials import api, periods
from .package import build_zip

PRACTICE_ID = "p1"
URL_TTL_SECONDS = 15 * 60

_s3 = None


def _reply(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def lambda_handler(event, _context):
    from shared import ddb  # C1

    global _s3
    _s3 = _s3 or boto3.client("s3")
    try:
        period = json.loads(event.get("body") or "{}").get("period", "")
        _, end = periods.parse(period)
    except ValueError as e:
        return _reply(400, {"error": str(e)})

    practice = ddb.get_practice(PRACTICE_ID) or {}
    entries = ddb.get_ledger_entries(PRACTICE_ID, date(2000, 1, 1), end)
    documents = ddb.list_documents(PRACTICE_ID)
    financials = api.build_financials(entries, period, practice)

    fetch = lambda key: _s3.get_object(Bucket=os.environ["DOCUMENTS_BUCKET"], Key=key)["Body"].read()
    data, summary = build_zip(period, practice.get("name", "Practice"), documents, entries, financials, fetch)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"exports/{PRACTICE_ID}/{period}-{stamp}.zip"
    bucket = os.environ["EXPORTS_BUCKET"]
    _s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/zip")
    url = _s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key},
                                     ExpiresIn=URL_TTL_SECONDS)
    return _reply(200, {"downloadUrl": url, **summary})

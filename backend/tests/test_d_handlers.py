"""D's API handlers against C's real ddb/repo/ledger code on moto."""

import io
import json
import zipfile
from collections import defaultdict

import boto3

from conftest import api_event, body_of
from export import handler as export_handler
from financials import api, handler as fin
from fixtures import DOCUMENTS, FEE_SCHEDULE, PAYOUT_SEP, PRACTICE, sample_entries
from shared import ddb, ledger, repo


def seed():
    journals = defaultdict(list)
    for e in sample_entries():
        journals[e["journalId"]].append(e)
    for jid, lines in journals.items():
        first = lines[0]
        ledger.post_journal("p1", jid, first["date"],
                            [{"account": l["account"], "debit": l["debit"], "credit": l["credit"]} for l in lines],
                            first["memo"], source_doc_id=first["sourceDocId"])
    ddb.put_item("p1", "META", {**PRACTICE, "feeSchedule": FEE_SCHEDULE})
    repo.put_revenue_lines("p1", "2026-09", "d3", [dict(l) for l in PAYOUT_SEP])
    for d in DOCUMENTS:
        ddb.put_item("p1", f"DOC#{d['documentId']}", d)


def test_financials_matches_pure_function(aws):
    seed()
    resp = fin.handler(api_event("GET /financials", query={"period": "2026-Q3"}))
    assert resp["statusCode"] == 200
    expected = api.build_financials(sample_entries(), "2026-Q3", PRACTICE)
    got = body_of(resp)
    assert got["pnl"] == expected["pnl"]
    assert got["balanceSheet"] == expected["balanceSheet"]
    assert got["cashFlow"] == expected["cashFlow"]
    assert got["valuation"]["mid"] == expected["valuation"]["mid"]


def test_bad_period_is_400(aws):
    resp = fin.handler(api_event("GET /financials", query={"period": "Q3"}))
    assert resp["statusCode"] == 400


def test_reconciliation_flags_412(aws):
    seed()
    body = body_of(fin.handler(api_event("GET /revenue/reconciliation", query={"period": "2026-09"})))
    assert body["variance"] == -412.0
    assert [f["status"] for f in body["flags"]] == ["short"]


def test_export_uploads_zip(aws, monkeypatch):
    seed()
    s3 = boto3.client("s3")
    for b in ("ledgerline-test-docs", "ledgerline-test-exports"):
        s3.create_bucket(Bucket=b)
    for d in DOCUMENTS:
        s3.put_object(Bucket="ledgerline-test-docs", Key=d["s3Key"], Body=b"%PDF sample")
    monkeypatch.setenv("EXPORTS_BUCKET", "ledgerline-test-exports")
    export_handler._s3 = None

    body = body_of(export_handler.handler(api_event("POST /export", body={"period": "2026-Q3"})))
    assert body["missing"] == [] and body["documents"] == 4
    key = s3.list_objects_v2(Bucket="ledgerline-test-exports")["Contents"][0]["Key"]
    z = zipfile.ZipFile(io.BytesIO(s3.get_object(Bucket="ledgerline-test-exports", Key=key)["Body"].read()))
    assert "ledger.csv" in z.namelist()
    assert json.loads(z.read("financials.json"))["period"] == "2026-Q3"


def test_ask_handler_with_stubbed_model(aws, monkeypatch):
    from ask import bedrock, handler as ask_handler

    seed()
    calls = {}

    def fake_claude(system, user, schema):
        calls["user"] = user
        return {"answer": "Rent rose $7,200 in Q3.", "citations": ["rent-2026-07"]}

    monkeypatch.setattr(bedrock, "claude_json", fake_claude)
    monkeypatch.delenv("GUARDRAIL_ID", raising=False)
    resp = ask_handler.handler(api_event("POST /ask", body={"question": "Why did my margin drop in Q3?"}))
    body = body_of(resp)
    assert resp["statusCode"] == 200
    assert body["citations"][0]["documentId"] == "rent-2026-07"
    assert "6200 Rent and occupancy" in calls["user"]

    assert ask_handler.handler(api_event("POST /ask", body={"question": ""}))["statusCode"] == 400

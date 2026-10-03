"""C11: POST /transactions/import (card CSV -> categorized journals + receipt matching)."""
import json

from shared import ddb, ledger, repo
from handlers import transactions

from conftest import api_event

CSV = """Date,Description,Amount,Card
2026-09-03,ZOOM.US 888-799-9666,149.90,4242
2026-09-08,DELTA AIR 0062345,612.40,4242
2026-09-10,Orion Software license,450.00,4242
2026-09-12,CORNER DELI,23.15,4242
2026-09-15,PAYMENT THANK YOU,-1235.45,4242
"""


def _import(body, groups=("ops",), b64=False):
    event = api_event("POST /transactions/import", groups=groups)
    event["headers"] = {"content-type": "text/csv"}
    event["body"] = body
    if b64:
        import base64
        event["body"] = base64.b64encode(body.encode()).decode()
        event["isBase64Encoded"] = True
    resp = transactions.handler(event)
    return resp["statusCode"], json.loads(resp["body"])


def _card_lines():
    return [line for line in ddb.get_ledger_entries("p1", "2026-01-01", "2026-12-31")
            if line["journalId"].startswith("j-card-")]


def test_import_categorizes_and_posts_balanced_journals(aws):
    repo.create_vendor("p1", "Orion Software", default_gl_account="6300")
    status, body = _import(CSV)
    assert status == 200
    assert body["imported"] == 4                # the -1235.45 card payment is skipped
    assert body["skipped"] == 1
    assert body["categorized"] == 3             # Zoom (keyword), Delta (keyword), Orion (vendor memory)
    by_desc = {t["description"]: t for t in body["transactions"]}
    assert by_desc["ZOOM.US 888-799-9666"]["glAccount"] == "6300"
    assert by_desc["DELTA AIR 0062345"]["glAccount"] == "6700"
    assert by_desc["Orion Software license"]["glAccount"] == "6300"
    assert by_desc["Orion Software license"]["categorizedBy"] == "vendor"
    assert "vendor memory" in by_desc["Orion Software license"]["categoryReason"]
    assert "keyword" in by_desc["ZOOM.US 888-799-9666"]["categoryReason"]
    assert "default expense account 6900" in by_desc["CORNER DELI"]["categoryReason"]
    assert by_desc["CORNER DELI"]["glAccount"] == "6900"   # uncategorized -> Other

    lines = _card_lines()
    assert len(lines) == 8
    balances = ledger.account_balances(lines)
    assert balances["2100"] == -(14990 + 61240 + 45000 + 2315)
    assert sum(balances.values()) == 0


def test_reimport_is_idempotent(aws):
    _import(CSV)
    status, body = _import(CSV)
    assert status == 200
    assert body["alreadyImported"] == 4
    assert body["imported"] == 0
    assert len(_card_lines()) == 8


def test_matches_receipt_by_merchant_amount_and_date(aws):
    doc = repo.create_document("p1", "deli.jpg", "image/jpeg", "uploads/p1/d1/deli.jpg", "dev")
    repo.update_document("p1", doc["documentId"], type="receipt", status="processed",
                         extracted={"vendorName": "Corner Deli", "amount": 23.15, "invoiceDate": "2026-09-11"})
    far = repo.create_document("p1", "old.jpg", "image/jpeg", "uploads/p1/d2/old.jpg", "dev")
    repo.update_document("p1", far["documentId"], type="receipt", status="processed",
                         extracted={"amount": 612.40, "invoiceDate": "2026-07-01"})   # date too far off

    status, body = _import(CSV)
    assert status == 200
    assert body["matchedReceipts"] == 1
    deli = next(t for t in body["transactions"] if t["description"] == "CORNER DELI")
    assert deli["receiptDocumentId"] == doc["documentId"]
    assert repo.get_document("p1", doc["documentId"])["cardTxnId"] == deli["txnId"]
    assert any(line["sourceDocId"] == doc["documentId"] for line in _card_lines())


def test_does_not_match_receipt_with_wrong_merchant_even_if_amount_and_date_match(aws):
    doc = repo.create_document("p1", "other.jpg", "image/jpeg", "uploads/p1/d1/other.jpg", "dev")
    repo.update_document("p1", doc["documentId"], type="receipt", status="processed",
                         extracted={"vendorName": "Different Merchant", "amount": 23.15,
                                    "invoiceDate": "2026-09-11"})

    status, body = _import(CSV)

    assert status == 200
    assert body["matchedReceipts"] == 0
    deli = next(t for t in body["transactions"] if t["description"] == "CORNER DELI")
    assert deli["receiptDocumentId"] is None
    assert repo.get_document("p1", doc["documentId"]).get("cardTxnId") is None


def test_receipt_with_ambiguous_equal_date_candidates_is_not_matched(aws):
    for index, day in enumerate(("2026-09-11", "2026-09-13"), start=1):
        doc = repo.create_document("p1", f"deli-{index}.jpg", "image/jpeg",
                                   f"uploads/p1/d{index}/deli.jpg", "dev")
        repo.update_document("p1", doc["documentId"], type="receipt", status="processed",
                             extracted={"vendorName": "Corner Deli", "amount": 23.15,
                                        "invoiceDate": day})

    status, body = _import(CSV)

    assert status == 200
    assert body["matchedReceipts"] == 0


def test_accepts_base64_body_and_alternate_headers(aws):
    csv = "Transaction Date,Merchant,Debit\n09/20/2026,Marriott Boston,389.00\n"
    status, body = _import(csv, b64=True)
    assert status == 200
    assert body["imported"] == 1
    assert body["transactions"][0]["date"] == "2026-09-20"
    assert body["transactions"][0]["glAccount"] == "6700"


def test_rejects_bad_csv_and_wrong_role(aws):
    assert _import("foo,bar\n1,2\n")[0] == 400
    assert _import("Date,Description,Amount\nnot-a-date,X,1.00\n")[0] == 400
    assert _import("Date,Description,Amount\n2026-09-01,X,abc\n")[0] == 400
    assert _import("")[0] == 400
    assert _import(CSV, groups=("partner",))[0] == 403


def test_list_transactions_reads_imported_charges(aws):
    _import(CSV)
    resp = transactions.handler(api_event("GET /transactions", groups=("owner",)))
    assert resp["statusCode"] == 200
    txns = json.loads(resp["body"])
    assert [t["description"] for t in txns][:1] == ["CORNER DELI"]  # newest first
    assert len(txns) == 4  # the payment row is skipped on import
    zoom = next(t for t in txns if t["description"].startswith("ZOOM"))
    assert (zoom["amount"], zoom["glAccount"], zoom["glAccountName"]) == (149.9, "6300", "Technology")
    assert "keyword" in zoom["categoryReason"]
    assert zoom["journalId"].startswith("j-card-")

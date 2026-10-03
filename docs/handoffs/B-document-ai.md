# Handoff → B (Document AI / Ingest)

Your pipeline sits between the upload and the bill. **Everything after you is already built:** the moment you call CreateBill, the rules, approvals, ledger and payment run on their own.

```
UI upload ─► S3 uploads/<practiceId>/<documentId>/<file>
                 │  (EventBridge "Object Created")
                 ├─► LockDocumentFunction  (already built: Object Lock retention)
                 └─► YOUR IngestDocument state machine
                        classify ─► Textract ─► normalize ─► match vendor
                           │
                           ├─ invoice ──────────────► invoke CreateBillFunction  ─► ApproveBill workflow (built)
                           ├─ receipt ─────────────► finalize + match card charge when available
                           ├─ w9 / void_check ─────► repo.record_vendor_docs     ─► held bills auto-resume (built)
                           └─ payout_statement ────► repo.put_revenue_lines + ledger.post_journal (payout)
```

## 1. Trigger
- Bucket: `DocsBucketName` ([deploy outputs](README.md)). S3 → EventBridge is **on**.
- Add an EventBridge rule: `source: aws.s3`, `detail-type: Object Created`, `detail.object.key: [{prefix: "uploads/"}]` → start your state machine.
- Parse ids from the key: `uploads/<practiceId>/<documentId>/<filename>`. Filenames are sanitized (no spaces), so no URL-decoding surprises.
- Object Lock is already handled by `LockDocumentFunction`; you don't need to touch it.

## 2. Keep the document updated (the UI polls it)
```python
repo.update_document(practice_id, document_id,
    type="invoice",            # invoice | receipt | void_check | w9 | payout_statement | unknown
    status="extracting",       # then "processed" or "needs_review"
    confidence=0.93, extracted={...})
```

## 3. Invoices → `CreateBillFunction`
Invoke it from your state machine (`arn:aws:states:::lambda:invoke`, ARN in deploy outputs):
```json
{"practiceId": "p1", "documentId": "doc_..", "vendorId": "ven_..", "vendorName": "Orion Software LLC",
 "amount": 1850.00, "invoiceNumber": "INV-2041", "invoiceDate": "2026-09-28", "dueDate": "2026-10-28",
 "glAccount": "6300", "lineItems": [{"description": "CRM seats", "amount": 1850.00}], "confidence": 0.93}
```
- Amounts in **dollars** here. Dates as `YYYY-MM-DD`.
- `vendorId` if your matcher found one; otherwise just `vendorName` (exact/alias match, else a new vendor is created).
- Omit `glAccount` to use the vendor's remembered default. If you pass one, it must be a 6xxx expense code (`shared/coa.py`).
- `confidence < 0.8` or no amount/vendor → bill goes to **Needs Review** instead of auto-processing. That's intended.
- Returns `{billId, status, isDuplicate}`. Duplicates (same vendor + invoice #) are blocked by the rules automatically.

## 4. Receipts → card matching, not bills
- A receipt never creates a payable bill.
- Confidence below `0.8` sets document status to `needs_review`; otherwise it is `processed`.
- Match a processed receipt to the closest unlinked card charge with the same amount within five days. This works whether the receipt or card CSV arrives first.

## 5. Vendor memory (the demo "wow")
In `shared/repo.py`: `list_vendors`, `find_vendor_by_name` (normalized exact + alias), `create_vendor`, **`add_vendor_alias`**.
After a fuzzy match (e.g. "ORION SOFTWARE, INC." → Orion Software LLC), call `add_vendor_alias(p, vendor_id, raw_name)` so it's an exact hit next time.

## 6. W-9 / void check
```python
repo.record_vendor_docs(practice_id, vendor_id, has_w9=True, has_void_check=True,
                        bank_last4="6789", document_id=doc_id)
```
This emits `VendorUpdated`. Any bill on hold for that vendor re-runs the rules by itself. That's the "upload the W-9 and the bill un-blocks" demo moment.

## 7. Payout statements
Two calls: one for reconciliation (D) and one for the ledger.
```python
repo.put_revenue_lines(p, "2026-09", doc_id, [
    {"source": "advisory", "label": "Advisory fees", "actual": 18240000},           # INTEGER CENTS
    {"source": "trail", "ref": "4471", "label": "VA trail 4471", "actual": 247800}])
ledger.post_journal(p, f"j-payout-{doc_id}", "2026-09-30",
    ledger.payout_lines({"advisory": 182400.00, "trail": 2478.00}),               # dollars in, cents stored
    memo="LPL payout statement Sep 2026", source_doc_id=doc_id, source_type="payout", source_id=doc_id)
```
- `source`: `advisory · commission · trail · other`. Put the contract/fund number in `ref` (D matches on it).
- Both calls are safe to re-run (same doc → overwrite / no-op).

## 7. Adding your state machine
Send Jay your ASL file and the Lambdas. He'll add them to `template.yaml` with the right permissions (Textract, Bedrock, invoke `CreateBillFunction`, DynamoDB). Put Lambda code under `backend/src/ingest/` so it can `from shared import repo, ledger`.

**Test without AWS:** `pytest` in `backend/` uses moto. `tests/test_bill_flow.py` shows CreateBill being called exactly as above.

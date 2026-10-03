import unittest
from decimal import Decimal
from types import ModuleType
from unittest.mock import Mock, patch

from ingest.classify import validate_classification
from ingest.common import invoke_bedrock_json, upload_context
from ingest.match_vendor import best_vendor_match
from ingest.normalize import (
    _normalized_vendor_document,
    _period,
    normalize_invoice,
)
from ingest.route import (
    complete_bill_handler,
    handler as route_handler,
    prepare_bill,
)


class IngestValidationTests(unittest.TestCase):
    def test_bedrock_converse_does_not_send_deprecated_temperature(self) -> None:
        client = Mock()
        client.converse.return_value = {
            "output": {"message": {"content": [{"text": '{"type":"invoice"}'}]}}
        }
        with (
            patch.dict("os.environ", {"BEDROCK_MODEL_ID": "us.test-model"}),
            patch("boto3.client", return_value=client),
        ):
            result = invoke_bedrock_json("classify")

        self.assertEqual(result, {"type": "invoice"})
        self.assertEqual(
            client.converse.call_args.kwargs["inferenceConfig"],
            {"maxTokens": 1200},
        )

    def test_ask_model_id_must_be_configured(self) -> None:
        from ask.bedrock import model_id

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ASK_MODEL_ID must be set"):
                model_id()
        with patch.dict("os.environ", {"ASK_MODEL_ID": "approved.model-id"}):
            self.assertEqual(model_id(), "approved.model-id")

    def test_parses_practice_and_document_from_upload_key(self) -> None:
        self.assertEqual(
            upload_context(
                {
                    "detail": {
                        "bucket": {"name": "ledgerline-docs"},
                        "object": {"key": "uploads/p1/doc-7/statement.pdf"},
                    }
                }
            ),
            {
                "bucket": "ledgerline-docs",
                "key": "uploads/p1/doc-7/statement.pdf",
                "practiceId": "p1",
                "documentId": "doc-7",
                "filename": "statement.pdf",
            },
        )

    def test_rejects_non_upload_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "uploads/<practiceId>"):
            upload_context({"bucket": "docs", "key": "other/p1/doc/file.pdf"})

    def test_validates_classifier_output(self) -> None:
        self.assertEqual(
            validate_classification({"type": "invoice", "confidence": 0.93}),
            ("invoice", 0.93),
        )
        with self.assertRaisesRegex(ValueError, "Unsupported document type"):
            validate_classification({"type": "bank_statement", "confidence": 0.9})
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            validate_classification({"type": "receipt", "confidence": 1.2})

    def test_normalizes_invoice_amounts_and_rejects_invalid_account(self) -> None:
        result = normalize_invoice(
            "invoice",
            {
                "confidence": 0.95,
                "vendorConfidence": 0.98,
                "vendorName": "Orion Software LLC",
                "amount": "$1,850.00",
                "invoiceNumber": "INV-2041",
                "invoiceDate": "2026-09-28",
                "dueDate": "2026-10-28",
                "glAccount": "6300",
                "lineItems": [{"description": "CRM seats", "amount": "1850.00"}],
            },
        )
        self.assertEqual(result["amount"], 1850.0)
        self.assertEqual(result["lineItems"][0]["amount"], 1850.0)
        self.assertEqual(result["confidence"], 0.95)
        self.assertEqual(result["vendorConfidence"], 0.98)
        with self.assertRaisesRegex(ValueError, "6xxx expense code"):
            normalize_invoice(
                "invoice",
                {
                    "confidence": 0.9,
                    "vendorConfidence": 0.9,
                    "glAccount": "4100",
                    "lineItems": [],
                },
            )

    def test_sub_account_codes_are_kept_and_unknown_ones_fall_back(self) -> None:
        base = {"confidence": 0.9, "vendorConfidence": 0.9, "lineItems": []}
        self.assertEqual(normalize_invoice("receipt", {**base, "glAccount": "6740"})["glAccount"], "6740")
        self.assertEqual(normalize_invoice("receipt", {**base, "glAccount": "6790"})["glAccount"], "6700")
        self.assertIsNone(normalize_invoice("receipt", {**base, "glAccount": "6890"})["glAccount"])

    def test_low_vendor_confidence_lowers_bill_confidence(self) -> None:
        result = normalize_invoice(
            "receipt",
            {
                "confidence": 0.98,
                "vendorConfidence": 0.55,
                "vendorName": "Brightline Marketing",
                "amount": 42.50,
            },
        )
        self.assertEqual(result["amount"], 42.5)
        self.assertEqual(result["vendorConfidence"], 0.55)
        self.assertEqual(result["confidence"], 0.55)

    def test_low_vendor_confidence_marks_completed_bill_for_review(self) -> None:
        repo = Mock()
        config = ModuleType("config")
        config.REVIEW_CONFIDENCE_THRESHOLD = 0.8
        shared = ModuleType("shared")
        shared.config = config
        shared.repo = repo
        event = {
            "classification": {
                "data": {
                    "bucket": "docs",
                    "key": "uploads/p1/d1/receipt.pdf",
                    "practiceId": "p1",
                    "documentId": "d1",
                    "filename": "receipt.pdf",
                    "documentType": "receipt",
                }
            },
            "normalization": {
                "data": {
                    "normalized": {
                        "type": "receipt",
                        "confidence": 0.95,
                        "vendorConfidence": 0.55,
                        "vendorName": "Brightline Marketing",
                        "amount": 42.5,
                    }
                }
            },
            "createdBill": {
                "data": {"bill": {"billId": "bill-1", "status": "pending_review"}}
            },
        }

        with patch.dict("sys.modules", {"shared": shared}):
            result = complete_bill_handler(event)

        self.assertEqual(result, {"status": "needs_review", "billId": "bill-1"})
        update = repo.update_document.call_args.kwargs
        self.assertEqual(update["status"], "needs_review")
        self.assertEqual(update["confidence"], 0.55)
        self.assertEqual(
            update["extracted"]["reviewReason"],
            "Vendor identity confidence requires confirmation",
        )

    def test_invoice_requires_vendor_confidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "confidence must be a number"):
            normalize_invoice("invoice", {"confidence": 0.95, "amount": 100})

    def test_normalizes_check_digits_and_statement_period(self) -> None:
        result = _normalized_vendor_document(
            "void_check",
            {"confidence": 0.9, "vendorName": "Northstar LLC", "bankLast4": "xx 6789"},
        )
        self.assertEqual(result["bankLast4"], "6789")
        self.assertEqual(_period("2026-09"), "2026-09")
        with self.assertRaisesRegex(ValueError, "invalid month"):
            _period("2026-13")

    def test_vendor_fuzzy_match_rejects_ambiguous_candidates(self) -> None:
        vendors = [
            {"vendorId": "v1", "name": "Orion Software LLC"},
            {"vendorId": "v2", "name": "Orion Software Inc"},
        ]
        self.assertIsNone(best_vendor_match("Orion Softwre LLC", vendors))
        match = best_vendor_match(
            "Northstar Software Ltd",
            [{"vendorId": "v3", "name": "Northstar Software LLC"}],
        )
        self.assertEqual(match["vendorId"], "v3")

    def test_prepare_bill_uses_matched_vendor_and_dollars(self) -> None:
        event = {
            "classification": {
                "data": {
                    "bucket": "docs",
                    "key": "uploads/p1/d1/invoice.pdf",
                    "practiceId": "p1",
                    "documentId": "d1",
                    "filename": "invoice.pdf",
                    "documentType": "invoice",
                }
            },
            "normalization": {
                "data": {
                    "normalized": {
                        "type": "invoice",
                        "confidence": 0.93,
                        "vendorConfidence": 0.55,
                        "vendorName": "ORION SOFTWARE INC.",
                        "amount": 1850.0,
                        "invoiceNumber": "INV-2041",
                        "invoiceDate": "2026-09-28",
                        "dueDate": "2026-10-28",
                        "glAccount": "6300",
                        "lineItems": [{"description": "CRM seats", "amount": 1850.0}],
                    }
                }
            },
            "vendorMatch": {
                "data": {
                    "vendor": {
                        "vendorId": "ven-1",
                        "name": "Orion Software LLC",
                        "defaultGlAccount": "6300",
                    }
                }
            },
        }
        payload = prepare_bill(event, Mock())
        self.assertEqual(payload["vendorId"], "ven-1")
        self.assertEqual(payload["vendorName"], "Orion Software LLC")
        self.assertEqual(payload["amount"], 1850.0)
        self.assertEqual(payload["glAccount"], "6300")
        self.assertIn("invoice details", payload["glAccountReason"])
        self.assertEqual(payload["confidence"], 0.55)

    def test_prepare_bill_explains_extracted_and_fallback_gl_accounts(self) -> None:
        event = {
            "classification": {"data": {"bucket": "docs", "key": "uploads/p1/d1/invoice.pdf",
                                        "practiceId": "p1", "documentId": "d1",
                                        "filename": "invoice.pdf", "documentType": "invoice"}},
            "normalization": {"data": {"normalized": {"type": "invoice", "confidence": 0.9,
                                                        "vendorConfidence": 0.9, "vendorName": "Unknown",
                                                        "amount": 10, "glAccount": "6500"}}},
            "vendorMatch": {"data": {"vendor": None}},
        }
        extracted = prepare_bill(event)
        self.assertEqual(extracted["glAccount"], "6500")
        self.assertIn("invoice details", extracted["glAccountReason"])

        event["normalization"]["data"]["normalized"]["glAccount"] = None
        event["vendorMatch"]["data"]["vendor"] = {
            "vendorId": "ven-1", "name": "Known Vendor", "defaultGlAccount": "6300"
        }
        vendor_default = prepare_bill(event)
        self.assertEqual(vendor_default["glAccount"], "6300")
        self.assertIn("vendor memory", vendor_default["glAccountReason"])

        event["vendorMatch"]["data"]["vendor"] = None
        fallback = prepare_bill(event)
        self.assertEqual(fallback["glAccount"], "6900")
        self.assertIn("default expense account", fallback["glAccountReason"])
    def test_payout_is_saved_for_reconciliation_and_posted_to_ledger(self) -> None:
        repo = Mock()
        ledger = Mock()
        ledger.payout_lines.return_value = [{"account": "balanced"}]
        shared = ModuleType("shared")
        shared.repo = repo
        shared.ledger = ledger
        event = {
            "classification": {
                "data": {
                    "bucket": "docs",
                    "key": "uploads/p1/d3/payout.pdf",
                    "practiceId": "p1",
                    "documentId": "d3",
                    "filename": "payout.pdf",
                    "documentType": "payout_statement",
                    "confidence": 0.99,
                }
            },
            "normalization": {
                "data": {
                    "normalized": {
                        "type": "payout_statement",
                        "confidence": 0.99,
                        "period": "2026-09",
                        "revenueLines": [
                            {
                                "id": "d3-line-1",
                                "source": "trail",
                                "ref": "4471",
                                "label": "VA trail 4471",
                                "actual": 247800,
                                "docId": "d3",
                            }
                        ],
                    }
                }
            },
            "vendorMatch": {"data": {"vendor": None}},
        }

        with patch.dict("sys.modules", {"shared": shared}):
            result = route_handler(event)

        self.assertEqual(result["status"], "processed")
        repo.put_revenue_lines.assert_called_once_with(
            "p1", "2026-09", "d3", event["normalization"]["data"]["normalized"]["revenueLines"]
        )
        ledger.payout_lines.assert_called_once()
        self.assertEqual(
            ledger.payout_lines.call_args.args[0]["trail"], Decimal("2478")
        )
        ledger.post_journal.assert_called_once()
        self.assertEqual(ledger.post_journal.call_args.args[2], "2026-09-30")


if __name__ == "__main__":
    unittest.main()

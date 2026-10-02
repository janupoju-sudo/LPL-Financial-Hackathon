import unittest
from decimal import Decimal
from types import ModuleType
from unittest.mock import Mock, patch

from ingest.classify import validate_classification
from ingest.common import upload_context
from ingest.match_vendor import best_vendor_match
from ingest.normalize import (
    _normalized_vendor_document,
    _period,
    normalize_invoice,
)
from ingest.route import handler as route_handler, prepare_bill


class IngestValidationTests(unittest.TestCase):
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
        with self.assertRaisesRegex(ValueError, "6xxx expense code"):
            normalize_invoice(
                "invoice",
                {"confidence": 0.9, "glAccount": "4100", "lineItems": []},
            )

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
        payload = prepare_bill(event)
        self.assertEqual(payload["vendorId"], "ven-1")
        self.assertEqual(payload["vendorName"], "Orion Software LLC")
        self.assertEqual(payload["amount"], 1850.0)
        self.assertEqual(payload["glAccount"], "6300")

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

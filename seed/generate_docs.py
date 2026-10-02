#!/usr/bin/env python3
"""Generate the E8 demo PDF set for the Ledgerline hackathon.

This is intentionally a local-only artifact: every file is marked with
"SAMPLE — FICTIONAL DATA" and keeps the vendor names, references, and amounts
consistent with the seeded practice and reconciliation logic.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

WATERMARK_TEXT = "SAMPLE — FICTIONAL DATA"
SEEDED_SOURCE_PREFIX = "seed-sources"


def add_watermark(pdf) -> None:
    pdf.saveState()
    pdf.translate(4.5 * inch, 5.5 * inch)
    pdf.rotate(45)
    pdf.setFillColor(HexColor("#DDE7FF"))
    pdf.setFont("Helvetica-Bold", 36)
    pdf.drawCentredString(0, 0, WATERMARK_TEXT)
    pdf.restoreState()


def add_footer(pdf, title: str) -> None:
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.setFillColor(HexColor("#475569"))
    pdf.drawRightString(letter[0] - 0.6 * inch, 0.5 * inch, f"{title} • SAMPLE — FICTIONAL DATA")


def draw_table(pdf, rows, x, y, cols, row_h=0.35 * inch):
    pdf.setStrokeColor(HexColor("#CBD5E1"))
    pdf.setFillColor(HexColor("#F8FAFC"))
    pdf.setFont("Helvetica-Bold", 10)
    for idx, (label, value) in enumerate(rows):
        yy = y - idx * row_h
        pdf.rect(x, yy - row_h + 0.05 * inch, cols[0], row_h, fill=1, stroke=1)
        pdf.rect(x + cols[0], yy - row_h + 0.05 * inch, cols[1], row_h, fill=1, stroke=1)
        pdf.setFillColor(HexColor("#0F172A"))
        pdf.drawString(x + 0.12 * inch, yy - 0.12 * inch, label)
        pdf.drawString(x + cols[0] + 0.12 * inch, yy - 0.12 * inch, value)
        pdf.setFillColor(HexColor("#F8FAFC"))


def make_invoice(path: Path, *, filename: str, vendor_name: str, amount: float,
                invoice_number: str, invoice_date: str, due_date: str, approval_note: str,
                title: str = "Invoice") -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setTitle(f"{vendor_name} {title}")
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(0.75 * inch, 10.25 * inch, title)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.75 * inch, 9.9 * inch, "Ledgerline Demo Document")
    add_watermark(pdf)

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(0.75 * inch, 8.7 * inch, vendor_name)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(0.75 * inch, 8.35 * inch, f"Invoice #: {invoice_number}")
    pdf.drawString(0.75 * inch, 8.0 * inch, f"Issue date: {invoice_date}")
    pdf.drawString(0.75 * inch, 7.65 * inch, f"Due date: {due_date}")

    pdf.setFillColor(HexColor("#1D4ED8"))
    pdf.setFont("Helvetica-Bold", 32)
    pdf.drawRightString(7.75 * inch, 8.65 * inch, f"${amount:,.2f}")
    pdf.setFillColor(HexColor("#0F172A"))

    rows = [
        ("Service", "Software subscription / digital marketing services"),
        ("GL account", "6300 (technology)" if vendor_name == "Orion Software LLC" else "6500 (marketing)"),
        ("Status", approval_note),
        ("Notes", "Fictional document generated for demo workflow validation."),
    ]
    x = 0.75 * inch
    y = 6.75 * inch
    cols = (2.25 * inch, 4.75 * inch)
    draw_table(pdf, rows, x, y, cols, row_h=0.45 * inch)

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(0.75 * inch, 2.1 * inch, "For demo use only")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(0.75 * inch, 1.75 * inch, "This document is not a live vendor invoice and should not be uploaded to a production account.")
    add_footer(pdf, filename)
    pdf.save()


def make_w9(path: Path, *, filename: str) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setTitle("Brightline Marketing W-9")
    add_watermark(pdf)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(0.75 * inch, 10.25 * inch, "Form W-9")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.75 * inch, 9.9 * inch, "Request for Taxpayer Identification Number and Certification")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(0.75 * inch, 8.8 * inch, "Brightline Marketing")
    pdf.setFont("Helvetica", 10)
    lines = [
        "Business name: Brightline Marketing",
        "Business address: 1810 Highland Loop, Suite 200, Denver, CO 80202",
        "Tax classification: LLC",
        "EIN: 12-3456789",
        "Authorized representative: Dana Lasker",
        "Certification: I certify under penalty of perjury that the information above is true.",
    ]
    y = 8.2 * inch
    for line in lines:
        pdf.drawString(0.75 * inch, y, line)
        y -= 0.35 * inch
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(0.75 * inch, 2.5 * inch, "Signature: Dana Lasker")
    pdf.drawString(5.2 * inch, 2.5 * inch, "Date: 2026-09-03")
    add_footer(pdf, filename)
    pdf.save()


def make_void_check(path: Path, *, filename: str) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setTitle("Brightline Marketing Void Check")
    add_watermark(pdf)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(0.75 * inch, 10.4 * inch, "VOID CHECK")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.75 * inch, 9.8 * inch, "Brightline Marketing")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(0.75 * inch, 8.7 * inch, "Pay to the order of")
    pdf.drawString(0.75 * inch, 7.9 * inch, "________________________")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(4.4 * inch, 8.7 * inch, "$__________________")
    pdf.drawString(4.4 * inch, 7.9 * inch, "Check # 2410149")
    pdf.drawString(0.75 * inch, 6.7 * inch, "Routing: 021000021")
    pdf.drawString(0.75 * inch, 6.25 * inch, "Account: 302581198")
    pdf.drawString(0.75 * inch, 5.8 * inch, "Bank: Harbor Community Bank")
    pdf.drawString(0.75 * inch, 5.35 * inch, "Authorized signature: ____________________")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(0.75 * inch, 2.3 * inch, "This check is intentionally void and used only for vendor onboarding verification.")
    add_footer(pdf, filename)
    pdf.save()


def make_receipt(path: Path, *, filename: str) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setTitle("Messy Receipt")
    add_watermark(pdf)
    pdf.setFillColor(HexColor("#f8fafc"))
    pdf.rect(0.4 * inch, 0.5 * inch, 7.9 * inch, 10.5 * inch, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(0.9 * inch, 10.3 * inch, "Riverside Cafe")
    pdf.setFont("Helvetica", 10)
    for label, value in [
        ("Date:", "2026-09-22"),
        ("Receipt #:", "RCPT-09122"),
        ("Merchant:", "Riverside Cafe - Team Dinner"),
        ("Total:", "$37.18"),
    ]:
        pdf.drawString(0.9 * inch, 9.7 * inch - 0.35 * inch * len(label), f"{label} {value}")

    pdf.setFillColor(HexColor("#A1A1AA"))
    for y in range(8, 3, -1):
        pdf.drawString(1.0 * inch, y * 0.65 * inch, "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _")
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(1.0 * inch, 5.0 * inch, "Line items")
    pdf.setFont("Helvetica", 10)
    rows = [
        ("2x Bistro sandwiches", "$18.00"),
        ("1x House salad", "$9.25"),
        ("2x Lemonades", "$7.95"),
        ("Tax", "$1.98"),
        ("Total", "$37.18"),
    ]
    y = 4.5 * inch
    for label, value in rows:
        pdf.drawString(1.0 * inch, y, label)
        pdf.drawRightString(7.2 * inch, y, value)
        y -= 0.35 * inch

    pdf.setStrokeColor(HexColor("#94A3B8"))
    for i in range(0, 20):
        x_start = 0.8 * inch + i * 0.18 * inch
        pdf.line(x_start, 2.1 * inch, x_start + 0.6 * inch, 2.7 * inch)
    pdf.setFillColor(HexColor("#F59E0B"))
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(4.4 * inch, 3.0 * inch, "RECEIPT")
    pdf.setFillColor(HexColor("#0F172A"))
    add_footer(pdf, filename)
    pdf.save()


def make_payout_statement(path: Path, *, filename: str) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter, pageCompression=0)
    pdf.setTitle("LPL Payout Statement September 2026")
    add_watermark(pdf)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(0.75 * inch, 10.4 * inch, "LPL Financial")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.75 * inch, 10.0 * inch, "Payout statement • September 2026")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(0.75 * inch, 8.75 * inch, "Revenue summary")

    row_data = [
        ("Advisory fees", "advisory", "", "$182,400.00"),
        ("Mutual fund commissions", "commission", "", "$14,200.00"),
        ("Monthly 12b-1 trails", "trail", "12b1", "$6,150.00"),
        ("Variable annuity trail, contract 4471", "trail", "4471", "$2,478.00"),
    ]

    headers = ["Description", "Source", "Reference", "Amount"]
    col_x = [0.9 * inch, 3.0 * inch, 4.8 * inch, 6.5 * inch]
    y = 7.95 * inch
    pdf.setFillColor(HexColor("#E2E8F0"))
    pdf.rect(0.7 * inch, y - 0.2 * inch, 7.1 * inch, 0.32 * inch, fill=1, stroke=1)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 9)
    for idx, header in enumerate(headers):
        pdf.drawString(col_x[idx], y - 0.08 * inch, header)

    pdf.setFont("Helvetica", 9)
    for row_index, (description, source, reference, amount) in enumerate(row_data, start=1):
        row_y = y - row_index * 0.42 * inch - 0.12 * inch
        pdf.rect(0.7 * inch, row_y - 0.2 * inch, 7.1 * inch, 0.32 * inch, fill=0, stroke=1)
        pdf.drawString(col_x[0], row_y, description)
        pdf.drawString(col_x[1], row_y, source)
        pdf.drawString(col_x[2], row_y, reference)
        pdf.drawRightString(col_x[3] + 0.6 * inch, row_y, amount)

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(0.9 * inch, 3.4 * inch, "Total paid")
    pdf.drawRightString(7.3 * inch, 3.4 * inch, "$205,228.00")
    add_footer(pdf, filename)
    pdf.save()


def make_lease_amendment(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter, pageCompression=0)
    pdf.setTitle("Fictional Lease Amendment - July 2026")
    add_watermark(pdf)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(0.75 * inch, 10.25 * inch, "Lease Amendment")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.75 * inch, 9.85 * inch, "Harbor Point Properties (FICTIONAL)")
    pdf.drawString(0.75 * inch, 9.3 * inch, "Tenant: Harbor Point Wealth (FICTIONAL)")
    pdf.drawString(0.75 * inch, 8.85 * inch, "Effective date: 2026-07-01")
    pdf.drawString(0.75 * inch, 8.4 * inch, "Previous monthly rent: $9,800.00")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(0.75 * inch, 7.85 * inch, "New monthly rent: $12,200.00")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(0.75 * inch, 7.25 * inch, "Account: 6200 - rent and occupancy")
    pdf.drawString(0.75 * inch, 6.8 * inch, "This fictional amendment is effective for rent beginning July 2026.")
    pdf.drawString(0.75 * inch, 1.3 * inch, "Local demo source document; cloud upload is pending.")
    add_footer(pdf, path.name)
    pdf.save()


def make_compliance_invoice(path: Path, *, year: int, month: int) -> None:
    tag = f"{year}-{month:02d}"
    pdf = canvas.Canvas(str(path), pagesize=letter, pageCompression=0)
    pdf.setTitle(f"Fictional Compliance Consultant Invoice {tag}")
    add_watermark(pdf)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(0.75 * inch, 10.25 * inch, "Consulting Invoice")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.75 * inch, 9.85 * inch, "Clearwater Compliance Advisors (FICTIONAL)")
    pdf.drawString(0.75 * inch, 9.3 * inch, "Bill to: Harbor Point Wealth (FICTIONAL)")
    pdf.drawString(0.75 * inch, 8.85 * inch, f"Invoice #: CCA-{year}-{month:02d}")
    pdf.drawString(0.75 * inch, 8.4 * inch, f"Invoice date: {year}-{month:02d}-05")
    pdf.drawString(0.75 * inch, 7.95 * inch, f"Service period: {tag}")
    pdf.drawString(0.75 * inch, 7.5 * inch, "Regulatory compliance consulting")
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawRightString(7.5 * inch, 6.85 * inch, "$2,550.00")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(0.75 * inch, 6.3 * inch, "Expense account: 6600 - compliance and licensing")
    pdf.drawString(0.75 * inch, 1.3 * inch, "Fictional invoice for local demo-seed validation.")
    add_footer(pdf, path.name)
    pdf.save()


def make_historical_payout_statement(path: Path, *, year: int, month: int) -> None:
    tag = f"{year}-{month:02d}"
    quarterly = month in {3, 6, 9, 12}
    row_data = [
        ("Advisory fees", "advisory", "", "$182,400.00"),
        ("Mutual fund commissions", "commission", "", "$14,200.00"),
        ("Monthly 12b-1 trails", "trail", "12b1", "$6,150.00"),
    ]
    total_paid = 202_750
    if quarterly:
        row_data.append(("Variable annuity trail, contract 4471", "trail", "4471", "$2,890.00"))
        total_paid += 2_890

    pdf = canvas.Canvas(str(path), pagesize=letter, pageCompression=0)
    pdf.setTitle(f"Fictional LPL Payout Statement {tag}")
    add_watermark(pdf)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(0.75 * inch, 10.25 * inch, "LPL Financial")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.75 * inch, 9.85 * inch, f"Payout statement - {tag}")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(0.75 * inch, 9.2 * inch, "Received payments")

    headers = ["Description", "Source", "Reference", "Amount"]
    col_x = [0.9 * inch, 3.0 * inch, 4.8 * inch, 6.5 * inch]
    y = 8.65 * inch
    pdf.setFillColor(HexColor("#E2E8F0"))
    pdf.rect(0.7 * inch, y - 0.2 * inch, 7.1 * inch, 0.32 * inch, fill=1, stroke=1)
    pdf.setFillColor(HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 9)
    for idx, header in enumerate(headers):
        pdf.drawString(col_x[idx], y - 0.08 * inch, header)
    pdf.setFont("Helvetica", 9)
    for row_index, row in enumerate(row_data, start=1):
        row_y = y - row_index * 0.42 * inch - 0.12 * inch
        pdf.rect(0.7 * inch, row_y - 0.2 * inch, 7.1 * inch, 0.32 * inch, fill=0, stroke=1)
        for col_index, value in enumerate(row):
            if col_index == 3:
                pdf.drawRightString(col_x[col_index] + 0.6 * inch, row_y, value)
            else:
                pdf.drawString(col_x[col_index], row_y, value)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(0.9 * inch, 5.45 * inch, "Total paid")
    pdf.drawRightString(7.3 * inch, 5.45 * inch, f"${total_paid:,.2f}")
    pdf.drawString(0.75 * inch, 1.3 * inch, "Fictional historical sample; cloud upload is pending.")
    add_footer(pdf, path.name)
    pdf.save()


def payout_rows() -> list[dict[str, object]]:
    return [
        {
            "id": "adv-1",
            "source": "advisory",
            "label": "Advisory fees",
            "actual": 18_240_000,
            "ref": "",
        },
        {
            "id": "comm-1",
            "source": "commission",
            "label": "Mutual fund commissions",
            "actual": 1_420_000,
            "ref": "",
        },
        {
            "id": "trail-12b1",
            "source": "trail",
            "label": "Monthly 12b-1 trails",
            "actual": 615_000,
            "ref": "12b1",
        },
        {
            "id": "trail-4471",
            "source": "trail",
            "label": "Variable annuity trail, contract 4471",
            "actual": 247_800,
            "ref": "4471",
        },
    ]


def build_manifest(output_dir: Path) -> dict:
    return {
        "generated_by": "seed/generate_docs.py",
        "watermark": WATERMARK_TEXT,
        "source_documents": source_document_manifest(),
        "files": [
            {
                "filename": "orion_invoice_450_2026-09-02.pdf",
                "document_type": "invoice",
                "s3_key_template": "uploads/{practiceId}/{documentId}/{filename}",
                "vendor_name": "Orion Software LLC",
                "expected_fields": {
                    "vendor_name": "Orion Software LLC",
                    "amount": 450.00,
                    "invoice_number": "INV-OR-2026-0902-001",
                    "invoice_date": "2026-09-02",
                    "due_date": "2026-09-30",
                    "gl_account": "6300",
                },
                "workflow_outcome": {
                    "status": "approved",
                    "rule": "auto_approve",
                    "reason": "amount <= $1,000 and vendor is already recognized",
                },
            },
            {
                "filename": "orion_invoice_1850_2026-09-12.pdf",
                "document_type": "invoice",
                "s3_key_template": "uploads/{practiceId}/{documentId}/{filename}",
                "vendor_name": "Orion Software LLC",
                "expected_fields": {
                    "vendor_name": "Orion Software LLC",
                    "amount": 1850.00,
                    "invoice_number": "INV-OR-2026-0912-002",
                    "invoice_date": "2026-09-12",
                    "due_date": "2026-10-12",
                    "gl_account": "6300",
                },
                "workflow_outcome": {
                    "status": "pending_approval",
                    "rule": "require_approval",
                    "required_approvers": ["partner", "owner"],
                    "reason": "amount > $1,000",
                },
            },
            {
                "filename": "brightline_invoice_650_2026-09-18.pdf",
                "document_type": "invoice",
                "s3_key_template": "uploads/{practiceId}/{documentId}/{filename}",
                "vendor_name": "Brightline Marketing",
                "expected_fields": {
                    "vendor_name": "Brightline Marketing",
                    "amount": 650.00,
                    "invoice_number": "INV-BRT-2026-0918-003",
                    "invoice_date": "2026-09-18",
                    "due_date": "2026-10-18",
                    "gl_account": "6500",
                    "onboarding_docs_missing": ["w9", "void_check"],
                },
                "workflow_outcome": {
                    "status": "held",
                    "rule": "vendor_docs_required",
                    "reason": "new vendor requires both W-9 and void check before approval",
                },
            },
            {
                "filename": "brightline_w9.pdf",
                "document_type": "w9",
                "s3_key_template": "uploads/{practiceId}/{documentId}/{filename}",
                "vendor_name": "Brightline Marketing",
                "expected_fields": {
                    "vendor_name": "Brightline Marketing",
                    "tax_id": "12-3456789",
                    "business_type": "LLC",
                    "authorized_signatory": "Dana Lasker",
                },
                "workflow_outcome": {
                    "status": "vendor_updated",
                    "reason": "W-9 arrives; vendor becomes eligible for review after matching",
                },
            },
            {
                "filename": "brightline_void_check.pdf",
                "document_type": "void_check",
                "s3_key_template": "uploads/{practiceId}/{documentId}/{filename}",
                "vendor_name": "Brightline Marketing",
                "expected_fields": {
                    "vendor_name": "Brightline Marketing",
                    "routing_number": "021000021",
                    "account_number": "302581198",
                    "bank_name": "Harbor Community Bank",
                },
                "workflow_outcome": {
                    "status": "vendor_updated",
                    "reason": "void check arrives; hold is cleared once W-9 and void check are both on file",
                },
            },
            {
                "filename": "receipt_scanned_2026-09-22.pdf",
                "document_type": "receipt",
                "s3_key_template": "uploads/{practiceId}/{documentId}/{filename}",
                "vendor_name": "Riverside Cafe",
                "expected_fields": {
                    "merchant": "Riverside Cafe",
                    "receipt_number": "RCPT-09122",
                    "date": "2026-09-22",
                    "total": 37.18,
                    "line_item_count": 5,
                },
                "workflow_outcome": {
                    "status": "needs_review",
                    "reason": "receipt is readable but the match is uncertain; allow human validation if vendor confidence is low",
                },
            },
            {
                "filename": "lpl_payout_statement_sep_2026.pdf",
                "document_type": "payout_statement",
                "document_id": "doc_lpl_payout_statement_sep_2026",
                "s3_key_template": "uploads/{practiceId}/doc_lpl_payout_statement_sep_2026/lpl_payout_statement_sep_2026.pdf",
                "upload_status": "pending",
                "vendor_name": "LPL Financial",
                "expected_fields": {
                    "vendor_name": "LPL Financial",
                    "statement_month": "2026-09",
                    "advisory_fees": 182400.00,
                    "mutual_fund_commissions": 14200.00,
                    "monthly_12b1_trails": 6150.00,
                    "actual_4471_cents": 247800,
                    "expected_4471_cents": 289000,
                    "total_paid": 205228,
                    "revenueLines": payout_rows(),
                },
                "workflow_outcome": {
                    "status": "short",
                    "total_paid": 205228,
                    "actual_4471_cents": 247800,
                    "expected_4471_cents": 289000,
                    "variance_cents": -41200,
                    "reason": "contract 4471 shortfall: actual 247800, expected 289000",
                },
            },
        ],
    }


def source_document_manifest() -> list[dict[str, object]]:
    documents = []
    for year, month in _history_months():
        tag = f"{year}-{month:02d}"
        doc_id = f"doc_lpl_payout_{year}_{month:02d}"
        filename = f"lpl_payout_statement_{tag}.pdf"
        total_paid = 202_750 + (2_890 if month in {3, 6, 9, 12} else 0)
        documents.append({
            "document_id": doc_id,
            "filename": filename,
            "local_path": f"sources/{filename}",
            "document_type": "payout_statement",
            "period": tag,
            "amount_dollars": total_paid,
            "s3_key_template": f"{SEEDED_SOURCE_PREFIX}/{{practiceId}}/{doc_id}/{filename}",
            "upload_status": "pending",
        })

    lease_id = "doc_lease_amendment_2026_07"
    lease_filename = "lease_amendment_effective_2026-07-01.pdf"
    documents.append({
        "document_id": lease_id,
        "filename": lease_filename,
        "local_path": f"sources/{lease_filename}",
        "document_type": "invoice",
        "vendor_name": "Harbor Point Properties (FICTIONAL)",
        "effective_date": "2026-07-01",
        "previous_monthly_rent_dollars": 9_800,
        "monthly_rent_dollars": 12_200,
        "expense_account": "6200",
        "s3_key_template": f"{SEEDED_SOURCE_PREFIX}/{{practiceId}}/{lease_id}/{lease_filename}",
        "upload_status": "pending",
    })

    for month in (7, 8, 9):
        tag = f"2026-{month:02d}"
        doc_id = f"doc_compliance_invoice_2026_{month:02d}"
        filename = f"compliance_consultant_invoice_{tag}.pdf"
        documents.append({
            "document_id": doc_id,
            "filename": filename,
            "local_path": f"sources/{filename}",
            "document_type": "invoice",
            "vendor_name": "Clearwater Compliance Advisors (FICTIONAL)",
            "invoice_number": f"CCA-2026-{month:02d}",
            "invoice_date": f"{tag}-05",
            "amount_dollars": 2_550,
            "expense_account": "6600",
            "s3_key_template": f"{SEEDED_SOURCE_PREFIX}/{{practiceId}}/{doc_id}/{filename}",
            "upload_status": "pending",
        })

    fallback_id = "doc_lpl_payout_statement_sep_2026_fallback"
    fallback_filename = "lpl_payout_statement_sep_2026.pdf"
    documents.append({
        "document_id": fallback_id,
        "filename": fallback_filename,
        "local_path": fallback_filename,
        "document_type": "payout_statement_fallback",
        "period": "2026-09",
        "amount_dollars": 205_228,
        "s3_key_template": f"{SEEDED_SOURCE_PREFIX}/{{practiceId}}/{fallback_id}/{fallback_filename}",
        "upload_status": "pending",
    })

    return documents


def _history_months():
    year, month = 2025, 9
    while (year, month) <= (2026, 8):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def generate(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = output_dir / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "orion_invoice_450_2026-09-02.pdf": lambda: make_invoice(
            output_dir / "orion_invoice_450_2026-09-02.pdf",
            filename="orion_invoice_450_2026-09-02.pdf",
            vendor_name="Orion Software LLC",
            amount=450.00,
            invoice_number="INV-OR-2026-0902-001",
            invoice_date="2026-09-02",
            due_date="2026-09-30",
            approval_note="Auto-approved",
            title="Invoice",
        ),
        "orion_invoice_1850_2026-09-12.pdf": lambda: make_invoice(
            output_dir / "orion_invoice_1850_2026-09-12.pdf",
            filename="orion_invoice_1850_2026-09-12.pdf",
            vendor_name="Orion Software LLC",
            amount=1850.00,
            invoice_number="INV-OR-2026-0912-002",
            invoice_date="2026-09-12",
            due_date="2026-10-12",
            approval_note="Pending partner approval",
            title="Invoice",
        ),
        "brightline_invoice_650_2026-09-18.pdf": lambda: make_invoice(
            output_dir / "brightline_invoice_650_2026-09-18.pdf",
            filename="brightline_invoice_650_2026-09-18.pdf",
            vendor_name="Brightline Marketing",
            amount=650.00,
            invoice_number="INV-BRT-2026-0918-003",
            invoice_date="2026-09-18",
            due_date="2026-10-18",
            approval_note="On hold - W-9 + void check required",
            title="Invoice",
        ),
        "brightline_w9.pdf": lambda: make_w9(output_dir / "brightline_w9.pdf", filename="brightline_w9.pdf"),
        "brightline_void_check.pdf": lambda: make_void_check(output_dir / "brightline_void_check.pdf", filename="brightline_void_check.pdf"),
        "receipt_scanned_2026-09-22.pdf": lambda: make_receipt(output_dir / "receipt_scanned_2026-09-22.pdf", filename="receipt_scanned_2026-09-22.pdf"),
        "lpl_payout_statement_sep_2026.pdf": lambda: make_payout_statement(output_dir / "lpl_payout_statement_sep_2026.pdf", filename="lpl_payout_statement_sep_2026.pdf"),
    }

    for _filename, fn in files.items():
        fn()

    make_lease_amendment(source_dir / "lease_amendment_effective_2026-07-01.pdf")
    for month in (7, 8, 9):
        filename = f"compliance_consultant_invoice_2026-{month:02d}.pdf"
        make_compliance_invoice(source_dir / filename, year=2026, month=month)
    for year, month in _history_months():
        filename = f"lpl_payout_statement_{year}-{month:02d}.pdf"
        make_historical_payout_statement(source_dir / filename, year=year, month=month)

    manifest = build_manifest(output_dir)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the Lightroom E8 sample PDF set.")
    ap.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "docs")
    args = ap.parse_args()
    generate(args.output_dir)
    print(f"Generated E8 sample PDFs in {args.output_dir}")


if __name__ == "__main__":
    main()

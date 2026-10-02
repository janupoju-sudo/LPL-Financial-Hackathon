"""Seed Harbor Point Wealth ledger history and demo source-document metadata.

Offline checks never access AWS. A write requires ``--table`` and one of these
September policies:

* default: seed history through August, leaving September untouched;
* ``--live-sept``: add September operating expenses, but no payout or REV# lines;
* ``--include-sept``: add September expenses and the fictional fallback payout.

The fallback refuses to post when September payout data already exists. Existing
journal IDs make repeated runs idempotent. Legacy July/August aggregate expense
journals are detected rather than duplicated; those require an explicit migration.
"""
import argparse
import os
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

MONTHLY_REVENUE = {
    "advisory": 182_400,
    "commission": 14_200,
    "trail": 6_150,
}
VA_TRAIL_QUARTERLY = 2_890
SEPT_VA_ACTUAL = 2_478
QUARTER_MONTHS = (3, 6, 9, 12)

MONTHLY_EXPENSES = {
    "6100": 86_000,
    "6200": 9_800,
    "6300": 7_400,
    "6400": 21_500,
    "6500": 5_200,
    "6600": 3_100,
    "6700": 2_900,
    "6900": 1_800,
}
SEASONAL = {
    "6500": {1: 1.8, 9: 1.8, 12: 0.7},
    "6700": {5: 2.2, 10: 2.2, 1: 0.5, 2: 0.5},
}
DECEMBER_BONUS = 25_000
MONTHLY_DISTRIBUTION = 30_000
OPENING_CASH = 150_000

START = (2025, 9)
END = (2026, 8)
SEPT_DEMO = (2026, 9)
SOURCE_START = (2025, 9)
SEEDED_SOURCE_PREFIX = "seed-sources"
LEASE_DOC_ID = "doc_lease_amendment_2026_07"
SEPT_PAYOUT_DOC_ID = "doc_lpl_payout_statement_sep_2026_fallback"


def months(first, last):
    year, month = first
    while (year, month) <= last:
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def month_end(year, month):
    return date(year + (month == 12), 1 if month == 12 else month + 1, 1).toordinal() - 1


def month_tag(year, month):
    return f"{year}-{month:02d}"


def payout_doc_id(year, month):
    return f"doc_lpl_payout_{year}_{month:02d}"


def compliance_doc_id(year, month):
    return f"doc_compliance_invoice_{year}_{month:02d}"


def expenses_for(year, month):
    """Return monthly expenses in dollars, preserving historic seasonality."""
    out = {
        account: base * SEASONAL.get(account, {}).get(month, 1.0)
        for account, base in MONTHLY_EXPENSES.items()
    }
    if month == 12:
        out["6100"] += DECEMBER_BONUS
    if (year, month) >= (2026, 7):
        out["6200"] = 12_200
        out["6600"] += 2_550
    return {account: round(amount, 2) for account, amount in out.items()}


def payout_revenue_lines(year, month, doc_id, fallback=False):
    """Return normalized payout lines; actual amounts are integer cents."""
    lines = [
        {"id": f"{doc_id}-01", "source": "advisory", "label": "Advisory fees",
         "actual": MONTHLY_REVENUE["advisory"] * 100},
        {"id": f"{doc_id}-02", "source": "commission", "label": "Mutual fund commissions",
         "actual": MONTHLY_REVENUE["commission"] * 100},
        {"id": f"{doc_id}-03", "source": "trail", "ref": "12b1",
         "label": "Monthly 12b-1 trails", "actual": MONTHLY_REVENUE["trail"] * 100},
    ]
    if month in QUARTER_MONTHS:
        va_actual = SEPT_VA_ACTUAL if fallback and (year, month) == SEPT_DEMO else VA_TRAIL_QUARTERLY
        lines.append({
            "id": f"{doc_id}-04",
            "source": "trail",
            "ref": "4471",
            "label": "Variable annuity trail, contract 4471",
            "actual": va_actual * 100,
        })
    return lines


def payout_journal_lines(revenue_lines):
    from shared import ledger

    cents_by_source = {}
    for line in revenue_lines:
        cents_by_source[line["source"]] = cents_by_source.get(line["source"], 0) + line["actual"]
    dollars_by_source = {
        source: Decimal(cents) / Decimal(100)
        for source, cents in cents_by_source.items()
    }
    return ledger.payout_lines(dollars_by_source)


def attributed_expense_journals(tag, entry_date, rent, compliance, compliance_doc):
    """Build balanced rent and base/consultant compliance journals separately."""
    from shared import coa, ledger

    consultant = compliance - MONTHLY_EXPENSES["6600"]
    entries = []
    for label, account, amount, source_doc in (
        ("rent", "6200", rent, LEASE_DOC_ID),
        ("compliance-base", "6600", MONTHLY_EXPENSES["6600"], None),
        ("compliance-consultant", "6600", consultant, compliance_doc),
    ):
        cents = ledger.to_cents(amount)
        entries.append((
            f"j-expense-{label}-{tag}", entry_date,
            [{"account": account, "debit": cents},
             {"account": coa.ACCOUNTS_PAYABLE, "credit": cents}],
            f"{label.replace('-', ' ').title()} expense {tag}", source_doc,
        ))
        entries.append((
            f"j-expense-paid-{label}-{tag}", entry_date,
            [{"account": coa.ACCOUNTS_PAYABLE, "debit": cents},
             {"account": coa.CASH, "credit": cents}],
            f"Paid {label.replace('-', ' ')} expense {tag}", source_doc,
        ))
    return entries


SEED_DOCS_DIR = Path(__file__).resolve().parents[2] / "seed" / "docs"


def _source_document(practice_id, doc_id, filename, doc_type, created_at, **fields):
    # seed-sources/, not uploads/: anything under uploads/ starts B's ingest pipeline,
    # which would read these historical payouts again and double-post the revenue.
    return {
        "documentId": doc_id,
        "filename": filename,
        "contentType": "application/pdf",
        "s3Key": f"seed-sources/{practice_id}/{doc_id}/{filename}",
        "status": "pending_upload",  # seed() marks it processed once the PDF is in S3
        "type": doc_type,
        "uploadedBy": "role-e-seed",
        "createdAt": created_at,
        **fields,
    }


def source_documents(practice_id, include_sept=False):
    """Stable document metadata for the PDFs in seed/docs (uploaded by upload_source_pdfs)."""
    documents = []
    for year, month in months(SOURCE_START, END):
        tag = month_tag(year, month)
        doc_id = payout_doc_id(year, month)
        actual = payout_revenue_lines(year, month, doc_id)
        total_cents = sum(line["actual"] for line in actual)
        documents.append(_source_document(
            practice_id,
            doc_id,
            f"lpl_payout_statement_{tag}.pdf",
            "payout_statement",
            f"{tag}-01T00:00:00+00:00",
            vendorName="LPL Financial",
            period=tag,
            amount=total_cents / 100,
        ))

    documents.append(_source_document(
        practice_id,
        LEASE_DOC_ID,
        "lease_amendment_effective_2026-07-01.pdf",
        "invoice",
        "2026-07-01T00:00:00+00:00",
        vendorName="Harbor Point Properties (FICTIONAL)",
        amount=12_200.00,
    ))
    for month in (7, 8, 9):
        tag = month_tag(2026, month)
        doc_id = compliance_doc_id(2026, month)
        documents.append(_source_document(
            practice_id,
            doc_id,
            f"compliance_consultant_invoice_{tag}.pdf",
            "invoice",
            f"{tag}-05T00:00:00+00:00",
            vendorName="Clearwater Compliance Advisors (FICTIONAL)",
            amount=2_550.00,
        ))

    if include_sept:
        documents.append(_source_document(
            practice_id,
            SEPT_PAYOUT_DOC_ID,
            "lpl_payout_statement_sep_2026.pdf",
            "payout_statement",
            "2026-09-30T00:00:00+00:00",
            vendorName="LPL Financial",
            period="2026-09",
            amount=205_228.00,
        ))
    return documents


def build(include_sept=False, live_sept=False):
    """Build (journal_id, date, lines, memo, source_doc_id) tuples without AWS."""
    from shared import coa, ledger

    if include_sept and live_sept:
        raise ValueError("Choose either --live-sept or --include-sept, not both")

    out = []
    opening = date(START[0], START[1], 1).toordinal() - 1
    out.append((
        "j-opening-balance",
        date.fromordinal(opening).isoformat(),
        [{"account": coa.CASH, "debit": ledger.to_cents(OPENING_CASH)},
         {"account": "3000", "credit": ledger.to_cents(OPENING_CASH)}],
        "Opening balance",
        None,
    ))

    for year, month in months(START, END):
        tag = month_tag(year, month)
        entry_date = date.fromordinal(month_end(year, month)).isoformat()
        doc_id = payout_doc_id(year, month)
        revenue_lines = payout_revenue_lines(year, month, doc_id)
        out.append((
            f"j-payout-{tag}", entry_date, payout_journal_lines(revenue_lines),
            f"LPL payout statement {tag}", doc_id,
        ))

        expenses = expenses_for(year, month)
        split_sources = (year, month) >= (2026, 7)
        if split_sources:
            rent = expenses.pop("6200")
            compliance = expenses.pop("6600")
        total = sum(ledger.to_cents(amount) for amount in expenses.values())
        expense_lines = [
            {"account": account, "debit": ledger.to_cents(amount)}
            for account, amount in sorted(expenses.items())
        ]
        expense_lines.append({"account": coa.ACCOUNTS_PAYABLE, "credit": total})
        out.append((f"j-expenses-{tag}", entry_date, expense_lines,
                    f"Operating expenses {tag}", None))
        out.append((f"j-exp-paid-{tag}", entry_date,
                    [{"account": coa.ACCOUNTS_PAYABLE, "debit": total},
                     {"account": coa.CASH, "credit": total}],
                    f"Paid operating expenses {tag}", None))

        if split_sources:
            out.extend(attributed_expense_journals(
                tag, entry_date, rent, compliance, compliance_doc_id(year, month)
            ))

        out.append((f"j-distribution-{tag}", entry_date,
                    [{"account": "3100", "debit": ledger.to_cents(MONTHLY_DISTRIBUTION)},
                     {"account": coa.CASH, "credit": ledger.to_cents(MONTHLY_DISTRIBUTION)}],
                    f"Owner distribution {tag}", None))

    if include_sept or live_sept:
        year, month = SEPT_DEMO
        tag = month_tag(year, month)
        entry_date = date.fromordinal(month_end(year, month)).isoformat()
        expenses = expenses_for(year, month)
        rent = expenses.pop("6200")
        compliance = expenses.pop("6600")
        total = sum(ledger.to_cents(amount) for amount in expenses.values())
        lines = [{"account": account, "debit": ledger.to_cents(amount)}
                 for account, amount in sorted(expenses.items())]
        lines.append({"account": coa.ACCOUNTS_PAYABLE, "credit": total})
        out.extend([
            (f"j-expenses-{tag}", entry_date, lines, f"Operating expenses {tag}", None),
            (f"j-exp-paid-{tag}", entry_date,
             [{"account": coa.ACCOUNTS_PAYABLE, "debit": total},
              {"account": coa.CASH, "credit": total}],
             f"Paid operating expenses {tag}", None),
        ])
        out.extend(attributed_expense_journals(
            tag, entry_date, rent, compliance, compliance_doc_id(year, month)
        ))
        out.append((f"j-distribution-{tag}", entry_date,
                    [{"account": "3100", "debit": ledger.to_cents(MONTHLY_DISTRIBUTION)},
                     {"account": coa.CASH, "credit": ledger.to_cents(MONTHLY_DISTRIBUTION)}],
                    f"Owner distribution {tag}", None))

        if include_sept:
            lines = payout_revenue_lines(year, month, SEPT_PAYOUT_DOC_ID, fallback=True)
            out.append((f"j-payout-{tag}", entry_date, payout_journal_lines(lines),
                        f"LPL payout statement {tag} (fallback)", SEPT_PAYOUT_DOC_ID))
    return out


def revenue_records(include_sept=False):
    records = []
    for year, month in months(START, END):
        doc_id = payout_doc_id(year, month)
        records.append((month_tag(year, month), doc_id,
                        payout_revenue_lines(year, month, doc_id)))
    if include_sept:
        records.append(("2026-09", SEPT_PAYOUT_DOC_ID,
                        payout_revenue_lines(2026, 9, SEPT_PAYOUT_DOC_ID, fallback=True)))
    return records


def has_september_payout(practice_id):
    """Detect either normalized payout lines or a posted live payout journal."""
    from shared import ddb

    if ddb.get_revenue_lines(practice_id, "2026-09"):
        return True
    return any(
        line.get("sourceType") == "payout" or str(line.get("journalId", "")).startswith("j-payout-")
        for line in ddb.query_prefix(practice_id, "LEDGER#2026-09#")
    )


def _reject_legacy_split_expenses(practice_id):
    from shared import ddb

    for month in (7, 8, 9):
        tag = month_tag(2026, month)
        old_lines = ddb.query_prefix(practice_id, f"LEDGER#2026-{month:02d}#j-expenses-{tag}#")
        if any(line.get("account") in {"6200", "6600"} for line in old_lines):
            raise RuntimeError(
                f"Legacy {tag} aggregate expense journal already includes rent/compliance; "
                "refusing to add split journals and double-count. Migrate that month first."
            )
        combined_compliance = ddb.query_prefix(
            practice_id, f"LEDGER#2026-{month:02d}#j-expense-compliance-{tag}#"
        )
        combined_payment = ddb.query_prefix(
            practice_id, f"LEDGER#2026-{month:02d}#j-expense-paid-compliance-{tag}#"
        )
        if combined_compliance or combined_payment:
            raise RuntimeError(
                f"Legacy {tag} combined compliance journals exist; refusing to duplicate "
                "the $3,100 base and $2,550 consultant expense. Migrate that month first."
            )


def local_pdf(filename):
    """Seed PDFs live in seed/docs/sources, except the Sept payout in seed/docs."""
    for folder in (SEED_DOCS_DIR / "sources", SEED_DOCS_DIR):
        path = folder / filename
        if path.exists():
            return path
    raise FileNotFoundError(f"{filename} not found under {SEED_DOCS_DIR}; run seed/generate_docs.py")


def upload_source_pdfs(documents, bucket):
    """Put each seed PDF at its s3Key unless it is already there (the bucket uses
    Object Lock, so re-uploads would only stack versions)."""
    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3")
    uploaded = 0
    for document in documents:
        try:
            s3.head_object(Bucket=bucket, Key=document["s3Key"])
            continue
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                raise
        s3.put_object(Bucket=bucket, Key=document["s3Key"], ContentType="application/pdf",
                      Body=local_pdf(document["filename"]).read_bytes(), ChecksumAlgorithm="SHA256")
        uploaded += 1
    return uploaded


def seed(practice_id, include_sept=False, live_sept=False, docs_bucket=None):
    """Write seed rows. This is only called by the --table path, never --check."""
    from shared import ddb, ledger, repo

    if include_sept and live_sept:
        raise ValueError("Choose either --live-sept or --include-sept, not both")
    _reject_legacy_split_expenses(practice_id)

    fallback_active = include_sept
    if fallback_active and has_september_payout(practice_id):
        print("September payout data already exists; skipping fallback payout and REV# records.")
        fallback_active = False

    sept_mode = include_sept or live_sept
    documents = source_documents(practice_id, include_sept=fallback_active)
    if docs_bucket:
        uploaded = upload_source_pdfs(documents, docs_bucket)
        print(f"Uploaded {uploaded} source PDFs to s3://{docs_bucket}/seed-sources/ "
              f"({len(documents) - uploaded} already there).")
        for document in documents:
            document["status"] = "processed"
    for document in documents:
        existing = ddb.get_item(practice_id, f"DOC#{document['documentId']}")
        # Seed-owned rows: write them, repoint rows from the old uploads/ layout, and
        # mark them processed once their PDFs are uploaded.
        if not existing or any(existing.get(k) != document[k] for k in ("s3Key", "status")):
            ddb.put_item(practice_id, f"DOC#{document['documentId']}", document)

    for journal_id, entry_date, lines, memo, source_doc_id in build(
        include_sept=fallback_active, live_sept=sept_mode and not fallback_active
    ):
        ledger.post_journal(
            practice_id, journal_id, entry_date, lines, memo,
            source_doc_id=source_doc_id,
            source_type="seed",
            source_id=source_doc_id,
        )

    for period, doc_id, lines in revenue_records(include_sept=fallback_active):
        repo.put_revenue_lines(practice_id, period, doc_id, lines)

    print(f"Posted history and {('fallback' if fallback_active else 'live' if live_sept else 'no')} September mode.")
    if not docs_bucket:
        print("No --docs-bucket given: DOC# rows written, but the PDFs were not uploaded, "
              "so Ask citations and exports can't open them.")


def _entries(include_sept=False, live_sept=False):
    from shared import ledger

    entries = []
    journals = build(include_sept=include_sept, live_sept=live_sept)
    for journal_id, entry_date, lines, memo, source_doc_id in journals:
        entries.extend(ledger.build_journal(
            journal_id, entry_date, lines, memo, source_doc_id,
            source_type="seed", source_id=source_doc_id,
        ))
    return entries, len(journals)


def _margin(entries, period):
    from financials import kpis, statements

    pnl = statements.profit_and_loss(entries, period)
    return pnl, kpis.compute(pnl, 180)


def _fallback_reconciliation():
    from financials.reconciliation import compute

    schedule = [
        {"id": "adv", "label": "Advisory fees", "source": "advisory",
         "basis": "fixed", "amount": 18_240_000, "frequency": "monthly"},
        {"id": "mf-comm", "label": "Mutual fund commissions", "source": "commission",
         "basis": "fixed", "amount": 1_420_000, "frequency": "monthly"},
        {"id": "12b1", "label": "12b-1 trails", "source": "trail", "ref": "12b1",
         "basis": "fixed", "amount": 615_000, "frequency": "monthly"},
        {"id": "va-4471", "label": "Variable annuity trail, contract 4471",
         "source": "trail", "ref": "4471", "basis": "aum", "aum": 115_600_000,
         "annualRate": 0.01, "frequency": "quarterly", "billingMonths": [3, 6, 9, 12]},
    ]
    lines = payout_revenue_lines(2026, 9, SEPT_PAYOUT_DOC_ID, fallback=True)
    return compute(schedule, lines, "2026-09")


def check(include_sept=False, live_sept=False):
    """Print local financial checks only. This function makes no AWS calls."""
    if include_sept and live_sept:
        raise ValueError("Choose either --live-sept or --include-sept, not both")
    os.environ.setdefault("TABLE_NAME", "unused-for-check")
    from financials import statements, valuation

    entries, journal_count = _entries(include_sept, live_sept)
    print(f"{len(entries)} ledger lines across {journal_count} journals, all balanced.\n")

    q2_pnl, q2 = _margin(entries, "2026-Q2")
    live_entries, _ = _entries(live_sept=True)
    q3_partial_pnl, q3_partial = _margin(live_entries, "2026-Q3")
    fallback_entries, _ = _entries(include_sept=True)
    q3_complete_pnl, q3_complete = _margin(fallback_entries, "2026-Q3")

    def show_margin(label, pnl, kpis):
        print(f"  {label:43} revenue ${pnl['totalRevenue']/100:>11,.0f}   "
              f"expenses ${pnl['totalExpenses']/100:>10,.0f}   margin {kpis['margin']:.1%}")

    show_margin("2026-Q2 complete", q2_pnl, q2)
    show_margin("2026-Q3 partial (live seed; payout pending)", q3_partial_pnl, q3_partial)
    show_margin("2026-Q3 complete (fallback payout included)", q3_complete_pnl, q3_complete)

    reconciliation = _fallback_reconciliation()
    va_line = next(line for line in reconciliation["lines"] if line.get("ref") == "4471")
    print("\n  2026-09 contract 4471 fallback: "
          f"expected {va_line['expected']} cents, actual {va_line['actual']} cents, "
          f"variance {va_line['variance']} cents")

    selected_entries = live_entries if live_sept else fallback_entries if include_sept else entries
    selected_as_of = date(2026, 9, 30) if include_sept or live_sept else date(2026, 8, 31)
    selected_pnl, selected_kpis = _margin(selected_entries, "2026-08")
    value = valuation.estimate(
        selected_entries, selected_as_of, selected_kpis["recurringPct"], selected_kpis["margin"], 0.22
    )
    print(f"\n  Estimated practice value  ${value['low']/100:,.0f} - ${value['high']/100:,.0f}"
          f"   (mid ${value['mid']/100:,.0f})")

    balance = statements.balance_sheet(selected_entries, selected_as_of)
    difference = balance["totalAssets"] - (balance["totalLiabilities"] + balance["totalEquity"])
    print(f"  Balance sheet: assets ${balance['totalAssets']/100:,.0f} = "
          f"liabilities ${balance['totalLiabilities']/100:,.0f} + equity ${balance['totalEquity']/100:,.0f}"
          f"   {'BALANCED' if difference == 0 else f'OFF BY {difference}'}")

    complete_q3_is_lower = q3_complete["margin"] < q2["margin"]
    fallback_is_correct = (
        va_line["expected"] == 289_000
        and va_line["actual"] == 247_800
        and va_line["variance"] == -41_200
    )
    print(f"  Complete Q3 margin below Q2: {'YES' if complete_q3_is_lower else 'NO'}")
    print("\nPass --table <name> to write; --check never contacts AWS.")
    return difference == 0 and complete_q3_is_lower and fallback_is_correct


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table")
    parser.add_argument("--practice", default="p1")
    parser.add_argument("--docs-bucket", default=os.environ.get("DOCS_BUCKET"),
                        help="documents bucket (DocsBucketName output) to upload the source PDFs to")
    parser.add_argument("--check", action="store_true", help="show the numbers, write nothing")
    september = parser.add_mutually_exclusive_group()
    september.add_argument(
        "--live-sept", action="store_true",
        help="seed September operating expenses only; leave payout ingestion empty",
    )
    september.add_argument(
        "--include-sept", action="store_true",
        help="seed September expenses and fallback payout if live payout data is absent",
    )
    args = parser.parse_args()

    if args.check or not args.table:
        ok = check(args.include_sept, args.live_sept)
        if not args.table:
            print("\nPass --table <name> to write.")
        sys.exit(0 if ok else 1)

    os.environ["TABLE_NAME"] = args.table
    try:
        seed(args.practice, include_sept=args.include_sept, live_sept=args.live_sept,
             docs_bucket=args.docs_bucket)
    except RuntimeError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

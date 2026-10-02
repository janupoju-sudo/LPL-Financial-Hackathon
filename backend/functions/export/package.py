"""Builds the "Export package" ZIP for a period (task D6):
documents/<type>/<filename>, ledger.csv, financials.json and a README.

fetch(s3_key) -> bytes is passed in, so this runs in tests without S3.
"""

import csv
import io
import json
import zipfile
from datetime import date

from shared import coa
from functions.financials import periods

LEDGER_COLUMNS = ["date", "journalId", "account", "accountName", "debit", "credit", "sourceDocId", "memo"]


def ledger_csv(entries) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(LEDGER_COLUMNS)
    for e in sorted(entries, key=lambda e: (e["date"], e["journalId"])):
        w.writerow([e["date"], e["journalId"], e["account"], coa.get(e["account"]).name,
                    f"{int(e.get('debit', 0)) / 100:.2f}", f"{int(e.get('credit', 0)) / 100:.2f}",
                    e.get("sourceDocId") or "", e.get("memo") or ""])
    return buf.getvalue()


def period_documents(documents, entries, period: str) -> list[dict]:
    """Documents uploaded in the period, plus any the period's ledger entries point to."""
    start, end = periods.parse(period)
    referenced = {e.get("sourceDocId") for e in entries}
    out = []
    for d in documents:
        created = d.get("createdAt")
        in_period = created and start <= date.fromisoformat(str(created)[:10]) <= end
        if in_period or d["id"] in referenced:
            out.append(d)
    return out


def build_zip(period: str, practice_name: str, documents, entries, financials: dict, fetch) -> tuple[bytes, dict]:
    start, end = periods.parse(period)
    in_period = [e for e in entries if start <= date.fromisoformat(e["date"]) <= end]
    docs = period_documents(documents, in_period, period)

    buf = io.BytesIO()
    names, missing = set(), []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in docs:
            folder, filename = f"documents/{d.get('type', 'other')}", d.get("filename") or d["id"]
            name = f"{folder}/{filename}"
            if name in names:  # two files with the same name
                name = f"{folder}/{d['id']}-{filename}"
            try:
                z.writestr(name, fetch(d["s3Key"]))
                names.add(name)
            except Exception:  # keep exporting; list it in the README
                missing.append(d.get("filename") or d["id"])
        z.writestr("ledger.csv", ledger_csv(in_period))
        z.writestr("financials.json", json.dumps(financials, indent=2))
        readme = [
            f"{practice_name}: export package for {period} ({start} to {end})",
            "",
            f"documents/      {len(names)} source documents, by type",
            f"ledger.csv      {len(in_period)} ledger lines (double-entry, dollars)",
            "financials.json P&L, balance sheet, cash flow, KPIs and valuation estimate",
        ]
        if missing:
            readme += ["", "Could not include: " + ", ".join(missing)]
        z.writestr("README.txt", "\n".join(readme) + "\n")

    summary = {"documents": len(names), "ledgerLines": len(in_period), "missing": missing}
    return buf.getvalue(), summary

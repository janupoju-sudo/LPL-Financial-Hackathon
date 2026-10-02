"""Entity repository: documents, vendors, bills, rules.

Key layout (PK = PRACTICE#<practiceId>):
  DOC#<documentId>     Document
  VENDOR#<vendorId>    Vendor
  BILL#<billId>        Bill
  RULE#<ruleId>        Approval rule
  LEDGER#...           Journal entries (see ledger.py)
"""
import re

from . import coa, events
from .ddb import (from_ddb, get_item, new_id, now_iso, pk, put_item, query_prefix,
                  table, to_ddb, update_item)
from .rules_engine import DEFAULT_RULES

# ---------- audit ----------

def audit_event(actor: str, action: str, detail: str = "") -> dict:
    return {"at": now_iso(), "actor": actor, "action": action, "detail": detail}


# ---------- documents ----------

DOC_TYPES = ("invoice", "receipt", "void_check", "w9", "payout_statement", "unknown")


def create_document(practice_id, filename, content_type, s3_key, uploaded_by, document_id=None):
    doc_id = document_id or new_id("doc")
    item = {
        "documentId": doc_id, "filename": filename, "contentType": content_type,
        "s3Key": s3_key, "status": "uploaded", "type": "unknown",
        "uploadedBy": uploaded_by, "createdAt": now_iso(),
    }
    put_item(practice_id, f"DOC#{doc_id}", item)
    return item


def get_document(practice_id, doc_id):
    return get_item(practice_id, f"DOC#{doc_id}")


def update_document(practice_id, doc_id, **fields):
    return update_item(practice_id, f"DOC#{doc_id}", set_fields={**fields, "updatedAt": now_iso()})


def list_documents(practice_id, doc_type=None, q=None):
    docs = query_prefix(practice_id, "DOC#")
    if doc_type:
        docs = [d for d in docs if d.get("type") == doc_type]
    if q:
        needle = q.lower()
        docs = [d for d in docs if needle in (d.get("filename", "") + " " + d.get("vendorName", "")).lower()]
    return sorted(docs, key=lambda d: d.get("createdAt", ""), reverse=True)


# ---------- vendors ----------

def normalize_name(name: str) -> str:
    """'ACME Software, Inc.' -> 'acme software'"""
    text = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    text = re.sub(r"\b(inc|llc|ltd|co|corp|corporation|company|the)\b", " ", text)
    return " ".join(text.split())


def get_vendor(practice_id, vendor_id):
    return get_item(practice_id, f"VENDOR#{vendor_id}") if vendor_id else None


def list_vendors(practice_id):
    return sorted(query_prefix(practice_id, "VENDOR#"), key=lambda v: v.get("name", ""))


def find_vendor_by_name(practice_id, name):
    """Exact match on normalized name or alias. Fuzzy matching lives in the ingest pipeline."""
    target = normalize_name(name)
    if not target:
        return None
    for v in list_vendors(practice_id):
        if target == v.get("normalizedName") or target in (v.get("aliases") or []):
            return v
    return None


def create_vendor(practice_id, name, default_gl_account=coa.DEFAULT_EXPENSE, **attrs):
    vendor_id = attrs.pop("vendorId", None) or new_id("ven")
    item = {
        "vendorId": vendor_id, "name": name, "normalizedName": normalize_name(name),
        "aliases": [], "defaultGlAccount": default_gl_account,
        "hasW9": False, "hasVoidCheck": False, "billCount": 0,
        "createdAt": now_iso(), **attrs,
    }
    put_item(practice_id, f"VENDOR#{vendor_id}", item)
    return item


def find_or_create_vendor(practice_id, name, **attrs):
    return find_vendor_by_name(practice_id, name) or create_vendor(practice_id, name, **attrs)


def update_vendor(practice_id, vendor_id, **fields):
    return update_item(practice_id, f"VENDOR#{vendor_id}", set_fields={**fields, "updatedAt": now_iso()})


def add_vendor_alias(practice_id, vendor_id, alias):
    vendor = get_vendor(practice_id, vendor_id)
    alias = normalize_name(alias)
    if vendor and alias and alias not in (vendor.get("aliases") or []) and alias != vendor.get("normalizedName"):
        update_item(practice_id, f"VENDOR#{vendor_id}", append={"aliases": [alias]})


def increment_vendor_bill_count(practice_id, vendor_id):
    table().update_item(
        Key={"PK": pk(practice_id), "SK": f"VENDOR#{vendor_id}"},
        UpdateExpression="SET billCount = if_not_exists(billCount, :zero) + :one, lastSeen = :now",
        ExpressionAttributeValues={":zero": 0, ":one": 1, ":now": now_iso()},
    )


def record_vendor_docs(practice_id, vendor_id, has_w9=None, has_void_check=None, bank_last4=None,
                       document_id=None, source="ledgerline.backend"):
    """Call after a W-9 or void check is extracted. Emits VendorUpdated, which resumes held bills."""
    fields = {}
    if has_w9 is not None:
        fields["hasW9"] = bool(has_w9)
    if has_void_check is not None:
        fields["hasVoidCheck"] = bool(has_void_check)
    if bank_last4:
        fields["bankLast4"] = str(bank_last4)[-4:]
    if not fields:
        return get_vendor(practice_id, vendor_id)
    vendor = update_vendor(practice_id, vendor_id, **fields)
    events.put_event("VendorUpdated", {
        "practiceId": practice_id, "vendorId": vendor_id, "documentId": document_id, **fields,
    }, source=source)
    return vendor


# ---------- bills ----------

BILL_STATUSES = (
    "pending_review",    # low-confidence extraction; a human must confirm fields
    "processing",        # workflow running
    "pending_docs",      # on hold (missing vendor docs / not yet received)
    "pending_approval",  # waiting for an approver
    "approved",          # posted to ledger (accrual)
    "scheduled",         # mock payment scheduled + posted
    "rejected",
)


def put_bill(practice_id, bill: dict):
    put_item(practice_id, f"BILL#{bill['billId']}", bill)
    return bill


def get_bill(practice_id, bill_id):
    return get_item(practice_id, f"BILL#{bill_id}")


def update_bill(practice_id, bill_id, set_fields=None, remove=None, audit=None, condition=None, extra_values=None):
    set_fields = {**(set_fields or {}), "updatedAt": now_iso()}
    return update_item(
        practice_id, f"BILL#{bill_id}", set_fields=set_fields, remove=remove,
        append={"audit": [audit]} if audit else None, condition=condition, extra_values=extra_values,
    )


def list_bills(practice_id, statuses=None):
    bills = query_prefix(practice_id, "BILL#")
    if statuses:
        bills = [b for b in bills if b.get("status") in statuses]
    return sorted(bills, key=lambda b: b.get("createdAt", ""), reverse=True)


def list_bills_for_vendor(practice_id, vendor_id, statuses=None):
    return [b for b in list_bills(practice_id, statuses) if b.get("vendorId") == vendor_id]


def is_duplicate_invoice(practice_id, vendor_id, invoice_number, exclude_bill_id=None) -> bool:
    if not vendor_id or not invoice_number:
        return False
    for b in list_bills_for_vendor(practice_id, vendor_id):
        if b["billId"] != exclude_bill_id and b.get("invoiceNumber") == invoice_number and b.get("status") != "rejected":
            return True
    return False


def bill_summary(bill: dict) -> dict:
    keys = ("billId", "documentId", "vendorId", "vendorName", "invoiceNumber", "invoiceDate", "dueDate",
            "amount", "currency", "glAccount", "glAccountName", "status", "ruleHits", "requiredApprovers",
            "confidence", "createdAt", "updatedAt")
    return from_ddb({k: bill.get(k) for k in keys if k in bill})


# ---------- revenue lines (payout statements) ----------

REVENUE_SOURCES = ("advisory", "commission", "trail", "other")


def put_revenue_lines(practice_id, period: str, doc_id: str, lines: list) -> list:
    """Store payout statement lines for reconciliation (Financials / D4). Written by ingest (B).

    period: 'YYYY-MM' the statement covers.
    lines:  [{"source": "trail", "ref": "4471", "label": "VA trail 4471", "actual": 247800}, ...]
            actual is INTEGER CENTS. Ids are derived from doc_id, so re-running ingest overwrites
            instead of duplicating.
    """
    if len(period) != 7 or period[4] != "-":
        raise ValueError("period must be YYYY-MM")
    stored = []
    for n, line in enumerate(lines, start=1):
        if line.get("source") not in REVENUE_SOURCES:
            raise ValueError(f"source must be one of {', '.join(REVENUE_SOURCES)}")
        actual = line.get("actual")
        if not isinstance(actual, int) or isinstance(actual, bool):
            raise ValueError("actual must be integer cents")
        item = {
            "id": line.get("id") or f"{doc_id}-{n:02d}", "period": period, "source": line["source"],
            "ref": line.get("ref"), "label": line.get("label") or line["source"].title(),
            "actual": actual, "docId": doc_id, "createdAt": now_iso(),
        }
        put_item(practice_id, f"REV#{period}#{item['id']}", item)
        stored.append(item)
    return stored


# ---------- rules ----------

def list_rules(practice_id, seed_defaults=True):
    rules = query_prefix(practice_id, "RULE#")
    if not rules and seed_defaults:
        for rule in DEFAULT_RULES:
            put_rule(practice_id, rule)
        rules = query_prefix(practice_id, "RULE#")
    # Deleted rules stay stored for the audit trail but are hidden and never evaluated.
    # Checking the raw list above means deleting every rule doesn't re-seed the defaults.
    return sorted((r for r in rules if not r.get("deleted")), key=lambda r: r.get("priority", 100))


def put_rule(practice_id, rule: dict):
    rule = {**rule, "updatedAt": now_iso()}
    rule.setdefault("ruleId", new_id("rule"))
    rule.setdefault("enabled", True)
    rule.setdefault("priority", 100)
    put_item(practice_id, f"RULE#{rule['ruleId']}", rule)
    return to_ddb(rule)


def get_rule(practice_id, rule_id):
    return get_item(practice_id, f"RULE#{rule_id}")

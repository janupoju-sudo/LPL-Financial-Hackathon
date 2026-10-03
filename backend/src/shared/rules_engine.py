"""No-code approval rules, evaluated against a bill + vendor context.

A rule:
{
  "ruleId": "rule_large_bill", "name": "...", "enabled": true, "priority": 30,
  "condition": {"field": "bill.amount", "op": "gt", "value": 1000}
               | {"all": [cond, ...]} | {"any": [cond, ...]} | {"not": cond},
  "action": "require_approval" | "hold" | "block",
  "approverRole": "partner",          # only for require_approval
  "reason": "Amount is over $1,000"   # shown in the UI
}

Decision precedence: block > hold > require_approval > auto_approve.
"""
from decimal import Decimal

ACTIONS = ("require_approval", "hold", "block")
ROLES = ("owner", "partner", "ops", "lpl_bookkeeper")


def _num(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    return v


def _cmp(fn):
    def op(a, b):
        a, b = _num(a), _num(b)
        try:
            return a is not None and fn(a, b)
        except TypeError:
            return False
    return op


OPS = {
    "gt": _cmp(lambda a, b: a > b),
    "gte": _cmp(lambda a, b: a >= b),
    "lt": _cmp(lambda a, b: a < b),
    "lte": _cmp(lambda a, b: a <= b),
    "eq": lambda a, b: _num(a) == _num(b),
    "neq": lambda a, b: _num(a) != _num(b),
    "in": lambda a, b: a in (b or []),
    "not_in": lambda a, b: a not in (b or []),
    "exists": lambda a, b: (a is not None) == bool(b),
    "contains": lambda a, b: a is not None and str(b).lower() in str(a).lower(),
}


def resolve(ctx: dict, path: str):
    cur = ctx
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def matches(cond: dict, ctx: dict) -> bool:
    if "all" in cond:
        return all(matches(c, ctx) for c in cond["all"])
    if "any" in cond:
        return any(matches(c, ctx) for c in cond["any"])
    if "not" in cond:
        return not matches(cond["not"], ctx)
    return OPS[cond["op"]](resolve(ctx, cond["field"]), cond.get("value"))


def validate_condition(cond):
    if not isinstance(cond, dict):
        raise ValueError("condition must be an object")
    for key in ("all", "any"):
        if key in cond:
            if not isinstance(cond[key], list) or not cond[key]:
                raise ValueError(f"'{key}' must be a non-empty list")
            for c in cond[key]:
                validate_condition(c)
            return
    if "not" in cond:
        validate_condition(cond["not"])
        return
    if not isinstance(cond.get("field"), str) or "." not in cond["field"]:
        raise ValueError("leaf condition needs field like 'bill.amount' or 'vendor.hasW9'")
    if cond.get("op") not in OPS:
        raise ValueError(f"op must be one of {', '.join(OPS)}")


def validate_rule(rule: dict):
    if not rule.get("name"):
        raise ValueError("rule needs a name")
    if rule.get("action") not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    if rule["action"] == "require_approval" and rule.get("approverRole", "owner") not in ROLES:
        raise ValueError(f"approverRole must be one of {', '.join(ROLES)}")
    validate_condition(rule.get("condition"))


def evaluate(rules, ctx: dict) -> dict:
    hits = []
    for rule in sorted(rules, key=lambda r: _num(r.get("priority", 100))):
        if not rule.get("enabled", True):
            continue
        try:
            hit = matches(rule["condition"], ctx)
        except (KeyError, TypeError) as exc:
            print(f"[rules] skipping malformed rule {rule.get('ruleId')}: {exc}")
            continue
        if hit:
            hits.append({
                "ruleId": rule.get("ruleId"),
                "name": rule.get("name"),
                "action": rule["action"],
                "approverRole": rule.get("approverRole") if rule["action"] == "require_approval" else None,
                "reason": rule.get("reason") or rule.get("name"),
            })
    actions = {h["action"] for h in hits}
    if "block" in actions:
        decision = "blocked"
    elif "hold" in actions:
        decision = "on_hold"
    elif "require_approval" in actions:
        decision = "needs_approval"
    else:
        decision = "auto_approve"
    approvers = sorted({h["approverRole"] or "owner" for h in hits if h["action"] == "require_approval"})
    return {"decision": decision, "hits": hits, "requiredApprovers": approvers}


DEFAULT_RULES = [
    {
        "ruleId": "rule_duplicate", "name": "Block duplicate invoices", "enabled": True, "priority": 10,
        "condition": {"field": "bill.isDuplicate", "op": "eq", "value": True},
        "action": "block", "reason": "Same vendor and invoice number was already submitted",
    },
    {
        "ruleId": "rule_vendor_docs", "name": "Vendor must have W-9 and void check on file",
        "enabled": True, "priority": 20,
        # Receipts are already paid (card/cash): vendor onboarding docs only apply to bills we pay.
        "condition": {"all": [
            {"field": "bill.documentType", "op": "neq", "value": "receipt"},
            {"any": [
                {"field": "vendor.hasW9", "op": "neq", "value": True},
                {"field": "vendor.hasVoidCheck", "op": "neq", "value": True},
            ]},
        ]},
        "action": "hold", "reason": "Vendor is missing a W-9 or void check",
    },
    {
        "ruleId": "rule_large_bill", "name": "Bills over $1,000 need partner approval",
        "enabled": True, "priority": 30,
        "condition": {"field": "bill.amount", "op": "gt", "value": 1000},
        "action": "require_approval", "approverRole": "partner", "reason": "Amount is over $1,000",
    },
    {
        "ruleId": "rule_receipt", "name": "Pay only after goods/services are received",
        "enabled": True, "priority": 40,
        "condition": {"all": [
            {"field": "bill.requiresReceipt", "op": "eq", "value": True},
            {"field": "bill.received", "op": "neq", "value": True},
        ]},
        "action": "hold", "reason": "Waiting for confirmation that it was received",
    },
]

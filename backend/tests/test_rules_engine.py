import pytest

from shared.rules_engine import DEFAULT_RULES, evaluate, validate_rule


def ctx(amount=500, w9=True, void=True, dup=False, requires_receipt=False, received=False):
    return {"bill": {"amount": amount, "isDuplicate": dup, "requiresReceipt": requires_receipt, "received": received},
            "vendor": {"hasW9": w9, "hasVoidCheck": void}}


def test_small_bill_known_vendor_auto_approves():
    assert evaluate(DEFAULT_RULES, ctx())["decision"] == "auto_approve"


def test_large_bill_needs_partner():
    r = evaluate(DEFAULT_RULES, ctx(amount=1850))
    assert r["decision"] == "needs_approval"
    assert r["requiredApprovers"] == ["partner"]


def test_missing_vendor_docs_holds_even_if_large():
    r = evaluate(DEFAULT_RULES, ctx(amount=5000, w9=False))
    assert r["decision"] == "on_hold"
    assert {h["ruleId"] for h in r["hits"]} == {"rule_vendor_docs", "rule_large_bill"}


def test_duplicate_blocks():
    assert evaluate(DEFAULT_RULES, ctx(dup=True))["decision"] == "blocked"


def test_receipt_hold():
    assert evaluate(DEFAULT_RULES, ctx(requires_receipt=True))["decision"] == "on_hold"
    assert evaluate(DEFAULT_RULES, ctx(requires_receipt=True, received=True))["decision"] == "auto_approve"


def test_disabled_rule_is_ignored():
    rules = [dict(r, enabled=(r["ruleId"] != "rule_large_bill")) for r in DEFAULT_RULES]
    assert evaluate(rules, ctx(amount=9999))["decision"] == "auto_approve"


def test_validate_rule_rejects_bad_op():
    with pytest.raises(ValueError):
        validate_rule({"name": "x", "action": "hold", "condition": {"field": "bill.amount", "op": "bigger", "value": 1}})

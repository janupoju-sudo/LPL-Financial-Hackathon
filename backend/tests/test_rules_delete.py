"""DELETE /rules/{id}: owner-only soft delete."""
from conftest import api_event, body_of
from handlers import rules as rules_api
from shared import repo
from shared.rules_engine import evaluate


def _list():
    return body_of(rules_api.handler(api_event("GET /rules")))


def test_owner_deletes_a_rule_and_it_stops_applying(aws):
    rules = _list()
    large = next(r for r in rules if r["ruleId"] == "rule_large_bill")
    resp = rules_api.handler(api_event("DELETE /rules/{id}", path={"id": "rule_large_bill"}))
    assert resp["statusCode"] == 200

    assert "rule_large_bill" not in [r["ruleId"] for r in _list()]
    stored = repo.get_rule("p1", "rule_large_bill")  # kept for the audit trail
    assert stored["deleted"] is True and stored["enabled"] is False and stored["deletedBy"]

    ctx = {"bill": {"amount": 5000, "isDuplicate": False, "requiresReceipt": False, "received": True},
           "vendor": {"hasW9": True, "hasVoidCheck": True}}
    assert evaluate(repo.list_rules("p1"), ctx)["decision"] == "auto_approve"
    assert large["name"] == "Bills over $1,000 need partner approval"


def test_only_the_owner_can_delete(aws):
    _list()
    resp = rules_api.handler(api_event("DELETE /rules/{id}", path={"id": "rule_large_bill"}, groups=("partner",)))
    assert resp["statusCode"] == 403
    assert "rule_large_bill" in [r["ruleId"] for r in _list()]


def test_deleting_twice_or_unknown_is_404_and_defaults_do_not_come_back(aws):
    for rule in _list():
        assert rules_api.handler(api_event("DELETE /rules/{id}", path={"id": rule["ruleId"]}))["statusCode"] == 200
    assert _list() == []  # deleting every rule doesn't re-seed the defaults
    assert rules_api.handler(api_event("DELETE /rules/{id}", path={"id": "rule_large_bill"}))["statusCode"] == 404
    assert rules_api.handler(api_event("DELETE /rules/{id}", path={"id": "nope"}))["statusCode"] == 404

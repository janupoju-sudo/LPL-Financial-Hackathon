"""Approval rules API.

GET   /rules          list (seeds defaults on first call)
POST  /rules          create {name, condition, action, approverRole?, priority?, reason?}   (owner only)
PATCH /rules/{id}     partial update, e.g. {"enabled": false}                                (owner only)
DELETE /rules/{id}    remove a rule (soft delete: kept with deletedBy/deletedAt, never evaluated) (owner only)
"""
from shared import repo
from shared.auth import get_caller, require_role
from shared.ddb import now_iso, public
from shared.http import HttpError, parse_body, path_param, router
from shared.rules_engine import validate_rule

EDITABLE = ("name", "condition", "action", "approverRole", "priority", "reason", "enabled")


def list_rules(event):
    caller = get_caller(event)
    return 200, [public(r) for r in repo.list_rules(caller.practice_id)]


def create_rule(event):
    caller = get_caller(event)
    require_role(caller, "owner")
    body = parse_body(event)
    rule = {k: body[k] for k in EDITABLE if k in body}
    try:
        validate_rule(rule)
    except ValueError as err:
        raise HttpError(400, str(err))
    repo.list_rules(caller.practice_id)  # make sure defaults exist before adding custom rules
    return 201, public(repo.put_rule(caller.practice_id, {**rule, "createdBy": caller.label}))


def update_rule(event):
    caller = get_caller(event)
    require_role(caller, "owner")
    existing = repo.get_rule(caller.practice_id, path_param(event, "id"))
    if not existing:
        raise HttpError(404, "Rule not found")
    body = parse_body(event)
    merged = {**public(existing), **{k: body[k] for k in EDITABLE if k in body}}
    try:
        validate_rule(merged)
    except ValueError as err:
        raise HttpError(400, str(err))
    return 200, public(repo.put_rule(caller.practice_id, merged))


def delete_rule(event):
    caller = get_caller(event)
    require_role(caller, "owner")
    existing = repo.get_rule(caller.practice_id, path_param(event, "id"))
    if not existing or existing.get("deleted"):
        raise HttpError(404, "Rule not found")
    repo.put_rule(caller.practice_id, {**public(existing), "enabled": False, "deleted": True,
                                       "deletedBy": caller.label, "deletedAt": now_iso()})
    return 200, {"ruleId": existing["ruleId"], "deleted": True}


handler = router({
    "GET /rules": list_rules,
    "POST /rules": create_rule,
    "PATCH /rules/{id}": update_rule,
    "DELETE /rules/{id}": delete_rule,
})

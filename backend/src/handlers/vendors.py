"""GET /vendors"""
from shared import repo
from shared.auth import get_caller
from shared.ddb import public
from shared.http import router


def list_vendors(event):
    caller = get_caller(event)
    keys = ("vendorId", "name", "defaultGlAccount", "hasW9", "hasVoidCheck", "bankLast4",
            "billCount", "lastSeen", "aliases")
    return 200, [{k: v.get(k) for k in keys if k in v} for v in map(public, repo.list_vendors(caller.practice_id))]


handler = router({"GET /vendors": list_vendors})

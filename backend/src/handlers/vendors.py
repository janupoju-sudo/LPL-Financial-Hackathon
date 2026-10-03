"""GET /vendors"""
from shared import repo
from shared.auth import get_caller
from shared.ddb import public
from shared.http import router


def list_vendors(event):
    caller = get_caller(event)
    vendors = repo.list_vendors(caller.practice_id)
    vendors_by_last4 = {}
    for vendor in vendors:
        last4 = vendor.get("bankLast4")
        normalized_name = vendor.get("normalizedName") or repo.normalize_name(vendor.get("name", ""))
        if last4 and normalized_name:
            vendors_by_last4.setdefault(str(last4)[-4:], []).append((vendor, normalized_name))

    keys = ("vendorId", "name", "defaultGlAccount", "hasW9", "hasVoidCheck", "bankLast4",
            "billCount", "lastSeen", "aliases")
    result = []
    for vendor in map(public, vendors):
        normalized_name = vendor.get("normalizedName") or repo.normalize_name(vendor.get("name", ""))
        possible_matches = [
            other.get("name")
            for other, other_name in vendors_by_last4.get(str(vendor.get("bankLast4", ""))[-4:], [])
            if other.get("vendorId") != vendor.get("vendorId") and other_name != normalized_name
        ]
        result.append({
            **{k: vendor.get(k) for k in keys if k in vendor},
            "bankDetailReviewRequired": bool(possible_matches),
            "possibleDuplicateVendorNames": possible_matches,
        })
    return 200, result


handler = router({"GET /vendors": list_vendors})

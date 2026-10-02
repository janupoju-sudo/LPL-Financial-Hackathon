from difflib import SequenceMatcher
import re
from typing import Any, Mapping

from .common import state_context


def _normalized_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9 ]", " ", name.casefold())
    value = re.sub(r"\b(inc|llc|ltd|co|corp|corporation|company|the)\b", " ", value)
    return " ".join(value.split())


def best_vendor_match(
    name: str, vendors: list[Mapping[str, Any]], threshold: float = 0.9
) -> Mapping[str, Any] | None:
    target = _normalized_name(name)
    if not target:
        return None
    scored = [
        (
            SequenceMatcher(
                None, target, _normalized_name(str(vendor.get("name", "")))
            ).ratio(),
            vendor,
        )
        for vendor in vendors
        if vendor.get("name")
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < threshold:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        return None
    return scored[0][1]


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    from shared import repo

    upload = state_context(event)
    normalized = event["normalization"]["data"]["normalized"]
    raw_name = normalized.get("vendorName")
    if not raw_name:
        return {"vendor": None}

    vendor = repo.find_vendor_by_name(upload["practiceId"], raw_name)
    fuzzy_match = False
    if vendor is None:
        vendor = best_vendor_match(
            raw_name, repo.list_vendors(upload["practiceId"])
        )
        fuzzy_match = vendor is not None
    if vendor is None:
        return {
            "vendor": {
                "vendorId": None,
                "name": raw_name,
                "defaultGlAccount": None,
            }
        }

    vendor_id = vendor["vendorId"]
    if fuzzy_match:
        repo.add_vendor_alias(upload["practiceId"], vendor_id, raw_name)
    return {
        "vendor": {
            "vendorId": vendor_id,
            "name": vendor["name"],
            "defaultGlAccount": vendor.get("defaultGlAccount"),
        }
    }

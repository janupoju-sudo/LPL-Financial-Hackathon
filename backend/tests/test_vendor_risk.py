"""Potential duplicated vendor bank details must be surfaced cautiously."""
import json

from handlers import vendors
from shared import repo

from conftest import api_event


def _listed_vendors():
    response = vendors.handler(api_event("GET /vendors"))
    assert response["statusCode"] == 200
    return json.loads(response["body"])


def test_shared_bank_last_four_flags_distinct_vendor_names_without_revealing_digits(aws):
    repo.create_vendor("p1", "Acme Consulting LLC", bankLast4="6789")
    repo.create_vendor("p1", "Northstar Advisors Inc", bankLast4="6789")

    listed = _listed_vendors()

    assert len(listed) == 2
    assert all(vendor["bankDetailReviewRequired"] for vendor in listed)
    assert listed[0]["possibleDuplicateVendorNames"] == ["Northstar Advisors Inc"]
    assert listed[1]["possibleDuplicateVendorNames"] == ["Acme Consulting LLC"]
    warnings = [vendor["possibleDuplicateVendorNames"] for vendor in listed]
    assert "6789" not in json.dumps(warnings)


def test_same_vendor_alias_and_different_last_four_do_not_flag(aws):
    repo.create_vendor("p1", "Acme Consulting LLC", bankLast4="6789")
    repo.create_vendor("p1", "ACME Consulting", bankLast4="1234")
    repo.create_vendor("p1", "Northstar Advisors Inc", bankLast4="9876")

    listed = _listed_vendors()

    assert all(not vendor["bankDetailReviewRequired"] for vendor in listed)

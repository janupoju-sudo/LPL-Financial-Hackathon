from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_bills
from shared import ddb, repo


def _vendors():
    for name, gl in (("Orion Software LLC", "6300"), ("Seaport Office Partners", "6200"),
                     ("LPL Financial", "6400")):
        repo.create_vendor("p1", name, default_gl_account=gl, hasW9=True, hasVoidCheck=True)


def test_history_bills_make_orion_a_recognized_vendor(aws):
    _vendors()
    created, skipped = seed_bills.seed("p1")
    assert (created, skipped) == (len(seed_bills.HISTORY), 0)

    bills = repo.list_bills("p1")
    assert all(b["status"] == "scheduled" for b in bills)
    orion = repo.find_vendor_by_name("p1", "Orion Software LLC")
    assert orion["billCount"] == 4  # > 1, so the UI shows "Recognized vendor"
    assert repo.find_vendor_by_name("p1", "Clearwater Compliance Advisors (FICTIONAL)")

    big = repo.get_bill("p1", seed_bills.bill_id("ORN-2026-07A"))
    assert big["requiredApprovers"] == ["partner"]
    assert [a["action"] for a in big["audit"]] == ["extracted", "routed", "approved", "posted", "scheduled"]
    assert big["audit"][2]["actor"] == seed_bills.PARTNER
    small = repo.get_bill("p1", seed_bills.bill_id("ORN-2026-06"))
    assert small["ruleHits"] == [] and "approved" not in [a["action"] for a in small["audit"]]


def test_history_bills_do_not_touch_the_ledger_and_rerun_is_safe(aws):
    _vendors()
    seed_bills.seed("p1")
    assert ddb.get_ledger_entries("p1", "2026-06-01", "2026-08-31") == []
    assert seed_bills.seed("p1") == (0, len(seed_bills.HISTORY))
    assert repo.find_vendor_by_name("p1", "Orion Software LLC")["billCount"] == 4

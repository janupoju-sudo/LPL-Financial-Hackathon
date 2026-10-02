import unittest

from financials import reconciliation as rec
from fixtures import FEE_SCHEDULE, PAYOUT_SEP


class Reconciliation(unittest.TestCase):
    def test_demo_flags_412_short(self):
        r = rec.compute(FEE_SCHEDULE, PAYOUT_SEP, "2026-09")
        self.assertEqual(r["variance"], -412_00)
        self.assertEqual(len(r["flags"]), 1)
        va = next(l for l in r["lines"] if l["id"] == "va-4471")
        self.assertEqual((va["expected"], va["actual"], va["status"]), (2_890_00, 2_478_00, "short"))
        self.assertIn("0.86% vs. 1.00%", va["reason"])

    def test_quarterly_item_not_expected_off_cycle(self):
        r = rec.compute(FEE_SCHEDULE, PAYOUT_SEP[:3], "2026-08")
        self.assertFalse(any(l["id"] == "va-4471" for l in r["lines"]))
        self.assertEqual(r["flags"], [])

    def test_missing_and_unexpected(self):
        lines = PAYOUT_SEP[:3] + [{"id": "x9", "source": "commission", "label": "Insurance commission",
                                   "actual": 500_00, "docId": "d3"}]
        r = rec.compute(FEE_SCHEDULE, lines, "2026-09")
        statuses = {l["id"]: l["status"] for l in r["lines"]}
        self.assertEqual(statuses["va-4471"], "missing")
        self.assertIn("unexpected", statuses.values())

    def test_rounding_is_ok(self):
        lines = [dict(p, actual=p["actual"] + 50) for p in PAYOUT_SEP]  # 50 cents over each
        lines[3]["actual"] = 2_890_40
        r = rec.compute(FEE_SCHEDULE, lines, "2026-09")
        self.assertEqual(r["flags"], [])

    def test_quarter_period_sums_months(self):
        r = rec.compute(FEE_SCHEDULE, [], "2026-Q3")
        adv = next(l for l in r["lines"] if l["id"] == "adv")
        self.assertEqual(adv["expected"], 3 * 182_400_00)

    def test_response_in_dollars(self):
        r = rec.response(FEE_SCHEDULE, PAYOUT_SEP, "2026-09")
        self.assertEqual(r["variance"], -412.0)
        self.assertEqual(r["lines"][3]["actual"], 2478.0)


if __name__ == "__main__":
    unittest.main()

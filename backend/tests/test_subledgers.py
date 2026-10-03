"""General ledger with subledgers: sub-accounts roll up into their category on the P&L."""
import unittest

from financials import api, kpis, statements
from shared import coa
from ask import context
from fixtures import sample_entries


def journal(jid, day, account, cents):
    return [{"journalId": jid, "date": day, "account": account, "debit": cents, "credit": 0},
            {"journalId": jid, "date": day, "account": "2000", "debit": 0, "credit": cents}]


class Chart(unittest.TestCase):
    def test_sub_accounts_are_expenses_that_roll_up(self):
        self.assertTrue(coa.is_expense("6740"))
        self.assertEqual(coa.category("6740"), "6700")
        self.assertEqual(coa.category("6700"), "6700")
        self.assertEqual([a.code for a in coa.subaccounts("6700")],
                         ["6710", "6720", "6730", "6740", "6750", "6760"])

    def test_every_sub_account_points_at_a_category(self):
        for a in coa.CHART:
            if a.parent:
                parent = coa.get(a.parent)
                self.assertEqual(parent.type, "expense")
                self.assertIsNone(parent.parent, a.code)

    def test_menu_lists_categories_with_indented_children(self):
        menu = coa.expense_menu()
        self.assertIn("6700 Travel and entertainment\n  6710 Airfare", menu)


class Breakdown(unittest.TestCase):
    def setUp(self):
        # Sample history posts travel to the 6700 category; add sub-account activity on top.
        self.e = sample_entries() + journal("air", "2026-09-10", "6710", 64_000) \
            + journal("park", "2026-09-11", "6740", 3_500) + journal("air-q2", "2026-05-02", "6710", 20_000)

    def test_category_total_includes_sub_accounts_and_general(self):
        p = statements.profit_and_loss(self.e, "2026-Q3")
        travel = next(l for l in p["expenses"] if l["account"] == "6700")
        names = [c["name"] for c in travel["children"]]
        self.assertEqual(names[1:], ["Airfare", "Parking"])
        self.assertEqual(travel["amount"], sum(c["amount"] for c in travel["children"]))
        if names[0] == "General":
            self.assertGreater(travel["children"][0]["amount"], 0)
        self.assertEqual(p["totalExpenses"], sum(l["amount"] for l in p["expenses"]))
        self.assertEqual(p["operatingIncome"], p["totalRevenue"] - p["totalExpenses"])

    def test_category_without_sub_accounts_has_no_children(self):
        p = statements.profit_and_loss(sample_entries(), "2026-Q3")
        rent = next(l for l in p["expenses"] if l["account"] == "6200")
        self.assertEqual(rent["children"], [])

    def test_kpi_ratios_stay_at_category_level(self):
        k = kpis.compute(statements.profit_and_loss(self.e, "2026-Q3"))
        codes = [r["account"] for r in k["expenseRatios"]]
        self.assertNotIn("6710", codes)
        self.assertIn("6700", codes)

    def test_api_carries_breakdown_and_previous_period(self):
        out = api.build_financials(self.e, "2026-Q3")
        travel = next(l for l in out["pnl"]["expenseLines"] if l["account"] == "6700")
        air = next(c for c in travel["children"] if c["account"] == "6710")
        self.assertEqual(air["amount"], 640.0)
        self.assertEqual(air["previous"], 200.0)
        self.assertIn("previous", travel)

    def test_ask_summary_names_sub_accounts_but_drivers_are_categories(self):
        text, drivers = context.ledger_summary(self.e, "2026-Q3")
        self.assertIn("  - 6710 Airfare: $640", text)
        self.assertTrue(all(not coa.get(d).parent for d in drivers))


if __name__ == "__main__":
    unittest.main()

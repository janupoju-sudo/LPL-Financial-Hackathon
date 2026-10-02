import unittest
from datetime import date

from financials import api, kpis, periods, statements, valuation
from fixtures import PRACTICE, sample_entries


class Periods(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(periods.parse("2026-09"), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(periods.parse("2026-Q3"), (date(2026, 7, 1), date(2026, 9, 30)))
        self.assertEqual(periods.parse("2026-02"), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(periods.parse("2026"), (date(2026, 1, 1), date(2026, 12, 31)))
        with self.assertRaises(ValueError):
            periods.parse("Q3-2026")

    def test_previous(self):
        self.assertEqual(periods.previous("2026-Q3"), "2026-Q2")
        self.assertEqual(periods.previous("2026-Q1"), "2025-Q4")
        self.assertEqual(periods.previous("2026-01"), "2025-12")
        self.assertEqual(periods.previous("2026"), "2025")


class Statements(unittest.TestCase):
    def setUp(self):
        self.e = sample_entries()

    def test_journals_balance(self):
        statements.check_balanced(self.e)
        bad = self.e + [{"journalId": "x", "date": "2026-09-01", "account": "1000", "debit": 5, "credit": 0}]
        with self.assertRaises(ValueError):
            statements.check_balanced(bad)

    def test_pnl(self):
        p = statements.profit_and_loss(self.e, "2026-Q3")
        self.assertEqual(p["totalRevenue"], (182_400 + 14_200) * 3 * 100 + (19_400 + 17_400 + 21_400) * 100)
        self.assertEqual(p["operatingIncome"], p["totalRevenue"] - p["totalExpenses"])
        rent = next(l for l in p["expenses"] if l["account"] == "6200")
        self.assertEqual(rent["amount"], 9_800 * 3 * 100)

    def test_balance_sheet_balances_every_month(self):
        for m in range(3, 10):
            _, end = periods.parse(f"2026-{m:02d}")
            bs = statements.balance_sheet(self.e, end)
            self.assertEqual(bs["totalAssets"], bs["totalLiabilities"] + bs["totalEquity"], end)

    def test_open_bill_shows_in_payables(self):
        bs = statements.balance_sheet(self.e, date(2026, 9, 30))
        ap = next(l for l in bs["liabilities"] if l["account"] == "2000")
        self.assertEqual(ap["amount"], 1_240 * 100)

    def test_cash_flow_ties_to_balance_sheet(self):
        for period in ("2026-Q2", "2026-Q3", "2026-08"):
            start, end = periods.parse(period)
            cf = statements.cash_flow(self.e, period)
            cash = lambda d: next((l["amount"] for l in statements.balance_sheet(self.e, d)["assets"]
                                   if l["account"] == "1000"), 0)
            self.assertEqual(cf["endingCash"], cash(end), period)
            self.assertEqual(cf["netChange"], cf["netOperating"] + cf["netFinancing"])

    def test_distribution_is_financing(self):
        cf = statements.cash_flow(self.e, "2026-Q2")
        self.assertEqual(cf["netFinancing"], -40_000 * 100)


class KpisAndValuation(unittest.TestCase):
    def setUp(self):
        self.e = sample_entries()

    def test_margin_drops_in_q3(self):
        q2 = kpis.compute(statements.profit_and_loss(self.e, "2026-Q2"))
        q3 = kpis.compute(statements.profit_and_loss(self.e, "2026-Q3"))
        self.assertLess(q3["margin"], q2["margin"])
        self.assertGreater(q3["recurringPct"], 0.9)

    def test_valuation_annualizes_short_history(self):
        k = kpis.compute(statements.profit_and_loss(self.e, "2026-Q3"))
        v = valuation.estimate(self.e, date(2026, 9, 30), k["recurringPct"], k["margin"], 0.22)
        self.assertTrue(v["low"] < v["mid"] < v["high"])
        self.assertIn("annualized", v["method"])
        ttm, months = valuation.recurring_ttm(self.e, date(2026, 9, 30))
        self.assertEqual(months, 6)  # Apr–Sep; the March opening balance has no revenue


class Api(unittest.TestCase):
    def test_response_shape_and_dollars(self):
        r = api.build_financials(sample_entries(), "2026-Q3", PRACTICE)
        for key in ("pnl", "balanceSheet", "cashFlow", "kpis", "valuation"):
            self.assertIn(key, r)
        for key in ("margin", "recurringPct", "revPerClient"):
            self.assertIn(key, r["kpis"])
        for key in ("low", "mid", "high", "method"):
            self.assertIn(key, r["valuation"])
        self.assertIsInstance(r["pnl"]["totalRevenue"], float)
        self.assertEqual(r["kpis"]["previous"]["period"], "2026-Q2")


if __name__ == "__main__":
    unittest.main()

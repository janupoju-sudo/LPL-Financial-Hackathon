import unittest
from datetime import date

from ask import answer, context
from fixtures import DOCUMENTS, sample_entries

TODAY = date(2026, 10, 2)
no_guard = lambda text, source: (False, text)


class Period(unittest.TestCase):
    def test_pick_period(self):
        e = sample_entries()
        self.assertEqual(context.pick_period("Why did my margin drop in Q3?", e, TODAY), "2026-Q3")
        self.assertEqual(context.pick_period("What did we spend in August?", e, TODAY), "2026-08")
        self.assertEqual(context.pick_period("Revenue in Q4 2025", e, TODAY), "2025-Q4")
        self.assertEqual(context.pick_period("How much this year?", e, TODAY), "2026")
        self.assertEqual(context.pick_period("How are we doing?", e, TODAY), "2026-Q3")  # latest data
        self.assertEqual(context.pick_period("What's my margin?", e, TODAY), "2026-Q3")  # "mar" inside a word


class Context(unittest.TestCase):
    def test_margin_question_finds_rent_and_compliance(self):
        ctx = context.build("Why did my margin drop in Q3?", sample_entries(), DOCUMENTS, TODAY)
        ids = [context.doc_id(d) for d in ctx["documents"]]
        self.assertIn("rent-2026-07", ids)
        self.assertIn("Operating margin", ctx["text"])
        self.assertIn("6200 Rent and occupancy", ctx["text"])

    def test_keyword_match(self):
        ctx = context.build("What did Brightline charge us in September?", sample_entries(), DOCUMENTS, TODAY)
        self.assertEqual(context.doc_id(ctx["documents"][0]), "d1")


class Ask(unittest.TestCase):
    def test_answer_keeps_only_real_citations(self):
        seen = {}

        def fake_llm(system, user, schema):
            seen["user"] = user
            return {"answer": "Rent went up.", "citations": ["rent-2026-07", "made-up", "rent-2026-07"]}

        r = answer.ask("Why did my margin drop in Q3?", sample_entries(), DOCUMENTS, TODAY, fake_llm, no_guard)
        self.assertEqual([c["documentId"] for c in r["citations"]], ["rent-2026-07"])
        self.assertEqual(r["citations"][0]["label"], "Summit Office Partners (invoice)")
        self.assertIn("QUESTION\nWhy did my margin drop in Q3?", seen["user"])

    def test_blocked_question_skips_model(self):
        def guard(text, source):
            return (source == "INPUT", "blocked")

        def llm(*_):
            raise AssertionError("model should not be called")

        r = answer.ask("Which stocks should my clients buy?", sample_entries(), DOCUMENTS, TODAY, llm, guard)
        self.assertEqual(r["answer"], answer.BLOCKED_QUESTION)

    def test_output_guard_masks(self):
        llm = lambda *_: {"answer": "Call Sam at 704-555-0100.", "citations": []}
        guard = lambda text, source: (True, "Call Sam at {PHONE}.") if source == "OUTPUT" else (False, text)
        r = answer.ask("Who handles rent?", sample_entries(), DOCUMENTS, TODAY, llm, guard)
        self.assertEqual(r["answer"], "Call Sam at {PHONE}.")

    def test_refusal(self):
        def llm(*_):
            raise answer.Refused("cyber")
        r = answer.ask("Q3 margin?", sample_entries(), DOCUMENTS, TODAY, llm, no_guard)
        self.assertEqual(r["answer"], answer.REFUSED)

    def test_empty_question(self):
        with self.assertRaises(ValueError):
            answer.ask("  ", [], [], TODAY, None, no_guard)


if __name__ == "__main__":
    unittest.main()

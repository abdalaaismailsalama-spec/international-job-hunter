"""اختبارات التصنيف وحماية الملف. التشغيل:  python -m unittest discover -s tests -v"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jb_rules as jb

def c(desc, title="Warehouse Worker"):
    return jb.classify(title, desc)

FILES = ["jobs_bot.py", "jb_config.py", "jb_patterns.py", "jb_rules.py",
         "jb_store.py", "jb_sources.py", "jb_dashboard.py", "jb_report.py"]

def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()

class FileSafetyTests(unittest.TestCase):
    def test_files_compile(self):
        for name in FILES:
            compile(read(name), name, "exec")

    def test_no_backslash_n_sequences(self):
        # علامة backslash+n هي اللي بتتكسر لما الكود بيتنسخ ويتلصق
        for name in FILES:
            self.assertNotIn(chr(92) + "n", read(name), name)

    def test_files_stay_small_for_copying(self):
        for name in FILES:
            self.assertLessEqual(read(name).count(chr(10)), 90, name)

class ClassifyTests(unittest.TestCase):
    def test_permit_required_is_excluded(self):
        cls, _, ev = c("Permesso di lavoro richiesto. Candidati dall'estero.")
        self.assertEqual(cls, "excluded")
        self.assertIn("Permesso di lavoro richiesto", ev)

    def test_no_sponsorship_with_international_applicants_excluded(self):
        cls, _, ev = c("No sponsorship. We welcome international applicants.")
        self.assertEqual(cls, "excluded")
        self.assertIn("No sponsorship", ev)

    def test_hedged_sponsorship_is_only_possible(self):
        cls, _, ev = c("Visa sponsorship may be available for candidates from abroad.")
        self.assertEqual(cls, "possible")
        self.assertIn("may be available", ev)

    def test_no_evidence_is_excluded(self):
        self.assertEqual(c("Lavoro in magazzino, turni.")[0], "excluded")
        self.assertEqual(c("Great team, good salary, shifts.")[0], "excluded")

    def test_bare_work_permit_words_are_not_evidence(self):
        self.assertEqual(c("Work permit holders welcome. Shifts available.")[0], "excluded")
        self.assertEqual(c("Offriamo contratto e permesso di lavoro in magazzino.")[0], "excluded")

    def test_other_hedges(self):
        for t in ("Visa sponsorship might be offered to candidates from abroad.",
                  "Visa sponsorship is subject to approval. Candidates from abroad welcome.",
                  "Visa sponsorship for some roles. We accept applicants from abroad.",
                  "Il visto potrebbe essere organizzato da noi. Candidati dall'estero."):
            self.assertNotEqual(c(t)[0], "confirmed", t)

    def test_negations(self):
        for t in ("We do not sponsor visas. International applicants welcome.",
                  "Visa sponsorship is not available.",
                  "Sorry, no visa sponsorship for this role.",
                  "Keine Visa-Sponsoring möglich.",
                  "Candidates will not require sponsorship."):
            self.assertEqual(c(t)[0], "excluded", t)

    def test_clear_confirmed_keeps_full_sentence(self):
        cls, _, ev = c("We offer visa sponsorship and arrange the work permit for candidates from abroad. Shifts.")
        self.assertEqual(cls, "confirmed")
        self.assertIn("We offer visa sponsorship and arrange the work permit for candidates from abroad.", ev)

    def test_clear_italian_confirmed(self):
        self.assertEqual(c("Ci occupiamo noi del permesso di lavoro e del visto. Candidati dall'estero.")[0], "confirmed")

    def test_sponsorship_alone_is_possible(self):
        self.assertEqual(c("We offer visa sponsorship.")[0], "possible")

    def test_relocation_alone_is_weak(self):
        self.assertEqual(c("Visa sponsorship offered. Relocation within our sites.")[0], "possible")

    def test_old_filters(self):
        self.assertEqual(c("Registration fee 200 EUR required.")[0], "excluded")
        self.assertEqual(c("You must already have the right to work in Italy.")[0], "excluded")
        self.assertEqual(c("Offerta generica.", title="Senior Accountant")[0], "excluded")

if __name__ == "__main__":
    unittest.main()

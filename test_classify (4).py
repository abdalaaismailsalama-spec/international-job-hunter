import os
import sys
import tempfile
import unittest
from pathlib import Path

# Import module from project root without requiring production secrets.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jobs_bot


class ClassificationTests(unittest.TestCase):
    def classify(self, title, description):
        return jobs_bot.classify(title, description)

    def test_clear_sponsorship_and_abroad_is_confirmed(self):
        cls, reasons, evidence = self.classify(
            "Warehouse Worker",
            "We arrange the work permit for candidates from abroad."
        )
        self.assertEqual(cls, "confirmed")
        self.assertIn("from abroad", evidence)

    def test_permit_required_and_abroad_is_possible(self):
        cls, _, evidence = self.classify(
            "Magazziniere",
            "Permesso di lavoro richiesto. Candidati dall'estero."
        )
        self.assertEqual(cls, "possible")
        self.assertIn("Permesso di lavoro richiesto", evidence)

    def test_no_sponsorship_is_excluded(self):
        cls, _, _ = self.classify(
            "Production Worker",
            "No sponsorship. We welcome international applicants."
        )
        self.assertEqual(cls, "excluded")

    def test_may_be_available_is_possible(self):
        cls, _, _ = self.classify(
            "Warehouse Worker",
            "Visa sponsorship may be available for candidates from abroad."
        )
        self.assertEqual(cls, "possible")

    def test_will_not_require_sponsorship_is_not_negative(self):
        cls, _, _ = self.classify(
            "Warehouse Worker",
            "International applicants welcome. Candidates will not require sponsorship."
        )
        self.assertNotEqual(cls, "excluded")

    def test_existing_right_to_work_is_excluded(self):
        cls, _, _ = self.classify(
            "Warehouse Operative",
            "Applicants must already have the right to work in Italy."
        )
        self.assertEqual(cls, "excluded")

    def test_recruitment_fee_is_excluded(self):
        cls, _, _ = self.classify(
            "Packer",
            "A registration fee is required."
        )
        self.assertEqual(cls, "excluded")

    def test_unrelated_job_is_excluded(self):
        cls, _, _ = self.classify("Senior Marketing Director", "Visa sponsorship available.")
        self.assertEqual(cls, "excluded")

    def test_housing_alone_is_only_possible(self):
        cls, _, _ = self.classify("Production Worker", "Accommodation provided.")
        self.assertEqual(cls, "possible")

    def test_relocation_alone_is_only_possible(self):
        cls, _, _ = self.classify("Warehouse Worker", "Relocation support may be offered.")
        self.assertEqual(cls, "possible")

    def test_no_sponsorship_required_phrase_is_not_employer_refusal(self):
        cls, _, _ = self.classify(
            "Warehouse Worker",
            "International applicants welcome. No sponsorship required from the employer."
        )
        self.assertNotEqual(cls, "excluded")

    def test_no_recruitment_fee_is_not_excluded(self):
        cls, _, _ = self.classify(
            "Warehouse Worker",
            "International applicants welcome. No recruitment fee."
        )
        self.assertNotEqual(cls, "excluded")

    def test_candidate_must_work_without_sponsorship_is_excluded(self):
        cls, _, _ = self.classify(
            "Warehouse Worker",
            "Applicants must be eligible to work without sponsorship."
        )
        self.assertEqual(cls, "excluded")


class UtilityTests(unittest.TestCase):
    def test_process_accepts_normalized_feed_dictionary(self):
        with tempfile.TemporaryDirectory() as temp:
            old_test = jobs_bot.TEST
            old_db = jobs_bot.DB_PATH
            try:
                jobs_bot.TEST = True
                jobs_bot.DB_PATH = str(Path(temp) / "normalized.db")
                con = jobs_bot.db_connect()
                sample = [jobs_bot.normalized(
                    "Dev Global Jobs", "dev-123", "Warehouse Worker", "Example Ltd",
                    "IT", "Berlin", "https://example.com/job/123",
                    "We arrange the work permit for candidates from abroad."
                )]
                added = jobs_bot.process(con, sample)
                self.assertEqual(len(added), 1)
                self.assertEqual(added[0]["title"], "Warehouse Worker")
                self.assertEqual(added[0]["cls"], "confirmed")
                con.close()
            finally:
                jobs_bot.TEST = old_test
                jobs_bot.DB_PATH = old_db

    def test_process_skips_malformed_feed_items_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp:
            old_test = jobs_bot.TEST
            old_db = jobs_bot.DB_PATH
            try:
                jobs_bot.TEST = True
                jobs_bot.DB_PATH = str(Path(temp) / "malformed.db")
                con = jobs_bot.db_connect()
                self.assertEqual(jobs_bot.process(con, [None, "bad", ("it", None), {}]), [])
                con.close()
            finally:
                jobs_bot.TEST = old_test
                jobs_bot.DB_PATH = old_db

    def test_url_keeps_query_parameters(self):
        url = "https://example.com/job?id=7&source=adzuna"
        self.assertEqual(jobs_bot.safe_job_url(url), url)

    def test_unsafe_url_is_rejected(self):
        self.assertEqual(jobs_bot.safe_job_url("javascript://alert(1)"), "")


    def test_process_skips_job_without_valid_url_or_international_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            old_test = jobs_bot.TEST
            old_db = jobs_bot.DB_PATH
            try:
                jobs_bot.TEST = True
                jobs_bot.DB_PATH = str(Path(temp) / "strict.db")
                con = jobs_bot.db_connect()
                jobs_bot.process(con, [
                    jobs_bot.normalized("Test", "no-url", "Warehouse Worker", "No URL", "IT", "Berlin", "", "Visa sponsorship available."),
                    jobs_bot.normalized("Test", "no-evidence", "Warehouse Worker", "No Evidence", "IT", "Berlin", "https://example.com/no-evidence", "Good salary and accommodation provided."),
                    jobs_bot.normalized("Test", "good", "Warehouse Worker", "Good Co", "IT", "Berlin", "https://example.com/good", "We arrange the work permit for candidates from abroad."),
                ])
                rows = jobs_bot.pending_jobs(con, 10)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["ad_id"], "test:good")
                self.assertEqual(rows[0]["international"], 1)
                con.close()
            finally:
                jobs_bot.TEST = old_test
                jobs_bot.DB_PATH = old_db

    def test_failed_delivery_remains_pending_for_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            old_test = jobs_bot.TEST
            old_db = jobs_bot.DB_PATH
            try:
                jobs_bot.TEST = True
                jobs_bot.DB_PATH = str(Path(temp) / "retry.db")
                con = jobs_bot.db_connect()
                sample = [("it", {
                    "id": "retry-1",
                    "title": "Warehouse Worker",
                    "company": {"display_name": "Retry Company"},
                    "location": {"display_name": "Milano"},
                    "redirect_url": "https://example.com/job?x=1",
                    "description": "We arrange the work permit for candidates from abroad."
                })]
                jobs_bot.process(con, sample)
                row = jobs_bot.pending_jobs(con, 10)[0]
                self.assertEqual(row["sent"], 0)
                con.execute(
                    "UPDATE jobs SET send_attempts=1, last_send_error='Telegram send failed' WHERE ad_id=?",
                    (row["ad_id"],)
                )
                con.commit()
                self.assertEqual(len(jobs_bot.pending_jobs(con, 10)), 1)
                con.execute("UPDATE jobs SET sent=1, status='sent' WHERE ad_id=?", (row["ad_id"],))
                con.commit()
                self.assertEqual(len(jobs_bot.pending_jobs(con, 10)), 0)
                con.close()
            finally:
                jobs_bot.TEST = old_test
                jobs_bot.DB_PATH = old_db


if __name__ == "__main__":
    unittest.main(verbosity=2)

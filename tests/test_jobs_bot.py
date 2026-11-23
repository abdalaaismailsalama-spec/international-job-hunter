import importlib.util
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("jobs_bot", ROOT / "jobs_bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


class ClassificationTests(unittest.TestCase):
    def test_explicit_sponsorship_and_overseas(self):
        result, _, _ = bot.classify("Warehouse worker", "We provide work permits. We accept overseas applicants.")
        self.assertEqual(result, "confirmed")

    def test_no_sponsorship_is_excluded(self):
        self.assertEqual(bot.classify("Warehouse worker", "No visa sponsorship is available.")[0], "excluded")

    def test_previous_right_to_work_is_excluded(self):
        self.assertEqual(bot.classify("Factory worker", "Must have a valid work permit.")[0], "excluded")

    def test_no_visa_claim_does_not_mean_confirmed(self):
        self.assertEqual(bot.classify("Warehouse worker", "Packing orders on the morning shift.")[0], "possible")

    def test_unrelated_job_is_excluded(self):
        self.assertEqual(bot.classify("Senior software engineer", "Visa sponsorship. Overseas applicants welcome.")[0], "excluded")

    def test_unsafe_url_rejected(self):
        self.assertEqual(bot.safe_job_url("javascript:alert(1)"), "")
        self.assertEqual(bot.safe_job_url("file:///etc/passwd"), "")
        self.assertEqual(bot.safe_job_url("https://example.com/job#fragment"), "https://example.com/job")


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.paths = patch.multiple(bot, DB_PATH=str(pathlib.Path(self.temp.name) / "jobs.db"), TEST=True)
        self.paths.start()
        self.con = bot.db_connect()

    def tearDown(self):
        self.con.close()
        self.paths.stop()
        self.temp.cleanup()

    def job(self, source_id="1", desc="We provide work permits. Overseas applicants welcome.", country="IT"):
        return bot.normalized("test", source_id, "Warehouse worker", "Example", country, "Rome", "https://example.com/job/" + source_id, desc)

    def test_duplicate_job_not_inserted_twice(self):
        row = self.job()
        self.assertEqual(len(bot.process(self.con, [row, row])), 1)
        self.assertEqual(len(bot.process(self.con, [row])), 0)

    def test_only_international_unsent_jobs_are_pending(self):
        bot.process(self.con, [self.job()])
        self.assertEqual(len(bot.pending_jobs(self.con)), 1)
        self.con.execute("UPDATE jobs SET sent=1")
        self.assertEqual(bot.pending_jobs(self.con), [])

    def test_generic_local_job_is_not_telegram_candidate(self):
        bot.process(self.con, [self.job(desc="Pack orders on the morning shift.")])
        self.assertEqual(bot.pending_jobs(self.con), [])

    def test_non_target_country_is_filtered(self):
        self.assertEqual(bot.process(self.con, [self.job(country="DE")]), [])

    def test_failed_delivery_stays_pending(self):
        bot.process(self.con, [self.job()])
        self.con.execute("UPDATE jobs SET sent=0, status='pending', send_attempts=1, last_send_error='Telegram send failed'")
        self.assertEqual(len(bot.pending_jobs(self.con)), 1)

    def test_dry_run_telegram_never_posts(self):
        with patch.object(bot.requests, "post") as post:
            self.assertTrue(bot.telegram("Offline test"))
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import jobs_bot as b

class ClassificationTests(unittest.TestCase):
    def test_confirmed(self):
        c,_,_=b.classify("Warehouse Worker","We offer visa sponsorship for candidates from abroad.")
        self.assertEqual(c,"confirmed")
    def test_no_sponsorship_excluded(self):
        c,_,_=b.classify("Warehouse Worker","No visa sponsorship available.")
        self.assertEqual(c,"excluded")
    def test_suitable_without_visa_evidence_is_possible(self):
        c,_,_=b.classify("Production Worker","Packing products on a production line.")
        self.assertEqual(c,"possible")
    def test_hedged_is_possible(self):
        c,_,_=b.classify("Warehouse Worker","Visa sponsorship may be available for candidates from abroad.")
        self.assertEqual(c,"possible")
    def test_residency_excluded(self):
        c,_,_=b.classify("Cleaner","Must already have the right to work in France.")
        self.assertEqual(c,"excluded")
    def test_fee_excluded(self):
        c,_,_=b.classify("Packer","Registration fee 200 EUR required.")
        self.assertEqual(c,"excluded")
    def test_non_target_job_excluded(self):
        c,_,_=b.classify("Marketing Manager","Visa sponsorship available.")
        self.assertEqual(c,"excluded")
    def test_safe_url_keeps_query(self):
        self.assertEqual(b.safe_url("https://example.com/job?a=1#top"),"https://example.com/job?a=1")
    def test_reject_javascript(self):
        self.assertEqual(b.safe_url("javascript:alert(1)"),"")
    def test_country_alias(self):
        self.assertEqual(b.parse_country("Saudi Arabia"),"SA")

if __name__=="__main__": unittest.main()

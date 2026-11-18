"""الإعدادات والقوايم (دول، كلمات بحث). ملف صغير عشان النسخ."""
import sys

# من غير أي "backslash + n" عشان النسخ واللصق ما يكسرش الكود.
NL = chr(10)
BS = chr(92)

TEST = "--test" in sys.argv
DB_PATH = "data/test.db" if TEST else "data/jobs.db"
DASH_PATH = "data/test_dashboard.html" if TEST else "docs/index.html"
MAX_CARDS = 15      # أقصى عدد بطاقات في اليوم
MAX_ATTEMPTS = 5    # أقصى محاولات إعادة إرسال لبطاقة فشل إرسالها
RETRY_DAYS = 7      # نعيد إرسال الفاشل لمدة 7 أيام بس
TIMEOUT = 25
HEADERS = {"User-Agent": "JobAlertsPersonal/3.0 (personal job alert reader)"}

COUNTRY_NAMES = {"AE": "الإمارات", "SA": "السعودية", "IT": "إيطاليا", "PL": "بولندا",
                 "RS": "صربيا", "AL": "ألبانيا", "GR": "اليونان"}
ADZUNA_COUNTRIES = {"it": "إيطاليا", "pl": "بولندا"}   # اللي Adzuna بيغطيه من دولك
NOT_COVERED = "الإمارات، السعودية، صربيا، ألبانيا، اليونان"
CURRENCY = {"pl": "PLN"}
SOURCE_LABELS = {"Adzuna": "Adzuna (يحوّل للإعلان الأصلي)"}

EN = ["warehouse worker", "production worker", "packer", "general worker", "cleaner",
      "warehouse relocation accommodation"]
LOCAL = {
    "pl": ["pracownik magazynowy", "pracownik produkcji"],
    "it": ["magazziniere", "operaio generico"],
}

# بيانات تجريبية لوضع الاختبار (python jobs_bot.py --test): (رقم، عنوان، شركة، دولة، مدينة، رابط، نص، تاريخ)
SAMPLE_ROWS = [
    ('de:t1', 'Warehouse Worker (m/w/d)', 'Test Logistik GmbH', 'DE', 'Hamburg', 'https://example.com/ad/1', 'We offer visa sponsorship and work permit assistance for candidates from abroad. Accommodation provided.', '2026-11-16'),
    ('nl:t2', 'Production Worker', 'Voorbeeld BV', 'NL', 'Venlo', 'https://example.com/ad/2', 'Housing included, shifts. Relocation support.', '2026-11-16'),
    ('fr:t3', 'Warehouse Operative', 'Exemple SA', 'FR', 'Lyon', 'https://example.com/ad/3', 'You must already have the right to work in France.', '2026-11-16'),
    ('pl:t4', 'Packer', 'Przyklad', 'PL', 'Łódź', 'https://example.com/ad/4', 'Registration fee 200 EUR required.', '2026-11-16'),
    ('it:t6', 'Warehouse Operator', 'Nega Srl', 'IT', 'Roma', 'javascript://x/%0Aalert(1)', 'Please note: no visa sponsorship available for this role.', '2026-11-16'),
    ('pl:t7', 'Storekeeper <b>x</b>', 'Reloc Sp.', 'PL', 'Gdańsk', 'https://example.com/ad/7', 'Visa sponsorship offered. Relocation within our sites possible.', '2026-11-16'),
    ('it:t8', 'Warehouse Worker', 'May Srl', 'IT', 'Torino', 'https://example.com/ad/8', 'Visa sponsorship may be available for candidates from abroad.', '2026-11-16'),
    ('it:t5', 'Magazziniere', 'Esempio Srl', 'IT', 'Milano', 'https://example.com/ad/5', 'Lavoro in magazzino, turni.', '2026-11-16'),
]

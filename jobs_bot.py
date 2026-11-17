#!/usr/bin/env python3
"""International job alerts: multi-source, search/alert only."""
import os, sys, re, json, sqlite3, hashlib, datetime, time, html
from urllib.parse import urlsplit, urlunsplit
import requests

TEST = "--test" in sys.argv
DB_PATH = "data/test.db" if TEST else "data/jobs.db"
MAX_CARDS = 15
TIMEOUT = 25
HEADERS = {"User-Agent": "InternationalJobHunter/2.0"}

ADZUNA_COUNTRIES = {"it": "إيطاليا", "pl": "بولندا"}
TARGET_COUNTRIES = {"AE": "الإمارات", "SA": "السعودية", "IT": "إيطاليا", "PL": "بولندا", "RS": "صربيا", "AL": "ألبانيا", "GR": "اليونان"}
QUERIES = ["warehouse worker", "production worker", "packer", "general worker", "cleaner"]

JOB_WORDS = re.compile(r"warehouse|magazzin|magazyn|production|produkc|factory|packer|cleaner|عامل|مخزن|إنتاج|تغليف|تنظيف", re.I)
SPONSOR = re.compile(r"visa sponsor|sponsorship|work permit|relocation|housing provided|accommodation", re.I)

def clean_html(s):
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", str(s or " "))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def classify(title, desc):
    text = f"{title}\n{desc}"
    if not JOB_WORDS.search(title):
        return "excluded", ["الوظيفة خارج مجالات البحث"], ""
    if SPONSOR.search(text):
        return "confirmed", ["توفر دعم تأشيرة أو استقدام"], "ذكر دعم التأشيرة"
    return "possible", ["إعلان مناسب للمهنة، يلزم سؤال صاحب العمل"], ""

def db_connect():
    os.makedirs("data", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad_id TEXT UNIQUE, url TEXT, norm_key TEXT UNIQUE,
        title TEXT, company TEXT, country TEXT, city TEXT, salary TEXT, posted TEXT, deadline TEXT,
        snippet TEXT, source TEXT, cls TEXT, reasons TEXT, first_seen TEXT, status TEXT,
        sent INTEGER DEFAULT 0, visa_evidence TEXT DEFAULT '')""")
    con.commit()
    return con

def norm_key(company, title, country):
    s = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", f"{company}|{title}|{country}".lower())
    return hashlib.sha1(s.encode()).hexdigest()

def safe_url(raw):
    try:
        u = urlsplit(str(raw or "").strip())
        if u.scheme not in ("http", "https") or not u.netloc: return ""
        return urlunsplit((u.scheme, u.netloc, u.path, u.query, ""))
    except Exception: return ""

def fetch_adzuna(errors):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key): return []
    out = []
    for cc, country in ADZUNA_COUNTRIES.items():
        for q in QUERIES:
            try:
                r = requests.get(f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1",
                    params={"app_id": app_id, "app_key": app_key, "results_per_page": 20, "what": q, "max_days_old": 7, "content-type": "application/json"}, timeout=30)
                r.raise_for_status()
                for j in r.json().get("results", []):
                    loc = j.get("location") or {}
                    out.append({
                        "source": "Adzuna", "source_id": f"{cc}:{j.get('id')}",
                        "title": j.get("title"), "company": (j.get("company") or {}).get("display_name", "غير مذكور"),
                        "country": country, "city": loc.get("display_name", ""),
                        "url": safe_url(j.get("redirect_url")), "desc": j.get("description", ""),
                        "posted": (j.get("created") or "")[:10], "salary": "غير مذكور"
                    })
            except Exception as e:
                errors.append(f"Adzuna/{country}: {type(e).__name__}")
            time.sleep(0.2)
    return out

def process(con, raw):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    new = []
    for item in raw:
        title, company, country = str(item.get("title") or ""), str(item.get("company") or "غير مذكور"), str(item.get("country") or "غير محدد")
        if not JOB_WORDS.search(title): continue
        nk = norm_key(company, title, country)
        ad_id = f"adzuna:{item.get('source_id') or nk}"
        if con.execute("SELECT 1 FROM jobs WHERE ad_id=? OR norm_key=?", (ad_id, nk)).fetchone(): continue
        desc = clean_html(item.get("desc") or "")
        cls, reasons, evidence = classify(title, desc)
        row = {
            "ad_id": ad_id, "url": safe_url(item.get("url")), "norm_key": nk,
            "title": title, "company": company, "country": country,
            "city": str(item.get("city") or ""), "salary": "غير مذكور",
            "posted": str(item.get("posted") or ""), "deadline": "غير مذكور",
            "snippet": desc[:500], "source": str(item.get("source") or "Adzuna"),
            "cls": cls, "reasons": " | ".join(reasons), "visa_evidence": evidence,
            "first_seen": now, "status": "excluded" if cls == "excluded" else "pending", "sent": 0,
        }
        cols = list(row)
        con.execute(f"INSERT OR IGNORE INTO jobs({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", [row[k] for k in cols])
        if con.execute("SELECT changes()").fetchone()[0]: new.append(row)
    con.commit()
    return new

def telegram(message):
    if TEST: print(message); return True
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat): return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", data={"chat_id": chat, "text": message[:4000], "disable_web_page_preview": "true"}, timeout=30)
        return r.ok
    except Exception: return False

def card(r):
    return f"🟢 فرصة عمل\n\nالوظيفة: {r['title']}\nالشركة: {r['company']}\nالدولة: {r['country']}\nرابط: {r['url']}"

def main():
    con = db_connect()
    errors = []
    raw = fetch_adzuna(errors)
    new_rows = process(con, raw)
    rows = con.execute("SELECT * FROM jobs WHERE COALESCE(sent,0)=0 AND cls IN ('confirmed','possible') LIMIT 15").fetchall()
    for r in rows:
        # r mapping: 0:id, 1:ad_id, 2:url, 3:norm_key, 4:title, 5:company, 6:country, 7:city, 8:salary, 9:posted, 10:deadline, 11:snippet, 12:source, 13:cls, 14:reasons, 15:first_seen, 16:status, 17:sent, 18:visa_evidence
        d = {"title": r[4], "company": r[5], "country": r[6], "url": r[2]}
        if telegram(card(d)) and not TEST:
            con.execute("UPDATE jobs SET sent=1, status='sent' WHERE ad_id=?", (r[1],))
    con.commit()
    con.close()

if __name__ == "__main__":
    main()
    

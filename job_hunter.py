import os, re, json, sqlite3, hashlib, html
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests

DB_PATH = os.getenv("DB_PATH", "jobs.sqlite3")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY", "")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

COUNTRIES = {
    "Romania": {"jooble": "Romania", "adzuna": None},
    "Albania": {"jooble": "Albania", "adzuna": None},
    "Serbia": {"jooble": "Serbia", "adzuna": None},
    "Bulgaria": {"jooble": "Bulgaria", "adzuna": None},
    "Malta": {"jooble": "Malta", "adzuna": None},
    "Croatia": {"jooble": "Croatia", "adzuna": None},
    "Poland": {"jooble": "Poland", "adzuna": "pl"},
    "Italy": {"jooble": "Italy", "adzuna": "it"},
    "Germany": {"jooble": "Germany", "adzuna": "de"},
    "Netherlands": {"jooble": "Netherlands", "adzuna": "nl"},
    "France": {"jooble": "France", "adzuna": "fr"},
    "United Kingdom": {"jooble": "United Kingdom", "adzuna": "gb"},
    "United Arab Emirates": {"jooble": "United Arab Emirates", "adzuna": None},
    "Saudi Arabia": {"jooble": "Saudi Arabia", "adzuna": None},
    "Qatar": {"jooble": "Qatar", "adzuna": None},
    "Oman": {"jooble": "Oman", "adzuna": None},
    "Kuwait": {"jooble": "Kuwait", "adzuna": None},
}

KEYWORDS = [
    "warehouse worker", "warehouse assistant", "storekeeper", "warehouse operative",
    "material handler", "production worker", "factory worker", "packing worker",
    "packer", "order picker", "general worker", "construction helper",
    "farm worker", "agricultural worker", "cleaner", "kitchen helper",
    "عامل مخزن", "عامل إنتاج", "مناول بضائع", "مساعد مخزن",
    "lucrător depozit", "manipulant marfuri", "muncitor necalificat",
    "radnik u skladištu", "skladištar", "radnik u proizvodnji",
    "punues magazine", "punëtor magazine", "работник склад", "общ работник",
]

# These phrases only create a "possible/explicit sponsorship" label.
# They do NOT establish legal eligibility; human confirmation is still required.
SPONSORSHIP_PATTERNS = [
    r"visa sponsorship", r"work permit sponsorship", r"visa provided",
    r"work permit provided", r"employer sponsors", r"sponsorship available",
    r"relocation and visa", r"we hire foreign workers", r"foreign applicants",
    r"non[- ]eu applicants", r"third[- ]country nationals", r"work authorization support",
    r"permit de muncă", r"angajăm străini", r"lucrători străini",
    r"radna dozvola", r"strani radnici", r"leje pune", r"punëtorë të huaj",
]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        fingerprint TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
        country TEXT, url TEXT, source TEXT, posted TEXT, salary TEXT,
        snippet TEXT, sponsorship TEXT, first_seen TEXT, status TEXT DEFAULT 'new'
    )""")
    conn.commit()
    return conn

def clean(v):
    return html.unescape(str(v or "")).strip()

def fingerprint(job):
    raw = "|".join([clean(job.get("company")).lower(), clean(job.get("title")).lower(),
                    clean(job.get("location")).lower(), clean(job.get("url")).split("?")[0].lower()])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def sponsorship_label(text):
    t = text.lower()
    if any(re.search(p, t) for p in SPONSORSHIP_PATTERNS):
        return "إشارة صريحة في الإعلان — يلزم تأكيد صاحب العمل"
    return "غير مؤكد — يجب سؤال صاحب العمل عن الاستقدام من مصر"

def jooble_search(keyword, country):
    if not JOOBLE_API_KEY:
        return []
    endpoint = f"https://jooble.org/api/{JOOBLE_API_KEY}"
    payload = {"keywords": keyword, "location": country, "page": "1"}
    try:
        r = requests.post(endpoint, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[Jooble] {country} / {keyword}: {e}")
        return []
    out = []
    for x in data.get("jobs", []):
        out.append({
            "title": clean(x.get("title")), "company": clean(x.get("company")),
            "location": clean(x.get("location")) or country, "country": country,
            "url": clean(x.get("link")), "source": "Jooble API",
            "posted": clean(x.get("updated")), "salary": clean(x.get("salary")),
            "snippet": clean(x.get("snippet"))
        })
    return out

def adzuna_search(keyword, country_name, country_code):
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY and country_code):
        return []
    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
    params = {"app_id": ADZUNA_APP_ID, "app_key": ADZUNA_APP_KEY,
              "what": keyword, "results_per_page": 20, "content-type": "application/json"}
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[Adzuna] {country_name} / {keyword}: {e}")
        return []
    out = []
    for x in data.get("results", []):
        out.append({
            "title": clean(x.get("title")), "company": clean((x.get("company") or {}).get("display_name")),
            "location": clean((x.get("location") or {}).get("display_name")) or country_name,
            "country": country_name, "url": clean(x.get("redirect_url")),
            "source": "Adzuna API", "posted": clean(x.get("created")),
            "salary": clean(x.get("salary_min")) + (" - " + clean(x.get("salary_max")) if x.get("salary_max") else ""),
            "snippet": clean(x.get("description"))
        })
    return out

def collect():
    found = []
    for country, cfg in COUNTRIES.items():
        # Jooble supports broad country search; actual coverage/results depend on its index.
        for kw in KEYWORDS:
            found.extend(jooble_search(kw, cfg["jooble"]))
        # Adzuna only for configured country codes; never imply coverage elsewhere.
        if cfg["adzuna"]:
            for kw in KEYWORDS[:12]:
                found.extend(adzuna_search(kw, country, cfg["adzuna"]))
    return found

def save_new(jobs):
    conn = db()
    new = []
    now = datetime.now(timezone.utc).isoformat()
    for j in jobs:
        if not j.get("url") or not j.get("title"):
            continue
        fp = fingerprint(j)
        text = " ".join([j.get("title",""), j.get("snippet",""), j.get("company","")])
        label = sponsorship_label(text)
        try:
            conn.execute("""INSERT INTO jobs
                (fingerprint,title,company,location,country,url,source,posted,salary,snippet,sponsorship,first_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (fp,j.get("title"),j.get("company"),j.get("location"),j.get("country"),
                 j.get("url"),j.get("source"),j.get("posted"),j.get("salary"),
                 j.get("snippet"),label,now))
            new.append({**j, "sponsorship": label})
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return new

def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing; report printed instead.")
        print(text)
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Telegram limit is 4096 chars.
    chunks = [text[i:i+3900] for i in range(0, len(text), 3900)] or ["لا توجد فرص جديدة اليوم."]
    ok = True
    for chunk in chunks:
        try:
            r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk,
                                         "disable_web_page_preview": True}, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print("Telegram send failed:", e)
            ok = False
    return ok

def format_report(jobs):
    today = datetime.now().strftime("%Y-%m-%d")
    if not jobs:
        return f"🔎 تقرير فرص العمل الدولية — {today}\nلم يتم العثور على إعلانات جديدة من المصادر المتصلة اليوم.\nهذا لا يعني عدم وجود وظائف؛ قد تكون تغطية المصادر محدودة."
    lines = [f"🌍 فرص عمل جديدة — {today}", f"عدد الإعلانات الجديدة: {len(jobs)}", ""]
    for i, j in enumerate(jobs[:25], 1):
        lines += [
            f"{i}) {j.get('title','غير محدد')}",
            f"الشركة: {j.get('company') or 'غير معلنة'}",
            f"الدولة/الموقع: {j.get('country')} — {j.get('location')}",
            f"الراتب: {j.get('salary') or 'غير معلن'}",
            f"تاريخ الإعلان: {j.get('posted') or 'غير متاح'}",
            f"الاستقدام من مصر: {j.get('sponsorship')}",
            f"المصدر: {j.get('source')}",
            f"الرابط: {j.get('url')}",
            ""
        ]
    lines.append("تنبيه: ظهور الإعلان لا يثبت قبول المصريين من الخارج. أكّد تصريح العمل والتأشيرة مباشرة مع صاحب العمل قبل أي التزام.")
    return "\n".join(lines)

def main():
    if not JOOBLE_API_KEY and not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        raise SystemExit("أضف JOOBLE_API_KEY أو بيانات Adzuna في GitHub Secrets أولاً.")
    jobs = collect()
    fresh = save_new(jobs)
    report = format_report(fresh)
    telegram_send(report)
    print(f"Collected={len(jobs)} New={len(fresh)}")

if __name__ == "__main__":
    main()

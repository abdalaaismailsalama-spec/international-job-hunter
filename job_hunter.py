import os
import re
import html
import sqlite3
import hashlib
from datetime import datetime, timezone

import requests

DB_PATH = os.getenv("DB_PATH", "jobs.sqlite3")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Arbeitnow publishes a public Europe-focused feed without an API key.
SOURCES = [
    ("Arbeitnow", "https://www.arbeitnow.com/api/job-board-api?page=1"),
    ("Arbeitnow UK", "https://www.arbeitnow.co.uk/api/job-board-api?page=1"),
]

ROLE_TERMS = [
    "warehouse", "storekeeper", "stock assistant", "warehouse assistant",
    "warehouse operative", "material handler", "order picker", "picker packer",
    "packer", "packing", "production worker", "factory worker", "general worker",
    "cleaner", "cleaning operative", "kitchen porter", "farm worker",
    "agricultural worker", "construction labourer", "construction laborer",
    "manual worker", "unskilled worker", "muncitor necalificat",
    "lucrator depozit", "manipulant marfuri", "radnik skladiste",
    "radnik u proizvodnji", "skladistar", "punues magazine", "pastrues",
]

TARGET_COUNTRIES = [
    "romania", "albania", "serbia", "bulgaria", "croatia", "malta", "cyprus",
    "germany", "united kingdom", "uk", "poland", "italy", "netherlands",
    "france", "austria", "belgium", "ireland", "spain", "portugal", "greece",
    "slovenia", "slovakia", "hungary", "czechia", "czech republic", "lithuania",
    "latvia", "estonia", "sweden", "finland", "denmark", "norway", "switzerland",
]

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


def clean(value):
    value = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def fingerprint(job):
    raw = "|".join([
        clean(job.get("company")).lower(), clean(job.get("title")).lower(),
        clean(job.get("location")).lower(), clean(job.get("url")).split("?")[0].lower()
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sponsorship_label(text):
    lowered = text.lower()
    if any(re.search(pattern, lowered) for pattern in SPONSORSHIP_PATTERNS):
        return "وردت إشارة للتأشيرة/التصريح — يلزم تأكيد قبول متقدم من مصر"
    return "غير مذكور — اسأل صاحب العمل عن الاستقدام من مصر"


def role_matches(text):
    lowered = text.lower()
    return any(term in lowered for term in ROLE_TERMS)


def country_matches(location):
    lowered = clean(location).lower()
    return any(country in lowered for country in TARGET_COUNTRIES)


def fetch_source(source_name, endpoint):
    try:
        response = requests.get(endpoint, headers={"User-Agent": "InternationalJobAlerts/1.0"}, timeout=35)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[{source_name}] fetch failed: {exc}")
        return []

    items = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        print(f"[{source_name}] unexpected response format")
        return []

    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = clean(item.get("title"))
        company = clean(item.get("company_name") or item.get("company"))
        location = clean(item.get("location"))
        description = clean(re.sub(r"<[^>]+>", " ", str(item.get("description", ""))))
        tags = item.get("tags", [])
        if isinstance(tags, list):
            tags_text = " ".join(clean(tag) for tag in tags)
        else:
            tags_text = clean(tags)
        searchable = " ".join([title, description, tags_text])
        if not title or not role_matches(searchable) or not country_matches(location):
            continue

        posted = item.get("created_at") or item.get("date") or ""
        if isinstance(posted, (int, float)):
            posted = datetime.fromtimestamp(posted, timezone.utc).isoformat()
        url = clean(item.get("url"))
        if not url.startswith("https://"):
            continue
        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "country": location,
            "url": url,
            "source": source_name,
            "posted": clean(posted),
            "salary": clean(item.get("salary")),
            "snippet": description[:1200],
        })
    return jobs


def collect():
    all_jobs = []
    for source_name, endpoint in SOURCES:
        all_jobs.extend(fetch_source(source_name, endpoint))
    return all_jobs


def save_new(jobs):
    conn = db()
    new_jobs = []
    now = datetime.now(timezone.utc).isoformat()
    for job in jobs:
        fp = fingerprint(job)
        label = sponsorship_label(" ".join([job.get("title", ""), job.get("snippet", ""), job.get("company", "")]))
        try:
            conn.execute("""INSERT INTO jobs
                (fingerprint,title,company,location,country,url,source,posted,salary,snippet,sponsorship,first_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (fp, job.get("title"), job.get("company"), job.get("location"), job.get("country"),
                 job.get("url"), job.get("source"), job.get("posted"), job.get("salary"),
                 job.get("snippet"), label, now))
            new_jobs.append({**job, "sponsorship": label})
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    conn.close()
    return new_jobs


def telegram_send(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing; report printed instead.")
        print(message)
        return False

    endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunks = [message[i:i + 3900] for i in range(0, len(message), 3900)] or ["لا توجد فرص جديدة اليوم."]
    success = True
    for chunk in chunks:
        try:
            response = requests.post(endpoint, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
                "disable_web_page_preview": True,
            }, timeout=30)
            response.raise_for_status()
            if not response.json().get("ok"):
                raise RuntimeError("Telegram API returned ok=false")
        except Exception as exc:
            print(f"Telegram send failed: {exc}")
            success = False
    return success


def format_report(jobs):
    today = datetime.now().strftime("%Y-%m-%d")
    if not jobs:
        return (
            f"🔎 تقرير فرص العمل الدولية — {today}\n"
            "لم تظهر إعلانات جديدة مطابقة في المصادر المتصلة اليوم.\n\n"
            "المصدر الحالي يركز على أوروبا وبريطانيا، وقد لا يغطي الخليج أو كل دول البلقان. "
            "عدم ظهور نتائج لا يعني عدم وجود وظائف."
        )

    lines = [f"🌍 فرص عمل جديدة — {today}", f"عدد الإعلانات الجديدة: {len(jobs)}", ""]
    for index, job in enumerate(jobs[:20], 1):
        lines.extend([
            f"{index}) {job.get('title', 'غير محدد')}",
            f"الشركة: {job.get('company') or 'غير معلنة'}",
            f"الموقع: {job.get('location') or 'غير محدد'}",
            f"تاريخ الإعلان: {job.get('posted') or 'غير متاح'}",
            f"التأشيرة/الاستقدام: {job.get('sponsorship')}",
            f"المصدر: {job.get('source')} — https://www.arbeitnow.com",
            f"الرابط: {job.get('url')}",
            "",
        ])
    lines.append("تنبيه: الإعلان لا يثبت قبول متقدم من مصر. تأكد من عقد العمل وتصريح العمل والتأشيرة مباشرةً قبل أي التزام، ولا تدفع رسوم توظيف.")
    return "\n".join(lines)


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise SystemExit("إعدادات Telegram غير موجودة في GitHub Secrets.")
    jobs = collect()
    fresh = save_new(jobs)
    report = format_report(fresh)
    sent = telegram_send(report)
    print(f"Collected={len(jobs)} New={len(fresh)} TelegramSent={sent}")


if __name__ == "__main__":
    main()
    

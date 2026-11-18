"""قاعدة البيانات: حفظ الإعلانات، منع التكرار، والبطاقات اللي لسه ما اتبعتتش."""
import os, re, sqlite3, datetime
from jb_config import *
from jb_rules import classify, norm_key


def db_connect():
    os.makedirs("data", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad_id TEXT UNIQUE, url TEXT, norm_key TEXT UNIQUE,
        title TEXT, company TEXT, country TEXT, city TEXT, salary TEXT, posted TEXT, deadline TEXT,
        snippet TEXT, source TEXT, cls TEXT, reasons TEXT, first_seen TEXT, status TEXT,
        sent INTEGER DEFAULT 0, visa_evidence TEXT DEFAULT '', send_attempts INTEGER DEFAULT 0,
        last_send_error TEXT DEFAULT '')""")
    have = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
    for name, typ in (("visa_evidence", "TEXT DEFAULT ''"), ("send_attempts", "INTEGER DEFAULT 0"),
                      ("last_send_error", "TEXT DEFAULT ''")):
        if name not in have:
            con.execute("ALTER TABLE jobs ADD COLUMN " + name + " " + typ)
    con.commit()
    return con


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def process(con, items):
    now = utcnow().isoformat(timespec="seconds")
    new = []
    for it in items:
        title, company, cc = it["title"], it["company"], it["country_code"]
        ad_id = it["source"].lower() + ":" + it["source_id"]
        nk = norm_key(company, title, cc)
        if con.execute("SELECT 1 FROM jobs WHERE ad_id=? OR norm_key=?", (ad_id, nk)).fetchone():
            continue  # سبق ظهوره (حتى لو من رابط/موقع مختلف)
        cls, reasons, evidence = classify(title, it["desc"])
        row = dict(ad_id=ad_id, url=it["url"], norm_key=nk, title=title, company=company,
                   country=COUNTRY_NAMES.get(cc, cc), city=it["city"], salary=it["salary"],
                   posted=it["posted"], deadline=it["deadline"], snippet=it["desc"][:400],
                   source=SOURCE_LABELS.get(it["source"], it["source"]), cls=cls,
                   reasons=" | ".join(reasons), visa_evidence=evidence, first_seen=now,
                   status="excluded" if cls == "excluded" else "new", sent=0)
        con.execute("INSERT INTO jobs(" + ",".join(row) + ") VALUES(" + ",".join("?" * len(row)) + ")",
                    list(row.values()))
        new.append(row)
    con.commit()
    return new


def pending_rows(con):
    """البطاقات اللي لسه ما اتبعتتش (جديدة، أو فشل إرسالها قبل كده)."""
    cutoff = (utcnow() - datetime.timedelta(days=RETRY_DAYS)).isoformat(timespec="seconds")
    con.row_factory = sqlite3.Row
    rows = [dict(x) for x in con.execute(
        "SELECT * FROM jobs WHERE sent=0 AND cls IN ('confirmed','possible') AND first_seen>=? "
        "AND COALESCE(send_attempts,0)<? ORDER BY (cls='confirmed') DESC, first_seen DESC, id DESC",
        (cutoff, MAX_ATTEMPTS))]
    con.row_factory = None
    return rows

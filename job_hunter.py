#!/usr/bin/env python3
"""International job alerts: multi-source, search/alert only. No applications or document sending."""
import os, sys, re, json, sqlite3, hashlib, datetime, time, html
from urllib.parse import urlsplit, urlunsplit
import requests
import xml.etree.ElementTree as ET

TEST = "--test" in sys.argv
DB_PATH = "data/test.db" if TEST else "data/jobs.db"
MAX_CARDS = 15
TIMEOUT = 25
HEADERS = {"User-Agent": "InternationalJobHunter/2.0 (public job feed reader)"}

# Existing Adzuna retained as optional; no keys means it is skipped, not fatal.
ADZUNA_COUNTRIES = {"it": "إيطاليا", "pl": "بولندا"}
CURRENCY = {"pl": "PLN"}

TARGET_COUNTRIES = {
    "AE": "الإمارات", "SA": "السعودية", "IT": "إيطاليا", "PL": "بولندا",
    "RS": "صربيا", "AL": "ألبانيا", "GR": "اليونان", "RO": "رومانيا",
    "BG": "بلغاريا", "HR": "كرواتيا", "MT": "مالطا", "CY": "قبرص",
    "DE": "ألمانيا", "NL": "هولندا", "FR": "فرنسا", "GB": "بريطانيا",
    "US": "أمريكا", "CA": "كندا", "AU": "أستراليا", "NZ": "نيوزيلندا"
}
COUNTRY_ALIASES = {
    "united arab emirates":"AE", "uae":"AE", "saudi arabia":"SA", "italy":"IT",
    "poland":"PL", "serbia":"RS", "albania":"AL", "greece":"GR", "romania":"RO",
    "bulgaria":"BG", "croatia":"HR", "malta":"MT", "cyprus":"CY", "germany":"DE",
    "netherlands":"NL", "france":"FR", "united kingdom":"GB", "uk":"GB",
    "united states":"US", "usa":"US", "canada":"CA", "australia":"AU", "new zealand":"NZ"
}
QUERIES = [
    "warehouse worker", "warehouse assistant", "storekeeper", "warehouse operative",
    "material handler", "picker packer", "order picker", "production worker",
    "factory worker", "packing worker", "packer", "general worker", "cleaner",
    "housekeeping", "farm worker", "agricultural worker", "harvest worker",
    "construction labourer", "kitchen assistant", "loader", "unloader"
]
JOB_WORDS = re.compile(
    r"warehouse|lager|magazijn|magasin|magazzin|magazyn|production|produktion|productie|"
    r"produkc|factory|fabrik|packer|packing|pack|verpack|picker|kommission|préparateur|"
    r"general worker|helfer|helper|cleaner|reinigung|schoonmaak|nettoyage|sprz[aą]t|"
    r"pulizie|kitchen|küche|farm|agricult|landwirt|harvest|construction|housekeeping|"
    r"manutention|operaio|operai|loader|unloading|logisti|stock|storekeeper|material|"
    r"opérateur|medewerker|mitarbeiter|pracownik|labourer|laborer|packaging|"
    r"عامل|مخزن|مستودع|إنتاج|انتاج|تعبئة|تغليف|تنظيف|زراعة|حصاد|مساعد", re.I)
FEE = re.compile(r"registration fee|placement fee|processing fee|pay (a|the) fee|"
                 r"vermittlungsgeb[üu]hr|geb[üu]hr f[üu]r die vermittlung", re.I)
RESIDENCY = re.compile(
    r"must (already )?(have|hold) (a )?(valid )?(eu |european )?(work permit|right to work)|"
    r"right to work in|eu citizens? only|eu/eea (citizen|national)|already (living|residing|based) in|"
    r"must (be|live) (a )?resident|valid residence permit|eu passport|"
    r"arbeitserlaubnis (erforderlich|vorhanden|nachweisen)|werkvergunning (is )?(vereist|verplicht)|"
    r"inwoner van", re.I)
LANG = re.compile(r"fließend(e|es)? deutsch|deutsch (auf )?(muttersprach|c1|c2)|"
                  r"vloeiend nederlands|moedertaal nederlands|fran[cç]ais courant|"
                  r"langue maternelle fran|biegła znajomość|madrelingua italian", re.I)
NEG = re.compile(
    r"\bno\W+(visa\W+|work permit\W+)?sponsor|\bno\W+(visa|work permit)\b|"
    r"without (a )?(visa|sponsorship)|(?:do|does|did) not (offer|provide|sponsor|arrange)|"
    r"(don't|doesn't|cannot|can't|unable to) (offer|provide|sponsor|arrange)|"
    r"not (able|in a position) to (offer|provide|sponsor)|"
    r"(visa|sponsorship|work permit)s? (is |are )?(not|un)\W?(available|provided|offered|possible|included)|"
    r"keine (visa|arbeitserlaubnis|sponsor)|geen (visum|werkvergunning)|"
    r"senza (visto|permesso|sponsor)|bez (wizy|sponsoringu)", re.I)
SPONSOR = re.compile(
    r"visa sponsor|sponsor(ship)? (a )?(work )?(visa|permit)|sponsor your (visa|work permit)|"
    r"work permit (provided|arranged|assistance|support|sponsorship)|"
    r"we (arrange|organi[sz]e|handle|obtain|apply for|provide|cover|pay for) .{0,35}(visa|work permit)|"
    r"visa (and|/) work permit|work visa provided|"
    r"permesso di lavoro (fornito|garantito|incluso|a carico)|"
    r"(ci occupiamo|ti aiutiamo|supportiamo|assistiamo|forniamo) .{0,30}(permesso|visto)|"
    r"nous (nous occupons|fournissons|prenons en charge) .{0,30}(permis|visa)|"
    r"zapewniamy .{0,25}(zezwolenie|wiz)", re.I)
ABROAD = re.compile(r"from abroad|outside (of )?(the )?(eu|europe)|non-eu|third[- ]country|"
                    r"international (candidates|applicants)|aus dem ausland|drittstaat|"
                    r"uit het buitenland|de l'étranger|z zagranicy|dall'estero", re.I)
HEDGE = re.compile(r"\b(may|might|could|can be|possible|possibly|potentially|if (needed|required|eligible|"
                   r"applicable|selected)|subject to|depending|case[- ]by[- ]case|in some cases|"
                   r"for some (roles|positions)|selected candidates|where possible|sometimes|"
                   r"può|potrebbe|possibile|eventuale|in alcuni casi|kann|könnte|möglich|eventuell|"
                   r"mogą|może|możliwe|peut|pourrait)\b", re.I)
REQ_PERMIT = re.compile(
    r"(work permit|permesso di lavoro|permis de travail|zezwolenie na pracę|arbeitserlaubnis|werkvergunning)"
    r"\W{0,3}(is |è |est |jest |ist )?(required|needed|necessary|mandatory|richiest[oa]|"
    r"necessari[oa]|obbligatori[oa]|requis|requise|obligatoire|wymagane|erforderlich|vereist|verplicht)|"
    r"(valid|existing|current|own) (work permit|permesso di lavoro|permis de travail)", re.I)
HOUSING = re.compile(r"accommodation|housing (provided|included)|free (housing|lodging)|unterkunft|"
                     r"wohnung gestellt|huisvesting|logement fourni|hébergement|zakwaterowanie|alloggio", re.I)

def clean_html(s):
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", str(s or " "))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def sentence_of(text, m):
    for sm in re.finditer(r"[^.!?\n]+[.!?]?", text):
        if sm.start() <= m.start() < sm.end():
            return re.sub(r"\s+", " ", sm.group(0)).strip()[:350]
    return m.group(0)

def classify(title, desc):
    text = f"{title}\n{desc}"
    if not JOB_WORDS.search(title):
        return "excluded", ["الوظيفة خارج مجالات البحث"], ""
    for rx, label in ((FEE, "الإعلان يذكر رسوم توظيف"), (RESIDENCY, "يشترط إقامة/حق عمل سابق"),
                      (LANG, "يشترط لغة محلية بطلاقة"), (NEG, "الإعلان ينفي توفير التأشيرة")):
        m = rx.search(text)
        if m:
            return "excluded", [f"{label}: «{m.group(0)}»"], sentence_of(text, m)
    req = REQ_PERMIT.search(text)
    sponsor_matches = list(SPONSOR.finditer(text))
    firm, hedged = [], []
    for m in sponsor_matches:
        sent = sentence_of(text, m)
        (hedged if HEDGE.search(sent) else firm).append(sent)
    abroad, housing = ABROAD.search(text), HOUSING.search(text)
    if req and not firm and not abroad:
        return "possible", ["الإعلان يذكر تصريح عمل مطلوبًا دون توضيح من يستخرجه"], sentence_of(text, req)
    evidence = []
    for x in (firm[:1] + hedged[:1] + ([sentence_of(text, abroad)] if abroad else []) +
              ([sentence_of(text, housing)] if housing else []) +
              ([sentence_of(text, req)] if req else [])):
        if x and x not in evidence: evidence.append(x)
    reasons = []
    if firm: reasons.append("ذكر صريح لتوفير/ترتيب التأشيرة أو تصريح العمل")
    if hedged: reasons.append("دعم التأشيرة بصياغة احتمالية")
    if abroad: reasons.append("ذكر المتقدمين من خارج الدولة")
    if housing: reasons.append("ذكر السكن")
    if req: reasons.append("ورد شرط تصريح عمل ويحتاج تفسيرًا")
    if firm and abroad and not req:
        return "confirmed", reasons, " ‖ ".join(evidence)
    if firm or hedged or abroad or housing or req:
        return "possible", reasons, " ‖ ".join(evidence)
    # Keep suitable jobs as leads; absence of sponsorship text is not proof of refusal.
    return "possible", ["إعلان مناسب للمهنة، لكن لم يذكر قبول متقدمين من الخارج أو دعم التأشيرة؛ يلزم سؤال صاحب العمل"], ""

def db_connect():
    os.makedirs("data", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad_id TEXT UNIQUE, url TEXT, norm_key TEXT UNIQUE,
        title TEXT, company TEXT, country TEXT, city TEXT, salary TEXT, posted TEXT, deadline TEXT,
        snippet TEXT, source TEXT, cls TEXT, reasons TEXT, first_seen TEXT, status TEXT,
        sent INTEGER DEFAULT 0, visa_evidence TEXT DEFAULT '')""")
    cols = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
    for name, typ in (("visa_evidence","TEXT DEFAULT ''"), ("send_attempts","INTEGER DEFAULT 0"),
                      ("last_send_error","TEXT DEFAULT ''")):
        if name not in cols: con.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")
    return con

def norm_key(company, title, country):
    s = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", f"{company}|{title}|{country}".lower())
    return hashlib.sha1(s.encode()).hexdigest()

def parse_country(raw):
    s = str(raw or "").strip()
    if len(s) == 2 and s.upper() in TARGET_COUNTRIES: return s.upper()
    return COUNTRY_ALIASES.get(s.lower(), "")

def safe_url(raw):
    try:
        u = urlsplit(str(raw or "").strip())
        if u.scheme not in ("http", "https") or not u.netloc: return ""
        return urlunsplit((u.scheme, u.netloc, u.path, u.query, ""))
    except Exception: return ""

def request_json(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def request_text(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def normalized(source, source_id, title, company, country, city, url, desc="", posted="", salary="غير مذكور", deadline="غير مذكور"):
    cc = parse_country(country) or str(country or "غير محدد")
    return {"source": source, "source_id": str(source_id or url or hashlib.md5((title+company).encode()).hexdigest()),
            "title": str(title or ""), "company": str(company or "غير مذكور"), "country": TARGET_COUNTRIES.get(cc, cc),
            "country_code": cc, "city": str(city or ""), "url": safe_url(url), "desc": clean_html(desc),
            "posted": str(posted or "")[:10], "salary": str(salary or "غير مذكور"), "deadline": str(deadline or "غير مذكور")}

def fetch_yubhub(errors):
    out=[]
    for q in QUERIES:
        try:
            data=request_json("https://api.yubhub.co/search", {"q":q,"perPage":50,"page":1})
            rows=data.get("jobs", data.get("data", [])) if isinstance(data,dict) else data
            for j in rows or []:
                loc=j.get("location") or {}
                country=j.get("country") or (loc.get("country") if isinstance(loc,dict) else "")
                out.append(normalized("YubHub", j.get("id"), j.get("title"), j.get("company") or j.get("company_name"),
                    country, loc.get("city") if isinstance(loc,dict) else loc, j.get("apply_url") or j.get("url"),
                    j.get("description"), j.get("date_posted") or j.get("first_seen"), j.get("salary_text") or j.get("salary")))
            time.sleep(.25)
        except Exception as e: errors.append(f"YubHub/{q}: {type(e).__name__}")
    return out

def fetch_devglobal(errors):
    out=[]
    for q in QUERIES:
        try:
            data=request_json("https://devglobaljobs.com/api/v1/jobs", {"limit":100,"search":q})
            rows=data.get("jobs", data.get("data", [])) if isinstance(data,dict) else data
            for j in rows or []:
                out.append(normalized("Dev Global Jobs", j.get("id"), j.get("title"), j.get("organisation") or j.get("company") or j.get("company_name"),
                    j.get("country_code") or j.get("country"), j.get("location") or j.get("city"), j.get("url") or j.get("apply_url"),
                    j.get("description") or j.get("summary"), j.get("posted_at") or j.get("posted_date"), j.get("salary")))
            time.sleep(.25)
        except Exception as e: errors.append(f"DevGlobal/{q}: {type(e).__name__}")
    return out

def fetch_arbeitnow(errors):
    out=[]
    try:
        data=request_json("https://www.arbeitnow.com/api/job-board-api")
        for j in data.get("data", []):
            title=j.get("title","")
            if JOB_WORDS.search(title):
                loc=j.get("location","")
                # Arbeitnow's feed is Germany-focused; mark country explicitly.
                out.append(normalized("Arbeitnow", j.get("slug"), title, j.get("company_name"), "DE", loc,
                    j.get("url"), j.get("description"), j.get("created_at")))
    except Exception as e: errors.append(f"Arbeitnow: {type(e).__name__}")
    return out

def fetch_remoteok(errors):
    out=[]
    try:
        data=request_json("https://remoteok.com/api")
        for j in data if isinstance(data,list) else []:
            title=j.get("position","")
            if JOB_WORDS.search(title):
                # Remote OK postings are remote; retain only suitable manual/ops leads.
                out.append(normalized("Remote OK", j.get("id"), title, j.get("company"), j.get("location") or "Remote",
                    j.get("location") or "عن بُعد", j.get("apply_url") or j.get("url"), j.get("description"),
                    j.get("date"), "غير مذكور"))
    except Exception as e: errors.append(f"Remote OK: {type(e).__name__}")
    return out


def fetch_jobicy(errors):
    out=[]
    for q in QUERIES[:10]:
        try:
            data=request_json("https://jobicy.com/api/jobs", {"count":100,"tag":q})
            for j in data.get("jobs",[]):
                title=j.get("jobTitle","")
                if JOB_WORDS.search(title):
                    out.append(normalized("Jobicy",j.get("id"),title,j.get("companyName"),
                        j.get("jobGeo") or "Remote",j.get("jobGeo") or "عن بُعد",j.get("url"),
                        j.get("jobDescription") or j.get("jobExcerpt"),j.get("pubDate"),
                        (str(j.get("salaryMin") or "")+" "+str(j.get("salaryCurrency") or "")).strip() or "غير مذكور"))
            time.sleep(.25)
        except Exception as e: errors.append(f"Jobicy/{q}: {type(e).__name__}")
    return out

def fetch_wwr(errors):
    out=[]
    try:
        root=ET.fromstring(request_text("https://weworkremotely.com/remote-jobs.rss"))
        for item in root.findall(".//item"):
            title=item.findtext("title","")
            if JOB_WORDS.search(title):
                out.append(normalized("We Work Remotely",item.findtext("guid") or item.findtext("link"),
                    title,"غير مذكور","Remote","عن بُعد",item.findtext("link"),
                    item.findtext("description"),item.findtext("pubDate")))
    except Exception as e: errors.append(f"We Work Remotely: {type(e).__name__}")
    return out

def fetch_adzuna(errors):
    app_id, app_key=os.environ.get("ADZUNA_APP_ID"),os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key): return []
    out=[]
    for cc,country in ADZUNA_COUNTRIES.items():
        for q in QUERIES:
            try:
                data=request_json(f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1",
                    {"app_id":app_id,"app_key":app_key,"results_per_page":50,"what":q,"max_days_old":7,"content-type":"application/json"})
                for j in data.get("results",[]):
                    out.append(normalized("Adzuna",f"{cc}:{j.get('id')}",j.get("title"),
                        (j.get("company") or {}).get("display_name"),cc,
                        (j.get("location") or {}).get("display_name"),j.get("redirect_url"),j.get("description"),
                        j.get("created"), salary_text(j,cc)))
            except Exception as e: errors.append(f"Adzuna/{country}/{q}: {type(e).__name__}")
            time.sleep(.25)
    return out

def salary_text(j, cc):
    lo,hi=j.get("salary_min"),j.get("salary_max")
    if not lo and not hi:return "غير مذكور"
    cur=CURRENCY.get(cc,"EUR")
    return f"{int(lo or 0):,}" + (f" - {int(hi):,}" if hi and hi!=lo else "") + f" {cur} (الفترة وصافي/إجمالي غير محددين)"

def collect(errors):
    out=[]
    sources=[("YubHub",fetch_yubhub),("Dev Global Jobs",fetch_devglobal),
             ("Arbeitnow",fetch_arbeitnow),("Remote OK",fetch_remoteok),
             ("Jobicy",fetch_jobicy),("We Work Remotely",fetch_wwr),("Adzuna",fetch_adzuna)]
    for name,fn in sources:
        before=len(out)
        try:
            out.extend(fn(errors))
            print(f"SOURCE {name}: {len(out)-before} raw listings")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
    return out

def process(con, raw):
    now=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    new=[]
    for j in raw:
        title=j["title"]
        if not JOB_WORDS.search(title): continue
        company=j["company"]; country=j["country"]
        nk=norm_key(company,title,country)
        ad_id=f'{j["source"].lower().replace(" ","_")}:{j["source_id"]}'
        if con.execute("SELECT 1 FROM jobs WHERE ad_id=? OR norm_key=?",(ad_id,nk)).fetchone(): continue
        cls,reasons,evidence=classify(title,j["desc"])
        row={"ad_id":ad_id,"url":j["url"],"norm_key":nk,"title":title,"company":company,"country":country,
             "city":j["city"],"salary":j["salary"],"posted":j["posted"],"deadline":j["deadline"],
             "snippet":j["desc"][:500],"source":j["source"],"cls":cls,"reasons":" | ".join(reasons),
             "visa_evidence":evidence,"first_seen":now,"status":"excluded" if cls=="excluded" else "new","sent":0}
        con.execute(f"INSERT OR IGNORE INTO jobs({','.join(row)}) VALUES({','.join('?'*len(row))})",list(row.values()))
        if con.execute("SELECT changes()").fetchone()[0]: new.append(row)
    con.commit()
    return new

def telegram(message):
    if TEST:
        print("-----\n"+message); return True
    tok,chat=os.environ.get("TELEGRAM_BOT_TOKEN"),os.environ.get("TELEGRAM_CHAT_ID")
    if not(tok and chat): print("Telegram secrets missing"); return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
            data={"chat_id":chat,"text":message[:4000],"disable_web_page_preview":"true"},timeout=30)
        r.raise_for_status()
        return bool(r.json().get("ok"))
    except Exception as e:
        print(f"Telegram error: {type(e).__name__}: {e}")
        return False

def card(r):
    head={"confirmed":"🟢 استقدام مؤكد بدليل من نص الإعلان","possible":"🟡 فرصة مناسبة تحتاج سؤال صاحب العمل","excluded":"⚪ مستبعد"}[r["cls"]]
    return (f"{head}\n\nالوظيفة: {r['title']}\nالشركة: {r['company']}\nالدولة/المدينة: {r['country']} - {r['city']}\n"
            f"الراتب: {r['salary']}\nتاريخ النشر: {r['posted'] or 'غير مذكور'}\n"
            f"دليل التأشيرة: {r['reasons']}\nالنص الدال: {r['visa_evidence'] or 'لم يذكر الإعلان دعم التأشيرة'}\n"
            f"المصدر: {r['source']}\nرابط الإعلان: {r['url']}\n"
            "ملاحظة: قبول التقديم من مصر غير مضمون ما لم يذكره الإعلان؛ اسأل صاحب العمل قبل إرسال مستندات. لا تدفع رسومًا.")

def build_dashboard(con, source_stats=None):
    path="data/test_dashboard.html" if TEST else "docs/index.html"
    con.row_factory=sqlite3.Row
    rows=[dict(x) for x in con.execute("SELECT * FROM jobs ORDER BY first_seen DESC")]
    con.row_factory=None
    data=json.dumps(rows,ensure_ascii=False).replace("</","<\\\\/")
    safe=json.dumps(source_stats or {},ensure_ascii=False)
    template=DASH.replace("__DATA__",data).replace("__SOURCES__",safe)
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,"w",encoding="utf-8") as f:f.write(template)

DASH="""<!doctype html><html 

#!/usr/bin/env python3
"""تنبيهات وظائف يومية - بحث وتنبيه فقط. لا يقدّم على أي وظيفة ولا يرسل مستندات."""
import os, sys, re, json, sqlite3, hashlib, datetime, time
from urllib.parse import urlsplit

import requests

TEST = "--test" in sys.argv
DB_PATH = "data/test.db" if TEST else "data/jobs.db"
MAX_CARDS = 15  # أقصى عدد بطاقات في اليوم

# Adzuna يغطي من دولك المطلوبة إيطاليا وبولندا فقط. باقي الدول تحتاج مصادر تانية.
COUNTRIES = {"it": "إيطاليا", "pl": "بولندا"}
CURRENCY = {"pl": "PLN"}

EN = ["warehouse worker", "production worker", "packer", "general worker", "cleaner",
      "warehouse relocation accommodation"]
LOCAL = {
    "pl": ["pracownik magazynowy", "pracownik produkcji"],
    "it": ["magazziniere", "operaio generico"],
}

JOB_WORDS = re.compile(r"warehouse|lager|magazijn|magasin|magazzin|magazyn|production|produktion|productie|"
    r"produkc|factory|fabrik|packer|packing|pack|verpack|picker|kommission|préparateur|general worker|helfer|"
    r"helper|cleaner|reinigung|schoonmaak|nettoyage|sprz[aą]t|pulizie|kitchen|küche|farm|agricult|landwirt|"
    r"harvest|construction|housekeeping|manutention|operaio|operai|loader|unloading|logisti|stock|storekeeper|"
    r"material|opérateur|medewerker|mitarbeiter|pracownik", re.I)

FEE = re.compile(r"registration fee|placement fee|processing fee|pay (a|the) fee|vermittlungsgeb[üu]hr|"
    r"geb[üu]hr f[üu]r die vermittlung", re.I)
RESIDENCY = re.compile(r"must (already )?(have|hold) (a )?(valid )?(eu |european )?(work permit|right to work)|"
    r"right to work in|eu citizens? only|eu/eea (citizen|national)|already (living|residing|based) in|"
    r"must (be|live) (a )?resident|valid residence permit|eu passport|"
    r"arbeitserlaubnis (erforderlich|vorhanden|nachweisen)|wohnsitz in (deutschland|österreich) (erforderlich|vorausgesetzt)|"
    r"werkvergunning (is )?(vereist|verplicht)|inwoner van", re.I)
LANG = re.compile(r"fließend(e|es)? deutsch|deutsch (auf )?(muttersprach|c1|c2)|vloeiend nederlands|"
    r"moedertaal nederlands|fran[cç]ais courant|langue maternelle fran|biegła znajomość|madrelingua italian", re.I)

SPONSOR = re.compile(
    r"visa sponsor|sponsor(ship)? (a )?(work )?(visa|permit)|sponsor your (visa|work permit)|"
    r"work permit (provided|arranged|assistance|support|sponsorship)|"
    r"we (arrange|organi[sz]e|handle|obtain|apply for|provide|cover|pay for) .{0,25}(visa|work permit)|"
    r"visumhilfe|wir (übernehmen|kümmern uns um) .{0,30}(visum|arbeitserlaubnis)|arbeitserlaubnis (wird|übernehmen)|"
    r"werkvergunning (regelen|aanvragen|verzorgen)|wij (regelen|verzorgen) .{0,30}(visum|werkvergunning)|"
    r"permesso di lavoro (fornito|garantito|incluso|a carico)|"
    r"(ci occupiamo|ti aiutiamo|supportiamo|assistiamo|forniamo) .{0,30}(permesso|visto)|"
    r"nous (nous occupons|fournissons|prenons en charge) .{0,30}(permis|visa)|zapewniamy .{0,25}(zezwolenie|wiz)",
    re.I)
# ملاحظة: كلمة "work permit" أو "permesso di lavoro" لوحدها مش دليل إن صاحب العمل بيوفرها.
ABROAD = re.compile(r"from abroad|outside (of )?(the )?(eu|europe)|non-eu|third[- ]country|international (candidates|applicants)|"
    r"aus dem ausland|drittstaat|uit het buitenland|de l'étranger|z zagranicy|dall'estero", re.I)
RELOC = re.compile(r"relocation|relocate|worldwide", re.I)  # إشارة ضعيفة: ممكن تكون نقل داخلي
HOUSING = re.compile(r"accommodation|housing (provided|included)|free (housing|lodging)|unterkunft|wohnung gestellt|"
    r"huisvesting|logement fourni|hébergement|zakwaterowanie|alloggio", re.I)
# صياغة احتمالية: لو الجملة فيها كده، التأشيرة مش "مؤكدة"
HEDGE = re.compile(r"\b(may|might|could|can be|possible|possibly|potentially|if (needed|required|eligible|applicable|selected)|"
    r"subject to|depending|case[- ]by[- ]case|in some cases|for some (roles|positions)|selected candidates|where possible|"
    r"sometimes|eventually|può|potrebbe|possibile|eventuale|in alcuni casi|kann|könnte|möglich|eventuell|"
    r"mogą|może|możliwe|w niektórych|peut|pourrait)\b", re.I)
# "تصريح العمل مطلوب" = لازم يكون معاك، مش إن صاحب العمل بيوفره
REQ_PERMIT = re.compile(
    r"(work permit|permesso di lavoro|permis de travail|zezwolenie na pracę|arbeitserlaubnis|werkvergunning)\W{0,3}"
    r"(is |è |est |jest |ist )?(required|needed|necessary|mandatory|richiest[oa]|necessari[oa]|obbligatori[oa]|"
    r"requis|requise|obligatoire|wymagane|erforderlich|vereist|verplicht)|"
    r"(valid|existing|current|own) (work permit|permesso di lavoro|permis de travail)", re.I)
NEG = re.compile(
    r"\bno\W+(visa\W+|work permit\W+)?sponsor|\bno\W+(visa|work permit)\b|without (a )?(visa|sponsorship)|"
    r"(do|does|did) not (offer|provide|sponsor|arrange)|(don't|doesn't|cannot|can't|unable to) (offer|provide|sponsor|arrange)|"
    r"not (able|in a position) to (offer|provide|sponsor)|"
    r"(visa|sponsorship|work permit)s? (is |are )?(not|un)\W?(available|provided|offered|possible|included)|"
    r"(not|never) require(s|d)? (visa |work permit )?sponsorship|"
    r"keine (visa|arbeitserlaubnis|sponsor)|geen (visum|werkvergunning)|senza (visto|permesso|sponsor)|bez (wizy|sponsoringu)",
    re.I)


def sentence_of(text, m):
    """الجملة الأصلية الكاملة اللي فيها الكلمة المطابقة."""
    for sm in re.finditer(r"[^.!?\n]+[.!?]?", text):
        if sm.start() <= m.start() < sm.end():
            return re.sub(r"\s+", " ", sm.group(0)).strip()[:300]
    return m.group(0)


def classify(title, desc):
    """يرجّع (التصنيف، الأسباب، الجملة الأصلية المستند إليها)."""
    text = f"{title} \n {desc}"
    if not JOB_WORDS.search(title):
        return "excluded", ["الوظيفة خارج مجالات بحثك"], ""
    for rx, label in ((FEE, "الإعلان يذكر رسوم تسجيل/توظيف (احتمال نصب)"),
                      (RESIDENCY, "يشترط إقامة/تصريح عمل سابق"),
                      (LANG, "يشترط لغة محلية بطلاقة"),
                      (NEG, "الإعلان ينفي توفير تأشيرة/تصريح")):
        m = rx.search(text)
        if m:
            return "excluded", [f"{label}: «{m.group(0)}»"], sentence_of(text, m)
    firm, hedged, first = [], [], None
    for m in SPONSOR.finditer(text):
        first = first or m
        sent = sentence_of(text, m)
        (hedged if HEDGE.search(sent) else firm).append(sent)
    a, h, rl, req = ABROAD.search(text), HOUSING.search(text), RELOC.search(text), REQ_PERMIT.search(text)
    if req and not firm:
        return "excluded", [f"يشترط تصريح عمل موجود مسبقًا: «{req.group(0)}»"], sentence_of(text, req)
    if not (first or a or h or rl):
        return "excluded", ["لا توجد أي إشارة لقبول المتقدمين من خارج الدولة"], ""
    sents = []
    for x in firm[:1] + hedged[:1] + [sentence_of(text, m) for m in (a, rl, h, req) if m]:
        if x not in sents:
            sents.append(x)
    reasons = [m.group(0) for m in (first, a, rl, h) if m]
    if hedged and not firm:
        reasons.append("صياغة التأشيرة احتمالية (may/possible...)")
    if req:
        reasons.append("الإعلان يذكر تصريح عمل مطلوب، فالمعنى غير واضح")
    cls = "confirmed" if (firm and a and not req) else "possible"
    return cls, reasons, " ‖ ".join(sents)


def db_connect():
    os.makedirs("data", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad_id TEXT UNIQUE, url TEXT, norm_key TEXT UNIQUE,
        title TEXT, company TEXT, country TEXT, city TEXT, salary TEXT, posted TEXT, deadline TEXT,
        snippet TEXT, source TEXT, cls TEXT, reasons TEXT, first_seen TEXT, status TEXT, sent INTEGER DEFAULT 0)""")
    if "visa_evidence" not in [r[1] for r in con.execute("PRAGMA table_info(jobs)")]:
        con.execute("ALTER TABLE jobs ADD COLUMN visa_evidence TEXT DEFAULT ''")
    return con


def norm_key(company, title, country):
    s = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", f"{company}|{title}|{country}".lower())
    return hashlib.sha1(s.encode()).hexdigest()


def salary_text(j, cc):
    if str(j.get("salary_is_predicted")) == "1":
        return "غير مذكور"
    lo, hi = j.get("salary_min"), j.get("salary_max")
    if not lo and not hi:
        return "غير مذكور"
    cur = CURRENCY.get(cc, "EUR")
    rng = f"{int(lo):,}" if lo and (not hi or int(lo) == int(hi)) else f"{int(lo or 0):,} - {int(hi or 0):,}"
    return f"{rng} {cur} (غالبًا سنوي، صافي/إجمالي غير محدد)"


def fetch_adzuna(cc, what, app_id, app_key):
    url = f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1"
    r = requests.get(url, params={"app_id": app_id, "app_key": app_key, "results_per_page": 50,
                                  "what": what, "max_days_old": 7, "content-type": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json().get("results", [])


def collect(errors):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        errors.append("مفاتيح Adzuna غير موجودة")
        return []
    out = []
    for cc in COUNTRIES:
        for q in EN + LOCAL.get(cc, []):
            try:
                for j in fetch_adzuna(cc, q, app_id, app_key):
                    out.append((cc, j))
            except Exception as e:  # لا نخفي الأخطاء: تظهر في تقرير اليوم
                errors.append(f"{COUNTRIES[cc]} ({q}): {type(e).__name__}")
            time.sleep(0.5)
    return out


SAMPLE = [
    ("de", {"id": "t1", "title": "Warehouse Worker (m/w/d)", "company": {"display_name": "Test Logistik GmbH"},
            "location": {"display_name": "Hamburg"}, "redirect_url": "https://example.com/ad/1?x=1",
            "created": "2026-11-16T08:00:00Z", "salary_min": 30000, "salary_max": 32000,
            "description": "We offer visa sponsorship and work permit assistance for candidates from abroad. Accommodation provided."}),
    ("nl", {"id": "t2", "title": "Production Worker", "company": {"display_name": "Voorbeeld BV"},
            "location": {"display_name": "Venlo"}, "redirect_url": "https://example.com/ad/2",
            "created": "2026-11-16T08:00:00Z", "description": "Housing included, shifts. Relocation support."}),
    ("fr", {"id": "t3", "title": "Warehouse Operative", "company": {"display_name": "Exemple SA"},
            "location": {"display_name": "Lyon"}, "redirect_url": "https://example.com/ad/3",
            "created": "2026-11-16T08:00:00Z", "description": "You must already have the right to work in France."}),
    ("pl", {"id": "t4", "title": "Packer", "company": {"display_name": "Przyklad"},
            "location": {"display_name": "Łódź"}, "redirect_url": "https://example.com/ad/4",
            "created": "2026-11-16T08:00:00Z", "description": "Registration fee 200 EUR required."}),
    ("it", {"id": "t6", "title": "Warehouse Operator", "company": {"display_name": "Nega Srl"},
            "location": {"display_name": "Roma"}, "redirect_url": "javascript://x/%0Aalert(1)",
            "created": "2026-11-16T08:00:00Z", "description": "Please note: no visa sponsorship available for this role."}),
    ("pl", {"id": "t7", "title": "Storekeeper <b>x</b>", "company": {"display_name": "Reloc Sp."},
            "location": {"display_name": "Gdańsk"}, "redirect_url": "https://example.com/ad/7",
            "created": "2026-11-16T08:00:00Z", "description": "Visa sponsorship offered. Relocation within our sites possible."}),
    ("it", {"id": "t8", "title": "Warehouse Worker", "company": {"display_name": "May Srl"},
            "location": {"display_name": "Torino"}, "redirect_url": "https://example.com/ad/8",
            "created": "2026-11-16T08:00:00Z", "description": "Visa sponsorship may be available for candidates from abroad."}),
    ("it", {"id": "t5", "title": "Magazziniere", "company": {"display_name": "Esempio Srl"},
            "location": {"display_name": "Milano"}, "redirect_url": "https://example.com/ad/5",
            "created": "2026-11-16T08:00:00Z", "description": "Lavoro in magazzino, turni."}),
]


def process(con, raw):
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    new = []
    for cc, j in raw:
        company = (j.get("company") or {}).get("display_name") or "غير مذكور"
        title = j.get("title") or ""
        ad_id = f"adzuna:{cc}:{j.get('id')}"
        nk = norm_key(company, title, cc)
        if con.execute("SELECT 1 FROM jobs WHERE ad_id=? OR norm_key=?", (ad_id, nk)).fetchone():
            continue  # سبق ظهوره (حتى لو من رابط/موقع مختلف)
        desc = re.sub(r"<[^>]+>", " ", j.get("description") or "")
        cls, reasons, evidence = classify(title, desc)
        u = urlsplit(j.get("redirect_url") or "")
        url = f"{u.scheme}://{u.netloc}{u.path}" if (u.netloc and u.scheme in ("http", "https")) else ""
        row = dict(ad_id=ad_id, url=url, norm_key=nk, title=title, company=company, country=COUNTRIES.get(cc, cc),
                   city=(j.get("location") or {}).get("display_name") or "", salary=salary_text(j, cc),
                   posted=(j.get("created") or "")[:10], deadline="غير مذكور", snippet=desc.strip()[:400],
                   source="Adzuna (يحوّل للإعلان الأصلي)", cls=cls, reasons=" | ".join(reasons), visa_evidence=evidence,
                   first_seen=now, status="excluded" if cls == "excluded" else "new", sent=0)
        con.execute(f"INSERT INTO jobs({','.join(row)}) VALUES({','.join('?'*len(row))})", list(row.values()))
        new.append(row)
    con.commit()
    return new


def card(r):
    visa = {"confirmed": "ذُكر في الإعلان ما يدل على تصريح عمل/تأشيرة وقبول متقدمين من الخارج",
            "possible": "غير مؤكدة، لازم تسأل صاحب العمل"}[r["cls"]]
    head = {"confirmed": "🟢 استقدام مؤكد بدليل من نص الإعلان", "possible": "🟡 محتملة وتحتاج تأكيد"}[r["cls"]]
    housing = "ذُكر سكن في الإعلان" if HOUSING.search(r["snippet"]) else "غير مذكور"
    fit = ("مناسبة لخبرتك في المخازن" if re.search(r"warehouse|lager|magazijn|magasin|magazzin|magazyn|stock",
           r["title"], re.I) else "مناسبة لأعمال الإنتاج/البدنية")
    return (f"{head}\n\nاسم الوظيفة: {r['title']}\nالشركة: {r['company']}\n"
            f"الدولة والمدينة: {r['country']} - {r['city']}\nالراتب: {r['salary']}\n"
            f"تاريخ النشر: {r['posted'] or 'غير مذكور'}\nآخر موعد: {r['deadline']}\n"
            f"متطلبات الخبرة واللغة: غير مذكورة في البيانات (راجع الإعلان الأصلي)\n"
            f"السكن والمميزات: {housing}\nإمكانية التقديم من مصر: {'الإعلان ذكر متقدمين من الخارج، لكن قبول مصريين تحديدًا لازم تتأكد منه من صاحب العمل' if r['cls']=='confirmed' else 'غير مؤكدة'}\n"
            f"حالة التأشيرة: {visa}\nدليل من النص: {r['reasons']}\nالجملة الأصلية: {r['visa_evidence'] or '—'}\nمصدر الإعلان: {r['source']}\n"
            f"رابط التقديم: {r['url']}\n\nالتقييم: {fit}. البيانات مقتطعة من Adzuna وغير مؤكدة، "
            f"افتح الإعلان وتأكد من شروطه قبل أي خطوة. لا تدفع أي رسوم لأي جهة.")


def telegram(text):
    if TEST:
        print("-----\n" + text)
        return True
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        print("Telegram secrets missing")
        return False
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}, timeout=30)
    return r.ok


def build_dashboard(con):
    out_path = "data/test_dashboard.html" if TEST else "docs/index.html"
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM jobs ORDER BY first_seen DESC")]
    con.row_factory = None
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    html = DASH.replace("__DATA__", data)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


DASH = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>لوحة الوظائف</title>
<style>body{font-family:system-ui,Tahoma,sans-serif;margin:0;padding:12px;background:#f6f7f9;color:#222}
.st{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.b{background:#fff;border-radius:10px;padding:10px;text-align:center}
.b b{display:block;font-size:22px}input,select{width:100%;padding:8px;margin:4px 0;border:1px solid #ccc;border-radius:8px}
.j{background:#fff;border-radius:10px;padding:10px;margin:8px 0}.t{font-weight:700}.m{font-size:13px;color:#555}
.c{display:inline-block;padding:1px 8px;border-radius:8px;font-size:12px}.confirmed{background:#cdf0d4}.possible{background:#fbefb5}.excluded{background:#eee}
a{color:#0a58ca}</style></head><body><h2>لوحة الوظائف</h2><div class="st" id="st"></div>
<h3>أسباب الاستبعاد</h3><div id="rs" class="m"></div><h3>السجل</h3>
<input id="q" placeholder="بحث بالمهنة أو الشركة"><select id="co"><option value="">كل الدول</option></select>
<select id="cl"><option value="">كل التصنيفات</option><option value="confirmed">مؤكد</option><option value="possible">محتمل</option><option value="excluded">مستبعد</option></select>
<div id="l"></div><script>const D=__DATA__;const $=i=>document.getElementById(i);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safe=u=>(u.startsWith('http://')||u.startsWith('https://'))?esc(u):'';
const n=c=>D.filter(x=>x.cls==c).length;
$('st').innerHTML=[['وجدنا',D.length],['مؤكد',n('confirmed')],['يحتاج تأكيد',n('possible')],['مستبعد',n('excluded')]].map(a=>`<div class=b><b>${a[1]}</b>${a[0]}</div>`).join('');
const R={};D.filter(x=>x.cls=='excluded').forEach(x=>{const k=x.reasons.replace(/«.*?»/g,'').trim();R[k]=(R[k]||0)+1});
$('rs').innerHTML=Object.entries(R).map(e=>`${esc(e[0])}: ${e[1]}`).join('<br>')||'لا يوجد';
[...new Set(D.map(x=>x.country))].forEach(c=>$('co').add(new Option(c,c)));
const lab={confirmed:'مؤكد',possible:'محتمل',excluded:'مستبعد'};
function r(){const q=$('q').value.toLowerCase(),co=$('co').value,cl=$('cl').value;
$('l').innerHTML=D.filter(x=>(!co||x.country==co)&&(!cl||x.cls==cl)&&(!q||(x.title+x.company).toLowerCase().includes(q))).slice(0,300).map(x=>
`<div class=j><span class="c ${x.cls}">${lab[x.cls]}</span><div class=t>${esc(x.title)}</div><div class=m>${esc(x.company)} · ${esc(x.country)} ${esc(x.city)} · ${esc(x.posted)}<br>الراتب: ${esc(x.salary)}<br>${esc(x.reasons)}<br>${esc(x.visa_evidence||'')}</div>${safe(x.url||'')?`<a href="${safe(x.url||'')}" target=_blank rel=noopener>الإعلان</a>`:''}</div>`).join('')}
['q','co','cl'].forEach(i=>$(i).addEventListener('input',r));r();</script></body></html>"""


def main():
    errors = []
    con = db_connect()
    raw = [(cc, j) for cc, j in SAMPLE] if TEST else collect(errors)
    new = process(con, raw)
    good = sorted([r for r in new if r["cls"] != "excluded"], key=lambda r: r["cls"] != "confirmed")
    excl = len(new) - len(good)
    today = datetime.date.today().isoformat()
    if good:
        c, p = sum(r["cls"] == "confirmed" for r in good), sum(r["cls"] == "possible" for r in good)
        head = f"تقرير الوظائف {today}\nجديد: {len(good)} (مؤكد: {c}، محتمل: {p}) | مستبعد: {excl}"
    else:
        head = f"تقرير الوظائف {today}\nلم يتم العثور على فرص جديدة مناسبة اليوم. (مستبعد: {excl})"
    head += "\nتغطية المصدر: Adzuna فقط (" + "، ".join(COUNTRIES.values()) + "). لسه مش مغطّى: الإمارات، السعودية، صربيا، ألبانيا، اليونان."
    if errors:
        head += f"\n⚠️ حصلت {len(errors)} أخطاء في الجلب، مثال: {errors[0]}"
    if len(good) > MAX_CARDS:
        head += f"\nهتوصلك أول {MAX_CARDS} بطاقة، والباقي في اللوحة."
    telegram(head)
    for r in good[:MAX_CARDS]:
        if telegram(card(r)):
            con.execute("UPDATE jobs SET sent=1, status='sent' WHERE ad_id=?", (r["ad_id"],))
        time.sleep(1)
    con.commit()
    build_dashboard(con)
    con.close()


if __name__ == "__main__":
    main()

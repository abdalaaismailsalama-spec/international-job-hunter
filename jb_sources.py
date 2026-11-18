"""مصادر الوظايف. كل مصدر جديد يتضاف هنا بعد ما نتأكد منه."""
import os, time, requests
from jb_config import *
from jb_rules import clean_html, safe_url


def normalized(source, source_id, title, company, country_code, city, url, desc="", posted="",
               salary="غير مذكور", deadline="غير مذكور"):
    return {"source": str(source), "source_id": str(source_id), "title": str(title or ""),
            "company": str(company or "غير مذكور"), "country_code": str(country_code or "").upper(),
            "city": str(city or ""), "url": safe_url(url), "desc": clean_html(desc),
            "posted": str(posted or "")[:10], "salary": str(salary or "غير مذكور"),
            "deadline": str(deadline or "غير مذكور")}


def salary_text(j, cc):
    if str(j.get("salary_is_predicted")) == "1":
        return "غير مذكور"
    lo, hi = j.get("salary_min"), j.get("salary_max")
    if not lo and not hi:
        return "غير مذكور"
    cur = CURRENCY.get(cc, "EUR")
    rng = f"{int(lo):,}" if lo and (not hi or int(lo) == int(hi)) else f"{int(lo or 0):,} - {int(hi or 0):,}"
    return rng + " " + cur + " (غالبًا سنوي، صافي/إجمالي غير محدد)"


def request_json(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_adzuna(errors):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        errors.append("مفاتيح Adzuna غير موجودة")
        return []
    out = []
    for cc, cname in ADZUNA_COUNTRIES.items():
        for q in EN + LOCAL.get(cc, []):
            try:
                data = request_json("https://api.adzuna.com/v1/api/jobs/" + cc + "/search/1",
                                    {"app_id": app_id, "app_key": app_key, "results_per_page": 50,
                                     "what": q, "max_days_old": 7, "content-type": "application/json"})
                for j in data.get("results", []):
                    if not isinstance(j, dict):
                        continue
                    out.append(normalized("Adzuna", cc + ":" + str(j.get("id")), j.get("title"),
                                          (j.get("company") or {}).get("display_name"), cc,
                                          (j.get("location") or {}).get("display_name"),
                                          j.get("redirect_url"), j.get("description"),
                                          j.get("created"), salary_text(j, cc)))
            except Exception as e:  # لا نخفي الأخطاء: بتظهر في تقرير اليوم
                errors.append(cname + " (" + q + "): " + type(e).__name__)
            time.sleep(0.5)
    return out


# كل مصدر جديد يتضاف هنا بعد ما نتأكد منه (اسم، دالة بترجّع قايمة normalized)
SOURCES = [("Adzuna", fetch_adzuna)]


def collect(errors):
    out = []
    for name, fn in SOURCES:
        try:
            got = fn(errors)
        except Exception as e:
            errors.append(name + ": " + type(e).__name__)
            got = []
        print("SOURCE " + name + ": " + str(len(got)) + " raw listings")
        out.extend(got)
    return out

SAMPLE = [normalized("Adzuna", r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in SAMPLE_ROWS]

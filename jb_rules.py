"""تنضيف النصوص وتصنيف الإعلان (مؤكد / محتمل / مستبعد)."""
import re, html, hashlib
from urllib.parse import urlsplit, urlunsplit
from jb_config import NL, BS
from jb_patterns import *


def clean_html(s):
    s = re.sub(r"(?is)<(script|style).*?>.*?</" + "(script|style)>", " ", str(s or " "))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def safe_url(raw):
    try:
        u = urlsplit(str(raw or "").strip())
        if u.scheme not in ("http", "https") or not u.netloc:
            return ""
        return urlunsplit((u.scheme, u.netloc, u.path, "", ""))
    except Exception:
        return ""


def sentence_of(text, m):
    """الجملة الأصلية الكاملة اللي فيها الكلمة المطابقة."""
    for sm in SENT_RE.finditer(text):
        if sm.start() <= m.start() < sm.end():
            return re.sub(r"\s+", " ", sm.group(0)).strip()[:300]
    return m.group(0)


def classify(title, desc):
    """يرجّع (التصنيف، الأسباب، الجملة الأصلية المستند إليها)."""
    text = title + NL + desc
    if not JOB_WORDS.search(title):
        return "excluded", ["الوظيفة خارج مجالات بحثك"], ""
    for rx, label in ((FEE, "الإعلان يذكر رسوم تسجيل/توظيف (احتمال نصب)"),
                      (RESIDENCY, "يشترط إقامة/تصريح عمل سابق"),
                      (LANG, "يشترط لغة محلية بطلاقة"),
                      (NEG, "الإعلان ينفي توفير تأشيرة/تصريح")):
        m = rx.search(text)
        if m:
            return "excluded", [label + ": «" + m.group(0) + "»"], sentence_of(text, m)
    firm, hedged, first = [], [], None
    for m in SPONSOR.finditer(text):
        first = first or m
        sent = sentence_of(text, m)
        (hedged if HEDGE.search(sent) else firm).append(sent)
    a, h, rl, req = ABROAD.search(text), HOUSING.search(text), RELOC.search(text), REQ_PERMIT.search(text)
    if req and not firm:
        return "excluded", ["يشترط تصريح عمل موجود مسبقًا: «" + req.group(0) + "»"], sentence_of(text, req)
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


def norm_key(company, title, country):
    s = re.sub(r"[^a-z0-9" + BS + "u0600-" + BS + "u06ff]+", "", (company + "|" + title + "|" + country).lower())
    return hashlib.sha1(s.encode()).hexdigest()

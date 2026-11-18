"""شكل بطاقة تليجرام والإرسال."""
import os, re, requests
from jb_config import NL, TEST
from jb_patterns import HOUSING


def card(r):
    cls = r.get("cls")
    visa = {"confirmed": "ذُكر في الإعلان ما يدل على تصريح عمل/تأشيرة وقبول متقدمين من الخارج",
            "possible": "غير مؤكدة، لازم تسأل صاحب العمل"}.get(cls, "غير مؤكدة")
    head = {"confirmed": "🟢 استقدام مؤكد بدليل من نص الإعلان",
            "possible": "🟡 محتملة وتحتاج تأكيد"}.get(cls, "🟡 محتملة وتحتاج تأكيد")
    housing = "ذُكر سكن في الإعلان" if HOUSING.search(r.get("snippet") or "") else "غير مذكور"
    fit = ("مناسبة لخبرتك في المخازن"
           if re.search(r"warehouse|lager|magazijn|magasin|magazzin|magazyn|stock", r.get("title") or "", re.I)
           else "مناسبة لأعمال الإنتاج/البدنية")
    egypt = ("الإعلان ذكر متقدمين من الخارج، لكن قبول مصريين تحديدًا لازم تتأكد منه من صاحب العمل"
             if cls == "confirmed" else "غير مؤكدة")
    lines = [head, "",
             "اسم الوظيفة: " + str(r.get("title")),
             "الشركة: " + str(r.get("company")),
             "الدولة والمدينة: " + str(r.get("country")) + " - " + str(r.get("city") or ""),
             "الراتب: " + str(r.get("salary") or "غير مذكور"),
             "تاريخ النشر: " + str(r.get("posted") or "غير مذكور"),
             "آخر موعد: " + str(r.get("deadline") or "غير مذكور"),
             "متطلبات الخبرة واللغة: غير مذكورة في البيانات (راجع الإعلان الأصلي)",
             "السكن والمميزات: " + housing,
             "إمكانية التقديم من مصر: " + egypt,
             "حالة التأشيرة: " + visa,
             "دليل من النص: " + str(r.get("reasons") or ""),
             "الجملة الأصلية: " + str(r.get("visa_evidence") or "—"),
             "مصدر الإعلان: " + str(r.get("source")),
             "رابط التقديم: " + str(r.get("url") or "غير متوفر"), "",
             "التقييم: " + fit + ". البيانات مقتطعة وغير مؤكدة، افتح الإعلان وتأكد من شروطه قبل أي خطوة. "
             "لا تدفع أي رسوم لأي جهة."]
    return NL.join(lines)[:4000]


def telegram(text):
    """يرجّع (نجح؟، سبب الفشل)."""
    if TEST:
        print("-----" + NL + text)
        return True, ""
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return False, "أسرار تليجرام ناقصة (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)"
    try:
        r = requests.post("https://api.telegram.org/bot" + tok + "/sendMessage",
                          data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"},
                          timeout=30)
    except Exception as e:
        return False, type(e).__name__
    if r.ok:
        return True, ""
    try:
        desc = r.json().get("description", "")
    except Exception:
        desc = ""
    return False, ("HTTP " + str(r.status_code) + " " + desc)[:200]

#!/usr/bin/env python3
"""تنبيهات وظائف دولية - بحث وتنبيه فقط. لا يقدّم على أي وظيفة ولا يرسل مستندات."""
import sys, time, datetime
from jb_config import *
from jb_store import db_connect, process, pending_rows
from jb_sources import collect, SAMPLE
from jb_dashboard import build_dashboard
from jb_report import card, telegram


def main():
    errors = []
    con = db_connect()
    items = SAMPLE if TEST else collect(errors)
    new = process(con, items)
    good_new = [r for r in new if r["cls"] != "excluded"]
    excl = len(new) - len(good_new)
    pending = pending_rows(con)
    today = datetime.date.today().isoformat()
    lines = ["تقرير الوظائف " + today]
    if errors and not items:
        lines.append("⚠️ فشل جلب الوظايف من كل المصادر النهاردة. ده مش معناه إن مفيش وظايف.")
    elif good_new or pending:
        c = sum(r["cls"] == "confirmed" for r in good_new)
        p = sum(r["cls"] == "possible" for r in good_new)
        lines.append("جديد: " + str(len(good_new)) + " (مؤكد: " + str(c) + "، محتمل: " + str(p) + ") | في الانتظار للإرسال: "
                     + str(len(pending)) + " | مستبعد: " + str(excl))
    else:
        lines.append("لم يتم العثور على فرص جديدة مناسبة اليوم. (مستبعد: " + str(excl) + ")")
    lines.append("تغطية المصدر: Adzuna فقط (" + "، ".join(ADZUNA_COUNTRIES.values()) + "). لسه مش مغطّى: " + NOT_COVERED + ".")
    if errors:
        lines.append("⚠️ حصلت " + str(len(errors)) + " أخطاء في الجلب، مثال: " + errors[0])
    if len(pending) > MAX_CARDS:
        lines.append("هتوصلك أول " + str(MAX_CARDS) + " بطاقة، والباقي في الأيام الجاية (وكلهم في اللوحة).")
    ok, err = telegram(NL.join(lines))
    if not ok:
        con.commit()
        con.close()
        print("TELEGRAM FAILED: " + err)
        sys.exit(1)
    sent = 0
    for r in pending[:MAX_CARDS]:
        ok, err = telegram(card(r))
        if ok:
            con.execute("UPDATE jobs SET sent=1, status='sent', last_send_error='' WHERE ad_id=?", (r["ad_id"],))
            sent += 1
        else:
            con.execute("UPDATE jobs SET send_attempts=COALESCE(send_attempts,0)+1, last_send_error=? WHERE ad_id=?",
                        (err, r["ad_id"]))
        con.commit()
        if not TEST:
            time.sleep(1)
    build_dashboard(con)
    con.close()
    print("DONE new=" + str(len(new)) + " good_new=" + str(len(good_new)) + " sent=" + str(sent)
          + " errors=" + str(len(errors)))


if __name__ == "__main__":
    main()

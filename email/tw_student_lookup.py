"""READ-ONLY: find a student by NAME in Teachworks (both accounts) and print
the family (customer) attached — parent name/email/phone + last lesson."""
import os, sys
from src import teachworks_client as tw

first, last = os.environ.get("STUDENT_FIRST", ""), os.environ.get("STUDENT_LAST", "")
for acct, token in tw.accounts().items():
    for s in tw.tw_get("students", {"first_name": first, "last_name": last}, token=token):
        if (s.get("first_name") or "").strip().lower() != first.lower() or \
           (s.get("last_name") or "").strip().lower() != last.lower():
            continue
        cust = {}
        for c in tw.tw_get("customers", {"id": s.get("customer_id")}, token=token):
            if str(c.get("id")) == str(s.get("customer_id")):
                cust = c
        lessons = tw.tw_get("lessons", {"student_id": s["id"]}, token=token)
        last_l = max((str(l.get("from_date") or "")[:10] for l in lessons), default="")
        print(f"[{acct}] student {s.get('id')} {s.get('first_name')} {s.get('last_name')} "
              f"status={s.get('status')} customer={s.get('customer_id')} "
              f"parent={cust.get('first_name','')} {cust.get('last_name','')} "
              f"<{cust.get('email','')}> {cust.get('mobile_phone') or cust.get('phone') or ''} "
              f"lessons={len(lessons)} last={last_l}")

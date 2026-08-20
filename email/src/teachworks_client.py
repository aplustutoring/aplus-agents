"""Teachworks enrichment client — TWO accounts (online + in-person).

A+ runs two separate Teachworks accounts; tokens are per-account, so every lookup
queries both and uses whichever has the family. Vendored tw_get pattern from
aplus-sync (no public SDK): base https://api.teachworks.com/v1, token auth,
paginate 80, 403 backoff.

FERPA: callers send only the *summary* (counts + a few dates + tutor name) to the
classifier — never full lesson rows or attendance histories.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta

import requests

from .config import TEACHWORKS_TOKEN, TEACHWORKS_TOKEN_INPERSON

TW_BASE = "https://api.teachworks.com/v1"


def accounts() -> dict:
    """{account_name: token} for every configured Teachworks account."""
    out = {}
    if TEACHWORKS_TOKEN:
        out["online"] = TEACHWORKS_TOKEN
    if TEACHWORKS_TOKEN_INPERSON:
        out["in_person"] = TEACHWORKS_TOKEN_INPERSON
    return out


def tw_get(endpoint: str, params: dict | None = None, token: str | None = None) -> list:
    """Paginated GET against one Teachworks account (max 80/page, 3x 403 backoff).
    Defaults to the online account for backward compatibility."""
    token = token or TEACHWORKS_TOKEN
    if not token:
        return []
    headers = {
        "Authorization": f"Token token={token}",
        "Content-Type": "application/json",
    }
    params = dict(params or {})
    params["per_page"] = 80
    params["page"] = 1
    results: list = []
    while True:
        r = None
        for attempt in range(3):
            r = requests.get(f"{TW_BASE}/{endpoint}", headers=headers, params=params, timeout=30)
            if r.status_code == 403:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        else:
            r.raise_for_status()
        data = r.json()
        if not data:
            break
        results.extend(data)
        if len(data) < 80:
            break
        params["page"] += 1
    return results


def tw_write(method: str, endpoint: str, payload: dict, token: str) -> dict:
    """POST/PUT to Teachworks (short-circuited in DRY_RUN). 403 = Teachworks rate
    limit → back off and retry (same as tw_get; a burst of writes hits it fast).
    Teachworks accepts flat JSON per its docs; on a 400 we retry once with the
    documented resource wrapper (e.g. {"customer": {...}})."""
    from .config import DRY_RUN
    if DRY_RUN:
        print(f"[DRY_RUN] teachworks {method} /{endpoint} {str(payload)[:160]}")
        return {"id": "DRYRUN", "dry_run": True}
    headers = {"Authorization": f"Token token={token}", "Content-Type": "application/json"}
    r = None
    for attempt in range(4):
        r = requests.request(method, f"{TW_BASE}/{endpoint}", headers=headers, json=payload, timeout=30)
        if r.status_code == 403:
            time.sleep(5 * (attempt + 1))
            continue
        break
    if r.status_code == 400:
        wrapper = "student" if endpoint.startswith("students") else "customer"
        r = requests.request(method, f"{TW_BASE}/{endpoint}", headers=headers,
                             json={wrapper: payload}, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


def create_family(fields: dict, token: str) -> dict:
    return tw_write("POST", "customers/family", fields, token)


def update_customer(customer_id, fields: dict, token: str) -> dict:
    return tw_write("PUT", f"customers/{customer_id}", fields, token)


def create_student(fields: dict, token: str) -> dict:
    return tw_write("POST", "students", fields, token)


def find_student_by_email(email: str, token: str | None = None) -> dict | None:
    """Best-effort student lookup by email in one account. Tries the student record,
    then the parent/customer email. Returns the first match or None."""
    if not email:
        return None
    email = email.strip().lower()
    # 1) direct student email
    for s in tw_get("students", {"email": email}, token=token):
        return s
    # 2) family/customer email → their students
    for cust in tw_get("customers", {"email": email}, token=token):
        students = tw_get("students", {"customer_id": cust.get("id")}, token=token)
        if students:
            return students[0]
    return None


def find_customer_by_email(email: str, token: str | None = None) -> dict | None:
    """The Teachworks customer (parent/family account) for an email, if any."""
    if not email:
        return None
    for cust in tw_get("customers", {"email": email.strip().lower()}, token=token):
        return cust
    return None


def customers_for_family(email: str, last_name: str = "", first_name: str = "",
                         token: str | None = None) -> list[dict]:
    """EVERY customer record for a family in one account — email match PLUS
    name match, deduped, ACTIVE records first. Teachworks carries duplicate
    customers (the Aly Daly case, 2026-08-12: an inactive dupe owned the email
    while the live record held the invoices/students) — email-only lookups can
    land on the empty dupe and report a real family as inactive. Name filters
    are re-checked client-side in case the API ignores unknown params."""
    seen: set = set()
    out: list[dict] = []
    queries: list = []
    if (email or "").strip():
        queries.append(({"email": email.strip().lower()}, None))
    ln = (last_name or "").strip()
    if ln:
        q = {"last_name": ln}
        fn = (first_name or "").strip()
        if fn:
            q["first_name"] = fn
        queries.append((q, (fn.lower(), ln.lower())))
    for params, name_check in queries:
        try:
            for c in tw_get("customers", params, token=token):
                if name_check:
                    fn_c, ln_c = name_check
                    if (c.get("last_name") or "").strip().lower() != ln_c:
                        continue
                    if fn_c and (c.get("first_name") or "").strip().lower() != fn_c:
                        continue
                if c.get("id") in seen:
                    continue
                seen.add(c.get("id"))
                out.append(c)
        except Exception:  # noqa: BLE001 — a failed variant must not kill the lookup
            continue
    out.sort(key=lambda c: 0 if str(c.get("status") or "").lower().startswith("activ") else 1)
    return out


def _safe_date(value) -> str | None:
    if not value:
        return None
    return str(value)[:10]


def find_family_by_student(student_first: str, student_last: str,
                           tutor_hint: str = "") -> dict | None:
    """The family Teachworks ALREADY knows for a student named in a PO — the
    fastest, surest parent resolution there is (Roman, 2026-08-18: "matthew
    rose can be found in teachworks"). Searches both accounts for students
    with that exact name; each candidate is scored by real lesson history
    (a 0-lesson shell like the duplicate 'Dina Rose / Matthew Rose' record
    scores nothing) and by whether the PO's tutor taught them. Returns
    {parent_first, parent_last, email, phone, tutor, lessons, customer_id,
    account} for the strongest candidate, or None when no candidate has
    lesson history (a real family with lessons always wins over a shell)."""
    sf, sl = (student_first or "").strip().lower(), (student_last or "").strip().lower()
    if not sf or not sl:
        return None
    hint = (tutor_hint or "").strip().lower()
    hint_parts = [p for p in re.split(r"[\s,]+", hint) if p]
    best, best_score = None, 0
    for acct, token in accounts().items():
        try:
            studs = tw_get("students", {"first_name": student_first, "last_name": student_last},
                           token=token)
        except Exception:  # noqa: BLE001
            continue
        for s in studs:
            if (s.get("first_name") or "").strip().lower() != sf or \
               (s.get("last_name") or "").strip().lower() != sl:
                continue
            try:
                lessons = tw_get("lessons", {"student_id": s["id"]}, token=token)
            except Exception:  # noqa: BLE001
                lessons = []
            if not lessons:
                continue                       # shell record — never evidence
            latest = max(lessons, key=lambda l: str(l.get("from_date") or ""))
            last_tutor = (latest.get("employee_name") or "").strip()
            score = 1 + min(len(lessons), 50)   # history weight
            if hint_parts and all(p in last_tutor.lower() for p in hint_parts):
                score += 100                    # PO tutor == last tutor: decisive
            if score <= best_score:
                continue
            cust = {}
            try:
                for c in tw_get("customers", {"id": s.get("customer_id")}, token=token):
                    if str(c.get("id")) == str(s.get("customer_id")):
                        cust = c
            except Exception:  # noqa: BLE001
                pass
            if not (cust.get("email") or "").strip():
                continue
            best_score = score
            best = {"parent_first": (cust.get("first_name") or "").strip(),
                    "parent_last": (cust.get("last_name") or "").strip(),
                    "email": (cust.get("email") or "").strip().lower(),
                    "phone": (cust.get("mobile_phone") or cust.get("phone") or "").strip(),
                    "tutor": last_tutor, "lessons": len(lessons),
                    "last_lesson": str(latest.get("from_date") or "")[:10],
                    "customer_id": cust.get("id"), "account": acct,
                    "tutor_match": bool(hint_parts) and all(p in last_tutor.lower() for p in hint_parts)}
    return best


def student_lesson_activity(email: str, student_first: str,
                            lookback_days: int = 30,
                            parent_first: str = "", parent_last: str = "") -> dict:
    """THIS student's lesson signal, both accounts, keyed by the parent's email:
    {found, recent, upcoming} — `recent` = attended/completed lessons within
    `lookback_days`, `upcoming` = future not-cancelled lessons. found=False when
    the family or the named student isn't in Teachworks at all (a confident
    'not currently tutored', NOT an error — API errors raise to the caller).

    Drives is_the_family_currently_being_tutored_by_us_ (Roman, 2026-08-11):
    Yes = recent OR upcoming lessons for the PO's student; No otherwise."""
    sf = (student_first or "").strip().lower()
    if not email or not sf:
        return {"found": False, "recent": 0, "upcoming": 0}
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    today = date.today().isoformat()
    found, recent, upcoming = False, 0, 0
    upcoming_dates: list[str] = []
    upcoming_lessons: list[dict] = []
    recent_lessons: list[dict] = []
    for _acct, token in accounts().items():
        # customers_for_family, not a bare email match — duplicate/inactive
        # customer records would otherwise hide the student (Aly Daly case)
        for cust in customers_for_family(email, parent_last, parent_first, token=token):
            for s in tw_get("students", {"customer_id": cust.get("id")}, token=token):
                if (s.get("first_name") or "").strip().lower() != sf:
                    continue
                found = True
                for l in tw_get("lessons", {"student_id": s["id"],
                                            "from_date[gte]": since}, token=token):
                    status = str(l.get("status", "")).lower()
                    d = _safe_date(l.get("from_date")) or ""
                    slot = {"date": d, "time": str(l.get("from_time") or "")[:5],
                            "tutor": l.get("employee_name") or ""}
                    if d >= today and "cancel" not in status:
                        upcoming += 1
                        upcoming_dates.append(d)
                        upcoming_lessons.append(slot)
                    elif "attend" in status or "complete" in status:
                        recent += 1
                        recent_lessons.append(slot)
    return {"found": found, "recent": recent, "upcoming": upcoming,
            "upcoming_dates": upcoming_dates,
            "upcoming_lessons": upcoming_lessons, "recent_lessons": recent_lessons}


def upcoming_lessons_for_family(email: str, student_first: str | None = None) -> list[dict]:
    """Future, not-yet-cancelled lessons for a family, across BOTH accounts.

    Used by the cancellation verify-and-report: finds the customer by email in each
    account, their students (narrowed to `student_first` when given — falls back to
    all siblings if the name doesn't match), and lists lessons from today onward
    whose status isn't already cancelled.
    """
    if not email:
        return []
    today = date.today().isoformat()
    sf = (student_first or "").strip().lower()
    out: list[dict] = []
    for acct, token in accounts().items():
        for cust in tw_get("customers", {"email": email.strip().lower()}, token=token):
            students = tw_get("students", {"customer_id": cust.get("id")}, token=token)
            for s in students:
                for l in tw_get("lessons", {"student_id": s["id"], "from_date[gte]": today}, token=token):
                    if "cancel" in str(l.get("status", "")).lower():
                        continue
                    out.append({
                        "account": acct,
                        "student": f"{s.get('first_name','')} {s.get('last_name','')}".strip(),
                        "student_first": (s.get("first_name") or "").strip().lower(),
                        "lesson_id": l.get("id"),
                        "date": _safe_date(l.get("from_date")),
                        "time": str(l.get("from_time") or "")[:5],
                        "status": l.get("status"),
                        "tutor": l.get("employee_name") or "",
                    })
    # Narrow globally: if the named student matched anywhere, report only theirs;
    # otherwise fall back to all siblings (over-report rather than miss).
    if sf:
        named = [l for l in out if l["student_first"] == sf]
        if named:
            out = named
    for l in out:
        l.pop("student_first", None)
    return out


def enrichment_for_email(email: str) -> dict:
    """FERPA-safe enrichment summary for the classifier, searched across BOTH
    Teachworks accounts (online + in-person). Uses whichever account has the family
    (prefers a student match; tiebreak = most recent lesson activity)."""
    best = None
    for acct, token in accounts().items():
        e = _enrich_one(email, acct, token)
        if not e:
            continue
        if best is None or _enrich_rank(e) > _enrich_rank(best):
            best = e
    return best or {"teachworks_match": False}


def _enrich_rank(e: dict) -> tuple:
    """Orderable quality of a match: student found > upcoming lessons > recency."""
    return (1 if e.get("student_name") else 0,
            e.get("upcoming_lessons") or 0,
            e.get("last_lesson_date") or "")


def _enrich_one(email: str, account: str, token: str) -> dict | None:
    customer = find_customer_by_email(email, token)     # parent / family account
    student = find_student_by_email(email, token)
    if not customer and not student:
        return None

    # Parent (family) name drives the A-L / M-Z scheduler split.
    parent_last_name = (customer or {}).get("last_name")
    parent_name = None
    if customer:
        parent_name = customer.get("full_name") or " ".join(
            filter(None, [customer.get("first_name"), customer.get("last_name")])
        )

    if not student:
        return {"teachworks_match": True, "teachworks_account": account,
                "parent_name": parent_name, "parent_last_name": parent_last_name}

    sid = student.get("id")
    name = student.get("full_name") or " ".join(
        filter(None, [student.get("first_name"), student.get("last_name")])
    )
    last_name = student.get("last_name")

    lessons = tw_get("lessons", {"student_id": sid}, token=token) if sid else []
    today = date.today().isoformat()
    upcoming = [l for l in lessons if _safe_date(l.get("from_date")) and _safe_date(l["from_date"]) >= today]
    recent = [l for l in lessons if _safe_date(l.get("from_date")) and _safe_date(l["from_date"]) < today]

    def _attendance_count(status_substr: str) -> int:
        n = 0
        for l in recent:
            st = str(l.get("status", "")).lower()
            if status_substr in st:
                n += 1
        return n

    last_lesson_date = None
    if recent:
        last_lesson_date = max(_safe_date(l.get("from_date")) for l in recent if l.get("from_date"))

    tutor = None
    if lessons:
        tutor = lessons[-1].get("employee_name") or lessons[-1].get("teacher_name")

    return {
        "teachworks_match": True,
        "teachworks_account": account,
        "parent_name": parent_name,
        "parent_last_name": parent_last_name,
        "student_name": name,
        "student_last_name": last_name,
        "assigned_tutor": tutor,
        "upcoming_lessons": len(upcoming),
        "recent_lessons": len(recent),
        "attended_count": _attendance_count("attend") + _attendance_count("complete"),
        "no_show_count": _attendance_count("no show") + _attendance_count("no_show") + _attendance_count("missed"),
        "cancelled_count": _attendance_count("cancel"),
        "last_lesson_date": last_lesson_date,
    }

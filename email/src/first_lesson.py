"""First-lesson stamp: the Teachworks truth behind "when did this family start".

Retention step 2's data foundation (docs/RETENTION-PROCESS.md, "Where the
lists live"). HubSpot's "date entered Post-Lesson" is when a human moved the
deal, in batches, so it lags the real first lesson by days and every
pre-created sibling deal moves at once. This sweep reads attended lessons
from Teachworks (both accounts), finds each student's FIRST attended lesson
ever, and stamps it as `[Agent] First lesson date`
(`retention_first_lesson_date`) on

  * the student's earliest deal of the season (the "1 - 26/27" PO deal for
    charter, the one purchase deal for private pay), and
  * the family contact (the earliest first lesson across siblings).

The "New Starts (Care Calls)" deal view (72186918) filters on that one
property, so the day-14 and day-45 calls run on the lesson date, not on a
stage move. Deterministic: no prompt, no CARE pointer.

Cadence: called from deal_sync.run() every cycle, self-gated to once every
`every_hours`. Each run pulls the last `window_days` of lessons in bulk (one
paginated call per account), and only students not yet in
state/first_lessons.json cost extra calls (their full lesson history, their
customer record, one HubSpot contact search, one deal search).

Backfill / preview: `FIRST_LESSON_BACKFILL_DAYS=60 python -m src.first_lesson`
(the email-deal-sync workflow input `first_lesson_backfill_days`; pair with
dry_run to print the plan).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

from . import audit, hubspot_client as hs, teachworks_client as tw
from .business_hours import now_la
from .config import DRY_RUN, ROOT, cfg

STATE = ROOT / "state" / "first_lessons.json"
PROP = "retention_first_lesson_date"
_ATTENDED = ("attend", "complete")


def _cfg() -> dict:
    return cfg().get("first_lesson", {}) or {}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _today() -> str:
    return now_la().date().isoformat()


# ── state ───────────────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        return json.loads(STATE.read_text()) if STATE.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def save_state(state: dict) -> None:
    if DRY_RUN:
        return
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


# ── pure helpers (unit-tested) ──────────────────────────────────────────────

def attended_participants(lessons: list[dict]) -> dict[str, dict]:
    """{normalised 'first last': {'name': as written, 'dates': sorted attended
    dates, 'ids': {student ids seen}}} from a bulk lessons pull. A participant
    counts when its own status (or the lesson's, when the participant carries
    none) says attended/completed. Future-dated lessons never count."""
    today = _today()
    out: dict[str, dict] = {}
    for l in lessons:
        d = str(l.get("from_date") or "")[:10]
        if not d or d > today:
            continue
        lst = str(l.get("status") or "").lower()
        for p in l.get("participants") or []:
            raw = (p.get("student_name") or "").strip()
            key = _norm(raw)
            st = str(p.get("status") or lst).lower()
            if not key or not any(a in st for a in _ATTENDED):
                continue
            rec = out.setdefault(key, {"name": raw, "dates": [], "ids": set()})
            rec["dates"].append(d)
            if p.get("student_id"):
                rec["ids"].add(str(p["student_id"]))
    for rec in out.values():
        rec["dates"] = sorted(set(rec["dates"]))
    return out


def earliest_attended(lessons: list[dict]) -> str:
    """Earliest attended date in one student's full lesson history ('' if none).
    Lesson-level status is enough here: the history call is per student."""
    today = _today()
    dates = []
    for l in lessons:
        d = str(l.get("from_date") or "")[:10]
        if not d or d > today:
            continue
        st = str(l.get("status") or "").lower()
        parts = l.get("participants") or []
        pst = [str(p.get("status") or "").lower() for p in parts]
        if any(any(a in x for a in _ATTENDED) for x in pst + [st]):
            dates.append(d)
    return min(dates) if dates else ""


def choose_deal(deals: list[dict], season_start: str, exclude_pipelines: set | None = None) -> dict | None:
    """The student's earliest-created deal of the season: for charter the
    '1 - YY/YY' PO deal (its siblings 2..5 are pre-created later), for private
    pay the single purchase deal. None when the student has no deal this
    season yet (the stamp waits; the family contact still gets it)."""
    ex = exclude_pipelines or set()
    cands = []
    for d in deals:
        p = d.get("properties") or {}
        cd = (p.get("createdate") or "")[:10]
        if not cd or cd < season_start or (p.get("pipeline") or "") in ex:
            continue
        cands.append((cd, d))
    if not cands:
        return None
    cands.sort(key=lambda t: t[0])
    return cands[0][1]


def split_name(name: str) -> tuple[str, str]:
    """(first, last). Teachworks writes participants as 'Last, First' (the
    'Torres, Maria' lesson in the low-balance replay); plain 'First Last' is
    accepted too. The 2026-09-10 preview resolved 0 of 164 students before
    the comma form was handled."""
    name = (name or "").strip()
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        return first, last
    parts = name.split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def display_name(name: str) -> str:
    first, last = split_name(name)
    return f"{first} {last}".strip()


# ── Teachworks + HubSpot lookups ────────────────────────────────────────────

def _bulk_lessons(window_days: int) -> dict[str, list[dict]]:
    """{account: lessons} for the last window_days, both accounts."""
    since = (now_la().date() - timedelta(days=window_days)).isoformat()
    out = {}
    for acct, token in tw.accounts().items():
        out[acct] = tw.tw_get("lessons", {"from_date[gte]": since, "from_date[lte]": _today()},
                              token=token)
    return out


def _tw_student(first: str, last: str, ids: set, token: str) -> dict | None:
    """The Teachworks student record (id + customer_id) for a participant
    name; the participant's student_id wins when the pull carried one."""
    last_queries = [last] + [p for p in re.split(r"[-\s]+", last) if p and p.lower() != last.lower()]
    for lq in last_queries:
        try:
            studs = tw.tw_get("students", {"first_name": first, "last_name": lq}, token=token)
        except Exception:  # noqa: BLE001
            continue
        for s in studs:
            if ids and str(s.get("id")) in ids:
                return s
            if _norm(s.get("first_name") or "") == _norm(first) and \
               _norm(s.get("last_name") or "") == _norm(lq):
                return s
    return None


def _customer_email(customer_id, token: str) -> str:
    try:
        for c in tw.tw_get("customers", {"id": customer_id}, token=token):
            if str(c.get("id")) == str(customer_id):
                return (c.get("email") or "").strip().lower()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _student_deals(first: str, last: str) -> list[dict]:
    """All deals HubSpot holds for this student, by the agent-stamped first
    name, kept to those whose name carries the surname (Roman/Saenz collisions,
    2026-08-26)."""
    try:
        deals = hs.search_deals_by_student(first)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  deal search failed for {first} {last}: {e}")
        return []
    ln = _norm(last)
    parts = [p for p in re.split(r"[-\s]+", ln) if p]
    keep = []
    for d in deals:
        name = _norm((d.get("properties") or {}).get("dealname") or "")
        if ln in name or any(p in name for p in parts if len(p) > 2):
            keep.append(d)
    return keep


def _stamp(obj: str, obj_id: str, value: str) -> None:
    hs._write("PATCH", f"/crm/v3/objects/{obj}/{obj_id}", {"properties": {PROP: value}})


# ── the sweep ───────────────────────────────────────────────────────────────

def run(force: bool = False, window_days: int | None = None) -> dict:
    fc = _cfg()
    if not fc.get("enabled", False):
        return {"skipped": "disabled"}
    state = load_state()
    every = float(fc.get("every_hours", 6))
    last = state.get("_last_run")
    now_utc = datetime.now(timezone.utc)
    if not force and last:
        try:
            if now_utc - datetime.fromisoformat(last) < timedelta(hours=every):
                return {"skipped": "recent"}
        except ValueError:
            pass
    env_days = (os.environ.get("FIRST_LESSON_BACKFILL_DAYS") or "").strip()
    window = int(window_days or (env_days if env_days.isdigit() else 0) or fc.get("window_days", 10))
    season_start = str(fc.get("season_start") or "2026-08-01")
    exclude = set((cfg().get("deal_sync") or {}).get("exclude_pipelines") or [])
    new_window_days = int(fc.get("new_start_days", 60))
    passthrough = getattr(hs, "SEARCH_PASSTHROUGH", None)
    if DRY_RUN:
        hs.SEARCH_PASSTHROUGH = True          # reads only; the preview must resolve real deals
    summary = {"window_days": window, "students_seen": 0, "new": 0, "stamped_deals": 0,
               "stamped_contacts": 0, "no_deal": 0, "no_contact": 0, "not_in_tw": 0, "new_starts": []}
    try:
        by_acct = _bulk_lessons(window)
        for acct, lessons in by_acct.items():
            token = tw.accounts().get(acct)
            parts = attended_participants(lessons)
            summary["students_seen"] += len(parts)
            print(f"first_lesson [{acct}]: {len(lessons)} lesson(s) in the last {window} days, "
                  f"{len(parts)} attended student(s)")
            for key, rec in sorted(parts.items()):
                skey = f"{acct}:{key}"
                cur = state.get(skey) or {}
                if cur.get("first") and (cur.get("deal_id") or cur.get("no_deal_until", "") > _today()) \
                        and cur.get("contact_id"):
                    continue                                    # fully stamped
                first, last = split_name(rec["name"])
                if not first or not last:
                    continue
                s = _tw_student(first, last, rec["ids"], token) if token else None
                if not s:
                    summary["not_in_tw"] += 1
                    continue
                first_date = cur.get("first")
                if not first_date:
                    try:
                        hist = tw.tw_get("lessons", {"student_id": s["id"]}, token=token)
                    except Exception as e:  # noqa: BLE001
                        print(f"  ⚠️  history failed for {rec['name']}: {e}")
                        continue
                    first_date = earliest_attended(hist) or rec["dates"][0]
                    summary["new"] += 1
                email = cur.get("email") or _customer_email(s.get("customer_id"), token)
                is_new_start = (now_la().date() - datetime.fromisoformat(first_date).date()).days <= new_window_days
                entry = {"name": display_name(rec["name"]), "first": first_date, "email": email,
                         "tw_student_id": str(s.get("id")), "checked": _today()}
                entry.update({k: cur[k] for k in ("deal_id", "contact_id", "no_deal_until") if k in cur})
                # deal: the season's earliest
                if not entry.get("deal_id"):
                    deal = choose_deal(_student_deals(first, last), season_start, exclude)
                    if deal:
                        dp = deal.get("properties") or {}
                        if (dp.get(PROP) or "")[:10] != first_date:
                            if DRY_RUN:
                                print(f"[DRY_RUN] stamp deal {deal['id']} ({dp.get('dealname')}) {PROP}={first_date}")
                            else:
                                _stamp("deals", deal["id"], first_date)
                            summary["stamped_deals"] += 1
                        entry["deal_id"] = deal["id"]
                        entry.pop("no_deal_until", None)
                    else:
                        summary["no_deal"] += 1
                        entry["no_deal_until"] = (now_la().date() + timedelta(days=int(fc.get("retry_days", 3)))).isoformat()
                # contact: the family, earliest sibling wins
                if not entry.get("contact_id") and email:
                    c = None
                    try:
                        c = hs.find_contact_by_email(email, properties=["email", "firstname", "lastname", PROP])
                    except Exception as e:  # noqa: BLE001
                        print(f"  ⚠️  contact search failed for {email}: {e}")
                    if c:
                        have = ((c.get("properties") or {}).get(PROP) or "")[:10]
                        if not have or first_date < have:
                            if DRY_RUN:
                                print(f"[DRY_RUN] stamp contact {c['id']} ({email}) {PROP}={first_date}")
                            else:
                                _stamp("contacts", c["id"], first_date)
                            summary["stamped_contacts"] += 1
                        entry["contact_id"] = c["id"]
                    else:
                        summary["no_contact"] += 1
                elif not email:
                    summary["no_contact"] += 1
                if is_new_start and not cur.get("first"):
                    summary["new_starts"].append(f"{display_name(rec['name'])} ({first_date})")
                    audit.append({"message_id": f"first-lesson:{skey}:{first_date}", "source": "first_lesson",
                                  "action_taken": "first_lesson_stamped", "student": display_name(rec["name"]),
                                  "first_lesson": first_date, "account": acct,
                                  "deal_id": entry.get("deal_id"), "contact_id": entry.get("contact_id")})
                state[skey] = entry
        state["_last_run"] = now_utc.isoformat()
        save_state(state)
    finally:
        if DRY_RUN:
            hs.SEARCH_PASSTHROUGH = passthrough
    print(f"first_lesson: {summary['students_seen']} student(s) seen, {summary['new']} new to state, "
          f"{summary['stamped_deals']} deal(s) + {summary['stamped_contacts']} contact(s) stamped, "
          f"{summary['no_deal']} without a deal yet, {summary['no_contact']} without a contact, "
          f"{summary['not_in_tw']} not resolvable in Teachworks")
    if summary["new_starts"]:
        print("  new starts (first lesson within %d days): " % new_window_days + "; ".join(summary["new_starts"]))
    return summary


if __name__ == "__main__":
    days = (os.environ.get("FIRST_LESSON_BACKFILL_DAYS") or "").strip()
    run(force=True, window_days=int(days) if days.isdigit() else None)

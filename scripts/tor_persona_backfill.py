#!/usr/bin/env python3
"""Persona backfill review list: who looks like a teacher but has no a_persona.

The teacher campaign's audience is `a_persona` = "Teacher of Record/EF/ES"
(see scripts/charter_tor_segments.py). Contacts that other signals think are
teachers but that carry no persona are NOT emailed — they are listed here with
their evidence so a human can decide, because the signals that flagged them are
exactly the unreliable ones:

  * `hs_lead_status` = "Charter School Teacher TOR/EF" is doing identity duty
    for thousands of contacts and is frequently wrong (12 of the 13 Sage Oak
    candidates carried it; none were confirmed teachers).
  * `charter_school_teacher` holds WHICH SCHOOL, not "is a teacher".

Proposes a persona per contact from the evidence, ranked by confidence, and
writes a CSV for review. --write applies ONLY the rows whose proposal is
high-confidence, and only with --confirm APPLY.

Read-only by default.
"""

import argparse
import collections
import csv
import os
import re
import sys
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path("/Users/romanslavinsky/code/aplus-agents/.env"), override=False)
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}

PERSONA_TOR = "Teacher of Record/EF/ES"
PERSONA_DM = "Decision Maker/Director"

# jobtitle words that decide the persona outright
# Conflict scan: a job title that disagrees with the persona on the record.
#
# IT DOES NOT SAY WHICH ONE IS WRONG. An earlier version assumed the title
# arbitrated and reported Lisa Barlow as a mis-tagged teacher. Roman
# 2026-08-25: she was PROMOTED into Amy Chapin's position. Her persona
# (Decision Maker/Director) is correct and current; her job title
# ("Educational Facilitator") is the stale field, left over from when she was
# a teacher, which is also why old deals name her as Teacher of Record.
#
# Promotions are exactly the case that breaks a title-wins rule, and schools
# promote from within constantly. So a conflict is reported with BOTH values
# and the record's last-modified date, for a human to resolve. The script does
# not guess.
CONFLICT_TEACHER = re.compile(r"\b(teacher|educational facilitator|facilitator|tosa|"
                              r"tor\b|instructor|faculty)\b", re.I)
CONFLICT_DM = re.compile(r"\b(director|principal|superintendent|dean|chief|officer)\b", re.I)

DM_TITLE = re.compile(r"\b(director|principal|superintendent|dean|head of|chief|"
                      r"executive|coordinator of|manager of|vp|president)\b", re.I)
SUPPORT_TITLE = re.compile(r"\b(assistant|specialist|clerk|receptionist|aide|"
                           r"technician|bookkeeper|accountant|purchasing|payroll)\b", re.I)
TEACHER_TITLE = re.compile(r"\b(teacher|educational facilitator|ef\b|es\b|"
                           r"teacher of record|tor\b|instructor|faculty)\b", re.I)


def hs(method, path, **kw):
    for _ in range(5):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=40, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10) or 10))
            continue
        r.raise_for_status()
        return r.json() if r.text else {}
    r.raise_for_status()


def search_all(groups, props):
    out, after = {}, None
    while True:
        body = {"filterGroups": groups, "properties": props, "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", "/crm/v3/objects/contacts/search", json=body)
        for r in j.get("results", []):
            out[r["id"]] = r["properties"]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return out
        time.sleep(0.12)


PROPS = ["email", "firstname", "lastname", "jobtitle", "charter_school_teacher",
         "a_persona", "hs_lead_status", "createdate", "hs_object_source_label",
         "aplus_event_role", "aplus_event_tag", "aplus_marketing_consent",
         "educational_facillitator_teacher_of_record",
         "student_first_name", "student_names", "last_tutor_name", "teacher_of_record_name"]


def propose(p, named_on_deals):
    """(persona_or_none, confidence, why). Confidence: high / medium / review."""
    role = (p.get("aplus_event_role") or "").strip().lower()
    title = p.get("jobtitle") or ""

    # 1. the booth asked them directly — that is self-reported and beats everything
    if role == "teacher":
        return PERSONA_TOR, "high", "self-identified as teacher at the booth"
    if role == "administrator":
        return PERSONA_DM, "high", "self-identified as administrator at the booth"
    if role == "support_staff":
        return None, "high", "self-identified as support staff — correctly has no persona"

    # 2. an explicit job title
    if TEACHER_TITLE.search(title):
        return PERSONA_TOR, "high", f"job title: {title}"
    if DM_TITLE.search(title):
        return PERSONA_DM, "high", f"job title: {title}"
    if SUPPORT_TITLE.search(title):
        return None, "high", f"support role, not a teacher — job title: {title}"

    # 3. charter deals name them as the teacher of record
    if named_on_deals:
        return PERSONA_TOR, "high", f"named as Teacher of Record on {named_on_deals} charter deal(s)"

    # 4. the EF checkbox is a deliberate human tick, unlike lead status
    if p.get("educational_facillitator_teacher_of_record") == "true":
        return PERSONA_TOR, "medium", "Educational Facilitator/TOR checkbox is ticked"

    # 5. nothing but the unreliable signals
    bits = []
    if p.get("hs_lead_status") == "Charter School Teacher TOR/EF":
        bits.append("lead status says TOR (unreliable)")
    if p.get("charter_school_teacher"):
        bits.append(f"school stamped: {p['charter_school_teacher']}")
    src = p.get("hs_object_source_label")
    if src:
        bits.append(f"source: {src}")
    return None, "review", "; ".join(bits) or "no evidence either way"


def is_shared(r):
    """Row-level view of the same test the campaign segmenter uses."""
    local = (r["email"] or "").split("@")[0].lower()
    words = set(re.split(r"[._\-+0-9]+", local))
    name_words = set(re.findall(r"[a-z]+", r["name"].lower()))
    SHARED = {"vendor", "vendors", "vendorsupport", "vendorinvoicing", "accountspayable",
              "finance", "purchasing", "enrichment", "info", "admin", "support", "cp",
              "contractprograms", "learningfund", "team", "department", "dept",
              "invoicing", "invoice", "orders", "noreply"}
    return bool((words | name_words) & SHARED) or not r["name"] or r["name"] == "(no name)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="tor_persona_backfill.csv")
    ap.add_argument("--include-excluded-schools", action="store_true",
                    help="also list Sage Oak (excluded from the campaign, worked separately)")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN not set")

    tagged = search_all([{"filters": [{"propertyName": "a_persona",
                                       "operator": "CONTAINS_TOKEN", "value": PERSONA_TOR}]}], PROPS)
    print(f"already carry the {PERSONA_TOR} persona: {len(tagged)}")
    # Anyone carrying ANY persona has already been classified by a human. They
    # are not a backfill candidate -- proposing a re-tag would be noise. 15 of
    # the 16 "Decision Makers" this script first surfaced were already tagged
    # correctly; what was stale was their LEAD STATUS, which is a different fix.
    any_persona = search_all([{"filters": [{"propertyName": "a_persona",
                                            "operator": "HAS_PROPERTY"}]}], PROPS)
    print(f"carry some other persona (already classified): {len(any_persona) - len(tagged)}")

    candidates = {}
    for label, groups in [
        ("lead status", [{"filters": [{"propertyName": "hs_lead_status", "operator": "EQ",
                                       "value": "Charter School Teacher TOR/EF"}]}]),
        ("school stamped", [{"filters": [{"propertyName": "charter_school_teacher",
                                          "operator": "HAS_PROPERTY"}]}]),
        ("EF checkbox", [{"filters": [{"propertyName": "educational_facillitator_teacher_of_record",
                                       "operator": "EQ", "value": "true"}]}]),
    ]:
        for cid, p in search_all(groups, PROPS).items():
            if cid not in any_persona:
                candidates.setdefault(cid, p)
    print(f"flagged by another signal and carrying NO persona at all: {len(candidates)}")

    # separate cleanup: already classified, but lead status contradicts the persona
    mismatch = [p for cid, p in any_persona.items()
                if cid not in tagged
                and p.get("hs_lead_status") == "Charter School Teacher TOR/EF"]
    print(f"persona says NOT a teacher but lead status says TOR: {len(mismatch)}")

    # who do charter deals name as TOR? (strongest positive evidence)
    deals, after = {}, None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "IN",
             "values": ["907748", "72281989", "88841552", "5119061", "1066195"]}]}],
            "properties": ["teacher_of_record_name"], "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", "/crm/v3/objects/deals/search", json=body)
        for r in j.get("results", []):
            deals[r["id"]] = r["properties"]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            break
        time.sleep(0.1)
    deal_names = collections.Counter(
        re.sub(r"[^a-z ]", " ", (d.get("teacher_of_record_name") or "").lower()).split().__str__()
        for d in deals.values() if d.get("teacher_of_record_name"))
    name_hits = collections.Counter()
    for d in deals.values():
        n = " ".join(re.sub(r"[^a-z ]", " ", (d.get("teacher_of_record_name") or "").lower()).split())
        if n:
            name_hits[n] += 1

    rows = []
    for cid, p in candidates.items():
        school = p.get("charter_school_teacher") or ""
        if school == "Sage Oak" and not args.include_excluded_schools:
            pass  # still listed; Sage Oak is worked separately but the tag is still wrong
        full = " ".join(re.sub(r"[^a-z ]", " ",
                               f"{p.get('firstname') or ''} {p.get('lastname') or ''}".lower()).split())
        persona, conf, why = propose(p, name_hits.get(full, 0))
        rows.append({
            "contact_id": cid,
            "name": f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip() or "(no name)",
            "email": p.get("email") or "",
            "school": school,
            "job_title": p.get("jobtitle") or "",
            "booth_role": p.get("aplus_event_role") or "",
            "lead_status": p.get("hs_lead_status") or "",
            "proposed_persona": persona or "(none — not a teacher)",
            "confidence": conf,
            "evidence": why,
            "hubspot_link": f"https://app.hubspot.com/contacts/6312752/contact/{cid}",
        })

    order = {"high": 0, "medium": 1, "review": 2}
    rows.sort(key=lambda r: (order[r["confidence"]], r["proposed_persona"], r["school"], r["name"]))

    out = Path(args.csv)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out}  ({len(rows)} rows)")

    print("\n=== proposal summary ===")
    for (persona, conf), n in sorted(collections.Counter(
            (r["proposed_persona"], r["confidence"]) for r in rows).items(),
            key=lambda kv: (order[kv[0][1]], -kv[1])):
        print(f"  {n:>4}  {conf:<7} {persona}")

    print("\n=== HIGH confidence: tag as Teacher of Record ===")
    for r in [r for r in rows if r["confidence"] == "high" and r["proposed_persona"] == PERSONA_TOR]:
        print(f"  {r['name']:<24} {r['email']:<42} {r['school']:<12} {r['evidence']}")
    print("\n=== HIGH confidence: NOT a teacher (leave persona empty or set DM) ===")
    for r in [r for r in rows if r["confidence"] == "high" and r["proposed_persona"] != PERSONA_TOR]:
        print(f"  {r['name']:<24} {r['email']:<42} {r['proposed_persona']:<28} {r['evidence'][:60]}")
    review = [r for r in rows if r["confidence"] == "review"]
    people = [r for r in review if not is_shared(r)]
    shared = [r for r in review if is_shared(r)]
    print(f"\n=== NOT PEOPLE — shared/system inboxes ({len(shared)}) ===")
    print("  Already excluded from the campaign by the role-mailbox filter.")
    print("  Worth archiving or tagging so they stop showing up as teacher candidates.")
    for r in shared[:12]:
        print(f"  {r['name'][:22]:<22} {r['email']:<44} {r['school']}")
    if len(shared) > 12:
        print(f"    ... and {len(shared) - 12} more (full list in the CSV)")

    print(f"\n=== NEEDS A HUMAN ({len(people)}) ===")
    print("  No job title, no booth role, no deal names them. Flagged only by the")
    print("  unreliable signals. Most have personal email addresses at a charter")
    print("  school, which is the shape of a FAMILY, not a teacher.")
    for r in people[:20]:
        print(f"  {r['name']:<24} {r['email']:<42} {r['school']:<12} {r['evidence'][:44]}")
    if len(people) > 20:
        print(f"    ... and {len(people) - 20} more (full list in the CSV)")

    conflicts = []
    for cid, p in any_persona.items():
        title, persona = p.get("jobtitle") or "", p.get("a_persona") or ""
        if not title:
            continue
        # Only compare title against persona for SCHOOL-side roles. A parent who
        # happens to be "Director of Jewish Life and Learning" somewhere else is
        # a Family, correctly, and their day job says nothing about their
        # relationship to us. Comparing everyone turned 7 real conflicts into 50
        # rows of noise about parents' careers.
        if not (PERSONA_TOR in persona or "Decision Maker" in persona):
            continue
        if CONFLICT_TEACHER.search(title) and not CONFLICT_DM.search(title) \
                and PERSONA_TOR not in persona:
            conflicts.append((cid, p, "title says TEACHER", PERSONA_TOR))
        elif CONFLICT_DM.search(title) and "Decision Maker" not in persona:
            conflicts.append((cid, p, "title says DIRECTOR/CHIEF", PERSONA_DM))
    print(f"\n=== PERSONA AND JOB TITLE DISAGREE ({len(conflicts)}) ===")
    print("  This does NOT say which field is wrong. A promotion leaves the TITLE")
    print("  stale (Lisa Barlow: promoted into Amy Chapin's role, persona correct,")
    print("  title still says Educational Facilitator). A bad import leaves the")
    print("  PERSONA stale. Both look identical here. A human decides.")
    for cid, p, why, should in conflicts:
        deals_named = name_hits.get(" ".join(re.sub(
            r"[^a-z ]", " ", f"{p.get('firstname') or ''} {p.get('lastname') or ''}".lower()).split()), 0)
        extra = f"  [{deals_named} charter deals name them as TOR]" if deals_named else ""
        print(f"  {(p.get('firstname') or '') + ' ' + (p.get('lastname') or ''):<24} "
              f"title={(p.get('jobtitle') or '')!r}")
        print(f"      persona={p.get('a_persona')!r}  (title alone would suggest "
              f"{should}){extra}")
        print(f"      https://app.hubspot.com/contacts/6312752/contact/{cid}")

    print(f"\n=== SEPARATE FIX: lead status contradicts the persona ({len(mismatch)}) ===")
    print("  These are already correctly classified by persona. Their hs_lead_status")
    print("  still says 'Charter School Teacher TOR/EF', which is what made them look")
    print("  like teachers. This is the 08-14 open item, not a persona problem.")
    for m in mismatch[:15]:
        print(f"  {(m.get('firstname') or '')} {(m.get('lastname') or ''):<20} "
              f"{(m.get('email') or ''):<42} persona={m.get('a_persona')}")
    if len(mismatch) > 15:
        print(f"    ... and {len(mismatch) - 15} more")


if __name__ == "__main__":
    main()

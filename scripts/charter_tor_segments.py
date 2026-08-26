#!/usr/bin/env python3
"""Charter TOR (teacher) segmentation for the 26/27 outreach from Danielle.

The teacher-side counterpart to scripts/charter_gap_segments.py. Where the
family segmenter splits on recency x student-count x personalization, the
teacher relationship has different axes: whether the teacher has already sent
us business in 26/27, and how much business came through them in 25/26.

AUDIENCE = `a_persona` contains "Teacher of Record/EF/ES", and nothing else.
The persona property is the master contact-type switch (CLAUDE.md: every agent
reads it FIRST), so it is the audience, not one vote among several.

An earlier version unioned four signals. That was wrong: it bypassed the
persona architecture and let `charter_school_teacher` (which holds WHICH
SCHOOL, not "is a teacher") drag in 42 families and 15 school role mailboxes.
The other three signals are still READ, but only to print a backfill queue --
people who look like teachers and are missing the persona. They are reported,
never emailed. Tag them in the portal and the next run picks them up.

Then attributes charter deals to teachers. NOTE: deals carry
`teacher_of_record_name` but NOT an email (checked 2026-08-21 — 2244 of 2284
deals since 2025-08-01 have the name, 0 have an email), so attribution is a
normalized full-name match against the TOR contacts. Unmatched names are
reported, never guessed at.

Segments (one static list per cell):
  A   Restarted        >=1 charter deal created since 2026-07-01
  B1  Anchor           no 26/27 deal, 5+ families in 25/26
  B2  Multi            no 26/27 deal, 2-4 families in 25/26
  B3  Single           no 26/27 deal, 1 family in 25/26
  C1  Intro - iLEAD    no deal history, school = iLEAD (case-study variant)
  C2  Intro - other    no deal history, any other partner school

Sage Oak is excluded at every segment (EXCLUDE_SCHOOLS): those teachers are
worked separately through the August Summit booth follow-up.

--write-props stamps tor_family_count / tor_student_count /
tor_families_lapsed / tor_segment onto the contacts (batch update, UPDATE-only
by definition). --build-lists creates/refreshes the six static lists.
Read-only otherwise.
"""

import argparse
import collections
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent.parent
    load_dotenv(_here / ".env", override=False)
    # worktrees have no .env — fall back to the main checkout's
    if "/.claude/worktrees/" in str(_here) or "/scratchpad/" in str(_here):
        base = str(_here).split("/.claude/worktrees/")[0]
        load_dotenv(Path("/Users/romanslavinsky/code/aplus-agents/.env"), override=False)
except ImportError:
    pass

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}

GAP_LIST_ID = 3104                 # lapsed 25/26 families (charter_gap_analysis)
SINCE = "2025-08-01"               # start of the 25/26 attribution window
EVER_SINCE = "2019-01-01"          # far enough back to catch "referred at some point"
YEAR_2627 = "2026-07-01"           # a deal created on/after this is 26/27 business
CHARTER_PIPELINES = {"907748", "72281989", "88841552", "5119061", "1066195"}
LIST_PREFIX = "Charter TOR 26/27 - "
INTERNAL_DOMAIN = "@wetutorathome.com"
# Sage Oak teachers are worked separately, through the August Summit booth
# follow-up Danielle is running. Roman to Danielle in Slack 2026-08-20: "auto
# email campaign to all charter teachers from you (except sage oak)";
# reconfirmed to this session 2026-08-21 ("exclude sage oak, they will be
# separate"). Excluded at every segment, not just wave 1.
EXCLUDE_SCHOOLS = {"Sage Oak"}

# `charter_school_teacher` holds WHICH SCHOOL, not "is a teacher", so it drags
# two non-teacher populations into the union (found 2026-08-24 when Roman asked
# whether an email was going to teachers or families):
#   * school role mailboxes — vendors@, accountspayable@, ap@, noreply@ ...
#     A personally-signed "I taught K-8" email to accounts payable is a
#     deliverability problem, not just an awkward one.
#   * actual FAMILIES whose contact carries a school — they have students and
#     tutors named on them, and they belong to the family campaign.
# Matched as WHOLE WORDS anywhere in the localpart, not just at the start:
# Sage Oak's event accounts are `summit-techteam@` and `sageoaksummit@`, which a
# prefix-anchored pattern misses entirely (found 2026-08-24 reviewing the Sage
# Oak backfill candidates). Words are split on . _ - and camelCase boundaries.
ROLE_WORDS = {
    "vendor", "vendors", "vendorsupport", "vendorrelations", "vendorservices",
    "accountspayable", "accounting", "ap", "billing", "invoice", "invoices",
    "purchasing", "finance", "contracts", "contract", "contractprograms", "cp",
    "enrichment", "info", "admin", "office", "support", "contact", "help",
    "noreply", "nореply", "donotreply", "hr", "jobs", "careers", "recruiting",
    "team", "staff", "techteam", "helpdesk", "webmaster", "postmaster",
    "vendorinquiries", "orders", "reception", "frontdesk", "mail",
}


def _localpart_words(local):
    """Split an email localpart into comparable words.

    'summit-techteam' -> {summit, techteam}; 'sageoaksummit' stays whole (no
    separators to split on) and is caught by the substring pass below."""
    parts = re.split(r"[._\-+0-9]+", local)
    words = set()
    for part in parts:
        if not part:
            continue
        words.add(part.lower())
        # camelCase / TitleCase runs: VendorSupport -> vendor, support
        for w in re.findall(r"[A-Z]?[a-z]+", part):
            words.add(w.lower())
    return words


def is_role_mailbox(email):
    """True when the address is a shared/system inbox rather than a person.

    Two passes: exact word match after splitting on separators and camelCase,
    then a substring check for the run-together forms ('sageoaksummit')."""
    local = (email or "").split("@")[0]
    if not local:
        return False
    if _localpart_words(local) & ROLE_WORDS:
        return True
    flat = re.sub(r"[^a-z]", "", local.lower())
    return any(w in flat for w in ("techteam", "helpdesk", "accountspayable",
                                   "vendorsupport", "vendorrelations", "donotreply",
                                   "noreply", "frontdesk", "webmaster"))


# Run-together shared inboxes with no separator to split on ('sageoaksummit@',
# 'communityproviders@') defeat any localpart rule that does not also guess at
# real people's names. The contact's NAME is the cleaner signal: a record called
# "Summit Tech Team" is not a person no matter what its address looks like.
TEAM_NAME_WORDS = {"team", "tech", "support", "office", "department", "dept",
                   "staff", "admin", "vendor", "vendors", "providers", "services",
                   "accounts", "billing", "purchasing", "enrollment", "helpdesk"}


def looks_like_team_name(p):
    name = f"{p.get('firstname') or ''} {p.get('lastname') or ''}".lower()
    return bool(set(re.findall(r"[a-z]+", name)) & TEAM_NAME_WORDS)


def looks_like_family(p):
    """Family signals stamped by the family campaign's own tooling.

    The persona WINS over this heuristic. A contact explicitly tagged
    "Teacher of Record/EF/ES" is a teacher even when family fields are also
    stamped on them -- that is the dual-persona case the 5-persona model was
    designed for (#AP030). Kristy Doyal is exactly this: a real Heartland
    teacher who is also a parent, tagged "Teacher of Record/EF/ES;Family"."""
    if PERSONA_TOR in (p.get("a_persona") or ""):
        return False
    return bool(p.get("student_first_name") or p.get("student_names")
                or p.get("last_tutor_name") or p.get("teacher_of_record_name"))
NOT_STUDENT_TOKENS = {"a", "summer", "level", "ilead", "charter"}

TIER_4_MIN_FAMILIES = 5      # heavy referrers, pulled OUT for individual sends

# Tier 2 is "referred at some point, but not last year". Left implicit, that
# means ANY prior deal however old, and the copy says "it has been a while",
# which is true at 14 months and absurd at six years.
#
# Measured 2026-08-25: all 45 Tier 2 teachers last referred 1.2 to 1.4 years
# ago. It is one clean cohort — they referred in 24/25, sat out 25/26, and it is
# now 26/27. So this bound changes NOTHING today. It exists so that next year,
# when the 25/26 non-returners age into this tier and the 24/25 group ages past
# it, nobody gets a warm-reopen email about a student they placed with us
# before the pandemic. Past the bound, a teacher is functionally cold: Tier 1.
TIER_2_MAX_YEARS = 3

SEGMENTS = [
    ("T1", "All TORs, no history",  "Tier 1 - No referral history"),
    ("T2", "Referred, not last yr", "Tier 2 - Warm reopen"),
    ("T3", "Last year's referrers", "Tier 3 - Last year"),
    ("T4", "Heavy referrers",       "Tier 4 - Individual sends (NOT a campaign list)"),
]



# Deal names are "Parent - Student - School N - YY/YY", optionally prefixed with
# a PROGRAM marker. Roman 2026-08-26: "we would denote pipelines in the names
# like summer 2025 was an ilead program". Measured:
#
#   "A"           626 deals, 616 in the "Amy - Charter - iLead - Level Up" pipeline
#   "T"            88 deals,  82 in the "Terri - Charter - iLead - Level Up" pipeline
#   "Summer 2025" 110 deals, all in Amy's Level Up pipeline
#
# So A is Amy and T is Terri, the two iLEAD Level Up pipelines, and Summer 2025
# is an iLEAD programme. The family is then the SECOND segment:
#   "A - Emani Newman - Zoe - iLEAD Level Up 3 (Dec) - 24/25"
#        ^family        ^student
#
# An earlier pass treated these prefixes as junk and returned no family at all,
# which silently discarded 824 deals worth of real households and dropped eight
# teachers out of Tier 4. The prefix must be SKIPPED, not used as grounds to
# drop the deal.
PROGRAM_PREFIX = re.compile(
    r"^(?:[at]|summer|winter|spring|fall)(?:\s*20\d\d)?$", re.I)


def _segments(dealname):
    """Deal-name segments with any programme prefix stripped from the front."""
    parts = [x.strip() for x in (dealname or "").split(" - ") if x.strip()]
    if parts and PROGRAM_PREFIX.match(parts[0]):
        parts = parts[1:]
    return parts


def family_key(dealname):
    """The parent segment of a deal name, after skipping a programme prefix."""
    parts = _segments(dealname)
    return parts[0].lower() if parts else None


def student_from(dealname, parent_first):
    """The student segment, after skipping a programme prefix."""
    parts = _segments(dealname)
    if len(parts) < 2:
        return None
    cand = parts[1].split(" ")[0].strip(" .,")
    key = cand.lower()
    if (not cand or key == parent_first or key in NOT_STUDENT_TOKENS
            or not re.match(r"^[A-Za-zÀ-ÿ'\-]+$", cand)):
        return None
    return cand


def hs(method, path, **kw):
    for _ in range(5):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=40, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10) or 10))
            continue
        r.raise_for_status()
        return r.json() if r.text else {}
    r.raise_for_status()


def search_all(obj, filter_groups, props):
    out, after = {}, None
    while True:
        body = {"filterGroups": filter_groups, "properties": props, "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", f"/crm/v3/objects/{obj}/search", json=body)
        for r in j.get("results", []):
            out[r["id"]] = r["properties"]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return out
        time.sleep(0.12)


def list_members(list_id):
    ids, after = [], None
    while True:
        j = hs("GET", f"/crm/v3/lists/{list_id}/memberships?limit=250"
               + (f"&after={after}" if after else ""))
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return ids


TOR_PROPS = ["email", "firstname", "lastname", "charter_school_teacher", "hs_lead_status",
             "a_persona", "hs_marketable_status", "hs_email_optout",
             "hs_email_hard_bounce_reason", "hubspot_owner_id", "createdate",
             "tor_family_count", "tor_student_count", "tor_families_lapsed", "tor_segment",
             "hs_additional_emails",   # teachers use school AND personal addresses
             # non-teacher detection (see ROLE_MAILBOX / looks_like_family)
             "student_first_name", "student_names", "last_tutor_name", "teacher_of_record_name"]


PERSONA_TOR = "Teacher of Record/EF/ES"


def intake_referrals():
    """Teachers named on FAMILY contacts via legacy intake capture.

    Predates the deal-level teacher association, so this is the only evidence
    of referrals made before 25/26. Returns ({email: earliest_family_createdate},
    {normalised name: earliest_family_createdate})."""
    props = ["teacher_of_record_email_address", "teacher_of_record_name", "createdate"]
    by_email, by_name = {}, {}
    for field in ("teacher_of_record_email_address", "teacher_of_record_name"):
        fams = search_all("contacts",
                          [{"filters": [{"propertyName": field, "operator": "HAS_PROPERTY"}]}],
                          props)
        for p in fams.values():
            created = p.get("createdate")
            e = (p.get("teacher_of_record_email_address") or "").strip().lower()
            n = norm_name(p.get("teacher_of_record_name"))
            if e and created:
                by_email[e] = min(by_email.get(e, created), created)
            if n and " " in n and created:
                by_name[n] = min(by_name.get(n, created), created)
    return by_email, by_name


def load_tors():
    """THE audience: contacts carrying the Teacher of Record persona."""
    tors = search_all("contacts", [{"filters": [
        {"propertyName": "a_persona", "operator": "CONTAINS_TOKEN", "value": PERSONA_TOR}]}],
        TOR_PROPS)
    print(f"  a_persona = {PERSONA_TOR}: {len(tors)}")
    return tors


def backfill_queue(tors):
    """People the other signals think are teachers but the persona does not know
    about. Reported so a human can tag them; NEVER emailed from here."""
    others = [
        ("lead status = Charter School Teacher TOR/EF",
         [{"filters": [{"propertyName": "hs_lead_status", "operator": "EQ",
                        "value": "Charter School Teacher TOR/EF"}]}]),
        ("charter_school_teacher is known",
         [{"filters": [{"propertyName": "charter_school_teacher", "operator": "HAS_PROPERTY"}]}]),
        ("educational_facillitator_teacher_of_record = true",
         [{"filters": [{"propertyName": "educational_facillitator_teacher_of_record",
                        "operator": "EQ", "value": "true"}]}]),
    ]
    seen = {}
    for label, groups in others:
        for cid, p in search_all("contacts", groups, TOR_PROPS).items():
            if cid not in tors:
                seen.setdefault(cid, (label, p))
    real, junk = {}, {}
    for cid, (label, p) in seen.items():
        # same non-teacher tests the audience uses
        if is_role_mailbox(p.get("email")) or looks_like_family(p):
            junk[cid] = (label, p)
        else:
            real[cid] = (label, p)
    return real, junk


def load_charter_deals():
    """Every charter-pipeline deal, back to EVER_SINCE.

    Tier 2 is "referred at some point but not last year", which cannot be
    computed from a 25/26-only window — a teacher with no recent deal looks
    identical to one who has never referred anybody."""
    since_ms = int(datetime.fromisoformat(EVER_SINCE).replace(tzinfo=timezone.utc).timestamp() * 1000)
    deals, after = {}, None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "IN", "values": sorted(CHARTER_PIPELINES)},
            {"propertyName": "createdate", "operator": "GTE", "value": since_ms}]}],
            "properties": ["dealname", "amount", "dealstage", "pipeline", "createdate",
                           "teacher_of_record_name", "teacher_of_record_email",
                           "tor_first_name", "tor_last_name"],
            "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", "/crm/v3/objects/deals/search", json=body)
        for r in j.get("results", []):
            deals[r["id"]] = r["properties"]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return deals
        time.sleep(0.12)


def norm_name(s):
    """Accent-fold and turn punctuation into a separator (not nothing).

    The old version stripped every non [a-z ] char, which silently glued
    hyphenated surnames together ("Negrete-Claar" -> "negreteclaar") and
    deleted accented letters outright ("Véronique" -> "vronique", so the
    unaccented deal value could never match the accented contact)."""
    s = (s or "").replace("\u2019", "'").replace("\u2018", "'")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z]+", " ", s).lower()).strip()


def name_tokens(raw):
    """norm_name + un-reverse 'Last, First' + drop middle initials.

    Ocean Grove (ieminc.org) deals arrive as "Wood, Colleen " and
    "O'Hagan, Whitney"; iLEAD/Visions deals carry middle initials
    ("Dawn L Gordon"). Both forms name a contact we already have."""
    raw = raw or ""
    if "," in raw:
        head, _, tail = raw.partition(",")
        raw = f"{tail} {head}"
    toks = [t for t in norm_name(raw).split() if t]
    return [t for t in toks if len(t) > 1] or toks


def parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def build_index(tors):
    """Four lookup views over the TOR universe, tried in order of strictness."""
    by_full, by_set, by_first_last = {}, collections.defaultdict(list), collections.defaultdict(list)
    by_localpart = collections.defaultdict(list)
    for cid, p in tors.items():
        t = name_tokens(f"{p.get('firstname', '')} {p.get('lastname', '')}")
        if len(t) >= 2:               # single-token names are too ambiguous to match on
            by_full.setdefault(" ".join(t), []).append(cid)
            by_set[frozenset(t)].append(cid)
            by_first_last[(t[0], frozenset(t[1:]))].append(cid)
        em = (p.get("email") or "").lower()
        if "@" in em:
            by_localpart[norm_name(em.split("@")[0]).replace(" ", "")].append(cid)
    return by_full, by_set, by_first_last, by_localpart


def match_one(raw, idx):
    """(cid, tier) or (None, reason). A tier only fires when it is UNIQUE —
    two contacts matching the same way is reported, never guessed at."""
    by_full, by_set, by_first_last, by_localpart = idx
    t = name_tokens(raw)
    if not t:
        return None, "empty"
    if len(t) == 1:                   # bare surname / email localpart on the deal
        ids = by_localpart.get(t[0])
        return (ids[0], "email-localpart") if ids and len(ids) == 1 else (None, "single-token")
    for tier, ids in (("exact", by_full.get(" ".join(t))),
                      ("token-set", by_set.get(frozenset(t)))):
        if ids:
            return (ids[0], tier if len(ids) == 1 else tier + "-AMBIGUOUS")
    # married / double surnames: deal has "Pfeifer Tolan", contact has "Tolan"
    first, surnames = t[0], frozenset(t[1:])
    cands = {cid for (f, s), ids in by_first_last.items()
             if f == first and (s <= surnames or surnames <= s) for cid in ids}
    if cands:
        return (sorted(cands)[0], "surname-subset" if len(cands) == 1 else "surname-subset-AMBIGUOUS")
    ids = by_localpart.get("".join(t))
    return (ids[0], "email-localpart") if ids and len(ids) == 1 else (None, "no-match")


def attribute(tors, deals):
    """Deal -> TOR contact. EMAIL FIRST, then the name matcher.

    Roman 2026-08-25 pointed at the deal-level teacher properties. There are
    three, and the email one is both better covered and exactly matchable:

        school yr   deals   tor_name   tor_EMAIL
        2024/25      2105        528       1127
        2025/26      2221       2181       2187
        TOTAL        5555       2788       3390

    605 deals carry an email and no name, and in 24/25 email coverage is more
    than double, which is exactly the era where attribution was thinnest. An
    email is also an exact key: no accent folding, no hyphenated surnames, no
    "Last, First" reversal, no middle initials, and no ambiguity when two
    teachers share a name.

    An earlier version of this file recorded "deals carry no teacher email".
    That was wrong: it checked `teacher_of_record_email_address`, which is the
    CONTACT property. The deal property is `teacher_of_record_email`.

    Returns (hits, unmatched, ambiguous, by_tier).
    """
    idx = build_index(tors)
    # Map EVERY address a contact has, not just the primary. Kristy Doyal's
    # deals carry kristy.doyal@heartlandcharterschool.com while her contact's
    # primary is a gmail address; without the secondaries she reads as an
    # orphan despite being in the audience already. Teachers commonly have a
    # school address and a personal one.
    by_email = {}
    for cid, p in tors.items():
        addrs = [(p.get("email") or "")]
        addrs += (p.get("hs_additional_emails") or "").split(";")
        for a in addrs:
            a = a.strip().lower()
            if a:
                by_email.setdefault(a, cid)

    hits, unmatched, ambiguous = collections.defaultdict(list), collections.Counter(), set()
    by_tier = collections.Counter()
    for did, d in deals.items():
        # 1. exact email match. Most reliable key we have.
        e = (d.get("teacher_of_record_email") or "").strip().lower()
        # placeholders the PO flow writes when the teacher is unknown
        if e in ("none@wetutorathome.com", "unknown", "none", "n/a", "na"):
            e = ""
        if e and e in by_email:
            hits[by_email[e]].append(did)
            by_tier["email"] += 1
            continue

        # 2. name, falling back to tor_first_name / tor_last_name
        raw = d.get("teacher_of_record_name")
        if not norm_name(raw):
            first = (d.get("tor_first_name") or "").strip()
            last = (d.get("tor_last_name") or "").strip()
            raw = f"{first} {last}".strip()
        if not norm_name(raw):
            if e:
                unmatched["@" + e] += 1  # "@" marks an EMAIL orphan, see below
            continue
        cid, tier = match_one(raw, idx)
        if not cid:
            unmatched[norm_name(raw)] += 1
            continue
        if tier.endswith("-AMBIGUOUS"):
            ambiguous.add(norm_name(raw))
        by_tier[tier] += 1
        hits[cid].append(did)
    return hits, unmatched, ambiguous, by_tier


def profile(tors, deals, hits, gap, intake=None):
    """Per-teacher rollup: 25/26 families+students, 26/27 families, lapsed families."""
    cutoff = datetime.fromisoformat(YEAR_2627).replace(tzinfo=timezone.utc)
    start_2526 = datetime.fromisoformat(SINCE).replace(tzinfo=timezone.utc)
    rows = {}
    for cid, p in tors.items():
        fam25, fam2627, students, amount25 = set(), set(), {}, 0.0
        fam_older, last_older = set(), None
        for did in hits.get(cid, []):
            d = deals[did]
            parent = family_key(d.get("dealname"))
            created = parse_dt(d.get("createdate"))
            in_2627 = bool(created and created >= cutoff)
            in_2526 = bool(created and start_2526 <= created < cutoff)

            # Revenue counts regardless of whether the household name parses.
            if in_2526:
                try:
                    amount25 += float(d.get("amount") or 0)
                except (TypeError, ValueError):
                    pass

            if parent is None:
                pass                      # genuinely unparseable, not a prefix
            elif in_2627:
                fam2627.add(parent)
            elif in_2526:
                fam25.add(parent)
            else:
                fam_older.add(parent)          # referred, but before 25/26
                if created and (last_older is None or created > last_older):
                    last_older = created
            cand = student_from(d.get("dealname"), parent.split(" ")[0] if parent else "")
            if cand:
                students.setdefault(cand.lower(), cand)
        rows[cid] = {
            "email": (p.get("email") or "").strip(),
            "name": f"{p.get('firstname', '')} {p.get('lastname', '')}".strip(),
            "school": p.get("charter_school_teacher") or "",
            "fam25": len(fam25), "fam2627": len(fam2627),
            "fam_older": len(fam_older),
            "years_since_older": (
                round((datetime.now(timezone.utc) - last_older).days / 365.25, 1)
                if last_older else None),
            "intake_referral": False,
            "intake_age_years": None,
            "students": len(students), "amount25": round(amount25),
            "lapsed": 0,          # filled by caller from associations
            "firstname": (p.get("firstname") or "").strip(),
            "is_family": looks_like_family(p),
            "is_team": looks_like_team_name(p),
            "persona": p.get("a_persona") or "",
            "optout": p.get("hs_email_optout") == "true",
            "marketable": p.get("hs_marketable_status") == "true",
            "bounced": bool(p.get("hs_email_hard_bounce_reason")),
        }
    return rows


def segment_of(r):
    """Relationship history, most-trusted first. Order matters."""
    recent = r["fam25"] + r["fam2627"]          # trusted us this year or last
    if recent >= TIER_4_MIN_FAMILIES:
        return "T4"                             # heavy referrer -> individual send
    if recent >= 1:
        return "T3"                             # last year's referrers
    if r["fam_older"] >= 1:
        # too long ago to greet as a lapsed relationship: they are cold now
        age = r.get("years_since_older")
        if age is not None and age > TIER_2_MAX_YEARS:
            return "T1"
        return "T2"                             # referred once, but not lately
    return "T1"                                 # no referral history at all


def mailable(r):
    """Exclusions the campaign applies on top of HubSpot's own suppression."""
    if r["school"] in EXCLUDE_SCHOOLS:
        return f"{r['school']} (worked separately)"
    if not r["email"]:
        return "no email"
    if is_role_mailbox(r["email"]) or r["is_team"]:
        return "role mailbox (not a person)"
    if r["is_family"]:
        return "family, not a teacher"
    if r["email"].lower().endswith(INTERNAL_DOMAIN):
        return "internal"
    if r["optout"]:
        return "opted out"
    if r["bounced"]:
        return "hard bounced"
    if not r["marketable"]:
        return "non-marketable"
    return ""


# ---------------------------------------------------------------- writes

def write_props(rows):
    payload = [{"id": cid, "properties": {
        "tor_family_count": str(r["fam2627"] or r["fam25"]),
        "tor_student_count": str(r["students"]),
        "tor_families_lapsed": str(r["lapsed"]),
        "tor_segment": segment_of(r),
    }} for cid, r in rows.items()]
    done = 0
    for i in range(0, len(payload), 100):
        hs("POST", "/crm/v3/objects/contacts/batch/update", json={"inputs": payload[i:i + 100]})
        done += len(payload[i:i + 100])
        print(f"  stamped {done}/{len(payload)}")
        time.sleep(0.2)


def build_lists(rows):
    existing = {}
    j = hs("POST", "/crm/v3/lists/search", json={"query": LIST_PREFIX, "count": 250, "offset": 0})
    for L in j.get("lists", []):
        existing[L.get("name")] = L.get("listId")
    for code, _short, suffix in SEGMENTS:
        name = LIST_PREFIX + suffix
        members = [cid for cid, r in rows.items()
                   if segment_of(r) == code and not mailable(r)]
        lid = existing.get(name)
        if not lid:
            created = hs("POST", "/crm/v3/lists", json={
                "name": name, "objectTypeId": "0-1", "processingType": "MANUAL"})
            lid = created["list"]["listId"]
            print(f"  created list {lid}  {name}")
        else:
            cur = list_members(lid)
            if cur:
                hs("PUT", f"/crm/v3/lists/{lid}/memberships/remove", json=cur)
            print(f"  refreshed list {lid}  {name} (cleared {len(cur)})")
        for i in range(0, len(members), 100):
            hs("PUT", f"/crm/v3/lists/{lid}/memberships/add", json=members[i:i + 100])
        print(f"    -> {len(members)} members")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-props", action="store_true",
                    help="stamp tor_* properties onto the TOR contacts")
    ap.add_argument("--build-lists", action="store_true",
                    help="create/refresh the six static segment lists")
    ap.add_argument("--json", default="", help="dump the per-teacher rollup to this path")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN not set")

    print("TOR audience (a_persona is authoritative):")
    tors = load_tors()

    print(f"\ncharter deals created since {SINCE}:")
    deals = load_charter_deals()
    named = sum(1 for d in deals.values() if d.get("teacher_of_record_name"))
    print(f"  {len(deals)} deals since {SINCE}")

    hits, unmatched, ambiguous, by_tier = attribute(tors, deals)
    print(f"  attributed to {len(hits)} teachers; "
          f"{sum(unmatched.values())} deals name a teacher with no matching contact "
          f"({len(unmatched)} distinct names)")
    print("  match tiers: " + ", ".join(f"{t}={n}" for t, n in by_tier.most_common()))
    if ambiguous:
        print(f"  ⚠ {len(ambiguous)} names match >1 contact (first wins): "
              f"{', '.join(sorted(ambiguous)[:5])}")

    gap = set(list_members(GAP_LIST_ID))
    by_email, by_name = intake_referrals()
    rows = profile(tors, deals, hits, gap)

    # Referrals the deal data never recorded (pre-25/26). Only matters for
    # teachers the deals show as having no history at all.
    recovered = 0
    for cid, r in rows.items():
        if r["fam25"] or r["fam2627"] or r["fam_older"]:
            continue
        e = (r["email"] or "").lower()
        n = norm_name(r["name"])
        created = by_email.get(e) or (by_name.get(n) if " " in n else None)
        if not created:
            continue
        dt_ = parse_dt(created)
        if not dt_:
            continue
        # The family contact's createdate is a PROXY for when the referral
        # happened, and a weak one: a family created five weeks ago naming this
        # teacher means a referral that just happened, not a lapsed one. Route
        # by age or a current referrer lands in the "it has been a while" tier.
        age = round((datetime.now(timezone.utc) - dt_).days / 365.25, 1)
        r["intake_referral"] = True
        r["intake_age_years"] = age
        if age < 1.0:
            r["fam25"] = 1          # recent enough to be a current relationship
        else:
            r["fam_older"] = 1
            r["years_since_older"] = age
        recovered += 1
    rec_recent = sum(1 for r in rows.values() if r.get("intake_referral") and (r.get("intake_age_years") or 9) < 1.0)
    print(f"\n  referral history recovered from family intake fields: {recovered} "
          f"(deals did not record teachers before 25/26)")
    print(f"    of those, {rec_recent} are RECENT (intake family under a year old) "
          f"and route to Tier 3, not the lapsed tier")

    # lapsed-family count comes from the contact-to-contact Family association
    tor_ids = list(tors)
    for i in range(0, len(tor_ids), 100):
        j = hs("POST", "/crm/v4/associations/contact/contact/batch/read",
               json={"inputs": [{"id": c} for c in tor_ids[i:i + 100]]})
        for row in j.get("results", []):
            cid = str(row["from"]["id"])
            fams = [str(t["toObjectId"]) for t in row.get("to", [])
                    if any("Family" in (l.get("label") or "") for l in t.get("associationTypes", []))]
            rows[cid]["lapsed"] = len([f for f in fams if f in gap])
        time.sleep(0.1)

    print("\n=== SEGMENTS ===")
    print(f"  {'code':<4} {'segment':<22} {'total':>6} {'mailable':>9} {'excluded':>9}")
    for code, short, _suffix in SEGMENTS:
        cell = [r for r in rows.values() if segment_of(r) == code]
        ok = [r for r in cell if not mailable(r)]
        print(f"  {code:<4} {short:<22} {len(cell):>6} {len(ok):>9} {len(cell) - len(ok):>9}")
    print(f"  {'':<4} {'TOTAL':<22} {len(rows):>6} "
          f"{sum(1 for r in rows.values() if not mailable(r)):>9} "
          f"{sum(1 for r in rows.values() if mailable(r)):>9}")

    print("\n  exclusions by reason:")
    for reason, n in collections.Counter(mailable(r) for r in rows.values()).most_common():
        if reason:
            print(f"    {n:>5}  {reason}")

    t2 = [r for r in rows.values() if segment_of(r) == "T2" and not mailable(r)]
    ages = sorted(r["years_since_older"] for r in t2 if r.get("years_since_older"))
    if ages:
        print(f"\n  Tier 2 recency: last referral {ages[0]} to {ages[-1]} years ago "
              f"(bound is {TIER_2_MAX_YEARS}y; past it they fall to Tier 1)")

    print("\n  teachers with lapsed (gap-list) families: "
          f"{sum(1 for r in rows.values() if r['lapsed'])} "
          f"({sum(r['lapsed'] for r in rows.values())} families)")

    real, junk = backfill_queue(tors)
    print(f"\n=== PERSONA BACKFILL QUEUE ===")
    print(f"  {len(real)} contacts look like teachers but carry NO Teacher of Record persona.")
    print(f"  They are NOT in the audience. Tag them in the portal and they join the next run.")
    print(f"  ({len(junk)} more were skipped as families or role mailboxes.)")
    by_school = collections.Counter((p.get("charter_school_teacher") or "(none)")
                                    for _l, p in real.values())
    for k, v in by_school.most_common(10):
        print(f"    {v:>4}  {k}")

    if unmatched:
        # Two kinds, and they need different work. An EMAIL orphan is a teacher
        # we have an exact address for and simply no contact record: create it
        # and they join the tiers immediately, no guessing. A NAME orphan needs
        # a human to decide who is meant.
        by_email_orphan = {k[1:]: v for k, v in unmatched.items() if k.startswith("@")}
        by_name_orphan = {k: v for k, v in unmatched.items() if not k.startswith("@")}
        if by_email_orphan:
            print(f"\n  ⚠ EMAIL on the deal but NO contact record: "
                  f"{len(by_email_orphan)} addresses, {sum(by_email_orphan.values())} deals")
            print("    NB: charter POs are MONTHLY, so deal count overstates the")
            print("    relationship. Hannah Belcher's 43 deals are 7 families.")
            print("    Actionable without guesswork: create the contact, tag the persona,")
            print("    and they fall into the right tier on the next run.")
            for n, c in sorted(by_email_orphan.items(), key=lambda kv: -kv[1])[:10]:
                print(f"    {c:>3} deals  {n}")
        if by_name_orphan:
            print(f"\n  ⚠ NAME only, no contact match: "
                  f"{len(by_name_orphan)} names, {sum(by_name_orphan.values())} deals")
            print("    Needs a human to decide who is meant.")
            for n, c in sorted(by_name_orphan.items(), key=lambda kv: -kv[1])[:10]:
                print(f"    {c:>3} deals  {n}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {cid: dict(r, segment=segment_of(r), excluded=mailable(r))
             for cid, r in rows.items()}, indent=2))
        print(f"\n  wrote {args.json}")

    if args.write_props:
        print("\nstamping tor_* properties:")
        write_props(rows)
    if args.build_lists:
        print("\nbuilding segment lists:")
        build_lists(rows)
    if not (args.write_props or args.build_lists):
        print("\n(read-only — pass --write-props / --build-lists to write)")


if __name__ == "__main__":
    main()

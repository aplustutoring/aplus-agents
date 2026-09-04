#!/usr/bin/env python3
"""Teacher outreach 26/27: create the marketing-email DRAFTS for the campaign
rail (lists 3 and 4) by cloning the plain August template and swapping the
copy. Nothing is published or sent; Roman/Danielle review in the portal.

Copy source of truth: ops/messenger/templates/teacher-outreach-2026-09/campaign_cold.md.
Base email: 219949380453 (start_from_scratch, one body module + signature module).

  python3 scripts/teacher_outreach_drafts.py              # dry run: prints what would be created
  python3 scripts/teacher_outreach_drafts.py --create     # clone + patch, leaves DRAFT

Creates 6 drafts: wave 1 (Compass + Elite, new static list) x3, IEM (list 3213)
x3. Later stranger-school waves retarget the wave-1 drafts (copy is tokenised
on {{ contact.school_canonical }}), so no new drafts per school.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent.parent
    load_dotenv(_here / ".env", override=False)
    if "/.claude/worktrees/" in str(_here):
        load_dotenv(Path(str(_here).split("/.claude/worktrees/")[0]) / ".env", override=False)
except ImportError:
    pass

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
PORTAL = "6312752"
BASE_EMAIL = "219949380453"
BODY_MODULE = "module_17845724969542"
SIG_MODULE = "module_17845728089534"
LIST_STRANGER = 3212
LIST_IEM = 3213
WAVE1_NAME = "Teacher Outreach 26/27 - 3a Wave 1 Compass + Elite (campaign)"
WAVE1_SCHOOLS = {"Compass Charter Schools", "Elite Academic Academy"}
FORM = "https://share.hsforms.com/2rpbTDqE6RWWHjeKdFnEFgA3ray8"
FLYER = "https://6312752.fs1.hubspotusercontent-na1.net/hubfs/6312752/A%2B%20Tutoring%20-%20Teacher%20Scholarship%20Flyer.png"
FROM = {"fromName": "Danielle Brodetsky", "replyTo": "info@wetutorathome.com"}
FIRST = "{{ personalization_token('contact.firstname', 'there') }}"
SCHOOL = "{{ personalization_token('contact.school_canonical', 'your school') }}"
SIG = ("<p>Danielle Brodetsky<br>Director of School Partnerships, A+ Tutoring<br>"
       "<span style=\"font-size:12px;color:#555\">Tutoring Program Design Badge, National Student Support "
       "Accelerator at Stanford University, 2026 to 2029</span></p>")
BTN = f"<p><a href=\"{FORM}\" style=\"display:inline-block;padding:10px 18px;background:#EF5829;color:#fff;text-decoration:none;border-radius:4px\">Nominate a student</a></p>"


def hs(method, path, **kw):
    for _ in range(6):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)) or 10)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}


def p(*lines):
    return "".join(f"<p>{l}</p>" for l in lines)


def email1(school_line):
    return p(f"Hi {FIRST},",
             "I taught fourth grade before I did this job, and I remember the two or three kids every year who needed more than I could give them in a class of 32.",
             f"A+ Tutoring is an approved vendor at {school_line}, and this summer Stanford's National Student Support Accelerator awarded us its Tutoring Program Design Badge. Through our Teacher Scholarship Program, you can nominate up to two students for free one-on-one tutoring, live with a credentialed tutor. It doesn't come out of the student's allocation, so it's a way to see how we work before you send a PO.",
             "Nominating takes about two minutes: the student's name, grade, a sentence on why, and a parent contact.") + BTN + p(
             f"If you'd rather see it on one page first, <a href=\"{FLYER}\">here is the flyer</a>.", "Danielle")


def email2():
    return p(f"Hi {FIRST},",
             "In case it helps to know what you'd be nominating a student into: one tutor, the same one every session, matched to where the student is. That design is what Stanford reviewed when it awarded the Badge. Last year at iLEAD Antelope Valley, 16 of 20 students in the Tier 3 program showed measurable MAP Growth, averaging 19.4 RIT points at about 17 hours each.",
             "Parents get session notes. You get a progress update. Nobody is in the dark.") + BTN + p("Danielle")


def email3():
    return p(f"Hi {FIRST},",
             "I'm closing this round of scholarship nominations Friday so we can get students matched and started before October.",
             "If there's a student you've been meaning to send, this is the week. Two minutes, nothing off their allocation, no PO.") + BTN + p(
             "Any question, just reply. I answer my own email.", "Danielle")


DRAFTS = [
    # (name, subject, preview, body_fn, list_key)
    ("Teacher Outreach 26/27 - Campaign - Email 1 (stranger schools)", f"A free tutor for one of your students at {SCHOOL}",
     "Nominate up to two students for free one-on-one tutoring. Two minutes, nothing off their allocation.", lambda: email1(SCHOOL), "wave1"),
    ("Teacher Outreach 26/27 - Campaign - Email 2 (stranger schools)", "What the tutoring actually looks like",
     "One tutor, the same one every session. 16 of 20 students improved at iLEAD Antelope Valley.", email2, "wave1"),
    ("Teacher Outreach 26/27 - Campaign - Email 3 (stranger schools)", "Closing nominations for this round",
     "If there's a student you've been meaning to send, this is the week.", email3, "wave1"),
    ("Teacher Outreach 26/27 - Campaign - Email 1 (IEM)", "A free tutor for one of your students",
     "Nominate up to two students for free one-on-one tutoring. Two minutes, nothing off their allocation.",
     lambda: email1("Ocean Grove, Sky Mountain, and South Sutter"), "iem"),
    ("Teacher Outreach 26/27 - Campaign - Email 2 (IEM)", "What the tutoring actually looks like",
     "One tutor, the same one every session. 16 of 20 students improved at iLEAD Antelope Valley.", email2, "iem"),
    ("Teacher Outreach 26/27 - Campaign - Email 3 (IEM)", "Closing nominations for this round",
     "If there's a student you've been meaning to send, this is the week.", email3, "iem"),
]


def list_members(list_id):
    ids, after = [], None
    while True:
        j = hs("GET", f"/crm/v3/lists/{list_id}/memberships?limit=250" + (f"&after={after}" if after else ""))
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return ids


def wave1_list(create):
    """Static sub-list of list 3: Compass + Elite."""
    ids = list_members(LIST_STRANGER)
    keep = []
    for i in range(0, len(ids), 100):
        j = hs("POST", "/crm/v3/objects/contacts/batch/read",
               json={"inputs": [{"id": c} for c in ids[i:i + 100]], "properties": ["school_canonical"]})
        keep += [str(r["id"]) for r in j.get("results", []) if (r["properties"].get("school_canonical") or "") in WAVE1_SCHOOLS]
    print(f"wave 1 (Compass + Elite): {len(keep)} of {len(ids)} in list {LIST_STRANGER}")
    if not create:
        return None
    s = hs("POST", "/crm/v3/lists/search", json={"query": WAVE1_NAME, "count": 20})
    hit = next((l for l in s.get("lists", []) if l.get("name") == WAVE1_NAME), None)
    lid = hit["listId"] if hit else hs("POST", "/crm/v3/lists", json={"name": WAVE1_NAME, "objectTypeId": "0-1",
                                                                     "processingType": "MANUAL"})["list"]["listId"]
    if hit:
        cur = set(list_members(lid))
        rm = sorted(cur - set(keep))
        for i in range(0, len(rm), 250):
            hs("PUT", f"/crm/v3/lists/{lid}/memberships/remove", json=rm[i:i + 250])
    for i in range(0, len(keep), 250):
        hs("PUT", f"/crm/v3/lists/{lid}/memberships/add", json=keep[i:i + 250])
    print(f"  ✔ wave-1 list {lid}")
    return lid


def make_draft(name, subject, preview, html, list_id):
    clone = hs("POST", "/marketing/v3/emails/clone", json={"id": BASE_EMAIL, "cloneName": name})
    eid = clone["id"]
    e = hs("GET", f"/marketing/v3/emails/{eid}")
    widgets = e["content"]["widgets"]
    widgets[BODY_MODULE]["body"]["html"] = html
    widgets[SIG_MODULE]["body"]["html"] = SIG
    if "preview_text" in widgets:
        widgets["preview_text"]["body"]["value"] = preview
    patch = {"name": name, "subject": subject, "from": FROM,
             "to": {"contactIlsLists": {"include": [int(list_id)], "exclude": []},
                    "contactLists": {"include": [], "exclude": []}, "suppressGraymail": True},
             "content": {"widgets": widgets}}
    hs("PATCH", f"/marketing/v3/emails/{eid}", json=patch)
    return eid, f"https://app.hubspot.com/email/{PORTAL}/edit/{eid}/content"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--create", action="store_true", help="clone + patch drafts (default: dry run)")
    ap.add_argument("--out", default="teacher_outreach_drafts.json")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    w1 = wave1_list(args.create)
    lists = {"wave1": w1, "iem": LIST_IEM}
    out = {}
    for name, subject, preview, body, lk in DRAFTS:
        if not args.create:
            print(f"  would create: {name!r} → list {lists[lk] or WAVE1_NAME} | subject {subject!r}")
            continue
        eid, url = make_draft(name, subject, preview, body(), lists[lk])
        out[name] = {"email_id": eid, "list_id": lists[lk], "url": url}
        print(f"  ✔ {name} → email {eid}\n     {url}")
        time.sleep(0.3)
    if args.create:
        Path(args.out).write_text(json.dumps({"wave1_list": w1, "drafts": out}, indent=1))
        print(f"snapshot → {args.out}")
    else:
        print("DRY RUN — nothing created. Re-run with --create.")


if __name__ == "__main__":
    main()

"""Persona backfill from the approved rule spec (Roman 2026-08-25).

APPEND-ONLY: touches ONLY contacts whose a_persona is EMPTY. First-match
priority: staff-domain -> deal-pipeline map -> lead status -> intake
fingerprints -> no_identity (left empty, flagged in audit). Dual evidence
sets multiple personas. Full per-contact audit written to JSON.
--go = UPDATE-only email-keyed import; dry run otherwise."""
import io
import json
import os
import sys
import time
from collections import Counter

import requests
from dotenv import load_dotenv

load_dotenv("/Users/romanslavinsky/code/aplus-agents/.env")
TOK = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN")
H = {"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"}
B = "https://api.hubapi.com"
GO = "--go" in sys.argv

SCHOOL_DOM = {"ileadexploration.org", "ileadav.org", "ileadlancaster.org", "ieminc.org", "viedu.org",
              "gormanlc.org", "eliteacademic.com", "heartlandcharterschool.com", "compasscharters.org",
              "pacificcharters.org", "pacificcoastacademy.org", "granitemountainschool.com",
              "heartwoodcharterschool.org", "theblueridgeacademy.com", "hcs.k12.ca.us", "forestcharter.com",
              "taylion.com", "suncoastprep.org", "sageoak.education"}
P_FAMILY, P_TUTOR, P_STUDENT, P_DM, P_TOR = ("Family", "Tutors", "Student",
                                             "Decision Maker/Director", "Teacher of Record/EF/ES")
PIPE_PERSONA = {
    "971802": P_TUTOR,                       # New Tutor (recruiting)
    "917641511": P_TOR,                      # Teacher Scholarship - Teachers
    "145539386": P_DM,                       # School Partnership Tracking
    "918901819": P_FAMILY, "922794133": P_FAMILY,   # TSP Families / Trial Scheduling
    # revenue pipelines -> Family
    "default": P_FAMILY, "16547180": P_FAMILY, "3067397": P_FAMILY, "16858643": P_FAMILY,
    "907748": P_FAMILY, "72281989": P_FAMILY, "88841552": P_FAMILY, "1066195": P_FAMILY,
    "5119061": P_FAMILY, "30830920": P_FAMILY, "30837103": P_FAMILY, "19120821": P_FAMILY,
    "75e28846-ad0d-4be2-a027-5e1da6590b98": P_FAMILY, "21277473": P_FAMILY, "16195908": P_FAMILY,
    "2265590": P_FAMILY, "893740885": P_FAMILY,
}
STATUS_PERSONA = {
    "Tutor-Active": P_TUTOR, "Student": P_STUDENT, "Teacher in a School": P_DM,
    "Charter School Teacher TOR/EF": P_TOR,
    "Using Someone Else": P_FAMILY, "OPEN_DEAL": P_FAMILY, "Past Customer": P_FAMILY,
    "NEW": P_FAMILY, "ATTEMPTED_TO_CONTACT": P_FAMILY, "We Connected": P_FAMILY,
    "QTL - Charter": P_FAMILY, "QTL - Diagnostic Sent": P_FAMILY, "CAP": P_FAMILY,
    "Meeting Booked": P_FAMILY,
}

PROPS = ["a_persona", "hs_lead_status", "email", "firstname", "lastname",
         "charter_school_family_", "student_school", "parent_email", "parent_first_name"]
rows = []
after = None
while True:
    url = f"{B}/crm/v3/objects/contacts?limit=100&properties=" + ",".join(PROPS) + (f"&after={after}" if after else "")
    j = requests.get(url, headers=H, timeout=30).json()
    rows += j.get("results", [])
    after = (j.get("paging", {}).get("next") or {}).get("after")
    if not after:
        break
empty = [c for c in rows if not (c["properties"].get("a_persona") or "").strip()]
print(f"contacts {len(rows)} | empty persona {len(empty)}")


def is_staff(email):
    if "@" not in (email or ""):
        return None
    d = email.rsplit("@", 1)[1].lower()
    if d in SCHOOL_DOM:
        return d
    for s in SCHOOL_DOM:
        if d.endswith("." + s) and not d[: -len(s) - 1].startswith("student"):
            return d
    return None


ids = [str(c["id"]) for c in empty]
deal_of = {}
for i in range(0, len(ids), 100):
    a = requests.post(f"{B}/crm/v4/associations/contact/deal/batch/read", headers=H,
                      json={"inputs": [{"id": c} for c in ids[i:i + 100]]}, timeout=30).json()
    for row in a.get("results", []):
        deal_of[str(row["from"]["id"])] = [str(t["toObjectId"]) for t in row.get("to", [])]
    if i % 2000 == 0:
        print(f"  assoc {i}/{len(ids)}")
    time.sleep(0.05)
all_d = sorted({d for ds in deal_of.values() for d in ds})
dpipe = {}
for i in range(0, len(all_d), 100):
    r = requests.post(f"{B}/crm/v3/objects/deals/batch/read", headers=H, timeout=30,
                      json={"inputs": [{"id": d} for d in all_d[i:i + 100]], "properties": ["pipeline"]})
    for row in r.json()["results"]:
        dpipe[str(row["id"])] = row["properties"].get("pipeline")
print(f"deals read: {len(dpipe)}")

audit = []
assign = {}
for c in empty:
    cid = str(c["id"])
    p = c["properties"]
    email = (p.get("email") or "").strip().lower()
    name = ((p.get("firstname") or "") + " " + (p.get("lastname") or "")).lower()
    if "wetutorathome" in email or "test" in name:
        audit.append({"id": cid, "email": email, "rule": "skip_internal_test", "personas": []})
        continue
    dom = is_staff(email)
    if dom:
        st = p.get("hs_lead_status")
        if st == "Teacher in a School":
            assign[cid] = [P_DM]; rule = "1_staff_domain_status_dm"
        elif st == "Charter School Teacher TOR/EF":
            assign[cid] = [P_TOR]; rule = "1_staff_domain_status_tor"
        else:
            audit.append({"id": cid, "email": email, "rule": "1_staff_domain_REVIEW", "personas": []})
            continue
        audit.append({"id": cid, "email": email, "rule": rule, "personas": assign[cid]})
        continue
    pipes = {dpipe.get(d) for d in deal_of.get(cid, [])} - {None}
    persona_from_deals = sorted({PIPE_PERSONA[x] for x in pipes if x in PIPE_PERSONA})
    if persona_from_deals:
        assign[cid] = persona_from_deals
        audit.append({"id": cid, "email": email, "rule": "2_pipeline_map",
                      "pipelines": sorted(pipes), "personas": persona_from_deals})
        continue
    st = p.get("hs_lead_status")
    if st in STATUS_PERSONA:
        assign[cid] = [STATUS_PERSONA[st]]
        conf = "low" if st == "Tutor-Active" else "normal"   # roster check will verify tutors
        audit.append({"id": cid, "email": email, "rule": "3_lead_status", "status": st,
                      "confidence": conf, "personas": assign[cid]})
        continue
    if (p.get("charter_school_family_") == "true" or (p.get("student_school") or "").strip()
            or (p.get("parent_email") or "").strip() or (p.get("parent_first_name") or "").strip()):
        assign[cid] = [P_FAMILY]
        audit.append({"id": cid, "email": email, "rule": "4_intake_fingerprint", "personas": [P_FAMILY]})
        continue
    audit.append({"id": cid, "email": email, "rule": "5_no_identity_FLAG", "status": st, "personas": []})

by_rule = Counter(a["rule"] for a in audit)
by_persona = Counter(";".join(a["personas"]) for a in audit if a["personas"])
print("\nby rule:", dict(by_rule))
print("by persona:", dict(by_persona))
print(f"assigned: {len(assign)} | review/flag/skip: {len(audit) - len(assign)}")
json.dump(audit, open("/private/tmp/claude-501/-Users-romanslavinsky-code-aplus-agents/9cf1c000-d7d2-40f2-a71c-370cddbc53a9/scratchpad/persona_backfill_audit.json", "w"), indent=0)
print("audit written")

if not GO:
    print("DRY RUN")
    sys.exit(0)

import csv
rows_csv = [( [c for c in empty if str(c["id"]) == cid][0]["properties"].get("email") or "", ";".join(ps))
            for cid, ps in assign.items()]
rows_csv = [(e, ps) for e, ps in rows_csv if e.strip()]
noemail = len(assign) - len(rows_csv)
print(f"importing {len(rows_csv)} (skipped {noemail} without email — assigned via batch update instead)")
buf = io.StringIO()
w = csv.writer(buf)
w.writerow(["Email", "A Persona"])
for e, ps in rows_csv:
    w.writerow([e, ps])
req = {"name": "Persona backfill 2026-08-25 (Roman-approved rules)",
       "importOperations": {"0-1": "UPDATE"},
       "files": [{"fileName": "personas.csv", "fileFormat": "CSV",
                  "fileImportPage": {"hasHeader": True, "columnMappings": [
                      {"columnObjectTypeId": "0-1", "columnName": "Email", "propertyName": "email",
                       "columnType": "HUBSPOT_ALTERNATE_ID"},
                      {"columnObjectTypeId": "0-1", "columnName": "A Persona", "propertyName": "a_persona"}]}}]}
r = requests.post(f"{B}/crm/v3/imports", headers={"Authorization": f"Bearer {TOK}"},
                  files={"files": ("personas.csv", io.BytesIO(buf.getvalue().encode()), "text/csv")},
                  data={"importRequest": json.dumps(req)}, timeout=120)
if r.status_code >= 400:
    sys.exit(f"import failed {r.status_code}: {r.text[:300]}")
imp = r.json().get("importId") or r.json().get("id")
state = ""
for _ in range(60):
    time.sleep(10)
    state = requests.get(f"{B}/crm/v3/imports/{imp}", headers=H, timeout=30).json().get("state", "")
    if state in ("DONE", "FAILED", "CANCELED", "DEFERRED"):
        break
print(f"import {imp}: {state}")
# contacts with personas but no email: batch update directly
no_email_ids = [cid for cid, ps in assign.items()
                if not (([c for c in empty if str(c["id"]) == cid][0]["properties"].get("email") or "").strip())]
for i in range(0, len(no_email_ids), 100):
    requests.post(f"{B}/crm/v3/objects/contacts/batch/update", headers=H, timeout=30,
                  json={"inputs": [{"id": cid, "properties": {"a_persona": ";".join(assign[cid])}}
                                   for cid in no_email_ids[i:i + 100]]})
print(f"no-email batch updates: {len(no_email_ids)}")

# verify sample
sample = list(assign)[:100]
chk = requests.post(f"{B}/crm/v3/objects/contacts/batch/read", headers=H, timeout=30,
                    json={"inputs": [{"id": c} for c in sample], "properties": ["a_persona"]}).json()
ok = sum(1 for row in chk["results"] if (row["properties"].get("a_persona") or "").strip())
print(f"verify sample: {ok}/{len(sample)} stamped")

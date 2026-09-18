"""STEP 8: execute the migration table, one ticket at a time, with a note on
each. --live to write; default prints the plan. Idempotent: a ticket already
in its target pipeline is skipped. Ordering per the spec: pipelines built ->
table posted -> owners switched. REVIEW rows are left alone (note only)."""
import json, re, sys, datetime, urllib.request, urllib.error, collections
import pathlib
OUT = str(pathlib.Path(__file__).resolve().parent) + "/"
LIVE = "--live" in sys.argv
import os
tok = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")
if not tok:
    for ln in open(os.path.expanduser("~/code/aplus-agents/.env")):
        if ln.startswith("HUBSPOT_PRIVATE_APP_TOKEN="):
            tok = ln.split("=", 1)[1].strip().strip('"').strip("'")
H = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}
PIPES = json.load(open(OUT + "pipelines_2026_09_16.json"))
ROWS = json.load(open(OUT + "tickets_open_2026_09_16.json"))
OWNER = {"charter_sales": "81494333", "charter_admin": "513215050", "scheduler_a_l": "80047202",
         "scheduler_m_z": "86868539", "operations": "80047201", "partnerships": "227538487", "roman": "38681249"}
TRIAL_TICKETS = {"48584642985", "48590009948", "48631413801"}          # Elenes x3 (STEP 8: trial at zero)
STAGE = {("Renewals", "Waiting on family"): PIPES["Renewals"]["stages"]["Waiting on family"]["id"],
         ("Support", "New"): "1378066770", ("Support", "Waiting on us"): "131537027",
         ("Support", "Waiting on tutor"): "3", ("Support", "Waiting on family"): "2",
         ("Support", "Resolved"): "4", ("Support", "Won't fix"): PIPES["Support Pipeline"]["stages"]["Won't fix"]["id"],
         ("Tutor", "New"): PIPES["Tutor Accountability"]["stages"]["New"]["id"],
         ("Tutor", "Debrief"): PIPES["Tutor Accountability"]["stages"]["Debrief"]["id"],
         ("Tutor", "Probation"): PIPES["Tutor Accountability"]["stages"]["Probation"]["id"]}
PID = {"Renewals": PIPES["Renewals"]["id"], "Support": "0", "Tutor": PIPES["Tutor Accountability"]["id"]}


def call(method, path, body=None):
    req = urllib.request.Request("https://api.hubapi.com" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None, headers=H)
    try:
        r = urllib.request.urlopen(req)
        return json.load(r) if r.status != 204 else {}
    except urllib.error.HTTPError as e:
        print("   HTTP", e.code, path, e.read()[:200].decode(errors="ignore")); return None


def note(tid, text):
    if not LIVE:
        return
    call("POST", "/crm/v3/objects/notes", {"properties": {"hs_note_body": text, "hs_timestamp": int(datetime.datetime.utcnow().timestamp() * 1000)},
                                           "associations": [{"to": {"id": tid}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 228}]}]})


def split(last):
    l = (last or "").strip().lower()
    return "scheduler_a_l" if (not l or l[0] <= "l") else "scheduler_m_z"


def family_last(r):
    for c in r["contacts"]:
        name = re.sub(r"\s*\[.*\]$", "", c).replace("(NBCUniversal)", "").strip()
        if name and name.lower() != "teachworks" and len(name.split()) >= 2:
            return name.split()[-1]
    m = re.match(r"^Low balance: (.+?) \(", r["subject"])
    if m:
        return m.group(1).split()[-1]
    m = re.match(r"^([^,—]+),", r["subject"])
    return m.group(1).strip() if m else ""


def plan(r):
    s, cat, owner, contact = r["subject"], r["category"], r["owner"].split()[0], (r["contacts"][0] if r["contacts"] else "")
    is_tutor = "[Tutors]" in contact
    if r["id"] in TRIAL_TICKETS:
        return ("Renewals", "Waiting on family", "charter_sales", {"funding_type": "trial", "case_client": "low_balance"},
                "trial at zero hours: Renewals, charter_sales override (STEP 8)")
    if s.startswith("Low balance:"):
        role = split(family_last(r))
        return ("Renewals", "Waiting on family", role, {"funding_type": "charter", "case_client": "low_balance"},
                f"charter low-balance case; owner by surname split ({family_last(r)})")
    if "— Low Balance" in s:
        role = split(family_last(r))
        return ("Renewals", "Waiting on family", role, {"funding_type": "private_pay", "case_client": "low_balance"},
                f"private-pay low balance; owner by surname split ({family_last(r)}); payment-link rail not armed")
    if cat.startswith("Tutor Issue") or "complaint;Tutor" in cat or s.endswith("- Tutor") or "No TW Profile" in s:
        it = "incomplete_notes" if "notes not completed" in s else "late_or_no_notice" if "Missed lesson" in s else "other"
        return ("Tutor", "New", "operations", {"tutor_issue_type": it, "case_client": "tutor_issues"}, "tutor case (Escalation Procedure p.1)")
    if s.startswith("new_po"):
        return ("Support", "New", "charter_admin", {"support_category": "po_watch", "case_client": "po_inbox"}, "PO in process")
    if s.startswith("AR —") or cat.startswith("Billing"):
        return ("Support", "Waiting on us", "charter_admin", {"support_category": "billing"}, "billing / AR")
    if s.startswith("po_inbox review") or "School Partner" in s or s.startswith("school_partner"):
        if "do-not-reply" in s or "Stampli" in contact:
            return ("Support", "Won't fix", None, {"support_category": "other"}, "system notification, no case")
        return ("Support", "Waiting on us", "charter_admin", {"support_category": "po_exception", "case_client": "po_inbox"}, "PO exception")
    if cat.startswith("Cancellation"):
        return ("Support", "Waiting on us", "operations", {"support_category": "cancellation"}, "cancellation")
    if s.startswith("Check in with"):
        return ("TASK", None, "charter_sales", {}, "call-agent check-in: one person, one thing, one date = a Task")
    if "— Business Dev" in s:
        return ("TASK", None, "partnerships", {}, "business-dev thread 30 to 68 days stuck: a to-do for partnerships")
    if "COMPLIANCE" in s:
        return ("Support", "Waiting on us", "operations", {"support_category": "other"}, "compliance reminder")
    if "— Scheduling" in s or cat == "Reschedule":
        if is_tutor:
            return ("Support", "Waiting on tutor", "scheduler_m_z" if owner == "Yolanda" else "scheduler_a_l", {"support_category": "scheduling"}, "tutor reschedule")
        return ("Support", "Waiting on family", split(family_last(r)), {"support_category": "scheduling"}, f"family scheduling thread ({family_last(r)})")
    if "Study Plan" in s:
        return ("Support", "Waiting on us", "roman", {"support_category": "other"}, "Roman's thread")
    if "Recruitment" in s or (cat == "General" and "Unknown" in s and is_tutor):
        return ("Support", "Waiting on us", "operations", {"support_category": "other"}, "tutor thread")
    if cat == "General" and "Unknown" in s and "[Family]" in contact:
        return ("REVIEW", None, None, {}, "family thread tagged Unknown; likely duplicates a Renewals ticket")
    if cat == "General":
        return ("Support", "Waiting on us", "operations", {"support_category": "other"}, "unclassified inbound")
    return ("REVIEW", None, None, {}, "no rule matched")


# tutor counts (2nd ticket in the window = Probation, seeded; automation not armed)
tutor_of = {}
for r in ROWS:
    if plan(r)[0] == "Tutor":
        m = re.search(r": ([A-Z][\w'\-]+ [A-Z][\w'\-]+) \(wk", r["subject"]) or re.match(r"^([A-Z][\w'\-]+ [A-Z][\w'\-]+)", r["subject"])
        tutor_of[r["id"]] = m.group(1) if m else r["subject"][:30]
tutor_count = collections.Counter(tutor_of.values())

done = collections.Counter()
for r in sorted(ROWS, key=lambda x: x["created"]):
    tid = r["id"]
    target, stage, role, props, why = plan(r)
    if target == "REVIEW":
        print(f"  REVIEW  {tid} {r['subject'][:50]} :: {why}")
        done["review"] += 1
        continue
    if target == "TASK":
        oid = OWNER[role]
        due = int((datetime.datetime.utcnow() + datetime.timedelta(days=1)).timestamp() * 1000)
        print(f"  TASK    {tid} {r['subject'][:50]} -> task for {role}; ticket resolved")
        if LIVE:
            call("POST", "/crm/v3/objects/tasks", {"properties": {"hs_task_subject": r["subject"][:200], "hs_task_status": "NOT_STARTED",
                                                                   "hs_task_type": "TODO", "hs_timestamp": due, "hubspot_owner_id": oid,
                                                                   "hs_task_body": f"Converted from ticket {tid} on 2026-09-16 (Tasks / Tickets rule): {why}"}})
            call("PATCH", f"/crm/v3/objects/tickets/{tid}", {"properties": {"hs_pipeline_stage": "4"}})
            note(tid, f"🔁 Closed under the Tasks / Tickets rule (2026-09-16): {why}. A task was created for the owner instead.")
        done["task"] += 1
        continue
    if r["pipeline"] == PID[target] and target != "Support":
        print(f"  skip    {tid} already in {target}")
        continue
    stage_key = (target, stage)
    if target == "Tutor":
        stage_key = ("Tutor", "Probation" if tutor_count.get(tutor_of.get(tid), 1) >= 2 else "Debrief")
    p = {"hs_pipeline": PID[target], "hs_pipeline_stage": STAGE[stage_key], **props}
    if role:
        p["hubspot_owner_id"] = OWNER[role]
    label = f"{target}/{stage_key[1]} owner={role or '-'} {props}"
    print(f"  {'MOVE' if LIVE else 'plan'}    {tid} {r['subject'][:48]:48} -> {label}")
    if LIVE:
        res = call("PATCH", f"/crm/v3/objects/tickets/{tid}", {"properties": p})
        if res is None:
            done["error"] += 1
            continue
        note(tid, f"📦 Moved on 2026-09-16 under the Tasks / Tickets / Pipelines rule: {label}. Reason: {why}. "
                  f"Was: {r['owner']} / {r['category'] or 'uncategorized'} / {r['stage']}.")
    done[target] += 1
print(dict(done))

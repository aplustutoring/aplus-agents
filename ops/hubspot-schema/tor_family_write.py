"""WRITE PHASE: create Family->TOR associations with the 'Teacher of Record' label (typeId 15).
Shows full plan, asks for YES before writing. Re-runnable (skips existing links)."""
import os, time, requests
from collections import defaultdict
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path.home() / "Documents/aplus-agents/.env")
TOK = os.getenv("HUBSPOT_API_KEY","") or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN","")
H = {"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

SKIP_EMAILS = {"r@wetutorathome.com", "teacher@wetutorathome.com"}
EMAIL_FIX = {
    "mary.nieves@ileadexploration.or": "mary.nieves@ileadexploration.org",
    "adidi.arora@ileadexploration.com": "adidi.arora@ileadexploration.org",
    "kristy.doyal@heartlandcharterschool.com": "kristydoyal@gmail.com",  # her contact's primary email
}
FORCE = {}

def post(url, body):
    while True:
        r = requests.post(BASE+url, headers=H, json=body)
        if r.status_code == 429: time.sleep(1); continue
        if r.status_code >= 400: raise SystemExit(f"API {r.status_code}: {r.text[:300]}")
        return r.json()

def search_all(otype, filters, props):
    out, after = [], None
    while True:
        body = {"filterGroups":[{"filters":filters}], "properties":props, "limit":200}
        if after: body["after"] = after
        d = post(f"/crm/v3/objects/{otype}/search", body)
        out += d.get("results",[])
        after = d.get("paging",{}).get("next",{}).get("after")
        if not after: break
        time.sleep(0.2)
    return out

def batch_assoc(ft, tt, ids):
    m = defaultdict(list)
    for i in range(0, len(ids), 100):
        d = post(f"/crm/v4/associations/{ft}/{tt}/batch/read", {"inputs":[{"id":x} for x in ids[i:i+100]]})
        for r in d.get("results",[]): m[str(r["from"]["id"])] = [str(t["toObjectId"]) for t in r["to"]]
        time.sleep(0.2)
    return m

print("1) TORs...")
tors = search_all("contacts", [{"propertyName":"hs_lead_status","operator":"EQ","value":"Charter School Teacher TOR/EF"}],
                  ["firstname","lastname","email"])
tor_by_id = {str(t["id"]): t["properties"] for t in tors}
tor_by_email = {p.get("email","").lower(): i for i,p in tor_by_id.items() if p.get("email")}
def tor_by_name(first, last):
    hits = [i for i,p in tor_by_id.items()
            if ((p.get("firstname") or "").strip().lower(), (p.get("lastname") or "").strip().lower()) == (first, last)]
    return hits[0] if len(hits)==1 else None

print("2) Stamped families...")
fams = search_all("contacts", [{"propertyName":"teacher_of_record_email_address","operator":"HAS_PROPERTY"}],
                  ["firstname","lastname","teacher_of_record_email_address"])
fam_by_id = {str(f["id"]): f["properties"] for f in fams if str(f["id"]) not in tor_by_id}

souza = [i for i,p in fam_by_id.items() if (p.get("lastname") or "")=="Souza" and (p.get("firstname") or "")=="Erin"]
bobryk = [i for i,p in fam_by_id.items() if "Bobryk" in (p.get("lastname","") or "")]
staley = [i for i,p in fam_by_id.items() if (p.get("lastname") or "")=="Staley" and (p.get("firstname") or "")=="Sydnee"]
greenman = tor_by_name("jeanne","greenman") or tor_by_name("jeanne m","greenman")
dixon = tor_by_name("hilary","dixon") or tor_by_name("hillary","dixon") or tor_by_name("hillary l","dixon")
johnson = tor_by_name("monica","johnson"); archibald = tor_by_name("kimberlee","archibald")
if souza and greenman: FORCE[souza[0]] = [greenman]
if bobryk and dixon: FORCE[bobryk[0]] = [dixon]
if staley: FORCE[staley[0]] = [x for x in (johnson, archibald) if x]

print("3) Deal co-association...")
fam_deals = batch_assoc("contacts","deals", list(fam_by_id.keys()))
all_deals = sorted({d for ds in fam_deals.values() for d in ds})
deal_contacts = batch_assoc("deals","contacts", all_deals)

print("4) Existing contact-contact links...")
existing = batch_assoc("contacts","contacts", list(fam_by_id.keys()))

plan, skipped = [], []
for fid, fp in fam_by_id.items():
    fname = f"{fp.get('firstname') or ''} {fp.get('lastname') or ''}".strip()
    email = (fp.get("teacher_of_record_email_address") or "").strip().lower()
    email = EMAIL_FIX.get(email, email)
    if email in SKIP_EMAILS: skipped.append((fname,"test record")); continue
    if fid in FORCE: targets = FORCE[fid]
    else:
        co = sorted({c for d in fam_deals.get(fid,[]) for c in deal_contacts.get(str(d),[]) if c in tor_by_id and c != fid})
        stamp = tor_by_email.get(email)
        if stamp and co: targets = [stamp] if stamp in co else co
        elif stamp: targets = [stamp]
        elif len(co)>=1: targets = co
        else: skipped.append((fname,"unresolved - no TOR found")); continue
    new = [t for t in targets if t not in existing.get(fid,[])]
    if not new: skipped.append((fname,"already linked")); continue
    for t in new:
        tp = tor_by_id[t]
        plan.append((fid, fname, t, f"{tp.get('firstname') or ''} {tp.get('lastname') or ''}".strip()))

print(f"\n=== PLAN: {len(plan)} associations to create, {len(skipped)} skipped ===")
by_reason = defaultdict(int)
for _, r in skipped: by_reason[r if "unresolved" not in r else "unresolved"] += 1
for r, n in by_reason.items(): print(f"  skipped ({r}): {n}")
for _, fn, _, tn in plan[:12]: print(f"  {fn} -> {tn}")
if len(plan) > 12: print(f"  ... and {len(plan)-12} more")
for fn, r in skipped:
    if "unresolved" in r: print(f"  REVIEW LATER: {fn} ({r})")

if input("\nType YES to create these associations: ").strip() != "YES":
    raise SystemExit("Aborted. Nothing written.")

print("\n5) Writing with 'Teacher of Record' label (typeId 15)...")
inputs = [{"from":{"id":fid},"to":{"id":tid},"types":[{"associationCategory":"USER_DEFINED","associationTypeId":15}]}
          for fid,_,tid,_ in plan]
done = 0
for i in range(0, len(inputs), 100):
    post("/crm/v4/associations/contacts/contacts/batch/create", {"inputs": inputs[i:i+100]})
    done += len(inputs[i:i+100]); print(f"  {done}/{len(inputs)}"); time.sleep(0.3)
print(f"\nDONE: {done} Family->TOR associations created with the Teacher of Record label.")

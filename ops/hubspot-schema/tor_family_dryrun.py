"""DRY RUN: deduce Family->TOR relationships. READ-ONLY, writes two CSVs."""
import os, re, csv, time, requests
from collections import defaultdict
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path.home() / "Documents/aplus-agents/.env")
TOK = os.getenv("HUBSPOT_API_KEY","") or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN","")
H = {"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

def post(url, body):
    while True:
        r = requests.post(BASE+url, headers=H, json=body)
        if r.status_code == 429: time.sleep(1); continue
        r.raise_for_status(); return r.json()

def search_all(object_type, filters, props):
    out, after = [], None
    while True:
        body = {"filterGroups":[{"filters":filters}], "properties":props, "limit":200}
        if after: body["after"] = after
        d = post(f"/crm/v3/objects/{object_type}/search", body)
        out += d.get("results",[])
        after = d.get("paging",{}).get("next",{}).get("after")
        if not after: break
        time.sleep(0.25)
    return out

def batch_assoc(from_type, to_type, ids):
    m = defaultdict(list)
    for i in range(0, len(ids), 100):
        chunk = [{"id": x} for x in ids[i:i+100]]
        d = post(f"/crm/v4/associations/{from_type}/{to_type}/batch/read", {"inputs": chunk})
        for r in d.get("results",[]):
            m[r["from"]["id"]] = [t["toObjectId"] for t in r["to"]]
        time.sleep(0.25)
    return m

def batch_props(object_type, ids, props):
    m = {}
    ids = list(set(ids))
    for i in range(0, len(ids), 100):
        chunk = [{"id": str(x)} for x in ids[i:i+100]]
        d = post(f"/crm/v3/objects/{object_type}/batch/read", {"inputs": chunk, "properties": props})
        for r in d.get("results",[]):
            m[str(r["id"])] = r.get("properties",{})
        time.sleep(0.25)
    return m

print("1) Fetching TOR contacts...")
tors = search_all("contacts",
    [{"propertyName":"hs_lead_status","operator":"EQ","value":"Charter School Teacher TOR/EF"}],
    ["firstname","lastname","email","charter_school_teacher"])
tor_by_id = {str(t["id"]): t["properties"] for t in tors}
tor_by_email = {p.get("email","").lower(): i for i,p in tor_by_id.items() if p.get("email")}
print(f"   {len(tors)} TOR contacts")

print("2) Fetching stamped families (teacher_of_record_email_address set)...")
fams = search_all("contacts",
    [{"propertyName":"teacher_of_record_email_address","operator":"HAS_PROPERTY"}],
    ["firstname","lastname","email","teacher_of_record_name","teacher_of_record_email_address","charter_school_family_","hs_lead_status"])
fam_by_id = {str(f["id"]): f["properties"] for f in fams}
# exclude contacts that ARE TORs themselves
fam_by_id = {i:p for i,p in fam_by_id.items() if i not in tor_by_id}
print(f"   {len(fam_by_id)} stamped family contacts")

print("3) Families' deals...")
fam_deals = batch_assoc("contacts","deals", list(fam_by_id.keys()))
all_deal_ids = sorted({str(d) for ds in fam_deals.values() for d in ds})
print(f"   {len(all_deal_ids)} deals across stamped families")

print("4) Deals' contacts (to find co-associated TORs)...")
deal_contacts = batch_assoc("deals","contacts", all_deal_ids)

print("5) Deal names (for student parsing)...")
deal_props = batch_props("deals", all_deal_ids, ["dealname"])

def students_from_deals(deal_ids):
    names = set()
    for d in deal_ids:
        dn = deal_props.get(str(d),{}).get("dealname","") or ""
        parts = [p.strip() for p in dn.split(" - ")]
        if len(parts) >= 3: names.add(parts[1])  # Family - Student - School...
    return names

print("6) Reconciling...")
rows = []
tor_students = defaultdict(set); tor_families = defaultdict(set)
for fid, fp in fam_by_id.items():
    fname = f"{fp.get('firstname','')} {fp.get('lastname','')}".strip()
    stamp_email = (fp.get("teacher_of_record_email_address") or "").strip().lower()
    stamp_name  = fp.get("teacher_of_record_name","")
    stamp_tor_id = tor_by_email.get(stamp_email)
    deal_ids = fam_deals.get(fid, [])
    co_tors = sorted({str(c) for d in deal_ids for c in deal_contacts.get(str(d),[]) if str(c) in tor_by_id and str(c)!=fid})
    students = students_from_deals(deal_ids)
    if stamp_tor_id and co_tors:
        cat = "MATCH" if stamp_tor_id in co_tors else "CONFLICT"
        proposed = stamp_tor_id if cat=="MATCH" else ""
    elif stamp_tor_id: cat, proposed = "STAMP_ONLY(no-PO or no TOR on deals)", stamp_tor_id
    elif co_tors: cat, proposed = ("DEAL_ONLY", co_tors[0]) if len(co_tors)==1 else ("DEAL_MULTI", "")
    else: cat, proposed = "STAMP_UNRESOLVED(no TOR contact w/ that email)", ""
    if proposed:
        tor_families[proposed].add(fname or fid)
        tor_students[proposed] |= students
    tp = tor_by_id.get(proposed or stamp_tor_id or (co_tors[0] if co_tors else ""), {})
    rows.append({"family_id":fid,"family":fname,"category":cat,
        "stamped_tor":f"{stamp_name} <{stamp_email}>",
        "deal_tors":"; ".join(f"{tor_by_id[t].get('firstname','')} {tor_by_id[t].get('lastname','')}" for t in co_tors),
        "proposed_tor_id":proposed,
        "proposed_tor":f"{tp.get('firstname','')} {tp.get('lastname','')}".strip(),
        "school":tp.get("charter_school_teacher",""),
        "num_deals":len(deal_ids),"students_from_deals":"; ".join(sorted(students))})

with open("proposed_family_tor_links.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

with open("tor_student_counts.csv","w",newline="") as f:
    w = csv.writer(f); w.writerow(["tor","school","num_families","num_students","students"])
    for tid in sorted(tor_families, key=lambda t:-len(tor_families[t])):
        p = tor_by_id[tid]
        w.writerow([f"{p.get('firstname','')} {p.get('lastname','')}", p.get("charter_school_teacher",""),
                    len(tor_families[tid]), len(tor_students[tid]), "; ".join(sorted(tor_students[tid]))])

from collections import Counter
print("\n=== SUMMARY ===")
for k,v in Counter(r["category"] for r in rows).most_common(): print(f"  {k}: {v}")
print(f"\nWrote proposed_family_tor_links.csv ({len(rows)} families)")
print(f"Wrote tor_student_counts.csv ({len(tor_families)} TORs)")

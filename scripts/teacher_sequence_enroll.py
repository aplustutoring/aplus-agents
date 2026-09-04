#!/usr/bin/env python3
"""Daily sequence enroller for the teacher outreach 26/27.

Reads ops/messenger/teacher-sequences.yml. For each sequence, picks the next
`daily_cap` eligible contacts from its HubSpot list (priority list first, then
school order, then name) and enrolls them via the Sequences API, sending from
Danielle's connected inbox exactly as a manual "Enroll in sequence" would.
State (who was enrolled when, which sender email worked) lives in the repo and
is committed back by the workflow.

Gates: config `armed` AND today (PT) >= start_date AND weekday, unless --force.
Dry-run by default; live needs --confirm ENROLL.

  python3 scripts/teacher_sequence_enroll.py                      # dry run: shows today's batch
  python3 scripts/teacher_sequence_enroll.py --confirm ENROLL     # enroll for real (gated)
  python3 scripts/teacher_sequence_enroll.py --test-contact danielle+003@wetutorathome.com --confirm ENROLL
      # enroll ONE contact into sequence 1 to validate the sender inbox; bypasses gates and cap

Eligibility at enroll time: has email; not opted out; not hard-bounced;
generic_inbox != Yes; campaign_replied != Yes; not currently enrolled in any
sequence; not already enrolled by this script. Every skip is counted and
reported (Accountable: say what was NOT done).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent.parent
    load_dotenv(_here / ".env", override=False)
    if "/.claude/worktrees/" in str(_here):
        load_dotenv(Path(str(_here).split("/.claude/worktrees/")[0]) / ".env", override=False)
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ops" / "messenger" / "teacher-sequences.yml"
HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
PROPS = ["email", "firstname", "lastname", "school_canonical", "generic_inbox", "hs_email_optout",
         "hs_email_bounce", "hs_sequences_is_enrolled", "campaign_replied", "hs_latest_sequence_enrolled"]


def hs(method, path, **kw):
    for _ in range(6):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)) or 10)
            continue
        return r
    return r


def list_members(list_id):
    ids, after = [], None
    while True:
        r = hs("GET", f"/crm/v3/lists/{list_id}/memberships?limit=250" + (f"&after={after}" if after else ""))
        r.raise_for_status()
        j = r.json()
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return ids


def batch_read(ids):
    out = {}
    for i in range(0, len(ids), 100):
        r = hs("POST", "/crm/v3/objects/contacts/batch/read",
               json={"inputs": [{"id": c} for c in ids[i:i + 100]], "properties": PROPS})
        r.raise_for_status()
        for row in r.json().get("results", []):
            out[str(row["id"])] = row.get("properties", {})
    return out


def ineligible(p, done):
    email = (p.get("email") or "").strip().lower()
    if not email:
        return "no email"
    if (p.get("hs_email_optout") or "").lower() == "true":
        return "opted out"
    if (p.get("hs_email_bounce") or "0") not in ("0", ""):
        return "bounced"
    if (p.get("generic_inbox") or "") == "true":
        return "generic inbox"
    if (p.get("campaign_replied") or "") == "true":
        return "already replied"
    if (p.get("hs_sequences_is_enrolled") or "") == "true":
        return "already in a sequence"
    return None


def enroll(seq_id, contact_id, sender_email, user_id):
    r = hs("POST", f"/automation/v4/sequences/enrollments?userId={user_id}",
           json={"sequenceId": str(seq_id), "contactId": str(contact_id), "senderEmail": sender_email})
    return r.status_code, (r.text or "")[:300]


def slack_dm(user_id, text):
    if not SLACK_TOKEN or not user_id:
        return
    requests.post("https://slack.com/api/chat.postMessage",
                  headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
                  json={"channel": user_id, "text": text, "unfurl_links": False}, timeout=30)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirm", default="", help="ENROLL to enroll for real")
    ap.add_argument("--force", action="store_true", help="skip armed / start_date / weekday gates")
    ap.add_argument("--cap", type=int, help="override daily_cap")
    ap.add_argument("--test-contact", help="enroll only this contact email into the first sequence (sender validation)")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    cfg = yaml.safe_load(CONFIG.read_text())
    live = args.confirm == "ENROLL"
    tz = ZoneInfo(cfg.get("timezone", "America/Los_Angeles"))
    now = datetime.now(tz)
    today = now.date().isoformat()
    state_path = ROOT / cfg["state_file"]
    state = json.loads(state_path.read_text()) if state_path.exists() else {"enrolled": {}, "runs": [], "sender_email_confirmed": None}
    done = state["enrolled"]
    user_id = cfg["sender"]["user_id"]
    candidates = ([state["sender_email_confirmed"]] if state.get("sender_email_confirmed") else []) + \
                 [e for e in cfg["sender"]["email_candidates"] if e != state.get("sender_email_confirmed")]

    # ── gates ──
    if not args.test_contact and not args.force:
        if not cfg.get("armed"):
            print("not armed (ops/messenger/teacher-sequences.yml) — exiting"); return
        if today < cfg["start_date"]:
            print(f"today {today} < start_date {cfg['start_date']} — exiting"); return
        if now.weekday() >= 5:
            print(f"{today} is a weekend — exiting"); return

    def do_enroll(seq_id, cid, label):
        """Try the confirmed sender first, then the other candidates. Returns (ok, sender, detail)."""
        for sender in candidates:
            code, body = enroll(seq_id, cid, sender, user_id)
            if code in (200, 201):
                if state.get("sender_email_confirmed") != sender:
                    state["sender_email_confirmed"] = sender
                    print(f"  ✔ sender inbox confirmed: {sender}")
                return True, sender, body
            if "sender" in body.lower() or "inbox" in body.lower() or code in (400, 403):
                print(f"  sender {sender} rejected ({code}): {body[:140]}")
                continue
            return False, sender, f"{code} {body}"
        return False, None, "no sender candidate accepted"

    # ── sender validation mode ──
    if args.test_contact:
        r = hs("POST", "/crm/v3/objects/contacts/search", json={"filterGroups": [{"filters": [
            {"propertyName": "email", "operator": "EQ", "value": args.test_contact}]}], "properties": ["email"], "limit": 1})
        res = r.json().get("results", [])
        if not res:
            sys.exit(f"test contact {args.test_contact} not found in HubSpot")
        cid = str(res[0]["id"])
        seq = cfg["sequences"][0]
        print(f"test: enroll {args.test_contact} ({cid}) into {seq['name']} ({seq['sequence_id']}) as user {user_id}")
        if not live:
            print("DRY RUN — add --confirm ENROLL to send the test."); return
        ok, sender, detail = do_enroll(seq["sequence_id"], cid, args.test_contact)
        print("  result:", "OK" if ok else "FAILED", sender, detail)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=1))
        return

    cap = args.cap or cfg["daily_cap"]
    summary = []
    for seq in cfg["sequences"]:
        ids = list_members(seq["list_id"])
        props = batch_read(ids)
        pri = set(list_members(seq["priority_list_id"])) if seq.get("priority_list_id") else set()
        order = {s: i for i, s in enumerate(seq.get("school_order", []))}
        skips, pool = {}, []
        for cid in ids:
            p = props.get(cid, {})
            if cid in done:
                skips["already enrolled by script"] = skips.get("already enrolled by script", 0) + 1
                continue
            why = ineligible(p, done)
            if why:
                skips[why] = skips.get(why, 0) + 1
                continue
            pool.append(cid)
        pool.sort(key=lambda c: (0 if c in pri else 1, order.get(props[c].get("school_canonical"), 99),
                                 (props[c].get("lastname") or "").lower(), (props[c].get("firstname") or "").lower()))
        batch = pool[:cap]
        remaining = len(pool) - len(batch)
        print(f"\n{seq['name']} (seq {seq['sequence_id']}, list {seq['list_id']}): {len(ids)} on list, "
              f"{len(pool)} eligible, batch {len(batch)}, {remaining} left after today")
        if skips:
            print("  skipped:", dict(skips))
        by_school = {}
        for c in batch:
            by_school[props[c].get("school_canonical")] = by_school.get(props[c].get("school_canonical"), 0) + 1
        print("  batch by school:", by_school)
        ok_n, fail = 0, []
        for c in batch:
            p = props[c]
            if not live:
                continue
            ok, sender, detail = do_enroll(seq["sequence_id"], c, p.get("email"))
            if ok:
                ok_n += 1
                done[c] = {"seq": seq["sequence_id"], "date": today, "email": p.get("email")}
            else:
                fail.append((p.get("email"), detail))
            time.sleep(0.4)
        if live:
            print(f"  enrolled {ok_n}/{len(batch)}" + (f"; FAILED {len(fail)}: {fail[:3]}" if fail else ""))
        summary.append((seq["name"], len(batch), ok_n, len(fail), remaining, by_school))

    if not live:
        print("\nDRY RUN — nothing enrolled. Workflow passes --confirm ENROLL on schedule.")
        return
    state["runs"].append({"date": today, "at": now.isoformat(), "summary": [
        {"sequence": n, "batch": b, "enrolled": o, "failed": f, "remaining": r} for n, b, o, f, r, _ in summary]})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=1))
    lines = [f"Teacher outreach enrollments for {today} (from {state.get('sender_email_confirmed')}):"]
    for n, b, o, f, r, bs in summary:
        lines.append(f"• {n}: enrolled {o} of {b}" + (f", {f} failed" if f else "") + f", {r} still to go. " +
                     ", ".join(f"{k} {v}" for k, v in bs.items()))
    lines.append("Replies exit the sequence on their own. \"Send it\" replies: ping Roman for the roster.")
    text = "\n".join(lines)
    print("\n" + text)
    for uid in (cfg.get("notify", {}).get("slack_user_ids") or []) + ([os.getenv("ROMAN_SLACK_USER_ID")] if os.getenv("ROMAN_SLACK_USER_ID") else []):
        slack_dm(uid, text)


if __name__ == "__main__":
    main()

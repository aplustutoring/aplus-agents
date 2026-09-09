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
    if not (p.get("firstname") or "").strip():
        return "no first name"       # the templates open "Hi {{ contact.firstname }}," — never send "Hi ,"
    return None


def enroll(seq_id, contact_id, sender_email, user_id):
    r = hs("POST", f"/automation/v4/sequences/enrollments?userId={user_id}",
           json={"sequenceId": str(seq_id), "contactId": str(contact_id), "senderEmail": sender_email})
    return r.status_code, (r.text or "")[:300]


def search_count(object_type, filters):
    r = hs("POST", f"/crm/v3/objects/{object_type}/search",
           json={"filterGroups": [{"filters": filters}], "properties": ["hs_object_id"], "limit": 1})
    r.raise_for_status()
    return r.json().get("total", 0)


def signals(cfg):
    """The numbers that say whether the outreach is working, since start_date:
    replies (HubSpot reply date or the info@ classifier's campaign_replied stamp)
    from teachers enrolled in either sequence, Teacher Scholarship nominations
    (family deals in pipeline 918901819), and new 26/27 charter deals."""
    since = cfg["start_date"]
    since_ms = str(int(time.mktime(time.strptime(since, "%Y-%m-%d")) * 1000))
    seq_ids = [s["sequence_id"] for s in cfg["sequences"]]
    in_seq = {"propertyName": "hs_latest_sequence_enrolled", "operator": "IN", "values": seq_ids}
    replied = search_count("contacts", [in_seq, {"propertyName": "hs_sales_email_last_replied", "operator": "GTE", "value": since_ms}])
    stamped = search_count("contacts", [in_seq, {"propertyName": "campaign_replied", "operator": "EQ", "value": "true"}])
    campaign_replied = search_count("contacts", [{"propertyName": "campaign_replied", "operator": "EQ", "value": "true"}])
    nominations = search_count("deals", [{"propertyName": "pipeline", "operator": "EQ", "value": "918901819"},
                                          {"propertyName": "createdate", "operator": "GTE", "value": since_ms}])
    charter_deals = search_count("deals", [{"propertyName": "pipeline", "operator": "IN", "values": ["907748", "72281989", "88841552", "5119061", "1066195"]},
                                            {"propertyName": "createdate", "operator": "GTE", "value": since_ms}])
    return (f"Signals since {since}: sequence replies {max(replied, stamped)} (some are auto-replies), "
            f"campaign replies stamped {campaign_replied}, scholarship nominations {nominations}, "
            f"new charter deals {charter_deals}.")


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
        # One batch per day. The workflow has a retry cron (GitHub schedules are
        # best-effort: the 9:05 run did not fire on 2026-09-08), so a second
        # trigger on the same day must be a no-op, never a second 50.
        if any(r.get("date") == today for r in state.get("runs", [])):
            print(f"a batch already ran today ({today}) — exiting (use --force to add another)"); return

    # HubSpot error types that are about the CONTACT, not the sender inbox. Retrying
    # them with another sender is pointless; record them so they are never retried.
    CONTACT_ERRORS = ("RECIPIENT_PREVIOUSLY_BOUNCED", "RECIPIENT_UNSUBSCRIBED", "RECIPIENT_", "CONTACT_")

    # Consecutive sender-level rejections that mean the inbox itself is gone
    # rather than the contacts being bad. do_enroll returns sender=None only
    # when every candidate was refused for a sender reason, so this is already
    # a narrow signal. Three in a row rather than one, because CONTACT_ERRORS
    # is a prefix heuristic: an unusual contact-specific errorType it does not
    # match would masquerade as a sender fault, and three of those in a row is
    # far less likely than a genuinely dead inbox.
    SENDER_FAIL_ABORT = 3

    def do_enroll(seq_id, cid, label):
        """Try the confirmed sender first, then the other candidates.
        Returns (ok, sender, detail). Contact-level rejections come back as
        ok=False with detail starting 'contact:' and are recorded permanently."""
        last_error = "none attempted"
        for sender in candidates:
            code, body = enroll(seq_id, cid, sender, user_id)
            last_error = f"{sender} -> {code} {body[:160]}"
            if code in (200, 201):
                if state.get("sender_email_confirmed") != sender:
                    state["sender_email_confirmed"] = sender
                    print(f"  ✔ sender inbox confirmed: {sender}")
                return True, sender, body
            if any(k in body for k in CONTACT_ERRORS):
                reason = next((k for k in ("RECIPIENT_PREVIOUSLY_BOUNCED", "RECIPIENT_UNSUBSCRIBED") if k in body), "contact rejected")
                state.setdefault("skipped_permanent", {})[str(cid)] = {"seq": str(seq_id), "date": today, "email": label, "why": reason}
                return False, sender, f"contact: {reason}"
            if "connected inbox" in body.lower() or "sender" in body.lower() or code in (400, 403):
                print(f"  sender {sender} rejected ({code}): {body[:140]}")
                continue
            return False, sender, f"{code} {body}"
        # Carry the last real HubSpot error out. "no sender candidate accepted"
        # on its own throws away the only thing that says WHY, which is how a
        # dead-recipient problem got read as a sender problem on day one.
        return False, None, f"no sender candidate accepted; last error: {last_error}"

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
    sender_down = None      # set to the last real error once the inbox looks dead
    for seq in cfg["sequences"]:
        if sender_down:
            print(f"\n{seq['name']}: SKIPPED, sender inbox is down")
            continue
        ids = list_members(seq["list_id"])
        props = batch_read(ids)
        pri = set(list_members(seq["priority_list_id"])) if seq.get("priority_list_id") else set()
        order = {s: i for i, s in enumerate(seq.get("school_order", []))}
        only = set(seq.get("school_only") or [])       # optional: route one school to its own sequence
        exclude = set(seq.get("school_exclude") or [])  # optional: keep that school out of the shared one
        skips, pool = {}, []
        for cid in ids:
            p = props.get(cid, {})
            school = (p.get("school_canonical") or "").strip()
            if only and school not in only:
                continue                                 # not this sequence's audience; not a skip
            if school in exclude:
                continue
            if cid in done:
                skips["already enrolled by script"] = skips.get("already enrolled by script", 0) + 1
                continue
            if cid in state.get("skipped_permanent", {}):
                why = state["skipped_permanent"][cid].get("why", "contact rejected")
                skips[f"HubSpot: {why}"] = skips.get(f"HubSpot: {why}", 0) + 1
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
        ok_n, fail, consec_sender_fail = 0, [], 0
        for c in batch:
            p = props[c]
            if not live:
                continue
            ok, sender, detail = do_enroll(seq["sequence_id"], c, p.get("email"))
            if ok:
                ok_n += 1
                consec_sender_fail = 0
                done[c] = {"seq": seq["sequence_id"], "date": today, "email": p.get("email")}
            else:
                fail.append((p.get("email"), detail))
                # sender=None means no candidate inbox was accepted. That is the
                # inbox, not this teacher, so every remaining contact will fail
                # identically. Stop rather than spend 50 calls proving it and
                # marking 50 teachers failed for someone else's problem.
                if sender is None:
                    consec_sender_fail += 1
                    if consec_sender_fail >= SENDER_FAIL_ABORT:
                        sender_down = detail
                        print(f"  ABORTING: {consec_sender_fail} consecutive sender-level "
                              f"rejections. The sending inbox looks down, not the contacts.")
                        break
                else:
                    consec_sender_fail = 0
            time.sleep(0.4)
        if live:
            # Every failure, not fail[:3]. On 2026-09-08 the log read "FAILED 4"
            # and named three; the fourth teacher existed only as a number, in
            # both the run log and the Slack digest. A count is not a record.
            print(f"  enrolled {ok_n}/{len(batch)}" + (f"; FAILED {len(fail)}" if fail else ""))
            for email, detail in fail:
                print(f"    FAILED {email}: {detail}")
        summary.append((seq["name"], len(batch), ok_n, len(fail), remaining, by_school))

    if not live:
        print("\nDRY RUN — nothing enrolled. Workflow passes --confirm ENROLL on schedule.")
        return
    state["runs"].append({"date": today, "at": now.isoformat(), "summary": [
        {"sequence": n, "batch": b, "enrolled": o, "failed": f, "remaining": r} for n, b, o, f, r, _ in summary]})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=1))
    lines = []
    if sender_down:
        # Lead with this. A dead sender stops the whole campaign, and the run
        # otherwise reads like an ordinary day with a lot of failures.
        lines += [
            f":rotating_light: TEACHER OUTREACH STOPPED for {today}: the sending inbox was refused.",
            f"HubSpot would not send as {state.get('sender_email_confirmed') or 'the configured sender'}.",
            f"Last error: {sender_down[:300]}",
            "Nobody after that point was enrolled, and no teacher was contacted twice.",
            "Check that the inbox is still connected in HubSpot (Settings, General, Email).",
            "Tomorrow's run will pick up where this stopped once it is fixed.",
            "",
        ]
    lines.append(f"Teacher outreach enrollments for {today} (from {state.get('sender_email_confirmed')}):")
    for n, b, o, f, r, bs in summary:
        lines.append(f"• {n}: enrolled {o} of {b}" + (f", {f} failed" if f else "") + f", {r} still to go. " +
                     ", ".join(f"{k} {v}" for k, v in bs.items()))
    lines.append("Replies exit the sequence on their own. \"Send it\" replies: ping Roman for the roster.")
    try:
        lines.append(signals(cfg))
    except Exception as e:  # the summary must never fail because a count did
        lines.append(f"(signals unavailable this run: {str(e)[:80]})")
    text = "\n".join(lines)
    print("\n" + text)
    for uid in (cfg.get("notify", {}).get("slack_user_ids") or []) + ([os.getenv("ROMAN_SLACK_USER_ID")] if os.getenv("ROMAN_SLACK_USER_ID") else []):
        slack_dm(uid, text)


if __name__ == "__main__":
    main()

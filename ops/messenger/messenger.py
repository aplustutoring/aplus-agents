#!/usr/bin/env python3
"""Bulk messenger — custom email + SMS to customer LISTS, on demand.

BULK ONLY by design (Roman 2026-08-14): takes a HubSpot static/dynamic list id,
refuses to run under `min_bulk` recipients (config.yml) — this engine is not a
1:1 messaging tool. Approval-first: dry-run is the default; a live send
additionally requires --confirm SEND.

Channels (Roman's rail decisions, 2026-08-14):
  email — HubSpot marketing email. The agent CLONES an existing marketing
          email (template designed in-portal, personalization via native
          {{contact.*}} tokens e.g. contact.student_first_name /
          contact.last_tutor_name), retargets the clone at the list, and
          leaves it as a DRAFT with a review link. Sending is Roman clicking
          Send in HubSpot — suppression (opt-outs, bounces, non-marketing
          contacts) is HubSpot-native at send time.
  sms   — JustCall API, per-contact rendered from a repo template
          (ops/messenger/templates/*.txt, {{token}} = contact property).
          From-number routing: --sms-from sales|conference (config.yml).
          Guardrails: sms_opt_out contacts skipped, "STOP" opt-out line
          required in the template, quiet hours enforced (PT), phone
          normalized to E.164.

Usage:
  python3 ops/messenger/messenger.py --list-id 3104 --channel sms \
      --sms-template templates/charter_win_back.txt --sms-from sales
  ... add --live --confirm SEND to actually send (default is dry-run).

Auth (env / repo-root .env): HUBSPOT_PRIVATE_APP_TOKEN (or HUBSPOT_API_KEY),
JUSTCALL_API_KEY + JUSTCALL_API_SECRET (SMS only).
"""

import argparse
import base64
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
CFG = yaml.safe_load(open(HERE / "config.yml"))

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
JUSTCALL_API_KEY = os.getenv("JUSTCALL_API_KEY", "")
JUSTCALL_API_SECRET = os.getenv("JUSTCALL_API_SECRET", "")

HS_BASE = "https://api.hubapi.com"
JC_BASE = "https://api.justcall.io"
PORTAL = CFG["portal_id"]

MERGE_PROPS = ["firstname", "lastname", "email", "phone",
               "student_first_name", "last_tutor_name"]
SMS_OPT_OUT_PROP = "sms_opt_out"
TOKEN_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


# ─── HubSpot ─────────────────────────────────────────────────────────────────

def hs(method, path, **kwargs):
    headers = {"Authorization": f"Bearer {HUBSPOT_TOKEN}",
               "Content-Type": "application/json"}
    for attempt in range(5):
        r = requests.request(method, f"{HS_BASE}{path}", headers=headers,
                             timeout=30, **kwargs)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)) or 10)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.text else {}
    raise RuntimeError(f"{method} {path}: rate-limited after retries")


def fetch_list_contacts(list_id):
    ids = []
    after = None
    while True:
        path = f"/crm/v3/lists/{list_id}/memberships?limit=250"
        if after:
            path += f"&after={after}"
        page = hs("GET", path)
        ids += [str(m["recordId"]) for m in page.get("results", [])]
        after = (page.get("paging", {}).get("next") or {}).get("after")
        if not after:
            break
    out = []
    props = MERGE_PROPS + [SMS_OPT_OUT_PROP]
    for i in range(0, len(ids), 100):
        page = hs("POST", "/crm/v3/objects/contacts/batch/read",
                  json={"inputs": [{"id": c} for c in ids[i:i + 100]],
                        "properties": props})
        for row in page.get("results", []):
            c = {k: (row["properties"].get(k) or "").strip() for k in props}
            c["id"] = str(row["id"])
            out.append(c)
    return out


# ─── email channel: clone -> retarget -> DRAFT ───────────────────────────────

def prepare_email_draft(template_email_id, list_id, run_label):
    clone = hs("POST", "/marketing/v3/emails/clone",
               json={"id": str(template_email_id),
                     "cloneName": f"[messenger] {run_label}"})
    email_id = clone.get("id")
    try:
        hs("PATCH", f"/marketing/v3/emails/{email_id}",
           json={"to": {"contactIlsLists": {"include": [int(list_id)]}}})
        retargeted = True
    except RuntimeError as e:
        print(f"  ⚠️  clone created but list retarget failed ({e}); "
              f"set recipients by hand before sending")
        retargeted = False
    url = f"https://app.hubspot.com/email/{PORTAL}/edit/{email_id}/settings"
    return email_id, retargeted, url


# ─── sms channel: render + JustCall ──────────────────────────────────────────

def render(template, contact):
    def sub(m):
        return contact.get(m.group(1), "")
    return TOKEN_RE.sub(sub, template)


def normalize_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return ""  # unusable


_jc_auth_mode = "plain"


def _jc_headers():
    global _jc_auth_mode
    if _jc_auth_mode == "plain":
        auth = f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}"
    else:
        auth = "Basic " + base64.b64encode(
            f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}".encode()).decode()
    return {"Authorization": auth, "Accept": "application/json",
            "Content-Type": "application/json"}


def jc_send_sms(from_number, to_number, body):
    global _jc_auth_mode
    for attempt in range(4):
        r = requests.post(f"{JC_BASE}/v2.1/texts/new", headers=_jc_headers(),
                          json={"justcall_number": from_number,
                                "contact_number": to_number,
                                "body": body}, timeout=30)
        if r.status_code == 401 and _jc_auth_mode == "plain":
            _jc_auth_mode = "basic"
            continue
        if r.status_code == 404 and "v2.1" in r.url:
            # some accounts are still on v1
            r = requests.post(f"{JC_BASE}/v1/texts/new", headers=_jc_headers(),
                              json={"justcall_number": from_number,
                                    "contact_number": to_number,
                                    "body": body}, timeout=30)
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        return r.status_code < 400, f"{r.status_code} {r.text[:200]}"
    return False, "rate-limited after retries"


def within_quiet_hours():
    now = datetime.now(ZoneInfo(CFG["sms"]["timezone"]))
    return not (CFG["sms"]["send_window_start"] <= now.hour < CFG["sms"]["send_window_end"])


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Bulk messenger (bulk lists only)")
    ap.add_argument("--list-id", required=True)
    ap.add_argument("--channel", required=True, choices=["email", "sms", "both"])
    ap.add_argument("--sms-template", default="")
    ap.add_argument("--sms-from", default="sales",
                    choices=list(CFG["sms"]["numbers"]))
    ap.add_argument("--email-template-id", default="",
                    help="HubSpot marketing email id to clone")
    ap.add_argument("--live", action="store_true", help="default is dry-run")
    ap.add_argument("--confirm", default="",
                    help="must be SEND for a live run")
    args = ap.parse_args()

    if not HUBSPOT_TOKEN:
        sys.exit("Missing HUBSPOT_PRIVATE_APP_TOKEN")
    live = args.live
    if live and args.confirm != "SEND":
        sys.exit("Live run requires --confirm SEND (approval-first).")

    contacts = fetch_list_contacts(args.list_id)
    print(f"list {args.list_id}: {len(contacts)} contacts")
    if len(contacts) < CFG["min_bulk"]:
        sys.exit(f"BULK ONLY: {len(contacts)} recipients < min_bulk "
                 f"{CFG['min_bulk']} — this engine refuses small/1:1 sends.")

    run_label = f"list {args.list_id} {datetime.now(ZoneInfo(CFG['sms']['timezone'])):%Y-%m-%d %H:%M}"

    # ── email ──
    if args.channel in ("email", "both"):
        if not args.email_template_id:
            sys.exit("--email-template-id required for the email channel")
        print("📧 EMAIL — clone + retarget (draft only; send happens in HubSpot)")
        if live:
            email_id, retargeted, url = prepare_email_draft(
                args.email_template_id, args.list_id, run_label)
            print(f"  draft ready: {url}  (recipients {'set' if retargeted else 'NOT SET'})")
        else:
            print(f"  DRY RUN: would clone email {args.email_template_id} and "
                  f"retarget at list {args.list_id}")

    # ── sms ──
    if args.channel in ("sms", "both"):
        if not args.sms_template:
            sys.exit("--sms-template required for the sms channel")
        if not (JUSTCALL_API_KEY and JUSTCALL_API_SECRET):
            sys.exit("Missing JUSTCALL_API_KEY / JUSTCALL_API_SECRET")
        template = open(HERE / args.sms_template).read().strip() \
            if not os.path.isabs(args.sms_template) else open(args.sms_template).read().strip()
        if "stop" not in template.lower():
            sys.exit('SMS template must contain an opt-out line (e.g. "Reply STOP to opt out").')
        from_number = CFG["sms"]["numbers"][args.sms_from]

        sendable, skipped = [], {"opted_out": 0, "no_phone": 0, "bad_phone": 0}
        for c in contacts:
            if c.get(SMS_OPT_OUT_PROP) == "true":
                skipped["opted_out"] += 1
                continue
            if not c.get("phone"):
                skipped["no_phone"] += 1
                continue
            e164 = normalize_phone(c["phone"])
            if not e164:
                skipped["bad_phone"] += 1
                continue
            sendable.append((c, e164, render(template, c)))

        print(f"📱 SMS from {args.sms_from} ({from_number}): {len(sendable)} sendable, "
              f"skipped {skipped}")
        for c, e164, body in sendable[:5]:
            print(f"  sample -> {e164}: {body[:160]}")

        if not live:
            print("  DRY RUN — nothing sent.")
        else:
            if within_quiet_hours():
                sys.exit(f"Quiet hours ({CFG['sms']['send_window_start']}:00–"
                         f"{CFG['sms']['send_window_end']}:00 "
                         f"{CFG['sms']['timezone']}) — refusing live SMS now.")
            ok = failed = 0
            for c, e164, body in sendable:
                success, detail = jc_send_sms(from_number, e164, body)
                if success:
                    ok += 1
                else:
                    failed += 1
                    print(f"  ❌ {e164}: {detail}")
                time.sleep(CFG["sms"]["per_send_delay_s"])
            print(f"  SENT {ok}, FAILED {failed} of {len(sendable)}")

    print("done.")


if __name__ == "__main__":
    main()

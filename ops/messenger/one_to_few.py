#!/usr/bin/env python3
"""one_to_few: the small-send rail (1 to 24 recipients) behind the pre-send gate.

Why: the bulk messenger refuses under 25 recipients by design ("not a 1:1
tool"), so on 2026-09-08/09 every follow-up text to a family or tutor ran from
a session script that copied the engine's pieces and none of its checks. One
of those texts went to a family scheduling already owned on another line.

This rail sends to an explicit list of contacts (or a HubSpot list) under
`presend.max_few`, and every recipient passes email/src/presend.check() first:
opt-out, quiet hours, stage-to-line rule, active thread on another line,
unanswered reply, open scheduling ticket, frequency, standing go, STOP line.
Dry run is the default and prints one row per contact:

  ALLOW | Mary Gonzalez | charter_sales | lead | body...
  HOLD  | ...            | ...           | ...  | active thread on the support line, owned by Yolanda

Live (`--live --confirm SEND`) sends ALLOW rows only, records each send with
presend.record_send (HubSpot note + [Agent] properties + audit) and appends to
ops/messenger/state/sends/<date>-<purpose>.jsonl.

`--from` and `--purpose` have no defaults on purpose: the incident was a
default. Bodies: `--template templates/x.txt` ({{token}} merge, same as the
bulk messenger) or `--bodies bodies.json` ({contact_id: text}) for hand-written
relays. Every body goes through the em-dash scrub.

Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.
Before contacting a family, teacher, or tutor, read knowledge/journey/README.md
and pass knowledge/journey/00-pre-send-checklist.md. Act only on stages marked
REVIEWED.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "email"))

import messenger as m  # noqa: E402  (bulk engine: render, normalize_phone, jc_send_sms, hs)
from src import presend  # noqa: E402
from src.config import DRY_RUN, RESEND_API_KEY, cfg as email_cfg  # noqa: E402
from src.gmail_client import _scrub_outbound  # noqa: E402

EXTRA_PROPS = ["a_persona", "sms_opt_out", "hs_email_optout", "mobilephone",
               "agent_last_outbound_at", "agent_last_outbound_seat", "student_names",
               "student_count"]
CHANNELS = ("sms", "email")
EMAIL_LINE = "email"   # the from-line name presend accepts for email sends


def _pc() -> dict:
    return email_cfg().get("presend") or {}


def send_email(from_addr: str, to_addr: str, body: str, subject: str) -> tuple[bool, str]:
    """Email leg of the rail (added 2026-09-15 for the IEM HSA ES email): the
    same Resend identity the welcome emails use, plain text, reply-to admin@,
    HubSpot BCC stamp. Subject AND body are customer-facing copy, so both are
    scrubbed before this is called (build_rows). Returns (ok, detail) like
    jc_send_sms so send_rows treats the two legs alike."""
    payload = {"from": from_addr, "to": [to_addr],
               "reply_to": _pc().get("email_reply_to") or "admin@wetutorathome.com",
               "subject": subject, "text": body}
    bcc = (email_cfg().get("hubspot") or {}).get("bcc_log_address")
    if bcc:
        payload["bcc"] = [bcc]
    if DRY_RUN:
        return True, "dry run"
    import requests
    r = requests.post("https://api.resend.com/emails",
                      headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                      json=payload, timeout=30)
    if r.status_code >= 300:
        return False, f"HTTP {r.status_code}: {r.text[:120]}"
    return True, f"resend {r.json().get('id', 'ok')}"


def fetch_contacts(ids: list[str]) -> list[dict]:
    """Batch-read the merge props + gate props for explicit contact ids."""
    props = sorted(set(m.MERGE_PROPS + EXTRA_PROPS))
    out = []
    for i in range(0, len(ids), 100):
        j = m.hs("POST", "/crm/v3/objects/contacts/batch/read",
                 json={"inputs": [{"id": c} for c in ids[i:i + 100]], "properties": props})
        for row in j.get("results", []):
            c = {k: (row["properties"].get(k) or "").strip() for k in props}
            c["id"] = str(row["id"])
            out.append(c)
    return out


def build_rows(contacts: list[dict], *, purpose: str, from_line: str, template: str = "",
               bodies: dict | None = None, confirmed: bool = False, go_token: str = "",
               check=None, channel: str = "sms", subject: str = "",
               subjects: dict | None = None) -> list[dict]:
    """One row per contact: render, scrub, gate. Pure; no sends.
    channel="email": the recipient is the contact's email, `subject` (or
    per-contact `subjects`) is rendered and scrubbed like the body, and the
    gate runs on the email channel (no quiet hours, no STOP line)."""
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of {CHANNELS}")
    check = check or presend.check          # resolved at call time (tests patch presend.check)
    rows = []
    for c in contacts:
        cid = c["id"]
        if bodies is not None:
            body = bodies.get(cid, "")
        else:
            needed = set(m.TOKEN_RE.findall(template))
            if any(not c.get(t) for t in needed):
                rows.append({"contact": c, "verdict": "skip", "reasons":
                             [f"missing merge field(s): {sorted(t for t in needed if not c.get(t))}"],
                             "body": ""})
                continue
            body = m.render(template, c)
        body = _scrub_outbound(body or "")
        if not body:
            rows.append({"contact": c, "verdict": "skip", "reasons": ["no body"], "body": ""})
            continue
        if channel == "email":
            to = (c.get("email") or "").strip().lower()
            if "@" not in to:
                rows.append({"contact": c, "verdict": "skip", "reasons": [f"unusable email {to!r}"],
                             "body": body, "channel": channel})
                continue
            raw_subject = (subjects or {}).get(cid, subject) if subjects is not None else subject
            subj = _scrub_outbound(m.render(raw_subject, c) if "{{" in (raw_subject or "") else raw_subject)
            if not subj:
                rows.append({"contact": c, "verdict": "skip", "reasons": ["no subject"],
                             "body": body, "channel": channel})
                continue
            d = check(cid, "email", from_line, purpose, phone="", body=body,
                      contact={"id": cid, "properties": c}, confirmed=confirmed, go_token=go_token)
            rows.append({"contact": c, "verdict": d.verdict, "reasons": d.reasons, "body": body,
                         "subject": subj, "to": to, "owner": d.owner, "audience": d.audience,
                         "in_thread": d.in_thread, "channel": channel})
            continue
        phone = c.get("mobilephone") or c.get("phone") or ""
        e164 = m.normalize_phone(phone)
        if not e164:
            rows.append({"contact": c, "verdict": "skip", "reasons": [f"unusable phone {phone!r}"],
                         "body": body})
            continue
        d = check(cid, "sms", from_line, purpose, phone=e164, body=body,
                  contact={"id": cid, "properties": c}, confirmed=confirmed, go_token=go_token)
        rows.append({"contact": c, "verdict": d.verdict, "reasons": d.reasons, "body": body,
                     "to": e164, "owner": d.owner, "audience": d.audience, "in_thread": d.in_thread,
                     "channel": "sms"})
    return rows


def print_rows(rows: list[dict], from_line: str) -> None:
    for r in rows:
        c = r["contact"]
        name = f"{c.get('firstname', '')} {c.get('lastname', '')}".strip() or c["id"]
        who = ""
        if r.get("owner"):
            who = f" -> {r['owner'].get('name') or r['owner'].get('seat')}"
        print(f"{r['verdict'].upper():5s} | {name:28s} | {from_line:13s} | {r.get('audience', ''):10s} | "
              f"{'; '.join(r['reasons'])[:120]}{who}")
        if r["verdict"] in ("allow", "hold"):
            print(f"      {r['body'][:200]}")


def send_rows(rows: list[dict], *, purpose: str, from_line: str, approved_by: str = "",
              sender=None, record=None, delay: float | None = None,
              channel: str = "sms") -> dict:
    """Live path: ALLOW rows only. Returns counts. channel="email" sends each
    row's scrubbed subject + body through send_email as the configured
    presend.email_from identity instead of a JustCall line."""
    record = record or presend.record_send
    if channel == "email":
        from_id = (_pc().get("email_from")
                   or "A+ Tutoring Success Team <admin@wetutorathome.com>")
        sender = sender or send_email
    else:
        from_id = (_pc().get("lines") or {}).get(from_line, "")
        if not from_id:
            sys.exit(f"no number configured for line {from_line!r} (email/config.yaml presend.lines)")
        sender = sender or m.jc_send_sms
    if delay is None:
        delay = float(m.CFG["sms"].get("per_send_delay_s", 0.5))
    log_dir = HERE / "state" / "sends"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(ZoneInfo(m.CFG["sms"]["timezone"])).strftime("%Y-%m-%d")
    log_path = log_dir / f"{today}-{purpose}.jsonl"
    counts = {"sent": 0, "failed": 0, "held": 0, "blocked": 0, "skipped": 0}
    with open(log_path, "a") as log:
        for r in rows:
            if r["verdict"] != "allow":
                counts[{"hold": "held", "block": "blocked"}.get(r["verdict"], "skipped")] += 1
                continue
            if channel == "email":
                ok, detail = sender(from_id, r["to"], r["body"], r.get("subject", ""))
            else:
                ok, detail = sender(from_id, r["to"], r["body"])
            counts["sent" if ok else "failed"] += 1
            record(r["contact"]["id"], channel, from_line, purpose, r["to"], r["body"],
                   "one_to_few", ok, detail, approved_by)
            log.write(json.dumps({"contact_id": r["contact"]["id"], "email": r["contact"].get("email"),
                                  "to": r["to"], "ok": ok, "detail": str(detail)[:160],
                                  "body": r["body"], "subject": r.get("subject", ""),
                                  "channel": channel, "purpose": purpose, "from_line": from_line,
                                  "approved_by": approved_by,
                                  "ts": datetime.utcnow().isoformat()}) + "\n")
            time.sleep(delay)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="Small sends (1 to 24) behind the pre-send gate")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--contacts", help="comma-separated HubSpot contact ids")
    src.add_argument("--list-id", help="HubSpot list id (must be under presend.max_few)")
    ap.add_argument("--purpose", required=True, help="a key in email/config.yaml presend.purposes")
    ap.add_argument("--from", dest="from_line", required=True,
                    help="a key in presend.lines: charter_sales | support | sales | conference")
    body = ap.add_mutually_exclusive_group(required=True)
    body.add_argument("--template", help="path under ops/messenger/ with {{token}} merge fields")
    body.add_argument("--bodies", help="JSON file {contact_id: text} for hand-written relays")
    ap.add_argument("--live", action="store_true", help="default is dry-run")
    ap.add_argument("--confirm", default="", help='type SEND to allow a live run')
    ap.add_argument("--approved-by", default="", help="who said go (Slack id or name)")
    ap.add_argument("--channel", choices=CHANNELS, default="sms",
                    help="email = plain-text email via Resend to the contact's address; --from email")
    ap.add_argument("--subject", default="", help="email channel: subject ({{token}} merge, scrubbed)")
    args = ap.parse_args(argv)

    pc = _pc()
    if args.purpose not in (pc.get("purposes") or {}):
        sys.exit(f"unknown purpose {args.purpose!r}; declare it in email/config.yaml presend.purposes")
    if args.channel == "email":
        if args.from_line != EMAIL_LINE:
            sys.exit(f"--channel email sends from the {EMAIL_LINE!r} line (presend.email_from)")
        if not args.subject:
            sys.exit("--channel email requires --subject")
    elif args.from_line not in (pc.get("lines") or {}):
        sys.exit(f"unknown line {args.from_line!r}; one of {sorted((pc.get('lines') or {}).keys())}")
    live = args.live and args.confirm == "SEND"
    if args.live and not live:
        sys.exit("--live requires --confirm SEND")

    if args.contacts:
        ids = [x.strip() for x in args.contacts.split(",") if x.strip()]
        contacts = fetch_contacts(ids)
    else:
        contacts = m.fetch_list_contacts(args.list_id)
        # the bulk fetch carries only MERGE_PROPS; refetch with the gate props
        contacts = fetch_contacts([c["id"] for c in contacts])
    max_few = int(pc.get("max_few") or 25)
    if len(contacts) > max_few:
        sys.exit(f"{len(contacts)} recipients > presend.max_few {max_few}. Use the bulk messenger "
                 f"(ops/messenger/messenger.py) for rounds of {m.CFG['min_bulk']}+.")
    if not contacts:
        sys.exit("no contacts")

    template, bodies = "", None
    if args.template:
        path = Path(args.template) if Path(args.template).is_absolute() else HERE / args.template
        template = path.read_text().strip()
    else:
        bodies = json.loads(Path(args.bodies).read_text())

    rows = build_rows(contacts, purpose=args.purpose, from_line=args.from_line, template=template,
                      bodies=bodies, confirmed=live, channel=args.channel, subject=args.subject)
    print(f"one_to_few: {len(rows)} contacts, purpose={args.purpose}, from={args.from_line}, "
          f"channel={args.channel}, {'LIVE' if live else 'DRY RUN'}")
    print_rows(rows, args.from_line)
    if not live:
        print("DRY RUN, nothing sent.")
        return 0
    counts = send_rows(rows, purpose=args.purpose, from_line=args.from_line,
                       approved_by=args.approved_by, channel=args.channel)
    print(f"done: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

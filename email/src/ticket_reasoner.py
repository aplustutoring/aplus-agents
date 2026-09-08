"""Reasoning sweep over EVERY open ticket.

The aging sweep asks one question — how long since anyone touched this. That is
the wrong question on its own: on 2026-08-26 a pure 24-hour rule would have sent
102 DMs, 77 of them to Kath, and most of hers were PO tickets whose invoice had
already existed. Pestering someone about finished work is how a bot gets muted.

So this pass gathers evidence across HubSpot and JustCall, decides what state the
ticket is actually in, and only then acts:

  RESOLVED        proved done by hard evidence    → close
  NO_ACTION       a notification, never work      → close
  DUPLICATE       same PO or thread as another    → close
  BALL_IN_COURT   someone is waiting on us        → pester
  WAITING         we answered, they went quiet    → pester (Roman 2026-08-26:
                                                    pester regardless of who
                                                    owes what)
  UNCLEAR         evidence does not settle it     → pester, never close

Closing is gated on `reasoner.allow_close`. Run with --dry-run first: it prints
every verdict with the evidence behind it and writes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone

from . import (audit, gmail_client as gm, hubspot_client as hs,
               justcall_client as jc, slack_client)
from .config import ANTHROPIC_API_KEY, cfg, staff

CLOSEABLE = {"RESOLVED", "NO_ACTION", "DUPLICATE"}
AGENT_PREFIXES = ("po_inbox", "new_po")


# ── evidence ────────────────────────────────────────────────────────────────
def _ts(v):
    if not v:
        return None
    s = str(v)
    try:
        if s.isdigit():
            return datetime.fromtimestamp(int(s) / 1000, timezone.utc)
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _norm_phone(p: str) -> str:
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else ""


def gather(ticket: dict, sms_index: dict | None = None) -> dict:
    """Everything knowable about one ticket, from every system we have."""
    p = ticket.get("properties") or {}
    tid = ticket["id"]
    created = _ts(p.get("createdate"))
    now = datetime.now(timezone.utc)
    subject = (p.get("subject") or "").strip()

    ev = {
        "ticket_id": tid,
        "subject": subject,
        "stage": p.get("hs_pipeline_stage"),
        "owner_id": p.get("hubspot_owner_id"),
        "description": (p.get("content") or "")[:600],
        "age_hours": round((now - created).total_seconds() / 3600, 1) if created else 0,
        "quiet_hours": 0,
        "agent_filed": subject.startswith(AGENT_PREFIXES),
        "emails": [], "notes": [], "sms": [], "calls": [],
        "invoice_proof": None, "duplicate_of": None, "gmail_thread": None,
        # None means the pull failed, so an empty sms list proves nothing.
        "phone_evidence": "available" if sms_index is not None else "UNAVAILABLE",
    }
    lm = _ts(p.get("hs_lastmodifieddate"))
    if lm:
        ev["quiet_hours"] = round((now - lm).total_seconds() / 3600, 1)

    for m in hs.get_ticket_emails(tid):
        t = _ts(m.get("hs_timestamp"))
        if not t:
            continue
        ev["emails"].append({
            "at": t.isoformat(),
            "direction": "outbound" if m.get("hs_email_direction") == "EMAIL" else "inbound",
            "text": re.sub(r"\s+", " ", (m.get("hs_email_text") or ""))[:400]})
    ev["emails"].sort(key=lambda x: x["at"])

    for n in hs.get_ticket_notes(tid):
        t = _ts(n.get("hs_timestamp"))
        body = re.sub(r"<[^>]+>", " ", n.get("hs_note_body") or "")
        ev["notes"].append({"at": t.isoformat() if t else "",
                            "text": re.sub(r"\s+", " ", body)[:300]})

    contacts = hs.get_ticket_contacts(tid)
    if contacts:
        cp = contacts[0].get("properties") or {}
        ev["contact"] = f"{cp.get('firstname','')} {cp.get('lastname','')}".strip()
        phone = _norm_phone(cp.get("mobilephone") or cp.get("phone"))
        if phone and sms_index is not None:
            hit = sms_index.get(phone) or {}
            since = created.strftime("%Y-%m-%dT%H:%M:%S") if created else ""
            # Keep a wide window. A tutor match runs to 20+ messages in a single
            # afternoon, and the message that settles it sits in the middle:
            # truncating to the last 8 on 2026-08-26 cut "attached is his
            # profile" and turned a completed match into an unkept promise.
            ev["sms"] = [x for x in hit.get("texts", [])
                         if x.get("at", "") >= since][-40:]
            ev["calls"] = [x for x in hit.get("calls", [])
                           if x.get("at", "") >= since][-15:]
    return ev


# The sender is written two ways: the ticket DESCRIPTION says
# "From: Name <addr>" while the agent's note says "— from Name". Rather than
# matching either shape, take the first real address that is not our own inbox.
_PO_ADDR = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_PO_SUBJ = re.compile(r"Subject:\s*(.+)", re.I)


def enrich_gmail_thread(ev: dict) -> dict:
    """For PO tickets, read the charter@ Gmail thread.

    These tickets carry no HubSpot email engagements at all: the inbound mail is
    embedded as a note and every reply Kath sends leaves from Gmail, so HubSpot
    never sees it. Judging them on HubSpot alone made the sweep report "no
    response from us is recorded" on 44 of Kath's 97 tickets when it simply
    could not see her outbound (Roman, 2026-08-27).

    `gmail_thread: UNAVAILABLE` means the thread could not be located, which is
    NOT evidence that nobody replied.
    """
    if not ev.get("agent_filed"):
        return ev
    blob = ev.get("description") or ""
    for n in ev.get("notes", []):
        if "Original email" in n.get("text", ""):
            blob = f"{blob}\n{n['text']}"
            break
    inbox_addr = (cfg().get("po_inbox", {}).get("address") or "").lower()
    sender = next((a for a in _PO_ADDR.findall(blob)
                   if a.lower() != inbox_addr and "wetutorathome" not in a.lower()), "")
    # Prefer the TICKET subject: it is the email subject with a known prefix, so
    # it needs no delimiter guessing. The note body is flattened to one line by
    # gather(), which makes "Subject:(.+)" swallow the entire message.
    subject = re.sub(r"^(po_inbox review|new_po)\s*[—-]\s*", "",
                     ev.get("subject") or "", flags=re.I).strip()
    if not subject:
        m = _PO_SUBJ.search(blob)
        subject = (m.group(1)[:90] if m else "")
    ev["gmail_thread"] = "UNAVAILABLE"
    try:
        tid = gm.find_thread(subject, sender)
        if not tid:
            return ev
        msgs = gm.get_thread(tid)
    except Exception as e:  # noqa: BLE001 — degraded, never fatal
        print(f"  ⚠️  gmail thread lookup failed for ticket {ev['ticket_id']}: {e}")
        return ev
    inbox = (cfg().get("po_inbox", {}).get("address") or "").lower()
    ev["gmail_thread"] = [{
        "at": datetime.fromtimestamp(m["date_ms"] / 1000, timezone.utc).isoformat(),
        "direction": "outbound" if inbox and inbox in (m.get("sender") or "").lower() else "inbound",
        "from": (m.get("sender") or "")[:80],
        "text": re.sub(r"\s+", " ", m.get("body") or "")[:600],
    } for m in msgs][-12:]
    return ev


def enrich_invoice_proof(ev: dict, invoiced_pos: set[str]) -> dict:
    """The proof that turns a PO ticket from 'old' into 'finished': its deal
    already carries an Invoice #, so step 1 happened and nobody closed the
    ticket. Cross-checked against the Teachworks invoice xref on 2026-08-26 —
    identical answer on the open queue, from one system instead of two."""
    m = re.search(r"\(PO ([A-Za-z0-9\-]+)\)", ev["subject"])
    if m and m.group(1) in invoiced_pos:
        ev["invoice_proof"] = f"PO {m.group(1)} already has an Invoice # on its deal"
    return ev


def mark_duplicates(evs: list[dict]) -> list[dict]:
    """Two open tickets carrying the SAME PO NUMBER are the same work. The older
    one keeps the history; the newer one is noise.

    PO number is the only key used, deliberately. The 2026-08-26 dry run tried
    matching on subject text too and moved to close ticket 45243331980 — one of
    two tickets both titled "Eddie Sumlin" from the same referral partner, but
    for different students (CNA support on Saturdays vs a new intake for
    Kaliyah P). Closing it would have destroyed a live referral. Subject text is
    not identity, and `source_thread_id` — which would be — is populated on zero
    open tickets, so there is no thread key to fall back on yet.
    """
    by_po = {}
    for ev in sorted(evs, key=lambda e: -e["age_hours"]):
        ev["duplicate_of"] = None
        m = re.search(r"\(PO ([A-Za-z0-9\-]+)\)", ev["subject"])
        if not m:
            continue
        po = m.group(1)
        ev["duplicate_of"] = by_po.get(po)
        if po not in by_po:
            by_po[po] = ev["ticket_id"]
    return evs


# ── reasoning ───────────────────────────────────────────────────────────────
SYSTEM = """You triage support tickets for a tutoring company by reading the \
evidence trail, not by counting days.

Return ONLY a JSON object:
{"verdict": "...", "confidence": 0.0-1.0, "reason": "one sentence citing the evidence", "owed_to": "us|them|nobody"}

verdict is exactly one of:
  RESOLVED       the work is demonstrably done, or the thread reached its natural end
  NO_ACTION      an automated notification that never needed a human reply
  DUPLICATE      the same work as another open ticket
  BALL_IN_COURT  a person is waiting on US for a reply or an action
  WAITING        we answered and the other side has gone quiet
  UNCLEAR        the evidence does not settle it

Rules that matter here:
- An `invoice_proof` field is PROOF the PO work is done.
- notifications@teachworks.com messages (form completed, low balance, lesson
  cancelled) are NO_ACTION unless a human asked something.
- The agent's own auto-receipt ("we've received your document") is NOT a reply.
  If a person asked a question and only the auto-receipt followed, that is
  BALL_IN_COURT.
- Money owed in either direction, complaints, and resignations are BALL_IN_COURT
  unless there is clear evidence they were settled.
- Later SMS or calls about the same family can supersede an old ticket: say so.
- PO tickets (po_inbox / new_po) have NO HubSpot emails by design; their whole
  correspondence is in `gmail_thread`. Read that to see whether WE replied.
  `gmail_thread: UNAVAILABLE` means the thread could not be found — that is not
  evidence nobody replied, so cap confidence at 0.6 on those.
- `phone_evidence: UNAVAILABLE` means the SMS/call pull FAILED. An empty sms or
  calls list then proves nothing — never read it as "no contact happened", and
  never exceed 0.6 confidence on a ticket whose story would live in texts.
- Only use confidence above 0.85 when a second system proves it.
Be terse and concrete. Quote what you saw."""


def reason(ev: dict, client=None) -> dict:
    """Ask the model to read the evidence and return a verdict."""
    if ev.get("duplicate_of"):
        return {"verdict": "DUPLICATE", "confidence": 0.95,
                "reason": f"same PO/thread as open ticket {ev['duplicate_of']}",
                "owed_to": "nobody"}
    if ev.get("invoice_proof"):
        return {"verdict": "RESOLVED", "confidence": 0.95,
                "reason": ev["invoice_proof"], "owed_to": "nobody"}

    from anthropic import Anthropic  # lazy so tests need no SDK

    client = client or Anthropic(api_key=ANTHROPIC_API_KEY)
    c = cfg()["classifier"]
    payload = {k: ev.get(k) for k in
               ("subject", "description", "age_hours", "quiet_hours",
                "emails", "notes", "sms", "calls", "invoice_proof",
                "phone_evidence", "gmail_thread")}
    msg = client.messages.create(
        model=c["model"], max_tokens=400, system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload, default=str)[:14000]}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"verdict": "UNCLEAR", "confidence": 0.0,
                "reason": "model returned no JSON", "owed_to": "us"}
    try:
        out = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"verdict": "UNCLEAR", "confidence": 0.0,
                "reason": "unparseable model output", "owed_to": "us"}
    if out.get("verdict") not in (CLOSEABLE | {"BALL_IN_COURT", "WAITING", "UNCLEAR"}):
        out["verdict"] = "UNCLEAR"
    return out


# ── the pester ladder ───────────────────────────────────────────────────────
def pester_targets(age_hours: float, owner_key: str) -> list[str]:
    """Roman, 2026-08-26: 24h the owner, 48h the supervisor joins, 96h the last
    resort joins, daily after that. Applies whoever the ball sits with — an
    unanswered family is still our problem."""
    r = cfg().get("reasoner", {})
    esc = cfg().get("escalation", {})
    out = []
    if age_hours >= float(r.get("owner_after_hours", 24)):
        out.append(owner_key)
    if age_hours >= float(r.get("supervisor_after_hours", 48)):
        out.append(esc.get("level2"))
    if age_hours >= float(r.get("last_resort_after_hours", 96)):
        out.append(esc.get("level3"))
    seen, uniq = set(), []
    for k in out:
        if k and k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


def _due_for_pester(tid: str, now: datetime) -> bool:
    r = cfg().get("reasoner", {})
    last = audit.last_reasoner_pester(tid)
    if not last:
        return True
    t = _ts(last)
    if not t:
        return True
    return (now - t).total_seconds() / 3600 >= float(r.get("repeat_every_hours", 24))


# ── the sweep ───────────────────────────────────────────────────────────────
def run(dry_run: bool = False, limit: int | None = None,
        pester: bool = True) -> dict:
    """pester=False closes without DMing anyone.

    The first live pass has to be close-only. On 2026-08-27 the queue held 161
    open tickets, 83 of them past the 24h ladder — firing those alongside the
    first bulk close would put ~50 DMs on Kath in one minute, which is how a bot
    gets muted before it has proved anything. Close first, let the queue fall to
    roughly 90, then turn the ladder on.
    """
    rc = cfg().get("reasoner", {})
    if not rc.get("enabled") and not dry_run:
        print("reasoner disabled in config")
        return {}
    staff_map = cfg()["staff"]
    owner_key_by_id = {str(s.get("hubspot_owner_id")): k for k, s in staff_map.items()}
    now = datetime.now(timezone.utc)

    tickets = hs.search_open_tickets()
    if limit:
        tickets = tickets[:limit]
    invoiced = hs.invoiced_po_numbers()
    try:
        sms_index = jc.index_by_number(since_days=90)
    except jc.JustCallUnavailable as e:
        # Degraded, not fatal — but it must be LOUD and it must stop the sweep
        # closing anything. A lot of A+ support happens by text, so without it
        # "no evidence" is meaningless.
        print(f"  ⚠️  JustCall unavailable ({e}) — SMS and call evidence is MISSING. "
              f"Closing is disabled for this run.")
        sms_index, rc = None, {**rc, "allow_close": False}

    evs = [enrich_invoice_proof(enrich_gmail_thread(gather(t, sms_index)), invoiced)
           for t in tickets]
    evs = mark_duplicates(evs)

    tally, closed, pestered, lines = Counter(), 0, 0, []
    for ev in evs:
        v = reason(ev)
        tally[v["verdict"]] += 1
        owner_key = owner_key_by_id.get(str(ev.get("owner_id")), "")
        act = "none"

        if (v["verdict"] in CLOSEABLE
                and v.get("confidence", 0) >= float(rc.get("close_min_confidence", 0.85))):
            act = "CLOSE"
            if not dry_run and rc.get("allow_close"):
                _close(ev, v)
                closed += 1
        elif pester and ev["age_hours"] >= float(rc.get("owner_after_hours", 24)):
            targets = pester_targets(ev["age_hours"], owner_key)
            if targets and _due_for_pester(ev["ticket_id"], now):
                act = "PESTER " + ",".join(targets)
                if not dry_run:
                    _pester(ev, v, targets)
                    pestered += 1

        lines.append({"ticket": ev["ticket_id"], "subject": ev["subject"][:56],
                      "age_h": ev["age_hours"], "owner": owner_key,
                      "verdict": v["verdict"], "confidence": v.get("confidence"),
                      "reason": v.get("reason", "")[:150], "action": act})

    if dry_run:
        _print_dry_run(lines, tally)
    else:
        print(f"reasoner: {dict(tally)} | closed {closed} | pestered {pestered}")
    return {"tally": dict(tally), "lines": lines, "closed": closed, "pestered": pestered}


def _close(ev: dict, v: dict) -> None:
    stages = cfg()["hubspot"]["ticket_stages"]
    note = (f"Closed by the reasoning sweep: {v['verdict']} "
            f"(confidence {v.get('confidence')}). {v.get('reason','')}")
    try:
        hs.update_ticket_stage(ev["ticket_id"], stages["closed"])
        hs.add_ticket_note(ev["ticket_id"], note)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  could not close {ev['ticket_id']}: {e}")
        return
    audit.append({"ticket_id": ev["ticket_id"], "source": "ticket_reasoner",
                  "action_taken": "reasoner_closed", "verdict": v["verdict"],
                  "confidence": v.get("confidence"), "reason": v.get("reason")})


def _pester(ev: dict, v: dict, targets: list[str]) -> None:
    url = hs.ticket_url(ev["ticket_id"])
    msg = (f"⏰ Open {ev['age_hours'] / 24:.0f}d — *{ev['subject'][:70]}*\n"
           f"{v['verdict']}: {v.get('reason', '')}\n{url}")
    for key in targets:
        s = staff(key)
        if s.get("slack_user_id"):
            slack_client.dm(s["slack_user_id"], msg)
    audit.append({"ticket_id": ev["ticket_id"], "source": "ticket_reasoner",
                  "action_taken": "reasoner_pester", "verdict": v["verdict"],
                  "targets": targets, "age_hours": ev["age_hours"]})


def _print_dry_run(lines: list[dict], tally: Counter) -> None:
    print(f"\n{'ticket':<13}{'age':>7} {'owner':<9}{'verdict':<15}{'conf':>5}  "
          f"{'action':<22}subject / reason")
    for r in sorted(lines, key=lambda x: (x["action"] == "none", -x["age_h"])):
        print(f"{r['ticket']:<13}{r['age_h'] / 24:>6.0f}d {r['owner']:<9}"
              f"{r['verdict']:<15}{str(r['confidence'] or ''):>5}  {r['action']:<22}{r['subject']}")
        print(f"{'':>47}{'':<24}└ {r['reason']}")
    print(f"\nverdicts: {dict(tally)}")
    print(f"would CLOSE  {sum(1 for r in lines if r['action'] == 'CLOSE')}")
    print(f"would PESTER {sum(1 for r in lines if r['action'].startswith('PESTER'))}")
    print(f"no action    {sum(1 for r in lines if r['action'] == 'none')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-pester", action="store_true",
                    help="close only; send no DMs (use for the first live pass)")
    a = ap.parse_args()
    run(dry_run=a.dry_run, limit=a.limit, pester=not a.no_pester)

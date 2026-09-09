"""Pre-send gate: the code form of knowledge/journey/00-pre-send-checklist.md.

Why this exists (2026-09-09): an agent told to "watch for responses" texted
the Gonzalez family three times from the charter_sales (lead) line while
scheduling had already booked them on the support line. Mom: "I don't know
how many people I'm talking to at A+." Nothing in either SMS engine looked at
the other line, the inbox, or open tickets before sending, and small sends had
no rail at all. Every check below is one of the questions that afternoon
skipped.

One gate for every outbound. Both engines call it:
  email/src/sms.py          (transactional, support line)   -> purpose po_welcome
  ops/messenger/one_to_few  (small sends, any line)          -> the caller's purpose

check() never raises on a data problem. A source that cannot be read (JustCall
down, thread list 5xx) yields HOLD with "could not verify", because "quiet
phone" and "could not fetch" lead to opposite conclusions (see
justcall_client.JustCallUnavailable).

Verdict order: any BLOCK wins, then any HOLD, else ALLOW.

Shadow mode: presend.enabled false means engines log the decision as
`presend_shadow` and keep their old behaviour. Flip to true after a week of
clean audit (no false holds).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import audit, hubspot_client as hs, justcall_client as jc
from .business_hours import now_la
from .config import cfg, staff
from .router import scheduler_for_last_name

CONTACT_PROPS = ["firstname", "lastname", "email", "phone", "mobilephone", "a_persona",
                 "sms_opt_out", "hs_email_optout", "agent_last_outbound_at",
                 "agent_last_outbound_seat", "agent_last_inbound_at"]

AUDIENCE_LINE = {"lead": "charter_sales", "scheduling": "support",
                 "tutor": "support", "tor": "charter_sales"}


@dataclass
class Decision:
    verdict: str                       # allow | hold | block
    reasons: list[str] = field(default_factory=list)
    in_thread: bool = False
    audience: str = ""
    owner: dict | None = None          # staff record of the seat that owns the active thread
    facts: dict = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"


def _pc() -> dict:
    return cfg().get("presend") or {}


def enabled() -> bool:
    return bool(_pc().get("enabled"))


# ── JustCall index, cached per process ─────────────────────────────
_JC = {"at": None, "idx": None, "days": 0}


def _jc_index(days: int) -> dict:
    """index_by_number once per process (5-minute cache). Raises
    JustCallUnavailable; the caller turns that into HOLD."""
    now = datetime.now(timezone.utc)
    if _JC["idx"] is not None and _JC["days"] >= days and _JC["at"] and \
            (now - _JC["at"]) < timedelta(minutes=5):
        return _JC["idx"]
    idx = jc.index_by_number(since_days=days)
    _JC.update({"at": now, "idx": idx, "days": days})
    return idx


def _reset_cache() -> None:  # tests
    _JC.update({"at": None, "idx": None, "days": 0})


# ── lookups ────────────────────────────────────────────────────────
def _contact(contact_id: str, contact: dict | None) -> dict:
    if contact and (contact.get("properties") or {}).get("firstname") is not None:
        return contact
    return hs._get(f"/crm/v3/objects/contacts/{contact_id}",
                   {"properties": ",".join(CONTACT_PROPS)})


def _audience(props: dict, deals: list[dict], season_start: str) -> str:
    persona = (props.get("a_persona") or "")
    if "Tutors" in persona:
        return "tutor"
    if "Teacher of Record" in persona:
        return "tor"
    for d in deals:
        if (d.get("createdate") or "") >= season_start:
            return "scheduling"
    return "lead"


def _line_number(key: str) -> str:
    return jc.norm_number((_pc().get("lines") or {}).get(key, ""))


def _line_key_for_number(num10: str) -> str:
    for k, v in (_pc().get("lines") or {}).items():
        if jc.norm_number(v) == num10:
            return k
    return num10 or "?"


def _owner_for_line(line_key: str, last_name: str) -> dict | None:
    seat = (_pc().get("line_owner") or {}).get(line_key)
    if not seat:
        return None
    if seat == "scheduler_split":
        key, _ = scheduler_for_last_name(last_name)
        rec = dict(staff(key or "") or {})
        rec.setdefault("seat", key)
        return rec or None
    rec = dict(staff(seat) or {})
    rec.setdefault("seat", seat)
    return rec or None


def _scheduler_owner_ids() -> set[str]:
    ids = set()
    for seat in ("scheduler_a_l", "scheduler_m_z", "scheduling_lead"):
        oid = (staff(seat) or {}).get("hubspot_owner_id")
        if oid:
            ids.add(str(oid))
    return ids


def _ms_to_dt(v) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


# ── the gate ───────────────────────────────────────────────────────
def check(contact_id: str, channel: str, from_line: str, purpose: str, *,
          phone: str = "", contact: dict | None = None, body: str = "",
          confirmed: bool = False, go_token: str = "", now=None) -> Decision:
    """Run the six checklist items plus the copy gate for one outbound."""
    pc = _pc()
    blocks, holds = [], []
    facts: dict = {"channel": channel, "from_line": from_line, "purpose": purpose}
    owner = None
    in_thread = False

    try:
        c = _contact(contact_id, contact)
    except Exception as e:  # noqa: BLE001
        return Decision("hold", [f"could not verify contact {contact_id}: {e}"], facts=facts)
    p = c.get("properties") or {}
    last_name = p.get("lastname") or ""
    phone10 = jc.norm_number(phone or p.get("mobilephone") or p.get("phone") or "")
    facts["phone10"] = phone10

    # a. opt-out
    if channel == "sms" and str(p.get("sms_opt_out")) == "true":
        blocks.append("contact opted out of SMS (sms_opt_out)")
    if channel == "email" and str(p.get("hs_email_optout")) == "true":
        blocks.append("contact opted out of email (hs_email_optout)")

    # b. quiet hours (SMS)
    if channel == "sms":
        from . import sms as _sms  # local: sms imports presend
        if not _sms._in_send_window(now):
            holds.append("quiet hours (email/config.yaml sms send window)")

    # f0. purpose must be declared
    purposes = pc.get("purposes") or {}
    if purpose not in purposes:
        blocks.append(f"unknown purpose {purpose!r}; declare it in presend.purposes")

    # c. stage -> line (LOCKED, Roman 2026-09-08)
    try:
        deals = hs.get_contact_deals(contact_id)
    except Exception as e:  # noqa: BLE001
        deals, _ = [], holds.append(f"could not verify deals: {e}")
    audience = _audience(p, deals, str(pc.get("season_start") or "2026-08-15"))
    facts["audience"] = audience
    facts["deals_this_season"] = [d.get("id") for d in deals
                                  if (d.get("createdate") or "") >= str(pc.get("season_start") or "")]
    expected = AUDIENCE_LINE.get(audience, "charter_sales")
    if from_line != expected and from_line != "email":
        blocks.append(f"{audience} audience must go from the {expected} line, not {from_line} "
                      f"(ops/messenger/config.yml rule, Roman 2026-09-08)")

    # d. active thread on another line / unanswered reply (JustCall)
    window = int(pc.get("thread_window_days") or 14)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window)).strftime("%Y-%m-%dT%H:%M:%S")
    my_line10 = _line_number(from_line)
    texts: list[dict] = []
    if phone10:
        try:
            idx = _jc_index(window)
            texts = [t for t in (idx.get(phone10) or {}).get("texts", [])
                     if (t.get("at") or "") >= cutoff]
        except Exception as e:  # noqa: BLE001  JustCallUnavailable or anything else: never a silent allow
            holds.append(f"could not verify JustCall history: {e}")
    by_line: dict[str, list[dict]] = {}
    for t in texts:
        by_line.setdefault(jc.norm_number(t.get("line") or ""), []).append(t)
    facts["jc_lines"] = {_line_key_for_number(k): len(v) for k, v in by_line.items()}
    for ln, ts in by_line.items():
        key = _line_key_for_number(ln)
        if ln != my_line10 and channel == "sms":
            o = _owner_for_line(key, last_name)
            owner = owner or o
            who = (o or {}).get("name") or (o or {}).get("seat") or key
            holds.append(f"active thread on the {key} line in the last {window} days "
                         f"({len(ts)} texts), owned by {who}")
        last = ts[-1]
        # an unanswered reply on ANOTHER line belongs to that line's seat. On
        # the caller's own line it is the reply case (in_thread), not a hold.
        if (last.get("direction") or "").startswith("in") and ln != my_line10:
            o = _owner_for_line(key, last_name)
            owner = owner or o
            holds.append(f"unanswered reply from the contact on the {key} line at {last.get('at')}")
    if channel == "sms":
        in_thread = any((t.get("direction") or "").startswith("in")
                        for t in by_line.get(my_line10, []))

    # d. inbox
    try:
        inbound = hs.contact_inbound_since(contact_id, cutoff)
    except Exception as e:  # noqa: BLE001
        inbound, _ = [], holds.append(f"could not verify inbox threads: {e}")
    facts["inbox_inbound"] = len(inbound)
    for m in inbound:
        if not m.get("answered"):
            holds.append(f"unanswered inbox reply in thread {m.get('thread_id')} at {m.get('at')}")
            break
    if channel == "email" and inbound:
        in_thread = True

    # d. open tickets owned by scheduling
    try:
        tickets = hs.open_tickets_for_contact(contact_id)
    except Exception as e:  # noqa: BLE001
        tickets, _ = [], holds.append(f"could not verify open tickets: {e}")
    sched = _scheduler_owner_ids()
    for t in tickets:
        oid = str((t.get("properties") or {}).get("hubspot_owner_id") or "")
        if oid in sched and from_line != "support":
            o = _owner_for_line("support", last_name)
            owner = owner or o
            holds.append(f"open ticket {t.get('id')} owned by scheduling "
                         f"({(t.get('properties') or {}).get('subject', '')[:60]})")
            break

    # e. frequency
    today_la = (now or now_la()).strftime("%Y-%m-%d")
    out_today = sum(1 for t in texts if (t.get("direction") or "").startswith("out")
                    and (t.get("at") or "").startswith(today_la))
    facts["sms_out_today"] = out_today
    if channel == "sms" and out_today >= int(pc.get("max_sms_per_day") or 2) and not in_thread:
        holds.append(f"{out_today} texts already sent today across all lines")
    last_out = _ms_to_dt(p.get("agent_last_outbound_at"))
    gap = float(pc.get("min_gap_hours") or 20)
    if last_out and (datetime.now(timezone.utc) - last_out) < timedelta(hours=gap) and not in_thread:
        holds.append(f"last agent outbound {last_out.isoformat()} is inside the {gap:g}h gap "
                     f"(seat {p.get('agent_last_outbound_seat') or '?'})")

    # f. standing go
    if purpose in purposes and purpose not in (pc.get("standing_go") or []):
        if not (confirmed or go_token):
            holds.append(f"purpose {purpose!r} has no standing go; needs --confirm SEND or an approved proposal")

    # g. STOP line on cold SMS
    if channel == "sms" and not in_thread and purpose not in (pc.get("stop_line_exempt") or []) \
            and "stop" not in (body or "").lower():
        blocks.append("new-touch SMS without a STOP line")

    facts["in_thread"] = in_thread
    verdict = "block" if blocks else ("hold" if holds else "allow")
    return Decision(verdict, blocks + holds, in_thread, audience, owner, facts)


# ── the send log of record ─────────────────────────────────────────
def record_send(contact_id: str, channel: str, from_line: str, purpose: str, to: str,
                body: str, engine: str, ok: bool, detail: str = "",
                approved_by: str = "") -> None:
    """Three writes, in order: HubSpot note on the contact, the two [Agent]
    properties, the audit line. A failed note never skips the audit line."""
    at = datetime.now(timezone.utc)
    at_iso = at.isoformat()
    head = (f"[Agent] outbound {channel} from={from_line} purpose={purpose} "
            f"at={at_iso} engine={engine} ok={str(ok).lower()}"
            + (f" approved_by={approved_by}" if approved_by else ""))
    try:
        hs.add_contact_note(contact_id, head + "\n" + body)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  presend note failed for {contact_id} (non-fatal): {e}")
    if ok:
        try:
            hs.patch_contact_props(contact_id, {
                "agent_last_outbound_at": str(int(at.timestamp() * 1000)),
                "agent_last_outbound_seat": from_line})
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  presend property stamp failed for {contact_id} (non-fatal): {e}")
    audit.append({"message_id": f"outbound:{engine}:{contact_id}:{int(at.timestamp())}",
                  "source": "presend", "action_taken": "outbound_sent" if ok else "outbound_failed",
                  "contact_id": str(contact_id), "channel": channel, "from_line": from_line,
                  "purpose": purpose, "to": to, "body": (body or "")[:300], "engine": engine,
                  "ok": ok, "detail": (detail or "")[:160], "approved_by": approved_by})


# ── reply detection ────────────────────────────────────────────────
def has_replied_since(contact_id: str, phone: str, since_iso: str) -> dict:
    """Has this contact written to us since `since_iso`, on the inbox or by
    text on any line? Inbox replies never stamp hs_email_last_reply_date, so
    this scans threads. Raises nothing; unreadable sources are reported."""
    out = {"email": [], "sms": [], "latest": "", "errors": []}
    try:
        out["email"] = hs.contact_inbound_since(contact_id, since_iso)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"inbox: {e}")
    phone10 = jc.norm_number(phone)
    if phone10:
        try:
            idx = _jc_index(int(_pc().get("thread_window_days") or 14))
            out["sms"] = [{"at": t.get("at"), "line": _line_key_for_number(jc.norm_number(t.get("line") or "")),
                           "text": t.get("text")}
                          for t in (idx.get(phone10) or {}).get("texts", [])
                          if (t.get("direction") or "").startswith("in") and (t.get("at") or "") >= since_iso[:19]]
        except jc.JustCallUnavailable as e:
            out["errors"].append(f"justcall: {e}")
    ats = [m.get("at") or "" for m in out["email"]] + [m.get("at") or "" for m in out["sms"]]
    out["latest"] = max(ats) if ats else ""
    return out


def stamp_last_inbound(contact_id: str, at_iso: str) -> None:
    try:
        dt = datetime.fromisoformat(at_iso.replace("Z", "+00:00"))
    except ValueError:
        return
    hs.patch_contact_props(contact_id, {"agent_last_inbound_at": str(int(dt.timestamp() * 1000))})

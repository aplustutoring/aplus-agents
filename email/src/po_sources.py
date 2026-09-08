"""PO mail that lands OUTSIDE the charter inbox: detection, mirroring, handoff.

Schools' ordering systems email purchase orders to the VENDOR CONTACT on file,
and that address is not always charter@. Heartwood's OPS account is registered
to the sales seat, so its POs (PDF attached, no body text, sent on behalf of
noreply@ops-online.com) arrive at admin@. The PO agent only read charter@, and
the admin-inbox triage saw a bodiless PDF from a noreply sender and applied the
"automated notifications are junk" rule:

  * 2026-08-25  10 Heartwood POs junk-archived; re-fed to charter@ by hand
                six days later.
  * 2026-08-26  OPS "new POs processed, log in to review" notice junked.
  * 2026-09-02   4 more Heartwood POs (Phoenix Nourn Bernard, the Thursday
                sessions) junked. Nobody was told; found on 2026-09-03 while
                investigating a different school's POs.

The fix keeps ONE processing surface instead of teaching two agents to read POs:

  1. `is_po_shaped` is a single deterministic predicate shared by both agents
     (never two definitions of "this is a PO" that drift apart).
  2. The PO agent MIRRORS PO-shaped mail from `po_inbox.sources` (admin@) into
     charter@ with Gmail messages.insert (same domain-wide delegation, same
     gmail.modify scope), then its normal poll processes the copy: labels,
     threads, parent-chase drafts and every sweep stay in the charter mailbox.
  3. The triage agent never junks PO-shaped mail. It opens a HANDOFF ticket to
     charter_admin (a human is on the hook even if the mirror is broken), and
     the PO agent closes that ticket the moment the mirrored copy is processed.
     If the copy was already processed when triage gets there, the thread is
     archived as handled: no ticket, no noise.
"""
from __future__ import annotations

import re
import sys
import traceback
from datetime import datetime, timezone

from . import audit, gmail_client as gm, hubspot_client as hs, slack_client
from .config import DRY_RUN, cfg, staff

_SUBJECT_RX = re.compile(
    r"purchase\s*order\s*(?:#|no\.?|number)?\s*\d{4,}"   # "Purchase Order #6814193240"
    r"|\bnew\s+POs?\b"                                     # OPS "School - new POs - date"
    r"|\bPO\s*#\s*\d{4,}",                                 # "PO #2914206871"
    re.I)
_ATTACH_RX = re.compile(r"^(?:(?:PO|OA)[-_ ]?\d{5,}[^/\\]*|\d{8,})\.pdf$", re.I)   # PO6814193240.pdf, OA2914206871.pdf, 6814150575.pdf (a human re-sending from the portal)


def _pc() -> dict:
    return cfg().get("po_inbox", {}) or {}


def _sender_domains() -> set[str]:
    return {d.lower().lstrip("@") for d in (_pc().get("source_sender_domains") or ["ops-online.com"])}


def is_po_shaped(sender_addrs: list[str], subject: str, attachment_names: list[str]) -> str:
    """Why this message is a purchase-order document, or "" when it is not.
    Deterministic on headers + attachment names only (no body, no model): the
    whole point is that a bodiless PDF from a noreply address still matches."""
    for a in sender_addrs or []:
        dom = (a or "").lower().rsplit("@", 1)[-1]
        if dom in _sender_domains():
            return f"sent via {dom} (a school ordering system)"
    if _SUBJECT_RX.search(subject or ""):
        return "subject names a purchase order"
    for n in attachment_names or []:
        if _ATTACH_RX.match((n or "").strip()):
            return f"attachment {n} is a PO document"
    return ""


_PO_NUM_RX = re.compile(r"(?:purchase\s*order\s*(?:#|no\.?|number)?\s*|\bPO\s*#?\s*)(\d{5,})", re.I)


def po_numbers(subject: str, attachment_names: list[str]) -> set[str]:
    """PO numbers named on the document itself (subject or PO/OA-numbered PDF)."""
    nums = set(_PO_NUM_RX.findall(subject or ""))
    for n in attachment_names or []:
        m = re.match(r"^(?:(?:PO|OA)[-_ ]?)?(\d{5,})[^/\\]*\.pdf$", (n or "").strip(), re.I)
        if m:
            nums.add(m.group(1))
    return nums


def _processed_po_numbers() -> set[str]:
    """Every PO number the PO agent has already handled from charter@ (a human
    forwarding the same PO there beats the mirror: no second copy, no dupe alert)."""
    out: set[str] = set()
    for r in audit._iter_records():
        if r.get("source") == "po_inbox" and r.get("po_number"):
            out.add(str(r["po_number"]).strip())
    return out


def norm_subject(subject: str) -> str:
    s = re.sub(r"^\s*(?:(?:re|fwd?|fw)\s*:\s*)+", "", (subject or "").strip(), flags=re.I)
    return re.sub(r"\s+", " ", s).lower()


def _same_document(rec: dict, subject: str, attachment_names: list[str]) -> bool:
    """A mirror/handoff record and a message are about the same PO document
    when the subjects match, or they share a PO attachment name (subjects get
    'Fwd:' prefixes; PO PDFs keep their number-based names)."""
    if norm_subject(rec.get("subject") or "") and norm_subject(rec.get("subject") or "") == norm_subject(subject):
        return True
    mine = {(n or "").strip().lower() for n in (attachment_names or []) if _ATTACH_RX.match((n or "").strip())}
    theirs = {(n or "").strip().lower() for n in (rec.get("attachments") or [])}
    return bool(mine & theirs)


# ── PO agent side: mirror ────────────────────────────────────────────────────
def mirror_sources(state: dict) -> int:
    """Copy PO-shaped mail from every `po_inbox.sources` mailbox into charter@.
    `state` is the po_cursor.json dict; per-source cursors live under
    state["sources"][address]. Returns the number of messages mirrored. A
    broken source (delegation, quota) is reported and skipped, never fatal:
    the charter poll must still run."""
    pc = _pc()
    sources = [s for s in (pc.get("sources") or []) if s and s != pc.get("address")]
    if not sources:
        return 0
    overlap = int(pc.get("cursor_overlap_seconds", 3600))
    backfill = int(pc.get("source_backfill_hours", 48)) * 3600
    query = pc.get("source_query") or 'from:ops-online.com OR subject:"purchase order" OR subject:"new POs" OR filename:pdf'
    label_in = pc.get("label_mirrored") or "A+ Agent/Mirrored from other inbox"
    label_src = pc.get("label_mirrored_source") or "A+ Agent/Mirrored to charter"
    cursors = state.setdefault("sources", {})
    done = audit.processed_message_ids()
    known = _processed_po_numbers()
    now = int(datetime.now(timezone.utc).timestamp())
    mirrored = 0
    for addr in sources:
        since = int(cursors.get(addr) or (now - backfill))
        try:
            # includeSpamTrash: a bodiless PDF from a school's ordering system is
            # exactly what a spam filter flags, and Gmail search hides Spam by
            # default. Trash is a human decision and stays skipped.
            stubs = gm.list_messages(f"after:{max(0, since - overlap)} ({query})", max_results=200,
                                     mailbox=addr, include_spam_trash=True)
            for s in stubs:
                key = f"mirrored:{addr}:{s['id']}"
                if key in done:
                    continue
                m = gm.get_message(s["id"], mailbox=addr)
                labels = set(m.get("label_ids") or [])
                why = is_po_shaped(m.get("sender_addrs") or [], m.get("subject") or "",
                                   m.get("attachment_names") or [])
                if DRY_RUN:
                    print(f"    · {addr} {s['id']} labels={sorted(labels)} "
                          f"subj={(m.get('subject') or '')[:70]!r} → {why or 'not PO-shaped'}")
                if not why or "TRASH" in labels:
                    continue
                if "SPAM" in labels:
                    why += f" (was in Spam at {addr})"
                nums = po_numbers(m.get("subject") or "", m.get("attachment_names") or [])
                if nums and nums <= known:
                    audit.append({"message_id": key, "source": "po_inbox",
                                  "action_taken": "po_mirror_skipped", "from_mailbox": addr,
                                  "source_msg_id": s["id"], "subject": m.get("subject") or "",
                                  "attachments": m.get("attachment_names") or [],
                                  "po_numbers": sorted(nums),
                                  "why": "already processed from charter@ (forwarded by hand)"})
                    print(f"  ↩️  not mirrored, PO {', '.join(sorted(nums))} already processed: "
                          f"{(m.get('subject') or '')[:70]}")
                    continue
                raw = gm.get_raw(s["id"], mailbox=addr)
                if not raw:
                    print(f"  ⚠️  mirror: empty raw for {addr} {s['id']} — skipped")
                    continue
                copy = gm.insert_raw(raw, [label_in])
                try:
                    # The original stays visible to the humans who work that
                    # inbox: a spam-foldered PO is pulled back into the Inbox
                    # (the "never send to Spam" filter, done in code because a
                    # Gmail filter needs a settings scope the agent is not granted).
                    if "SPAM" in labels:
                        gm.move_to_inbox(s["id"], [label_src], mailbox=addr)
                    else:
                        gm.apply_labels(s["id"], [label_src], mailbox=addr)
                except Exception as e:  # noqa: BLE001 — cosmetic on the source side
                    print(f"  ⚠️  mirror: source label failed (non-fatal): {e}")
                audit.append({"message_id": key, "source": "po_inbox", "action_taken": "po_mirrored",
                              "from_mailbox": addr, "source_msg_id": s["id"],
                              "mirror_msg_id": copy.get("id"), "subject": m.get("subject") or "",
                              "attachments": m.get("attachment_names") or [], "why": why,
                              "sender": m.get("sender") or ""})
                mirrored += 1
                print(f"  📬 mirrored from {addr}: {(m.get('subject') or '')[:90]} ({why})")
            cursors[addr] = now
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  PO mirror from {addr} FAILED: {e}", file=sys.stderr)
            traceback.print_exc()
            _alert(f"🚩 PO mirror from {addr} FAILED: {str(e)[:200]}\n"
                   f"PO-shaped mail in that inbox is NOT reaching the PO agent until this is fixed "
                   f"(delegation for {addr}? quota?). The triage agent still opens a handoff ticket "
                   f"per PO document, so nothing is silently lost, but each one is manual until then.")
    return mirrored


def rescue_spam(state: dict) -> list[str]:
    """PO-shaped mail in charter@'s OWN Spam folder is moved to the Inbox and
    returned (message ids) for immediate processing. The same signature that
    spam-filtered Heartwood's POs at admin@ (bodiless PDF, noreply@ops-online.com)
    applies when a human emails a PO from the OPS portal straight to charter@,
    and the poll only reads `in:inbox`. Cursor: state["spam_cursor"]."""
    pc = _pc()
    overlap = int(pc.get("cursor_overlap_seconds", 3600))
    backfill = int(pc.get("source_backfill_hours", 48)) * 3600
    query = pc.get("source_query") or 'from:ops-online.com OR subject:"purchase order" OR subject:"new POs" OR filename:pdf'
    label = pc.get("label_rescued") or "A+ Agent/Rescued from Spam"
    now = int(datetime.now(timezone.utc).timestamp())
    since = int(state.get("spam_cursor") or (now - backfill))
    done = audit.processed_message_ids()
    rescued: list[str] = []
    try:
        stubs = gm.list_messages(f"in:spam after:{max(0, since - overlap)} ({query})",
                                 max_results=200, include_spam_trash=True)
        for s in stubs:
            key = f"spam-rescued:{s['id']}"
            if key in done:
                continue
            m = gm.get_message(s["id"])
            why = is_po_shaped(m.get("sender_addrs") or [], m.get("subject") or "",
                               m.get("attachment_names") or [])
            if DRY_RUN:
                print(f"    · charter spam {s['id']} subj={(m.get('subject') or '')[:70]!r} "
                      f"→ {why or 'not PO-shaped'}")
            if not why:
                continue
            gm.move_to_inbox(s["id"], [label])
            audit.append({"message_id": key, "source": "po_inbox", "action_taken": "po_spam_rescued",
                          "source_msg_id": s["id"], "subject": m.get("subject") or "",
                          "attachments": m.get("attachment_names") or [], "why": why,
                          "sender": m.get("sender") or ""})
            rescued.append(s["id"])
            print(f"  🛟 rescued from charter@ Spam: {(m.get('subject') or '')[:90]} ({why})")
        state["spam_cursor"] = now
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  charter@ Spam rescue FAILED: {e}", file=sys.stderr)
        traceback.print_exc()
        _alert(f"🚩 charter@ Spam rescue FAILED: {str(e)[:200]}. PO-shaped mail that Gmail "
               f"spam-filters at charter@ is invisible to the PO agent until this is fixed.")
    return rescued


def _alert(text: str) -> None:
    for key in _pc().get("missing_info_dms", ["charter_admin", "visionary"]):
        s = staff(key)
        if s.get("slack_user_id"):
            try:
                slack_client.dm(s["slack_user_id"], text)
            except Exception as e:  # noqa: BLE001 — alerting must not kill the run
                print(f"  ⚠️  mirror alert DM to {key} failed (non-fatal): {e}")


# ── Triage side: handoff bookkeeping ─────────────────────────────────────────
def mirrored_record_for(subject: str, attachment_names: list[str]) -> dict | None:
    """The po_mirrored audit record for this document, if the PO agent already
    pulled it into charter@ (then triage archives the admin@ thread as handled)."""
    latest = None
    for r in audit._iter_records():
        if r.get("action_taken") == "po_mirrored" and _same_document(r, subject, attachment_names):
            latest = r
    return latest


def open_handoffs_for(subject: str, attachment_names: list[str]) -> list[dict]:
    """Triage handoff tickets still open for this document."""
    opened: dict[str, dict] = {}
    closed: set[str] = set()
    for r in audit._iter_records():
        act = r.get("action_taken")
        if act == "po_handoff_ticket" and r.get("ticket_id") and _same_document(r, subject, attachment_names):
            opened[str(r["ticket_id"])] = r
        elif act == "po_handoff_closed" and r.get("ticket_id"):
            closed.add(str(r["ticket_id"]))
    return [r for tid, r in opened.items() if tid not in closed]


def close_handoffs(subject: str, attachment_names: list[str], po_ticket_id: str | None,
                   outcome: str = "") -> list[str]:
    """Called by the PO agent after it processed a message: close every triage
    handoff ticket for the same document, pointing at the real PO ticket."""
    closed_stage = cfg()["hubspot"]["ticket_stages"]["closed"]
    out: list[str] = []
    for r in open_handoffs_for(subject, attachment_names):
        tid = str(r["ticket_id"])
        try:
            note = "✅ Processed by the PO agent from the charter inbox."
            if po_ticket_id and po_ticket_id != "DRYRUN":
                note += f" PO ticket: {hs.ticket_url(po_ticket_id)}"
            if outcome:
                note += f"\n{outcome}"
            hs.add_ticket_note(tid, note)
            hs.update_ticket_stage(tid, closed_stage)
        except Exception as e:  # noqa: BLE001 — never let bookkeeping kill PO processing
            print(f"  ⚠️  closing handoff ticket {tid} failed (non-fatal): {e}")
            continue
        audit.append({"message_id": f"po-handoff-closed:{tid}", "source": "po_inbox",
                      "action_taken": "po_handoff_closed", "ticket_id": tid,
                      "po_ticket_id": po_ticket_id, "subject": subject})
        out.append(tid)
    return out

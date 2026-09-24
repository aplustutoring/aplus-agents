"""One-shot: give back the Teachworks notices the pre-deal-lead override took.

From 2026-07-24 to 2026-09-21 every Teachworks cancellation, reschedule and
scheduling notice tested its NO-REPLY sender for "active family?", got no, and
moved to charter sales. The audit log holds 90 such decisions, 71 of them from
the Teachworks notification contact (Sam Sterling's 9/20 cancellation among
them); the other 19 are real families who wrote in with no deal yet, which is
what the override is FOR. `router.is_notification_sender` is what separates
them, so this sweep and the live path draw the line in the same place.

Nothing here is inferred from HubSpot state: the audit log names the tickets,
the ticket subject (`Lastname, Firstname — Cancellation`) gives the surname,
and `scheduler_for_last_name` picks the owner exactly as triage does.

Tasks ride along by association: the companion `Reply: …` and `Re-engage: …`
tasks hang off the ticket's contact. A contact that several misrouted tickets
share — the no-reply address itself, when the family never resolved — is
AMBIGUOUS and is reported, not guessed: moving that task could hand one
family's work to another family's scheduler.

DRY_RUN=true prints every intended write and changes nothing.
"""
from __future__ import annotations

from . import audit, hubspot_client as hs
from .config import DRY_RUN, cfg, staff
from .router import is_notification_sender, scheduler_for_last_name

# The categories the split owns; the override could only ever fire on these.
SPLIT_CATEGORIES = {"cancellation", "reschedule", "scheduling"}

# Task subjects this bug produced: the SLA reply task triage opens per category,
# and the win-back task a pause/stop cancellation schedules.
TASK_PREFIXES = tuple(f"Reply: {c} — " for c in sorted(SPLIT_CATEGORIES)) + ("Re-engage: ",)


def _misrouted(sender_is_notice) -> list[dict]:
    """Audit records where the override took a scheduler's notice, newest
    decision per ticket (a thread can be triaged more than once)."""
    by_id: dict[str, dict] = {}
    for r in audit._iter_records():
        if (r.get("action_taken") == "ticket_created" and r.get("predeal_intake")
                and r.get("category") in SPLIT_CATEGORIES and r.get("ticket_id")
                and sender_is_notice(str(r.get("contact_id") or ""))):
            by_id[str(r["ticket_id"])] = r
    return list(by_id.values())


def _notice_contact_check():
    """contact id → 'was this the no-reply notification sender?', cached (71 of
    the 90 records share one contact, so this is a handful of GETs)."""
    cache: dict[str, bool] = {}

    def check(contact_id: str) -> bool:
        if not contact_id:
            return False
        if contact_id not in cache:
            try:
                c = hs._get(f"/crm/v3/objects/contacts/{contact_id}", {"properties": "email"})
                cache[contact_id] = is_notification_sender(
                    ((c.get("properties") or {}).get("email") or ""))
            except Exception:  # noqa: BLE001 — a deleted contact is not a notice
                cache[contact_id] = False
        return cache[contact_id]

    return check


def _surname_from_subject(subject: str) -> str | None:
    """'Sterling, Sam — Cancellation' → 'Sterling'. None when the subject fell
    back to an email local-part (no comma, so no surname we can trust)."""
    head = (subject or "").split(" — ")[0]
    if "," not in head:
        return None
    return head.split(",")[0].strip() or None


def _target_owner(subject: str) -> tuple[str | None, str | None, str]:
    """(staff key, surname, why not) for a misrouted ticket's subject."""
    last = _surname_from_subject(subject)
    if not last:
        return None, None, "no surname in the subject"
    key, notes = scheduler_for_last_name(last)
    # An unknown surname defaults to A-L inside the router. That default is a
    # guess, and undoing a guess is the whole point of this sweep.
    if notes:
        return None, last, notes[0]
    return key, last, ""


def _reassign(obj: str, obj_id: str, owner_id: str) -> None:
    hs._write("PATCH", f"/crm/v3/objects/{obj}/{obj_id}",
              {"properties": {"hubspot_owner_id": owner_id}})


def run() -> None:
    cs_key = cfg().get("roles", {}).get("charter_sales", "charter_sales")
    cs_id = str(staff(cs_key)["hubspot_owner_id"])
    rows = _misrouted(_notice_contact_check())
    print(f"backfill: {len(rows)} notice tickets the pre-deal override took "
          f"(DRY_RUN={DRY_RUN})")

    moved = kept = skipped = 0
    contact_target: dict[str, str | None] = {}   # contact id → owner id; None = ambiguous
    for r in rows:
        tid = str(r["ticket_id"])
        try:
            t = hs._get(f"/crm/v3/objects/tickets/{tid}",
                        {"properties": "subject,hubspot_owner_id,hs_is_closed"})
        except Exception as e:  # noqa: BLE001 — a deleted ticket is not a failure
            print(f"  ⚠️  ticket {tid} unreadable ({e})")
            continue
        p = t.get("properties") or {}
        # Closed, or a human already took it back — either way their call stands.
        if str(p.get("hs_is_closed") or "").lower() == "true" or \
                str(p.get("hubspot_owner_id") or "") != cs_id:
            kept += 1
            continue
        key, last, why = _target_owner(p.get("subject") or "")
        if not key:
            print(f"  ⚠️  ticket {tid} ('{p.get('subject')}'): {why}; left with charter sales")
            skipped += 1
            continue
        target = staff(key)
        target_id = str(target["hubspot_owner_id"])
        print(f"  {'[DRY] ' if DRY_RUN else ''}ticket {tid} '{p.get('subject')}' "
              f"→ {target.get('name', key)} [{last}]")
        moved += 1
        for c in hs.get_ticket_contacts(tid):
            cid = str(c["id"])
            contact_target[cid] = (target_id
                                   if contact_target.get(cid, target_id) == target_id else None)
        if DRY_RUN:
            continue
        try:
            _reassign("tickets", tid, target_id)
            hs.add_ticket_note(tid, (
                f"Owner corrected to {target.get('name', key)}. A Teachworks notice is mail "
                f"about the {last} family, not a pre-deal lead; the pre-deal-lead override "
                f"had been reading the no-reply sender instead (Paola, 2026-09-21)."))
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  ticket {tid} PATCH failed: {e}")

    resolved = {c: v for c, v in contact_target.items() if v}
    shared = {c for c, v in contact_target.items() if v is None}
    task_moved = task_left = 0
    for task in hs.search_open_tasks([cs_id]):
        subj = (task.get("properties") or {}).get("hs_task_subject") or ""
        if not subj.startswith(TASK_PREFIXES):
            continue
        try:
            assoc = hs._get(f"/crm/v4/objects/tasks/{task['id']}/associations/contacts",
                            {"limit": 10})
        except Exception:  # noqa: BLE001
            assoc = {}
        cids = {str(a.get("toObjectId")) for a in (assoc.get("results") or [])}
        targets = {resolved[c] for c in cids if c in resolved}
        if len(targets) != 1:
            if targets or (cids & shared):
                print(f"  ⚠️  task {task['id']} '{subj}': its contact is shared by several "
                      f"families — reassign by hand")
                task_left += 1
            continue
        target_id = targets.pop()
        print(f"  {'[DRY] ' if DRY_RUN else ''}task {task['id']} '{subj}' → owner {target_id}")
        task_moved += 1
        if not DRY_RUN:
            try:
                _reassign("tasks", task["id"], target_id)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  task {task['id']} PATCH failed: {e}")

    print(f"backfill done: tickets moved {moved}, already handled or closed {kept}, "
          f"no surname {skipped}; tasks moved {task_moved}, left for a human {task_left}")


if __name__ == "__main__":
    run()

"""One-shot: give the schedulers the scheduling tasks sitting on the care seat.

Paola, 2026-09-22: "Any task related to active-session scheduling or session
logistics should NOT be assigned to Paola. Assign these tasks directly to the
Scheduling Team, based on the family's last name." The live rule now runs at
task creation (`case_engine.owner_for_task`, wired into triage), but that only
covers tasks made from here on. Her open queue still holds the old ones, and a
rule nobody backfills is a rule the person who reported it never sees.

The same discipline as `backfill_notice_owners.py`: the surname comes from the
task's associated FAMILY contact, never the tutor's and never another contact
named in the task. Anything ambiguous — no family contact, two families on one
task, a contact with no surname — is PRINTED and left alone. Moving a task on a
guess hands one family's work to the other scheduler, which is the failure this
rule exists to prevent.

DRY_RUN=true prints every intended write and changes nothing. Run it that way
first, read the list, then live.
"""
from __future__ import annotations

from . import case_engine as ce, hubspot_client as hs
from .config import DRY_RUN, cfg, staff

FAMILY_PERSONA = "Family"
CONTACT_PROPS = "firstname,lastname,email,a_persona"


def _care_owner_ids() -> dict[str, str]:
    """hubspot_owner_id → role, for every seat task_routing re-owns away from."""
    out = {}
    for role in (cfg().get("case_engine", {}).get("task_routing") or {}).get("applies_to") or []:
        oid = (staff(role) or {}).get("hubspot_owner_id")
        if oid:
            out[str(oid)] = role
    return out


def _family_surname(task_id: str) -> tuple[str | None, str]:
    """(surname, why not) from the task's associated contacts. Exactly one
    distinct Family surname wins; anything else is ambiguous and refused."""
    try:
        assoc = hs._get(f"/crm/v4/objects/tasks/{task_id}/associations/contacts", {"limit": 10})
    except Exception as e:  # noqa: BLE001 — an unreadable association is not a surname
        return None, f"associations unreadable ({e})"
    surnames = set()
    for r in (assoc.get("results") or [])[:10]:
        try:
            c = hs._get(f"/crm/v3/objects/contacts/{r['toObjectId']}", {"properties": CONTACT_PROPS})
        except Exception:  # noqa: BLE001 — a deleted contact is not a family
            continue
        p = c.get("properties") or {}
        personas = [v.strip() for v in (p.get("a_persona") or "").split(";") if v.strip()]
        last = (p.get("lastname") or "").strip()
        # No persona at all is the common intake state, so it counts as a family
        # contact; a contact tagged ONLY as a tutor or a student never does.
        if last and (not personas or FAMILY_PERSONA in personas):
            surnames.add(last)
    if not surnames:
        return None, "no family contact with a surname on the task"
    if len(surnames) > 1:
        return None, f"several families on one task ({', '.join(sorted(surnames))})"
    return surnames.pop(), ""


def run() -> None:
    care = _care_owner_ids()
    if not care:
        print("  ⚠️  case_engine.task_routing.applies_to resolved to no seats; check config")
        return
    try:
        tasks = hs.search_open_tasks(list(care))
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  could not list open tasks (missing tasks read scope?): {e}")
        return
    print(f"reroute: {len(tasks)} open task(s) on {', '.join(sorted(care.values()))} "
          f"(DRY_RUN={DRY_RUN})")

    moved = skipped = 0
    for t in tasks:
        subject = ((t.get("properties") or {}).get("hs_task_subject") or "").strip()
        if not ce.task_is_scheduling(subject):
            continue
        last, why = _family_surname(str(t["id"]))
        if not last:
            print(f"  ⚠️  task {t['id']} '{subject[:70]}': {why}; left where it is")
            skipped += 1
            continue
        role = ce.split_role(last)
        target = staff(role) or {}
        target_id = str(target.get("hubspot_owner_id") or "")
        if not target_id:
            print(f"  ⚠️  task {t['id']}: role {role} has no HubSpot owner id; left where it is")
            skipped += 1
            continue
        print(f"  {'[DRY] ' if DRY_RUN else ''}task {t['id']} '{subject[:70]}' "
              f"→ {target.get('name', role)} [{last}]")
        moved += 1
        if DRY_RUN:
            continue
        try:
            hs._write("PATCH", f"/crm/v3/objects/tasks/{t['id']}",
                      {"properties": {"hubspot_owner_id": target_id}})
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  task {t['id']} PATCH failed: {e}")

    print(f"reroute done: {moved} moved, {skipped} left for a human")


if __name__ == "__main__":
    run()

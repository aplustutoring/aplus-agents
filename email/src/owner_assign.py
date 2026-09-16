"""New-deal owner assignment — the scheduler split, owned by the fleet.

Until 2026-09-04 a Zapier zap (HubSpot app 25200) re-owned every new deal in
the scheduling pipelines to a scheduler by family last name, A-L → Janelle,
M-Z → Yolanda, one to two minutes after creation. At 23:45 UTC that day it
wrote its last owner and went silent. Nothing alerted. Every deal created
since stayed with whoever clicked Create (Danielle's three Elenes trials sat
with her for almost four hours; Paola's Matiukhina Gold deal for 17) until a
scheduler noticed and took it by hand. Roman, 2026-09-09: build it here, then
turn the zap off.

Runs from deal_sync for every NEW deal (the deal-relay webhook fires the run
about a minute after creation). Rule: deal in an `owner_assign.pipelines`
pipeline → owner = the scheduler for the family's last name, taken from the
deal's Family contact, else the parent half of the deal name. Already the
right scheduler → no write. One decision per deal (audit owner:{id}); the
write is a plain owner PATCH, so a replay is harmless.
"""
from __future__ import annotations

import re

from . import audit, hubspot_client as hs
from .config import cfg, staff
from .router import scheduler_for_last_name


def group_number(raw) -> int | None:
    """'C1-G4' → 4, '4' → 4, '' → None: the trailing integer of the deal's
    [Agent] HSA Group value."""
    m = re.search(r"(\d+)\s*$", str(raw or ""))
    return int(m.group(1)) if m else None


def _parity_owner(deal: dict, props: dict, gp: dict) -> tuple[str | None, str, list[str]]:
    """(staff_key, group text, notes) for a group-parity pipeline (IEM HSA:
    odd group → scheduler_a_l, even → scheduler_m_z, LOCKED Roman 2026-09-15).
    The group comes from the deal property; when the search that found the
    deal did not carry it, one GET fills it in."""
    prop = gp.get("property", "hsa_group")
    raw = props.get(prop)
    if raw in (None, ""):
        got = hs._get(f"/crm/v3/objects/deals/{deal['id']}", {"properties": prop})
        raw = ((got or {}).get("properties") or {}).get(prop) if isinstance(got, dict) else None
    n = group_number(raw)
    if n is None:
        return None, str(raw or ""), [f"no group number in {prop}; owner left as is, retried next run"]
    key = gp["odd"] if n % 2 else gp["even"]
    return key, str(raw), [f"group {n} is {'odd' if n % 2 else 'even'} → {key}"]


def _parent_last_from_dealname(dealname: str) -> str | None:
    """'Lesly Elenes - Adrian' → 'Elenes'; 'Ana Diaz - Mateo - iLEAD 2 - 26/27' → 'Diaz'."""
    parent = (dealname or "").split(" - ")[0].strip()
    parts = [p for p in parent.replace("–", " ").split() if p]
    if len(parts) < 2:
        return None
    return parts[-1]


def family_last_name(deal: dict, contact: dict | None) -> tuple[str | None, str]:
    """(last name, where it came from). Contact wins; deal name is the fallback."""
    props = (contact or {}).get("properties") or {}
    last = (props.get("lastname") or "").strip()
    if last:
        return last, "contact"
    last = _parent_last_from_dealname(deal["properties"].get("dealname", ""))
    return (last, "dealname") if last else (None, "none")


def maybe_assign(deal: dict, contact: dict | None = None) -> dict | None:
    """Re-own one new deal to its scheduler. Returns the audit record, or None
    when the pass is off / the pipeline is not covered / already decided."""
    oa = cfg().get("owner_assign") or {}
    if not oa.get("enabled"):
        return None
    props = deal.get("properties") or {}
    pid = props.get("pipeline")
    gp = (oa.get("group_parity") or {}).get(pid)
    if pid not in set(oa.get("pipelines") or []) and not gp:
        return None
    key = f"owner:{deal['id']}"
    if audit.already_processed(key):
        return None

    if gp:
        staff_key, last, notes = _parity_owner(deal, props, gp)
        source = gp.get("property", "hsa_group")
        if not staff_key:
            print(f"  👤 deal {deal['id']} ({props.get('dealname')}): {notes[0]}")
            return None   # not marked: the agent stamps the group, a replay assigns
    else:
        last, source = family_last_name(deal, contact)
        staff_key, notes = scheduler_for_last_name(last)
    target = staff(staff_key)
    target_id = str(target["hubspot_owner_id"])
    current = str(props.get("hubspot_owner_id") or "")
    record = {"message_id": key, "source": "owner_assign", "deal_id": deal["id"],
              "deal_name": props.get("dealname"), "pipeline": pid,
              "last_name": last, "last_name_source": source,
              "previous_owner_id": current or None, "owner": staff_key,
              "owner_id": target_id, "notes": notes}
    if current == target_id:
        record["action_taken"] = "owner_kept"
        audit.append(record)
        return record
    hs._write("PATCH", f"/crm/v3/objects/deals/{deal['id']}",
              {"properties": {"hubspot_owner_id": target_id}})
    record["action_taken"] = "owner_assigned"
    audit.append(record)
    print(f"  👤 deal {deal['id']} ({props.get('dealname')}) → {target.get('name', staff_key)}"
          f" [{source}:{last}]" + (f" ({'; '.join(notes)})" if notes else ""))
    return record

"""Case engine: the one library every ticket-driven workflow uses.

Roman's rule (2026-09-16, locked; docs/CASE-ENGINE.md):
  1. Task: one person, one thing, one date. Machines create a task only when
     they cannot do the thing themselves. Never a task to record that
     something happened.
  2. Ticket: a case open until an outcome we count, can wait, may change
     hands, needs an age clock. One ticket per case.
  3. Pipeline: only when the owner set and the closed outcomes differ from
     every existing pipeline.

Shape: trigger -> ticket -> rails -> reply watcher -> closer sweep ->
escalation -> digest. Clients (low_balance, po_inbox, tutor_issues) call
open_case / move / close / mark_risk and declare their owner rule in config
as a named role or a split. The engine owns: the three pipelines and their
stage ids, the owner rules, the service-level clock (sla_due_at), the
case_key idempotency, the tutor-ticket link, and the per-pipeline queries
the digests read. It sends nothing to a family, ever.

Deterministic: no prompt, no CARE pointer.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import audit, hubspot_client as hs, slack_client
from .business_hours import add_business_hours, now_la
from .config import DRY_RUN, cfg, staff

ASSOC_TICKET_CONTACT = 16
ASSOC_TICKET_DEAL = 28
TICKET_PROPS = ["subject", "hs_pipeline", "hs_pipeline_stage", "hubspot_owner_id", "createdate",
                "hs_lastmodifieddate", "hs_ticket_priority", "case_key", "case_client", "funding_type",
                "retention_risk", "support_category", "linked_tutor_ticket_id", "sla_due_at",
                "tutor_issue_type", "tutor_probation_until", "hours_left"]


def _ce() -> dict:
    return cfg().get("case_engine") or {}


# ── pipelines and stages ────────────────────────────────────────────────────

def pipeline(name: str) -> dict:
    p = (_ce().get("pipelines") or {}).get(name)
    if not p:
        raise KeyError(f"case_engine.pipelines.{name} is not configured")
    return p


def stage_id(name: str, stage: str) -> str:
    p = pipeline(name)
    try:
        return str(p["stages"][stage])
    except KeyError:
        raise KeyError(f"case_engine.pipelines.{name}.stages.{stage} is not configured")


def closed_stage_ids(name: str | None = None) -> set:
    names = [name] if name else list((_ce().get("pipelines") or {}).keys())
    out = set()
    for n in names:
        p = pipeline(n)
        out |= {str(p["stages"][k]) for k in (p.get("closed") or []) if k in p["stages"]}
    return out


def is_closed_stage(stage: str | None) -> bool:
    return str(stage or "") in closed_stage_ids()


# ── owner rules ─────────────────────────────────────────────────────────────

def split_role(last_name: str) -> str:
    """Family surname A-L -> scheduler_a_l, M-Z -> scheduler_m_z (the split every
    scheduler-owned queue uses). No surname = A-L, and the caller says so."""
    rules = (_ce().get("owner_rules") or {}).get("renewals") or {}
    sp = rules.get("split") or {"a_l": "scheduler_a_l", "m_z": "scheduler_m_z"}
    l = (last_name or "").strip().lower()
    return sp["a_l"] if (not l or l[0] <= "l") else sp["m_z"]


def hsa_group_number(deal_props: dict | None) -> int | None:
    """IEM HSA deals carry hsa_group like 'C1-G4' (agents/cohort_intake); the
    number after G is the intake sheet's Group #."""
    g = str((deal_props or {}).get("hsa_group") or "").strip()
    m = re.search(r"G\s*(\d+)", g, flags=re.I)
    return int(m.group(1)) if m else None


def owner_for_renewals(funding_type: str, family_last: str, deal_props: dict | None = None) -> tuple[str, str]:
    """(role, why). Computed once at ticket open, one config block:
    trial -> charter_sales (the only override); IEM HSA deal (pipeline in
    hsa_pipelines) -> group parity, odd = scheduler_a_l, even = scheduler_m_z;
    else the surname split. Schedulers keep every charter and private-pay
    renewal, no exceptions."""
    rules = (_ce().get("owner_rules") or {}).get("renewals") or {}
    if funding_type == "trial":
        return rules.get("trial", "charter_sales"), "trial: charter_sales override"
    dp = deal_props or {}
    if str(dp.get("pipeline") or "") in set(str(x) for x in rules.get("hsa_pipelines") or []):
        n = hsa_group_number(dp)
        if n is not None:
            par = rules.get("hsa_parity") or {"odd": "scheduler_a_l", "even": "scheduler_m_z"}
            role = par["odd"] if n % 2 else par["even"]
            return role, f"IEM HSA group {n} ({'odd' if n % 2 else 'even'})"
    role = split_role(family_last)
    return role, (f"surname {family_last.strip()} ({'A-L' if role.endswith('a_l') else 'M-Z'})"
                  if (family_last or "").strip() else "no surname on file: A-L by default, CHECK")


def owner_for_support(category: str, family_last: str = "") -> tuple[str, str]:
    """Owner map by category in config; the token 'split' means the surname split."""
    rules = (_ce().get("owner_rules") or {}).get("support") or {}
    role = rules.get(category) or rules.get("default", "operations")
    if role == "split":
        r = split_role(family_last)
        return r, f"{category}: surname split"
    return role, f"{category}: {role}"


def owner_for_tutor() -> tuple[str, str]:
    role = (_ce().get("owner_rules") or {}).get("tutor", "operations")
    return role, "tutor accountability: operations"


def seat(role: str) -> dict:
    return staff(role) or {}


# ── task routing (Paola 2026-09-22) ─────────────────────────────────────────
# The owner rules above answer "who owns this ticket?" from the category the
# client declares. Nothing answered "who owns this TASK?" from what the task
# says, so session-logistics work created under any other category kept the
# category's owner — care. Paola, 2026-09-22: "Any task related to
# active-session scheduling or session logistics should NOT be assigned to
# Paola. Assign these to the Scheduling Team, based on the family's last name."

def _tr() -> dict:
    return _ce().get("task_routing") or {}


def task_is_scheduling(subject: str) -> bool:
    """True when a task subject is about managing an EXISTING schedule: the
    `[Scheduling]` label, or one of `task_routing.keywords`. A care keyword
    wins — a win-back, a renewal, a payment or a review reads as scheduling
    ('cancellation', 'renewal') but is Student Success work."""
    s = (subject or "").strip().lower()
    if not s:
        return False
    tr = _tr()
    if any(str(x).lower() in s for x in tr.get("labels") or []):
        return True
    if any(str(k).lower() in s for k in tr.get("care_keywords") or []):
        return False
    return any(str(k).lower() in s for k in tr.get("keywords") or [])


def owner_for_task(subject: str, family_last: str, current_owner_id: str | None) -> tuple[str | None, str]:
    """(role, why) for a task about to be created, or (None, why) to leave the
    caller's owner alone. `current_owner_id` is the HubSpot owner id the caller
    would otherwise use — an id, not a seat key, because callers hold ids and
    a seat key means nothing once roles resolve to people.

    Re-owns only a scheduling task that would otherwise land on one of
    `task_routing.applies_to` (care today), and only when we have the FAMILY
    surname — the split is meaningless without it, and guessing it from the
    tutor or from another contact named in the task is the exact mistake the
    rule exists to stop, so no surname means no change. `split_role` is the
    one implementation of the boundary; there is no second copy here."""
    tr = _tr()
    if not tr.get("enabled"):
        return None, "task_routing off"
    cur = str(current_owner_id or "")
    if not cur or cur not in {str(seat(r).get("hubspot_owner_id") or "")
                              for r in (tr.get("applies_to") or [])}:
        return None, "owner is not a re-owned seat"
    if not task_is_scheduling(subject):
        return None, "not a scheduling task"
    last = (family_last or "").strip()
    if not last:
        return None, "scheduling task with no family surname; owner left as is, CHECK"
    role = split_role(last)
    return role, f"scheduling task: surname {last} ({'A-L' if role.endswith('a_l') else 'M-Z'})"


# ── service levels ──────────────────────────────────────────────────────────

def sla_due_at(name: str, stage: str) -> str | None:
    """ISO datetime when the stage's service level runs out, or None when the
    stage has none (closed stages, or unconfigured). Business days = 9 to 6
    PT Mon to Fri (business_hours)."""
    levels = ((_ce().get("service_levels") or {}).get(name) or {})
    bd = levels.get(stage)
    if bd is None:
        return None
    hours = float(bd) * 9.0            # one business day = the 9-hour working day
    return add_business_hours(now_la(), hours).isoformat()


# ── tickets ─────────────────────────────────────────────────────────────────

def find_ticket(case_key: str, open_only: bool = True) -> dict | None:
    if not case_key:
        return None
    body = {"filterGroups": [{"filters": [{"propertyName": "case_key", "operator": "EQ", "value": case_key}]}],
            "properties": TICKET_PROPS, "limit": 10,
            "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]}
    res = hs._write("POST", "/crm/v3/objects/tickets/search", body)
    hits = res.get("results", []) if isinstance(res, dict) else []
    if open_only:
        hits = [t for t in hits if not is_closed_stage((t.get("properties") or {}).get("hs_pipeline_stage"))]
    return hits[0] if hits else None


def open_case(client: str, case_key: str, name: str, stage: str, subject: str, description: str,
              owner_role: str, contact_ids: list | None = None, deal_id: str | None = None,
              props: dict | None = None, priority: str | None = None, category: str | None = None,
              source: str | None = None) -> dict:
    """One ticket per case: an open ticket with this case_key is returned (with
    a note), never duplicated. Associates every contact given and the deal,
    stamps the engine properties and the stage's SLA clock."""
    existing = find_ticket(case_key)
    if existing:
        try:
            hs.add_ticket_note(existing["id"], f"↩️ {client}: repeat trigger, same case ({case_key}); no new ticket.")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  repeat note failed (non-fatal): {e}")
        return existing
    owner = seat(owner_role)
    tprops = {"subject": subject, "hs_pipeline": str(pipeline(name)["id"]), "hs_pipeline_stage": stage_id(name, stage),
              "content": description, "case_key": case_key, "case_client": client}
    if owner.get("hubspot_owner_id"):
        tprops["hubspot_owner_id"] = owner["hubspot_owner_id"]
    if priority:
        tprops["hs_ticket_priority"] = priority
    if category:
        tprops["hs_ticket_category"] = category
    if source:
        tprops["source_type"] = source
    due = sla_due_at(name, stage)
    if due:
        tprops["sla_due_at"] = _ms(due)
    for k, v in (props or {}).items():
        if v not in (None, ""):
            tprops[k] = v
    assoc = []
    for cid in [c for c in (contact_ids or []) if c and c != "DRYRUN"]:
        assoc.append({"to": {"id": str(cid)}, "types": [{"associationCategory": "HUBSPOT_DEFINED",
                                                        "associationTypeId": ASSOC_TICKET_CONTACT}]})
    if deal_id and deal_id != "DRYRUN":
        assoc.append({"to": {"id": str(deal_id)}, "types": [{"associationCategory": "HUBSPOT_DEFINED",
                                                            "associationTypeId": ASSOC_TICKET_DEAL}]})
    payload = {"properties": tprops}
    if assoc:
        payload["associations"] = assoc
    if DRY_RUN:
        print(f"[DRY_RUN] case_engine open {name}/{stage} owner={owner_role} key={case_key} :: {subject}")
        ticket = {"id": "DRYRUN", "properties": tprops}
    else:
        ticket = hs._write("POST", "/crm/v3/objects/tickets", payload)
    audit.append({"message_id": f"case:{case_key}:opened", "source": "case_engine", "action_taken": "case_opened",
                  "client": client, "pipeline": name, "stage": stage, "owner_role": owner_role,
                  "ticket_id": ticket.get("id"), "subject": subject})
    return ticket


def move(ticket_id: str, name: str, stage: str, note: str | None = None, props: dict | None = None) -> None:
    if not ticket_id or ticket_id == "DRYRUN":
        return
    p = {"hs_pipeline": str(pipeline(name)["id"]), "hs_pipeline_stage": stage_id(name, stage)}
    due = sla_due_at(name, stage)
    p["sla_due_at"] = _ms(due) if due else ""
    for k, v in (props or {}).items():
        p[k] = v
    hs._write("PATCH", f"/crm/v3/objects/tickets/{ticket_id}", {"properties": p})
    if note:
        try:
            hs.add_ticket_note(ticket_id, note)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  move note failed (non-fatal): {e}")
    audit.append({"message_id": f"ticket:{ticket_id}:{stage}:{_today()}", "source": "case_engine",
                  "action_taken": "case_moved", "pipeline": name, "stage": stage, "ticket_id": ticket_id})


def close(ticket_id: str, name: str, outcome: str, note: str | None = None, props: dict | None = None) -> None:
    """Close with an outcome we count (a closed stage of the pipeline)."""
    if outcome not in (pipeline(name).get("closed") or []):
        raise ValueError(f"{outcome} is not a closed stage of {name}")
    move(ticket_id, name, outcome, note, props)


def set_props(ticket_id: str, props: dict) -> None:
    if not ticket_id or ticket_id == "DRYRUN" or not props:
        return
    hs._write("PATCH", f"/crm/v3/objects/tickets/{ticket_id}", {"properties": props})


def mark_risk(ticket_id: str, note: str) -> None:
    """Retention risk = priority High + retention_risk true. No stage change, no
    subject rewrite: the board sorts on the flag."""
    set_props(ticket_id, {"hs_ticket_priority": "HIGH", "retention_risk": "true"})
    if ticket_id and ticket_id != "DRYRUN":
        try:
            hs.add_ticket_note(ticket_id, note)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  risk note failed (non-fatal): {e}")


def ticket_stage(ticket_id: str) -> str | None:
    if not ticket_id or ticket_id == "DRYRUN":
        return None
    try:
        return ((hs.get_ticket(ticket_id) or {}).get("properties") or {}).get("hs_pipeline_stage")
    except Exception:  # noqa: BLE001
        return None


def ticket_is_open(ticket_id: str) -> bool:
    st = ticket_stage(ticket_id)
    return True if st is None else not is_closed_stage(st)


# ── queries (sweeps and digests) ────────────────────────────────────────────

def open_tickets(name: str, extra_filters: list | None = None, props: list | None = None) -> list[dict]:
    closed = closed_stage_ids(name)
    filters = [{"propertyName": "hs_pipeline", "operator": "EQ", "value": str(pipeline(name)["id"])}]
    if closed:
        filters.append({"propertyName": "hs_pipeline_stage", "operator": "NOT_IN", "values": sorted(closed)})
    filters += extra_filters or []
    return hs._search_all("/crm/v3/objects/tickets/search", filters, props or TICKET_PROPS)


def tickets_closed_since(name: str, since_ms: int) -> list[dict]:
    closed = closed_stage_ids(name)
    if not closed:
        return []
    filters = [{"propertyName": "hs_pipeline", "operator": "EQ", "value": str(pipeline(name)["id"])},
               {"propertyName": "hs_pipeline_stage", "operator": "IN", "values": sorted(closed)},
               {"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": str(since_ms)}]
    return hs._search_all("/crm/v3/objects/tickets/search", filters, TICKET_PROPS)


def open_tutor_tickets_for_contacts(contact_ids: list) -> list[dict]:
    """Open Tutor Accountability tickets associated to any of the contacts
    (the family's), for the Renewals link + flag."""
    out = []
    for cid in [c for c in contact_ids or [] if c and c != "DRYRUN"]:
        try:
            assoc = hs._get(f"/crm/v4/objects/contacts/{cid}/associations/tickets", {"limit": 50})
        except Exception:  # noqa: BLE001
            continue
        for r in assoc.get("results") or []:
            tid = str(r.get("toObjectId"))
            try:
                t = hs._get(f"/crm/v3/objects/tickets/{tid}", {"properties": "hs_pipeline,hs_pipeline_stage,subject"})
            except Exception:  # noqa: BLE001
                continue
            p = t.get("properties") or {}
            if str(p.get("hs_pipeline")) == str(pipeline("tutor")["id"]) and not is_closed_stage(p.get("hs_pipeline_stage")):
                out.append(t)
    return out


def link_open_tutor_ticket(ticket_id: str, contact_ids: list) -> str | None:
    """A Renewals case whose family has an open Tutor ticket carries its id;
    the scheduler escalates to operations, ownership does not change."""
    hits = open_tutor_tickets_for_contacts(contact_ids)
    if not hits:
        return None
    tid = str(hits[0]["id"])
    set_props(ticket_id, {"linked_tutor_ticket_id": tid})
    if ticket_id and ticket_id != "DRYRUN":
        try:
            hs.add_ticket_note(ticket_id, f"🧑‍🏫 Open tutor ticket on this family: {hs.ticket_url(tid)}. "
                                          f"Escalate to operations if it bears on the renewal; the case stays yours.")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  tutor link note failed (non-fatal): {e}")
    return tid


def dm_role(role: str, text: str) -> None:
    who = seat(role)
    if who.get("slack_user_id"):
        try:
            slack_client.dm(who["slack_user_id"], text)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  DM to {role} failed (non-fatal): {e}")


# ── small helpers ───────────────────────────────────────────────────────────

def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def _today() -> str:
    return now_la().date().isoformat()


def age_days(createdate: str | None) -> int:
    if not createdate:
        return 0
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(str(createdate).replace("Z", "+00:00"))).days
    except ValueError:
        return 0


def business_days_between(a: datetime, b: datetime) -> int:
    from .business_hours import _is_business_day
    n, d = 0, a.date()
    while d < b.date():
        d += timedelta(days=1)
        if _is_business_day(d):
            n += 1
    return n

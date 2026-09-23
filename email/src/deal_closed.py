"""When a deal stops, its future work stops with it.

Why this exists. On 2026-09-15 Annie Wolfstein asked us to book Bradley for
Wednesday evenings, Paola called her back, and the family cancelled the same
afternoon: Bradley had found a tutor at his school. Someone moved the deal to
Stopped and wrote nothing down. Three days later the record still held two
scheduling tasks telling a scheduler to find a tutor and text the father, three
older follow-up tasks, and an unanswered "confirm this schedule still works"
text sitting on the father's contact. Anyone who picked those up would have
texted a family that had already said no, and the only place the cancellation
existed was in one person's memory.

So the failure class is not "someone forgot to close tasks". It is that a
decision to stop was made in conversation and never written where a system
could read it. This sweep makes that impossible to leave undone:

  1. A deal that lands in a stop stage gets its FUTURE work closed. Future
     means due on or after the day the deal stopped. Work that predates the
     decision is reported, never closed: it may have been overtaken by events,
     but it may also be the reason someone still owes this family a call, and
     an agent guessing at that is how real follow-ups disappear.
  2. A stop with no reason recorded gets one asked for. The agent writes the
     note saying the reason is missing and DMs the deal owner once. It does not
     invent a reason.
  3. Anything we asked the family that they never answered is named in the
     digest, so nobody chases a reply that no longer matters.

Deliberately NOT done here: moving deals, editing stage, or closing anything on
a deal that is merely quiet. This sweep acts only on deals a human already
decided to stop.

Stop stages are matched BY LABEL (enumeration rule: agents read labels, never
internal values), so a portal rename cannot silently turn this sweep off.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import audit, hubspot_client as hs, slack_client
from .business_hours import now_la
from .config import DRY_RUN, cfg

_TASK_PROPS = ["hs_task_subject", "hs_task_status", "hs_timestamp",
               "hubspot_owner_id", "hs_task_body"]


def _iso_to_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def stop_stage_ids() -> dict[str, str]:
    """{stage_id: "Pipeline / Stage"} for every stage whose LABEL reads as a stop.

    Labels, not ids, because the ids are portal trivia and a label is what a
    human sees when they drag the card. `Stopped` in the In-Person pipeline had
    an isClosed gap Roman was fixing in-portal, so this does not rely on
    isClosed either.
    """
    pats = [p.lower() for p in (cfg().get("deal_closed") or {}).get("stop_stage_labels") or []]
    out = {}
    for pid, stages in hs._deal_pipelines().items():
        for sid, label in stages.items():
            if any(p in (label or "").lower() for p in pats):
                out[sid] = f"{hs.pipeline_label(pid)} / {label}"
    return out


def recently_stopped(stage_ids: list[str], since_ms: int) -> list[dict]:
    """Deals sitting in a stop stage whose record moved inside the window."""
    if not stage_ids:
        return []
    return hs._search_all("/crm/v3/objects/deals/search", [
        {"propertyName": "dealstage", "operator": "IN", "values": stage_ids},
        {"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": str(since_ms)},
    ], ["dealname", "dealstage", "pipeline", "hubspot_owner_id",
        "closed_lost_reason", "hs_lastmodifieddate", "closedate"])


def _deal_contact_ids(deal_id: str) -> list[str]:
    try:
        assoc = hs._get(f"/crm/v3/objects/deals/{deal_id}/associations/contacts")
    except Exception:  # noqa: BLE001
        return []
    return [str(r.get("toObjectId") or r.get("id")) for r in assoc.get("results", [])][:10]


def _open_tasks_for_contact(contact_id: str) -> list[dict]:
    try:
        assoc = hs._get(f"/crm/v3/objects/contacts/{contact_id}/associations/tasks")
    except Exception:  # noqa: BLE001
        return []
    ids = [str(r.get("toObjectId") or r.get("id")) for r in assoc.get("results", [])][-60:]
    if not ids:
        return []
    try:
        res = hs._write("POST", "/crm/v3/objects/tasks/batch/read",
                        {"inputs": [{"id": i} for i in ids], "properties": _TASK_PROPS})
    except Exception:  # noqa: BLE001
        return []
    out = []
    for t in (res.get("results") or []) if isinstance(res, dict) else []:
        if (t.get("properties") or {}).get("hs_task_status") in ("COMPLETED", "DEFERRED"):
            continue
        out.append(t)
    return out


def split_by_stop_date(tasks: list[dict], stopped_at: datetime | None):
    """(future, prior) — tasks due on/after the stop, and tasks that predate it.

    Only `future` is ever closed. A task due before the decision was made is
    somebody's unfinished conversation, not a leftover of this deal, and the
    Lia Beck rule says do not let an agent decide that on a guess.
    """
    future, prior = [], []
    for t in tasks:
        due = _iso_to_dt((t.get("properties") or {}).get("hs_timestamp"))
        if stopped_at and due and due.date() >= stopped_at.date():
            future.append(t)
        else:
            prior.append(t)
    return future, prior


def has_reason(deal: dict, contact_ids: list[str], stopped_at: datetime | None) -> bool:
    """Is there anything on the record saying WHY this stopped?

    Either the closed-lost reason property, or a note written on the deal or one
    of its contacts on/after the stop date. A call summary counts: it is the
    commonest place a real reason lands.
    """
    p = deal.get("properties") or {}
    if (p.get("closed_lost_reason") or "").strip():
        return True
    for obj_id, path in ([(deal["id"], "deals")] +
                         [(c, "contacts") for c in contact_ids]):
        try:
            assoc = hs._get(f"/crm/v3/objects/{path}/{obj_id}/associations/notes")
        except Exception:  # noqa: BLE001
            continue
        ids = [str(r.get("toObjectId") or r.get("id")) for r in assoc.get("results", [])][-25:]
        if not ids:
            continue
        try:
            res = hs._write("POST", "/crm/v3/objects/notes/batch/read",
                            {"inputs": [{"id": i} for i in ids],
                             "properties": ["hs_timestamp", "hs_note_body"]})
        except Exception:  # noqa: BLE001
            continue
        for n in (res.get("results") or []) if isinstance(res, dict) else []:
            np = n.get("properties") or {}
            when = _iso_to_dt(np.get("hs_timestamp"))
            body = (np.get("hs_note_body") or "")
            if not when or not stopped_at or when.date() < stopped_at.date():
                continue
            if "[Agent] no closing reason" in body:
                continue        # our own nag is not a reason
            if len(body.strip()) >= 25:
                return True
    return False


def _owner_key(owner_id: str) -> str:
    for key, s in (cfg().get("staff") or {}).items():
        if str(s.get("hubspot_owner_id") or "") == str(owner_id or ""):
            return key
    return ""


def run() -> None:
    conf = cfg().get("deal_closed") or {}
    if not conf.get("enabled"):
        print("=== deal_closed: disabled in config ===")
        return
    print(f"=== deal-stopped sweep ({now_la().isoformat()}) "
          f"{'DRY RUN ' if DRY_RUN else ''}===")

    stages = stop_stage_ids()
    if not stages:
        print("  no stage label matched stop_stage_labels — refusing to act")
        return
    print(f"  stop stages: {', '.join(sorted(stages.values()))}")

    since = datetime.now(timezone.utc) - timedelta(days=float(conf.get("lookback_days", 7)))
    deals = recently_stopped(list(stages), int(since.timestamp() * 1000))
    cap = int(conf.get("max_deals_per_run", 25))
    if len(deals) > cap:
        print(f"  {len(deals)} stopped deals exceeds max_deals_per_run={cap} — "
              f"handling the {cap} most recent, the rest wait for the next run")
        deals = sorted(deals, key=lambda d: d["properties"].get("hs_lastmodifieddate") or "",
                       reverse=True)[:cap]

    handled = audit.deals_closed_swept()
    lines, closed_total, asked_total = [], 0, 0

    for deal in deals:
        did = str(deal["id"])
        if did in handled:
            continue
        p = deal.get("properties") or {}
        stopped_at = _iso_to_dt(p.get("closedate")) or _iso_to_dt(p.get("hs_lastmodifieddate"))
        contact_ids = _deal_contact_ids(did)

        tasks: list[dict] = []
        seen = set()
        for cid in contact_ids:
            for t in _open_tasks_for_contact(cid):
                if t["id"] not in seen:
                    seen.add(t["id"])
                    tasks.append(t)
        future, prior = split_by_stop_date(tasks, stopped_at)

        if future and not DRY_RUN:
            hs.batch_complete_tasks([str(t["id"]) for t in future])
        closed_total += len(future)

        reason = has_reason(deal, contact_ids, stopped_at)
        if not reason:
            asked_total += 1
            body = ("[Agent] no closing reason recorded — written by "
                    "email/src/deal_closed.py\n\n"
                    f"This deal was moved to {stages.get(p.get('dealstage'), 'a stop stage')} "
                    f"on {stopped_at.date() if stopped_at else 'an unknown date'} and nothing on "
                    "the record says why. Please add a note with what the family said. "
                    "The reason is what stops the next person restarting work the family "
                    "already declined.")
            if not DRY_RUN:
                try:
                    hs._write("POST", "/crm/v3/objects/notes", {
                        "properties": {"hs_timestamp": datetime.now(timezone.utc)
                                       .strftime("%Y-%m-%dT%H:%M:%SZ"),
                                       "hs_note_body": body},
                        "associations": [{"to": {"id": did}, "types": [
                            {"associationCategory": "HUBSPOT_DEFINED",
                             "associationTypeId": 214}]}]})
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️  could not write the reason note on deal {did}: {e}")
            okey = _owner_key(p.get("hubspot_owner_id"))
            sid = (cfg().get("staff") or {}).get(okey, {}).get("slack_user_id")
            if sid and not DRY_RUN:
                slack_client.dm(sid, (
                    f"📕 *{p.get('dealname')}* was stopped with no reason on the record. "
                    f"What did the family say? One line on the deal is enough, and it is "
                    f"what keeps the next person from restarting work they declined."))

        lines.append(f"• *{p.get('dealname')}* — {stages.get(p.get('dealstage'), '')} — "
                     f"closed {len(future)} future task(s)"
                     f"{f', {len(prior)} older task(s) left for a human' if prior else ''}"
                     f"{'' if reason else ', NO REASON recorded'}")
        if not DRY_RUN:
            audit.append({"deal_id": did, "action_taken": "deal_closed_swept",
                          "dealname": p.get("dealname"),
                          "tasks_closed": [str(t["id"]) for t in future],
                          "tasks_left": [str(t["id"]) for t in prior],
                          "reason_on_record": reason})

    print(f"=== {len(lines)} stopped deal(s), {closed_total} task(s) closed, "
          f"{asked_total} missing a reason ===")
    for line in lines:
        print(f"  {line}")

    chan = conf.get("digest_channel")
    if chan and lines and not DRY_RUN:
        slack_client.post_message(chan, "🧹 *Deals stopped, work stopped with them*\n" + "\n".join(lines))


if __name__ == "__main__":
    run()

"""HubSpot → Teachworks deal sync (replaces the Zapier zap).

Every NEW HubSpot deal (any creator): find the associated contact, pick the
Teachworks account by pipeline, then UPSERT the family — matched by EMAIL (the
identifier) — and create the student(s) if missing. Charter students get
billing_method=Package; private pay gets Service List Cost. HubSpot contact info
wins on updates, so contact drift can never spawn duplicate families again.

Guards (no Teachworks write, flagged instead): internal @wetutorathome.com
contacts, and charter deals whose contact doesn't match the deal-name parent
(usually the school's education specialist — creating a "family" for school
staff is the one mistake this sync must never make). PO-created deals are exempt
from the charter guard: po_inbox associates the parent deliberately.

Own cursor (state/sync_cursor.json); idempotent via audit (deal:{id}).
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import audit, hubspot_client as hs, slack_client, teachworks_client as tw
from .config import DRY_RUN, cfg

CUR_PATH = Path(__file__).resolve().parent.parent / "state" / "sync_cursor.json"

CONTACT_PROPS = ["email", "firstname", "lastname", "phone", "mobilephone",
                 "address", "city", "state", "zip"]


def _deal_contact(deal_id: str, dealname: str = "") -> dict | None:
    """The deal's FAMILY contact. Deals can carry several contacts (parent + TOR);
    prefer the one whose name matches the deal-name parent, else the first."""
    try:
        assoc = hs._get(f"/crm/v3/objects/deals/{deal_id}/associations/contacts")
    except Exception:  # noqa: BLE001
        return None
    ids = [r.get("toObjectId") or r.get("id") for r in assoc.get("results", [])]
    if not ids:
        return None
    first = None
    for cid in ids[:5]:
        try:
            c = hs._get(f"/crm/v3/objects/contacts/{cid}", {"properties": ",".join(CONTACT_PROPS)})
        except Exception:  # noqa: BLE001
            continue
        first = first or c
        if dealname and _contact_matches_dealname(c.get("properties") or {}, dealname):
            return c
    return first


def _tw_fields(props: dict) -> dict:
    """HubSpot contact properties → Teachworks family fields (email = identity)."""
    out = {
        "first_name": props.get("firstname") or "",
        "last_name": props.get("lastname") or "",
        "email": (props.get("email") or "").lower(),
        "mobile_phone": props.get("mobilephone") or props.get("phone") or "",
        "address": props.get("address") or "",
        "city": props.get("city") or "",
        "state": props.get("state") or "",
        "zip": props.get("zip") or "",
    }
    return {k: v for k, v in out.items() if v}


# Split only on a dash with a space on at least one side, so hyphenated names
# ("Anna-Marie", "Smith-Jones") survive but "Marcano- Kash" still splits.
_DASH_SPLIT = re.compile(r"\s+-\s*|\s*-\s+")


def _dealname_parts(dealname: str) -> list[str]:
    parts = [p.strip() for p in _DASH_SPLIT.split(dealname or "") if p.strip()]
    # "Renewal - Parent - Student": the prefix shifts every field — drop it.
    if parts and parts[0].lower() in ("renewal", "renewals"):
        parts = parts[1:]
    return parts


def _student_firsts_from_dealname(dealname: str) -> list[str]:
    """Team convention: 'Parent Name - Student' / 'School - First Last - PO 123' /
    'Renewal - Parent - Student'. The student segment may name siblings
    ('Kash and Kingston') — one first name per student, order kept."""
    parts = _dealname_parts(dealname)
    if len(parts) < 2 or parts[1].lower().startswith("po"):
        return []
    out: list[str] = []
    for chunk in re.split(r"\s+and\s+|\s*&\s*|\s*,\s*", parts[1]):
        first = chunk.strip().split()[0] if chunk.strip() else ""
        if first and first.lower() not in (o.lower() for o in out):
            out.append(first)
    return out


def _contact_matches_dealname(props: dict, dealname: str) -> bool:
    """Charter deals are named 'Parent - Student - School'; the associated HubSpot
    contact must BE the parent. School staff (education specialists) share none of
    those name tokens, so require both contact names to appear in the deal name."""
    dn = (dealname or "").lower()
    first = (props.get("firstname") or "").strip().lower()
    last = (props.get("lastname") or "").strip().lower()
    return bool(first and last and first in dn and last in dn)


def sync_deal(deal: dict, force: bool = False, contact_override: dict | None = None,
              students_override: list[str] | None = None) -> dict | None:
    """`force=True` (FORCE_DEAL_ID runs) does the REAL write for one deal even in
    pilot mode, and re-runs a deal the audit already marked (writes are upserts, so
    replaying is safe). The charter/internal guards still apply."""
    ds = cfg()["deal_sync"]
    pid = deal["properties"].get("pipeline")
    if pid in set(ds.get("exclude_pipelines", [])):
        return None
    key = f"deal:{deal['id']}"
    if not force and audit.already_processed(key):
        return None
    # Pilot runs re-fetch the same window every 15 min (cursor frozen); one log line
    # per deal is enough.
    if not force and ds.get("dry_run_first") and audit.already_processed(f"pilot-{key}"):
        return None

    # ALL charter families default to Package billing: a pipeline is charter when
    # listed in charter_pipelines OR when its NAME says Charter — so a new charter
    # pipeline can never silently fall back to private-pay billing.
    is_charter = (pid in set(ds.get("charter_pipelines", []))
                  or "charter" in hs.pipeline_label(pid).lower())
    # Per-pipeline Teachworks overrides (account, billing, extra fields) — the
    # different online pipelines need different TW settings, all editable in config.
    ps = (ds.get("pipeline_settings") or {}).get(pid) or {}
    acct = ps.get("account") or (
        "in_person" if pid in set(ds.get("in_person_pipelines", [])) else "online")
    token = tw.accounts().get(acct)
    if not token:
        print(f"  ⚠️  no token for TW account '{acct}'; skipping deal {deal['id']}")
        return None

    contact = contact_override or _deal_contact(deal["id"], deal["properties"].get("dealname", ""))
    props = (contact or {}).get("properties") or {}
    email = (props.get("email") or "").lower()
    record = {"message_id": key, "source": "deal_sync", "deal_id": deal["id"],
              "deal_name": deal["properties"].get("dealname"), "tw_account": acct,
              "charter": is_charter, "owner": None}
    if not email:
        record.update({"action_taken": "sync_skipped", "reason": "no contact email on deal"})
        audit.append(record)
        return record

    dealname = deal["properties"].get("dealname", "")
    fields = _tw_fields(props)
    # Pipeline-specific customer settings ride along on create AND update, so an
    # existing family gets its settings adjusted too.
    fields.update(ps.get("customer_fields") or {})
    students = students_override or _student_firsts_from_dealname(dealname)

    # Guards: never turn a non-family contact into a Teachworks family.
    internal_domain = cfg().get("internal", {}).get("domain", "wetutorathome.com")
    po_num = (deal["properties"].get("po_number") or "").strip()
    review = None  # (action, reason)
    if email.endswith(f"@{internal_domain}"):
        review = ("sync_skipped", f"internal contact (@{internal_domain}) — not a family")
    elif (is_charter and not po_num and not contact_override
          and not _contact_matches_dealname(props, dealname)):
        # Charter deals not born from a PO often carry the school ES as the contact;
        # PO-created deals get the parent associated deliberately (po_inbox), so the
        # po_number property exempts them.
        review = ("sync_needs_review",
                  f"contact '{props.get('firstname', '')} {props.get('lastname', '')}' "
                  f"({email}) doesn't match the deal name — likely school staff, not the parent")

    # Pilot gate: log the intended write, touch nothing, and don't mark processed —
    # so flipping dry_run_first=false replays these deals for real.
    if ds.get("dry_run_first") and not force:
        if review:
            intended = f"NEEDS REVIEW ({review[1]})"
        else:
            existing = tw.find_customer_by_email(email, token)
            intended = f"UPDATE customer {existing['id']}" if existing else "CREATE family"
        pilot_billing = ps.get("student_billing") or (
            ds["charter_student_billing"] if is_charter else ds["private_student_billing"])
        print(f"  [PILOT] {record['deal_name']} → TW[{acct}] {intended} {fields} "
              f"+ students {students or '(none)'} ({pilot_billing})"
              + (f" [pipeline_settings: {ps}]" if ps else ""))
        record.update({"message_id": f"pilot-{key}", "action_taken": "sync_pilot_logged",
                       "review": review[1] if review else None})
        audit.append(record)
        return record

    if review:
        action, why = review
        record.update({"action_taken": action, "reason": why})
        audit.append(record)
        if action == "sync_needs_review":
            slack_client.post_message(
                cfg()["slack"]["digest_channel"],
                f"🔎 Deal sync needs review: *{dealname}* — {why}. No Teachworks write was "
                f"made. Fix: create/verify the family in Teachworks manually (or associate "
                f"the parent contact and ask Roman to replay the deal).")
        print(f"  ⏭️  {record['deal_name']} → {action}: {why}")
        return record

    existing = tw.find_customer_by_email(email, token)
    if existing:
        tw.update_customer(existing["id"], fields, token)
        record["tw_customer_id"] = existing["id"]
        record["tw_action"] = "updated"
    else:
        created = tw.create_family(fields, token)
        record["tw_customer_id"] = created.get("id")
        record["tw_action"] = "created"

    # Students: from the deal name (may be siblings); skip any already under the family.
    if students and record.get("tw_customer_id") not in (None, "DRYRUN"):
        studs = tw.tw_get("students", {"customer_id": record["tw_customer_id"]}, token=token)
        have = {(s.get("first_name") or "").strip().lower() for s in studs}
        billing = ps.get("student_billing") or (
            ds["charter_student_billing"] if is_charter else ds["private_student_billing"])
        made = []
        for sf in students:
            if sf.lower() in have:
                continue
            tw.create_student({"customer_id": record["tw_customer_id"],
                               "first_name": sf,
                               "last_name": fields.get("last_name", ""),
                               "billing_method": billing,
                               **(ps.get("student_fields") or {})}, token)
            made.append(sf)
        if made:
            record["tw_student_created"] = ", ".join(made)
    record["action_taken"] = "tw_synced"
    audit.append(record)
    print(f"  🔄 {record['deal_name']} → TW[{acct}] {record['tw_action']}"
          + (f" + student {record.get('tw_student_created')}" if record.get("tw_student_created") else ""))
    return record


def run() -> None:
    ds = cfg().get("deal_sync", {})
    if not ds.get("enabled"):
        print("deal_sync disabled")
        return
    force_id = (os.environ.get("FORCE_DEAL_ID") or "").strip()
    if force_id:
        # One-deal REAL sync (test / selective go-live). Cursor untouched.
        d = hs._get(f"/crm/v3/objects/deals/{force_id}",
                    {"properties": "dealname,pipeline,dealstage,createdate,po_number"})
        # Optional trace-by-contact-email: fetch the contact, fix the missing
        # association on the HubSpot deal, and sync with that contact.
        contact = None
        force_email = (os.environ.get("FORCE_CONTACT_EMAIL") or "").strip().lower()
        if force_email:
            contact = hs.find_contact_by_email(force_email, properties=CONTACT_PROPS)
            if not contact:
                print(f"deal_sync FORCE: no HubSpot contact with email {force_email} — create it first")
                return
            try:
                hs.associate_contact_to_deal(force_id, contact["id"])
                print(f"  🔗 associated contact {contact['id']} ({force_email}) to deal {force_id}")
            except Exception as e:  # noqa: BLE001 — sync proceeds on the override either way
                print(f"  ⚠️  HubSpot association failed (syncing with override anyway): {e}")
        force_student = (os.environ.get("FORCE_STUDENT_FIRST") or "").strip()
        rec = sync_deal(d, force=True, contact_override=contact,
                        students_override=[force_student] if force_student else None) or {}
        print(f"deal_sync FORCE {force_id}: {rec.get('action_taken', 'skipped (excluded pipeline?)')}"
              + (f" — {rec['reason']}" if rec.get("reason") else ""))
        if rec.get("action_taken") == "sync_skipped" and "no contact email" in (rec.get("reason") or ""):
            print("  ↳ associate the parent/family contact on the deal in HubSpot, then re-run.")
        return
    state = json.loads(CUR_PATH.read_text()) if CUR_PATH.exists() else {}
    since_ms = state.get("last_createdate_ms")
    if not since_ms:
        since_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if not DRY_RUN:
            CUR_PATH.write_text(json.dumps({"last_createdate_ms": since_ms}))
        print(f"deal_sync: baseline set ({since_ms}); new deals picked up next run")
        return
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "createdate", "operator": "GT", "value": str(since_ms)}]}],
        "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}],
        "properties": ["dealname", "pipeline", "dealstage", "createdate", "po_number"],
        "limit": 50}
    deals: list = []
    while len(deals) < 200:  # paginate — a stuck 50-deal window must not hide new deals
        res = hs._write("POST", "/crm/v3/objects/deals/search", body)
        if not isinstance(res, dict):
            break
        deals.extend(res.get("results", []))
        after = ((res.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
        body["after"] = after
    print(f"deal_sync: {len(deals)} new deal(s)")
    newest = since_ms
    synced = 0
    for d in deals:
        try:
            if sync_deal(d):
                synced += 1
            cd = d["properties"].get("createdate")
            if cd:
                ms = int(datetime.fromisoformat(cd.replace("Z", "+00:00")).timestamp() * 1000)
                newest = max(newest, ms)
        except Exception as e:  # noqa: BLE001 — one bad deal never kills the run
            print(f"  ⚠️  sync error on deal {d.get('id')}: {e}", file=sys.stderr)
            traceback.print_exc()
            audit.append({"message_id": f"deal:{d.get('id')}", "source": "deal_sync",
                          "action_taken": "error", "error": str(e)[:200]})
    # In pilot mode the cursor stays put, so the same deals replay for real once
    # dry_run_first is flipped off.
    if not DRY_RUN and not ds.get("dry_run_first"):
        CUR_PATH.write_text(json.dumps({"last_createdate_ms": newest}))
    print(f"deal_sync: {synced} processed (pilot={bool(ds.get('dry_run_first'))})")
    try:
        from . import invoice_sweep
        invoice_sweep.run_sweep()
    except Exception as e:  # noqa: BLE001 — the sweep must never fail the sync
        import traceback as _tb
        print(f"⚠️  invoice_sweep error: {e}")
        _tb.print_exc()


if __name__ == "__main__":
    run()

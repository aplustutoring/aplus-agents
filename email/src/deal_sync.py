"""HubSpot → Teachworks deal sync (replaces the Zapier zap).

Every NEW HubSpot deal (any creator): find the associated contact, pick the
Teachworks account by pipeline, then UPSERT the family — matched by EMAIL (the
identifier) — and create the student if missing. Charter students get
billing_method=Package; private pay gets Service List Cost. HubSpot contact info
wins on updates, so contact drift can never spawn duplicate families again.

Own cursor (state/sync_cursor.json); idempotent via audit (deal:{id}).
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import audit, hubspot_client as hs, slack_client, teachworks_client as tw
from .config import DRY_RUN, cfg

CUR_PATH = Path(__file__).resolve().parent.parent / "state" / "sync_cursor.json"

CONTACT_PROPS = ["email", "firstname", "lastname", "phone", "mobilephone",
                 "address", "city", "state", "zip"]


def _deal_contact(deal_id: str) -> dict | None:
    try:
        assoc = hs._get(f"/crm/v3/objects/deals/{deal_id}/associations/contacts")
    except Exception:  # noqa: BLE001
        return None
    ids = [r.get("toObjectId") or r.get("id") for r in assoc.get("results", [])]
    if not ids:
        return None
    return hs._get(f"/crm/v3/objects/contacts/{ids[0]}", {"properties": ",".join(CONTACT_PROPS)})


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


def _student_first_from_dealname(dealname: str) -> str:
    """Team convention: 'Parent Name - Student' / 'School - First Last - PO 123'."""
    parts = [p.strip() for p in (dealname or "").split(" - ")]
    if len(parts) >= 2 and not parts[1].lower().startswith("po"):
        return parts[1].split()[0] if parts[1] else ""
    return ""


def sync_deal(deal: dict) -> dict | None:
    ds = cfg()["deal_sync"]
    pid = deal["properties"].get("pipeline")
    if pid in set(ds.get("exclude_pipelines", [])):
        return None
    key = f"deal:{deal['id']}"
    if audit.already_processed(key):
        return None

    is_charter = pid in set(ds.get("charter_pipelines", []))
    acct = "in_person" if pid in set(ds.get("in_person_pipelines", [])) else "online"
    token = tw.accounts().get(acct)
    if not token:
        print(f"  ⚠️  no token for TW account '{acct}'; skipping deal {deal['id']}")
        return None

    contact = _deal_contact(deal["id"])
    props = (contact or {}).get("properties") or {}
    email = (props.get("email") or "").lower()
    record = {"message_id": key, "source": "deal_sync", "deal_id": deal["id"],
              "deal_name": deal["properties"].get("dealname"), "tw_account": acct,
              "charter": is_charter, "owner": None}
    if not email:
        record.update({"action_taken": "sync_skipped", "reason": "no contact email on deal"})
        audit.append(record)
        return record

    fields = _tw_fields(props)
    existing = tw.find_customer_by_email(email, token)

    # Pilot gate: log the intended write, touch nothing, and don't mark processed —
    # so flipping dry_run_first=false replays these deals for real.
    if ds.get("dry_run_first"):
        intended = ("UPDATE customer %s" % existing["id"]) if existing else "CREATE family"
        student_first = _student_first_from_dealname(deal["properties"].get("dealname", ""))
        print(f"  [PILOT] {record['deal_name']} → TW[{acct}] {intended} {fields} "
              f"+ student {student_first or '(none)'} ({'Package' if is_charter else 'Service List Cost'})")
        record.update({"message_id": f"pilot-{key}", "action_taken": "sync_pilot_logged"})
        audit.append(record)
        return record

    if existing:
        tw.update_customer(existing["id"], fields, token)
        record["tw_customer_id"] = existing["id"]
        record["tw_action"] = "updated"
    else:
        created = tw.create_family(fields, token)
        record["tw_customer_id"] = created.get("id")
        record["tw_action"] = "created"

    # Student: from the deal name; skip if already under the family.
    student_first = _student_first_from_dealname(deal["properties"].get("dealname", ""))
    if student_first and record.get("tw_customer_id") not in (None, "DRYRUN"):
        studs = tw.tw_get("students", {"customer_id": record["tw_customer_id"]}, token=token)
        if not any((s.get("first_name") or "").strip().lower() == student_first.lower() for s in studs):
            billing = ds["charter_student_billing"] if is_charter else ds["private_student_billing"]
            tw.create_student({"customer_id": record["tw_customer_id"],
                               "first_name": student_first,
                               "last_name": fields.get("last_name", ""),
                               "billing_method": billing}, token)
            record["tw_student_created"] = student_first
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
    state = json.loads(CUR_PATH.read_text()) if CUR_PATH.exists() else {}
    since_ms = state.get("last_createdate_ms")
    if not since_ms:
        since_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if not DRY_RUN:
            CUR_PATH.write_text(json.dumps({"last_createdate_ms": since_ms}))
        print(f"deal_sync: baseline set ({since_ms}); new deals picked up next run")
        return
    res = hs._write("POST", "/crm/v3/objects/deals/search", {
        "filterGroups": [{"filters": [
            {"propertyName": "createdate", "operator": "GT", "value": str(since_ms)}]}],
        "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}],
        "properties": ["dealname", "pipeline", "dealstage", "createdate"], "limit": 50})
    deals = res.get("results", []) if isinstance(res, dict) else []
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


if __name__ == "__main__":
    run()
